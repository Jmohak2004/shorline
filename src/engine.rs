//! The UTXO engine: replays every transparent input and output of the
//! Zcash chain, in order, and tracks — per address — whether the public key
//! (or redeem script) protecting it has ever been revealed on-chain.
//!
//! The quantum-relevant fact (ZIP 2005, "Threat model"): an adversary able
//! to compute discrete logarithms can forge the ECDSA signatures protecting
//! a transparent output *provided that the public key has been revealed,
//! i.e. if the address has been spent from previously*. Until then, the
//! output is protected only by Hash160, which Shor's algorithm does not
//! break. ZIP 2007 asks how much value sits in each of these states.

use crate::rpc::CompactBlock;
use crate::script::{self, Kind};
use rustc_hash::FxHashMap;

/// Height value meaning "never".
pub const NEVER: u32 = u32::MAX;

/// Transparent value categories, by script kind and exposure state.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(usize)]
pub enum Cat {
    /// t1, public key never revealed on-chain: protected by Hash160 only.
    P2pkhHidden = 0,
    /// t1, public key revealed by an earlier spend (or by a P2PK/multisig output).
    P2pkhExposed = 1,
    /// t3, redeem script never revealed: cannot be classified from public data.
    P2shUnseen = 2,
    /// t3, redeem script (and the keys in it) revealed by an earlier spend.
    P2shSeen = 3,
    /// Public key sits in the output script itself.
    P2pk = 4,
    /// Top-level multisig: public keys sit in the output script.
    BareMultisig = 5,
    /// OP_RETURN outputs carrying value: provably unspendable.
    NullData = 6,
    /// Anything else.
    Nonstandard = 7,
}

pub const N_CATS: usize = 8;

pub const CAT_IDS: [&str; N_CATS] = [
    "p2pkh_hidden",
    "p2pkh_exposed",
    "p2sh_unseen",
    "p2sh_seen",
    "p2pk",
    "bare_multisig",
    "nulldata",
    "nonstandard",
];

/// Why an address's key material became public.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum RevealReason {
    None = 0,
    /// The address was spent from (scriptSig reveals the key / redeem script).
    Spend = 1,
    /// A P2PK or bare-multisig output placed the key on-chain directly.
    PubkeyInOutput = 2,
}

#[derive(Clone, Debug)]
pub struct AddrState {
    pub balance: u64,
    pub received: u64,
    /// Value received while the address's key was already public.
    pub received_after_reveal: u64,
    pub first_seen: u32,
    pub last_seen: u32,
    /// Height at which key material was first revealed, or NEVER.
    pub revealed: u32,
    pub utxos: u32,
    pub spends: u32,
    pub kind: u8,
    pub reveal_reason: u8,
}

impl AddrState {
    pub fn cat(&self) -> Cat {
        cat_of(Kind::from_u8(self.kind), self.revealed != NEVER)
    }
}

pub fn cat_of(kind: Kind, revealed: bool) -> Cat {
    match (kind, revealed) {
        (Kind::P2pkh, false) => Cat::P2pkhHidden,
        (Kind::P2pkh, true) => Cat::P2pkhExposed,
        (Kind::P2sh, false) => Cat::P2shUnseen,
        (Kind::P2sh, true) => Cat::P2shSeen,
        (Kind::P2pk, _) => Cat::P2pk,
        (Kind::BareMultisig, _) => Cat::BareMultisig,
        (Kind::NullData, _) => Cat::NullData,
        (Kind::Nonstandard, _) => Cat::Nonstandard,
    }
}

/// Where a P2SH address was first spent, so its redeem script can be fetched.
#[derive(Clone, Debug)]
pub struct SpendRef {
    pub txid: [u8; 32],
    pub vin_index: u32,
    pub height: u32,
    pub prevout_txid: [u8; 32],
    pub prevout_index: u32,
}

/// A periodic snapshot of category totals.
#[derive(Clone, Debug, serde::Serialize)]
pub struct Sample {
    pub height: u32,
    pub time: u32,
    /// Zatoshis per category, indexed like CAT_IDS.
    pub zat: [u64; N_CATS],
    /// Cumulative zatoshis ever sent to an address whose key was already public.
    pub sent_to_exposed: u64,
}

type OutKey = [u8; 16];
type AddrKey = [u8; 21];

fn outkey(txid: &[u8], index: u32) -> OutKey {
    let mut k = [0u8; 16];
    let n = txid.len().min(12);
    k[..n].copy_from_slice(&txid[..n]);
    k[12..].copy_from_slice(&index.to_le_bytes());
    k
}

fn addrkey(kind: Kind, hash: &[u8; 20]) -> AddrKey {
    let mut k = [0u8; 21];
    k[0] = kind as u8;
    k[1..].copy_from_slice(hash);
    k
}

pub struct Engine {
    utxos: FxHashMap<OutKey, (u32, u64)>,
    index: FxHashMap<AddrKey, u32>,
    pub addrs: Vec<AddrState>,
    pub cat_zat: [u64; N_CATS],
    pub cat_utxos: [u64; N_CATS],
    pub sent_to_exposed: u64,
    pub p2sh_first_spend: FxHashMap<u32, SpendRef>,
    /// Block time by height (for dating reveals and dormancy).
    pub times: Vec<u32>,
    pub height: Option<u32>,
    pub tip_hash: Vec<u8>,
    pub n_blocks: u64,
    pub n_tx: u64,
    pub n_vin: u64,
    pub n_vout: u64,
    pub missing_prevouts: u64,
    pub samples: Vec<Sample>,
    pub sample_every: u32,
}

impl Engine {
    pub fn new(sample_every: u32) -> Self {
        Engine {
            utxos: FxHashMap::default(),
            index: FxHashMap::default(),
            addrs: Vec::new(),
            cat_zat: [0; N_CATS],
            cat_utxos: [0; N_CATS],
            sent_to_exposed: 0,
            p2sh_first_spend: FxHashMap::default(),
            times: Vec::new(),
            height: None,
            tip_hash: Vec::new(),
            n_blocks: 0,
            n_tx: 0,
            n_vin: 0,
            n_vout: 0,
            missing_prevouts: 0,
            samples: Vec::new(),
            sample_every,
        }
    }

    pub fn utxo_count(&self) -> usize {
        self.utxos.len()
    }

    pub fn addr_count(&self) -> usize {
        self.addrs.len()
    }

    pub fn total_zat(&self) -> u64 {
        self.cat_zat.iter().sum()
    }

    /// Iterates over (kind, hash, state) for every address-like entity.
    pub fn iter_addrs(&self) -> impl Iterator<Item = (Kind, [u8; 20], &AddrState)> {
        self.index.iter().map(move |(k, &id)| {
            let mut h = [0u8; 20];
            h.copy_from_slice(&k[1..]);
            (Kind::from_u8(k[0]), h, &self.addrs[id as usize])
        })
    }

    /// Like `iter_addrs`, but also yields the internal entity id.
    pub fn iter_ids(&self) -> impl Iterator<Item = (u32, Kind, [u8; 20], &AddrState)> {
        self.index.iter().map(move |(k, &id)| {
            let mut h = [0u8; 20];
            h.copy_from_slice(&k[1..]);
            (id, Kind::from_u8(k[0]), h, &self.addrs[id as usize])
        })
    }

    pub fn lookup(&self, kind: Kind, hash: &[u8; 20]) -> Option<&AddrState> {
        self.index
            .get(&addrkey(kind, hash))
            .map(|&id| &self.addrs[id as usize])
    }

    fn get_or_insert(&mut self, kind: Kind, hash: &[u8; 20], h: u32) -> u32 {
        let k = addrkey(kind, hash);
        if let Some(&id) = self.index.get(&k) {
            return id;
        }
        let id = self.addrs.len() as u32;
        let always_public = matches!(kind, Kind::P2pk | Kind::BareMultisig);
        self.addrs.push(AddrState {
            balance: 0,
            received: 0,
            received_after_reveal: 0,
            first_seen: h,
            last_seen: h,
            revealed: if always_public { h } else { NEVER },
            utxos: 0,
            spends: 0,
            kind: kind as u8,
            reveal_reason: if always_public {
                RevealReason::PubkeyInOutput as u8
            } else {
                0
            },
        });
        self.index.insert(k, id);
        id
    }

    /// Marks an address's key material as public at height `h`, moving its
    /// current balance from the hidden category to the exposed one.
    fn reveal(&mut self, id: u32, h: u32, reason: RevealReason) {
        let a = &mut self.addrs[id as usize];
        if a.revealed != NEVER {
            return;
        }
        let before = a.cat();
        a.revealed = h;
        a.reveal_reason = reason as u8;
        let after = a.cat();
        if before != after {
            self.cat_zat[before as usize] -= a.balance;
            self.cat_zat[after as usize] += a.balance;
            self.cat_utxos[before as usize] -= a.utxos as u64;
            self.cat_utxos[after as usize] += a.utxos as u64;
        }
    }

    pub fn process_block(&mut self, b: &CompactBlock) -> anyhow::Result<()> {
        let h = b.height as u32;
        if let Some(prev) = self.height {
            anyhow::ensure!(h == prev + 1, "non-contiguous block: got {h} after {prev}");
            if !b.prev_hash.is_empty() && !self.tip_hash.is_empty() {
                anyhow::ensure!(
                    b.prev_hash == self.tip_hash,
                    "chain discontinuity at height {h}: prevHash does not match previous block hash"
                );
            }
        }
        if self.times.len() <= h as usize {
            self.times.resize(h as usize + 1, 0);
        }
        self.times[h as usize] = b.time;

        for tx in &b.vtx {
            self.n_tx += 1;
            // Inputs first: a transaction can spend only outputs created
            // earlier (in this or a previous block).
            for (vin_index, vin) in tx.vin.iter().enumerate() {
                self.n_vin += 1;
                let key = outkey(&vin.prevout_txid, vin.prevout_index);
                let Some((id, value)) = self.utxos.remove(&key) else {
                    self.missing_prevouts += 1;
                    continue;
                };
                let a = &mut self.addrs[id as usize];
                let cat = a.cat() as usize;
                self.cat_zat[cat] -= value;
                self.cat_utxos[cat] -= 1;
                a.balance -= value;
                a.utxos -= 1;
                a.spends += 1;
                a.last_seen = h;
                let kind = Kind::from_u8(a.kind);
                let first_reveal = a.revealed == NEVER && kind.has_address();
                if first_reveal {
                    self.reveal(id, h, RevealReason::Spend);
                    if kind == Kind::P2sh {
                        let mut txid = [0u8; 32];
                        let mut ptxid = [0u8; 32];
                        let n = tx.txid.len().min(32);
                        txid[..n].copy_from_slice(&tx.txid[..n]);
                        let pn = vin.prevout_txid.len().min(32);
                        ptxid[..pn].copy_from_slice(&vin.prevout_txid[..pn]);
                        self.p2sh_first_spend.insert(
                            id,
                            SpendRef {
                                txid,
                                vin_index: vin_index as u32,
                                height: h,
                                prevout_txid: ptxid,
                                prevout_index: vin.prevout_index,
                            },
                        );
                    }
                }
            }
            for (i, out) in tx.vout.iter().enumerate() {
                self.n_vout += 1;
                let c = script::classify(&out.script_pub_key);
                if c.kind == Kind::NullData && out.value == 0 {
                    continue; // unspendable and valueless: nothing to account for
                }
                let id = self.get_or_insert(c.kind, &c.hash, h);
                let a = &mut self.addrs[id as usize];
                if a.revealed != NEVER && Kind::from_u8(a.kind).has_address() {
                    a.received_after_reveal += out.value;
                    self.sent_to_exposed += out.value;
                }
                a.balance += out.value;
                a.received += out.value;
                a.utxos += 1;
                a.last_seen = h;
                let cat = a.cat() as usize;
                self.cat_zat[cat] += out.value;
                self.cat_utxos[cat] += 1;
                if c.kind != Kind::NullData {
                    self.utxos
                        .insert(outkey(&tx.txid, i as u32), (id, out.value));
                }
                for pk in &c.revealed_pubkeys {
                    for ph in script::exposed_pubkey_hashes(pk) {
                        let pid = self.get_or_insert(Kind::P2pkh, &ph, h);
                        self.reveal(pid, h, RevealReason::PubkeyInOutput);
                    }
                }
            }
        }

        self.height = Some(h);
        self.tip_hash = b.hash.clone();
        self.n_blocks += 1;
        if self.sample_every > 0 && h % self.sample_every == 0 {
            self.push_sample();
        }
        Ok(())
    }

    pub fn push_sample(&mut self) {
        let Some(h) = self.height else { return };
        if self.samples.last().map(|s| s.height) == Some(h) {
            return;
        }
        self.samples.push(Sample {
            height: h,
            time: self.times.get(h as usize).copied().unwrap_or(0),
            zat: self.cat_zat,
            sent_to_exposed: self.sent_to_exposed,
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rpc::{CompactTx, CompactTxIn, TxOut};
    use crate::script::script_for;

    fn block(h: u64, txs: Vec<CompactTx>) -> CompactBlock {
        CompactBlock {
            height: h,
            hash: vec![h as u8; 32],
            prev_hash: if h == 0 {
                vec![]
            } else {
                vec![(h - 1) as u8; 32]
            },
            vtx: txs,
            ..Default::default()
        }
    }

    fn tx(id: u8, vin: Vec<(u8, u32)>, vout: Vec<(Vec<u8>, u64)>) -> CompactTx {
        CompactTx {
            txid: vec![id; 32],
            vin: vin
                .into_iter()
                .map(|(t, i)| CompactTxIn {
                    prevout_txid: vec![t; 32],
                    prevout_index: i,
                })
                .collect(),
            vout: vout
                .into_iter()
                .map(|(s, v)| TxOut {
                    script_pub_key: s,
                    value: v,
                })
                .collect(),
            ..Default::default()
        }
    }

    #[test]
    fn spend_reveals_remaining_balance() {
        let alice = [1u8; 20];
        let bob = [2u8; 20];
        let a = script_for(Kind::P2pkh, &alice);
        let b = script_for(Kind::P2pkh, &bob);
        let mut e = Engine::new(0);
        // Block 0: alice receives two outputs (hidden).
        e.process_block(&block(
            0,
            vec![tx(10, vec![], vec![(a.clone(), 100), (a.clone(), 50)])],
        ))
        .unwrap();
        assert_eq!(e.cat_zat[Cat::P2pkhHidden as usize], 150);
        // Block 1: alice spends one output to bob; her remaining 50 is now exposed.
        e.process_block(&block(
            1,
            vec![tx(11, vec![(10, 0)], vec![(b.clone(), 100)])],
        ))
        .unwrap();
        assert_eq!(e.cat_zat[Cat::P2pkhExposed as usize], 50);
        assert_eq!(e.cat_zat[Cat::P2pkhHidden as usize], 100);
        // Block 2: someone sends alice 7 more: lands directly in exposed.
        e.process_block(&block(2, vec![tx(12, vec![], vec![(a.clone(), 7)])]))
            .unwrap();
        assert_eq!(e.cat_zat[Cat::P2pkhExposed as usize], 57);
        assert_eq!(e.sent_to_exposed, 7);
        assert_eq!(e.total_zat(), 157);
        assert_eq!(e.missing_prevouts, 0);
    }

    #[test]
    fn p2pk_output_exposes_matching_t1() {
        let g = hex::decode("0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798")
            .unwrap();
        let ghash = script::hash160(&g);
        let t1 = script_for(Kind::P2pkh, &ghash);
        let mut p2pk = vec![33u8];
        p2pk.extend_from_slice(&g);
        p2pk.push(0xac);
        let mut e = Engine::new(0);
        e.process_block(&block(0, vec![tx(1, vec![], vec![(t1, 40)])]))
            .unwrap();
        assert_eq!(e.cat_zat[Cat::P2pkhHidden as usize], 40);
        e.process_block(&block(1, vec![tx(2, vec![], vec![(p2pk, 5)])]))
            .unwrap();
        assert_eq!(e.cat_zat[Cat::P2pkhHidden as usize], 0);
        assert_eq!(e.cat_zat[Cat::P2pkhExposed as usize], 40);
        assert_eq!(e.cat_zat[Cat::P2pk as usize], 5);
    }

    #[test]
    fn rejects_gaps() {
        let mut e = Engine::new(0);
        e.process_block(&block(0, vec![])).unwrap();
        assert!(e.process_block(&block(2, vec![])).is_err());
    }
}
