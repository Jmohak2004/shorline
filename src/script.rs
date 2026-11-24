//! Transparent script classification, Hash160, and t-address encoding.
//!
//! Zcash defines only two transparent address forms: `t1…` (P2PKH) and
//! `t3…` (P2SH). Every other scriptPubKey form is classified so that its
//! value is still accounted for, which lets the indexer reconcile its
//! reconstructed UTXO set against the node's transparent value pool to
//! the zatoshi.

use k256::elliptic_curve::sec1::ToEncodedPoint;
use ripemd::Ripemd160;
use sha2::{Digest, Sha256};

/// Base58Check version prefix for mainnet P2PKH (`t1…`) addresses.
pub const T1_PREFIX: [u8; 2] = [0x1C, 0xB8];
/// Base58Check version prefix for mainnet P2SH (`t3…`) addresses.
pub const T3_PREFIX: [u8; 2] = [0x1C, 0xBD];

/// The kind of a transparent output script.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
#[repr(u8)]
pub enum Kind {
    /// `OP_DUP OP_HASH160 <20> OP_EQUALVERIFY OP_CHECKSIG` (t1 address)
    P2pkh = 0,
    /// `OP_HASH160 <20> OP_EQUAL` (t3 address)
    P2sh = 1,
    /// `<pubkey> OP_CHECKSIG` — the public key is in the output itself.
    P2pk = 2,
    /// `OP_m <pubkey>… OP_n OP_CHECKMULTISIG` at the top level.
    BareMultisig = 3,
    /// `OP_RETURN …` — provably unspendable.
    NullData = 4,
    /// Anything else.
    Nonstandard = 5,
}

impl Kind {
    pub fn from_u8(v: u8) -> Kind {
        match v {
            0 => Kind::P2pkh,
            1 => Kind::P2sh,
            2 => Kind::P2pk,
            3 => Kind::BareMultisig,
            4 => Kind::NullData,
            _ => Kind::Nonstandard,
        }
    }

    /// Whether this kind has a representable t-address.
    pub fn has_address(self) -> bool {
        matches!(self, Kind::P2pkh | Kind::P2sh)
    }
}

/// The result of classifying a scriptPubKey.
pub struct Classified {
    pub kind: Kind,
    /// Hash160 identifying the output's owner: the pubkey hash for P2PKH,
    /// the script hash for P2SH, and Hash160 of the pubkey / script for the
    /// other kinds (used only to group identical scripts).
    pub hash: [u8; 20],
    /// Public keys that this output places on-chain in the clear
    /// (P2PK and bare multisig only).
    pub revealed_pubkeys: Vec<Vec<u8>>,
}

pub fn hash160(data: &[u8]) -> [u8; 20] {
    let sha = Sha256::digest(data);
    let rip = Ripemd160::digest(sha);
    let mut out = [0u8; 20];
    out.copy_from_slice(&rip);
    out
}

fn is_pubkey_push(script: &[u8], at: usize) -> Option<(usize, &[u8])> {
    let len = *script.get(at)? as usize;
    if len != 33 && len != 65 {
        return None;
    }
    let key = script.get(at + 1..at + 1 + len)?;
    Some((at + 1 + len, key))
}

fn small_int(op: u8) -> Option<usize> {
    // OP_1 .. OP_16
    if (0x51..=0x60).contains(&op) {
        Some((op - 0x50) as usize)
    } else {
        None
    }
}

/// Parses a top-level `m-of-n` multisig script, returning `(m, pubkeys)`.
pub fn parse_multisig(script: &[u8]) -> Option<(usize, Vec<&[u8]>)> {
    if script.len() < 3 || *script.last()? != 0xae {
        return None;
    }
    let m = small_int(script[0])?;
    let n = small_int(script[script.len() - 2])?;
    let mut keys = Vec::with_capacity(n);
    let mut at = 1;
    while at < script.len() - 2 {
        let (next, key) = is_pubkey_push(script, at)?;
        keys.push(key);
        at = next;
    }
    if at != script.len() - 2 || keys.len() != n || m == 0 || m > n {
        return None;
    }
    Some((m, keys))
}

pub fn classify(script: &[u8]) -> Classified {
    // P2PKH
    if script.len() == 25
        && script[0] == 0x76
        && script[1] == 0xa9
        && script[2] == 0x14
        && script[23] == 0x88
        && script[24] == 0xac
    {
        let mut hash = [0u8; 20];
        hash.copy_from_slice(&script[3..23]);
        return Classified {
            kind: Kind::P2pkh,
            hash,
            revealed_pubkeys: vec![],
        };
    }
    // P2SH
    if script.len() == 23 && script[0] == 0xa9 && script[1] == 0x14 && script[22] == 0x87 {
        let mut hash = [0u8; 20];
        hash.copy_from_slice(&script[2..22]);
        return Classified {
            kind: Kind::P2sh,
            hash,
            revealed_pubkeys: vec![],
        };
    }
    // P2PK (compressed or uncompressed)
    if (script.len() == 35 && script[0] == 33 || script.len() == 67 && script[0] == 65)
        && script[script.len() - 1] == 0xac
    {
        let key = &script[1..script.len() - 1];
        return Classified {
            kind: Kind::P2pk,
            hash: hash160(key),
            revealed_pubkeys: vec![key.to_vec()],
        };
    }
    // Bare multisig
    if let Some((_, keys)) = parse_multisig(script) {
        return Classified {
            kind: Kind::BareMultisig,
            hash: hash160(script),
            revealed_pubkeys: keys.into_iter().map(|k| k.to_vec()).collect(),
        };
    }
    // OP_RETURN
    if script.first() == Some(&0x6a) {
        return Classified {
            kind: Kind::NullData,
            hash: [0u8; 20],
            revealed_pubkeys: vec![],
        };
    }
    Classified {
        kind: Kind::Nonstandard,
        hash: hash160(script),
        revealed_pubkeys: vec![],
    }
}

/// Given a public key that has appeared on-chain in the clear, returns the
/// P2PKH pubkey hashes it compromises. A quantum adversary who learns the
/// curve point can derive *both* SEC1 encodings, so both the compressed and
/// uncompressed addresses for that point are exposed.
pub fn exposed_pubkey_hashes(pubkey: &[u8]) -> Vec<[u8; 20]> {
    let mut out = vec![hash160(pubkey)];
    if let Ok(pk) = k256::PublicKey::from_sec1_bytes(pubkey) {
        for compress in [true, false] {
            let enc = pk.to_encoded_point(compress);
            let h = hash160(enc.as_bytes());
            if !out.contains(&h) {
                out.push(h);
            }
        }
    }
    out
}

/// Encodes a mainnet t-address for a P2PKH or P2SH hash.
pub fn encode_taddr(kind: Kind, hash: &[u8; 20]) -> Option<String> {
    let prefix = match kind {
        Kind::P2pkh => T1_PREFIX,
        Kind::P2sh => T3_PREFIX,
        _ => return None,
    };
    let mut payload = Vec::with_capacity(22);
    payload.extend_from_slice(&prefix);
    payload.extend_from_slice(hash);
    Some(bs58::encode(payload).with_check().into_string())
}

/// Decodes a mainnet t-address (t1/t3) into its kind and hash.
pub fn decode_taddr(addr: &str) -> Option<(Kind, [u8; 20])> {
    let raw = bs58::decode(addr).with_check(None).into_vec().ok()?;
    if raw.len() != 22 {
        return None;
    }
    let kind = match [raw[0], raw[1]] {
        T1_PREFIX => Kind::P2pkh,
        T3_PREFIX => Kind::P2sh,
        _ => return None,
    };
    let mut hash = [0u8; 20];
    hash.copy_from_slice(&raw[2..]);
    Some((kind, hash))
}

/// Builds the scriptPubKey for a t-address hash.
pub fn script_for(kind: Kind, hash: &[u8; 20]) -> Vec<u8> {
    match kind {
        Kind::P2pkh => {
            let mut s = vec![0x76, 0xa9, 0x14];
            s.extend_from_slice(hash);
            s.extend_from_slice(&[0x88, 0xac]);
            s
        }
        Kind::P2sh => {
            let mut s = vec![0xa9, 0x14];
            s.extend_from_slice(hash);
            s.push(0x87);
            s
        }
        _ => vec![],
    }
}

/// Classification of a P2SH redeemScript, as discussed in the ZIP 2007 thread.
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum RedeemKind {
    /// `OP_m <keys…> OP_n OP_CHECKMULTISIG`
    Multisig {
        m: usize,
        n: usize,
    },
    /// `OP_m <keys…> OP_n OP_CHECKMULTISIGVERIFY <salt> OP_DROP OP_DEPTH OP_0 OP_EQUAL`:
    /// one key set behind many addresses, distinguished only by a short salt.
    SaltedMultisig {
        m: usize,
        n: usize,
        salt_bytes: usize,
    },
    /// `<key> OP_CHECKSIGVERIFY <salt> OP_DROP OP_DEPTH OP_0 OP_EQUAL`
    SaltedSingleKey {
        salt_bytes: usize,
    },
    /// `<key> OP_CHECKSIGVERIFY OP_DROP… OP_TRUE`: data carried in the scriptSig.
    DataEnvelope,
    P2pkhWrapped,
    P2pkWrapped,
    Other,
}

impl RedeemKind {
    pub fn label(&self) -> String {
        match self {
            RedeemKind::Multisig { m, n } => format!("multisig_{m}_of_{n}"),
            RedeemKind::SaltedMultisig { m, n, .. } => format!("salted_multisig_{m}_of_{n}"),
            RedeemKind::SaltedSingleKey { .. } => "salted_single_key".into(),
            RedeemKind::DataEnvelope => "data_envelope".into(),
            RedeemKind::P2pkhWrapped => "p2pkh_wrapped".into(),
            RedeemKind::P2pkWrapped => "p2pk_wrapped".into(),
            RedeemKind::Other => "other".into(),
        }
    }
}

/// Recognizes a trailing `<salt> OP_DROP OP_DEPTH OP_0 OP_EQUAL` after a
/// VERIFY opcode at `at`; returns (salt offset, salt length).
fn salted_tail(rs: &[u8], at: usize) -> Option<(usize, usize)> {
    let push = *rs.get(at)? as usize;
    if !(1..=8).contains(&push) {
        return None;
    }
    let off = at + 1;
    let tail = rs.get(off + push..)?;
    if tail == [0x75, 0x74, 0x00, 0x87] {
        Some((off, push))
    } else {
        None
    }
}

/// Public keys pushed at the start of a (salted) multisig or single-key script.
pub fn parse_multisig_keys_any(rs: &[u8]) -> Vec<Vec<u8>> {
    let mut at = if rs.first().and_then(|&o| small_int(o)).is_some() {
        1
    } else {
        0
    };
    let mut keys = Vec::new();
    while let Some((next, k)) = is_pubkey_push(rs, at) {
        keys.push(k.to_vec());
        at = next;
    }
    keys
}

/// For salted templates, returns (salt offset, salt length) within the script.
pub fn salt_position(rs: &[u8]) -> Option<(usize, usize)> {
    // multisig form
    if rs.len() > 3 {
        if let Some(m) = small_int(rs[0]) {
            let mut at = 1;
            let mut keys = 0;
            while let Some((next, _)) = is_pubkey_push(rs, at) {
                at = next;
                keys += 1;
            }
            if keys > 0
                && rs.get(at).and_then(|&o| small_int(o)) == Some(keys)
                && rs.get(at + 1) == Some(&0xaf)
                && m <= keys
            {
                return salted_tail(rs, at + 2);
            }
        }
    }
    // single-key form
    if let Some((next, _)) = is_pubkey_push(rs, 0) {
        if rs.get(next) == Some(&0xad) {
            return salted_tail(rs, next + 1);
        }
    }
    None
}

pub fn classify_redeem_script(rs: &[u8]) -> RedeemKind {
    if let Some((m, keys)) = parse_multisig(rs) {
        return RedeemKind::Multisig { m, n: keys.len() };
    }
    if let Some((_, salt_bytes)) = salt_position(rs) {
        if let Some(m) = small_int(rs[0]) {
            let mut at = 1;
            let mut keys = 0;
            while let Some((next, _)) = is_pubkey_push(rs, at) {
                at = next;
                keys += 1;
            }
            return RedeemKind::SaltedMultisig {
                m,
                n: keys,
                salt_bytes,
            };
        }
        return RedeemKind::SaltedSingleKey { salt_bytes };
    }
    // <key> OP_CHECKSIGVERIFY OP_DROP… OP_TRUE
    if let Some((next, _)) = is_pubkey_push(rs, 0) {
        if rs.get(next) == Some(&0xad) {
            let rest = &rs[next + 1..];
            if rest.len() >= 2
                && rest[..rest.len() - 1].iter().all(|&b| b == 0x75)
                && rest[rest.len() - 1] == 0x51
            {
                return RedeemKind::DataEnvelope;
            }
        }
    }
    let c = classify(rs);
    match c.kind {
        Kind::P2pkh => RedeemKind::P2pkhWrapped,
        Kind::P2pk => RedeemKind::P2pkWrapped,
        _ => RedeemKind::Other,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_t1() {
        // Zcash Foundation's well-known donation t-address style check: any
        // decodable t1 must re-encode identically.
        let hash = [7u8; 20];
        let a = encode_taddr(Kind::P2pkh, &hash).unwrap();
        assert!(a.starts_with("t1"));
        assert_eq!(decode_taddr(&a), Some((Kind::P2pkh, hash)));
        let b = encode_taddr(Kind::P2sh, &hash).unwrap();
        assert!(b.starts_with("t3"));
        assert_eq!(decode_taddr(&b), Some((Kind::P2sh, hash)));
    }

    #[test]
    fn classify_forms() {
        let h = [9u8; 20];
        assert_eq!(classify(&script_for(Kind::P2pkh, &h)).kind, Kind::P2pkh);
        assert_eq!(classify(&script_for(Kind::P2sh, &h)).kind, Kind::P2sh);
        assert_eq!(classify(&[0x6a, 0x01, 0x00]).kind, Kind::NullData);
        // 1-of-1 bare multisig with a compressed key
        let mut ms = vec![0x51, 33];
        ms.extend_from_slice(&[2u8; 33]);
        ms.extend_from_slice(&[0x51, 0xae]);
        let c = classify(&ms);
        assert_eq!(c.kind, Kind::BareMultisig);
        assert_eq!(c.revealed_pubkeys.len(), 1);
        assert_eq!(
            classify_redeem_script(&ms),
            RedeemKind::Multisig { m: 1, n: 1 }
        );
    }

    #[test]
    fn salted_templates() {
        // The 2-of-3 salted template observed on mainnet (t3hdTwzc…).
        let rs = hex::decode("52210352d50656796dd79e3e3385c29636d849b8705c9c6d9b86a1717adc38e4a567c72102f39d0b69c3b8e06030ef9dc295cf8c848f51e398fe85414e33509afdc7f01fb321027072ba2319ead2b0b387d69d36508f57b397da8d4ac76ea64676ee8a1356dae053af04ffc378b775740087").unwrap();
        assert_eq!(
            classify_redeem_script(&rs),
            RedeemKind::SaltedMultisig {
                m: 2,
                n: 3,
                salt_bytes: 4
            }
        );
        assert_eq!(salt_position(&rs), Some((106, 4)));
        assert_eq!(&rs[106..110], &[0xff, 0xc3, 0x78, 0xb7]);
        // Its Hash160 is the t3 address it came from.
        let (k, h) = decode_taddr("t3hdTwzcVVGEqDdNKJTBfWvWyaFYNJv7KkA").unwrap();
        assert_eq!(k, Kind::P2sh);
        assert_eq!(hash160(&rs), h);
        // Data envelope: <pk> OP_CHECKSIGVERIFY OP_DROP x4 OP_TRUE
        let mut env = vec![33u8];
        env.extend_from_slice(&[2u8; 33]);
        env.extend_from_slice(&[0xad, 0x75, 0x75, 0x75, 0x75, 0x51]);
        assert_eq!(classify_redeem_script(&env), RedeemKind::DataEnvelope);
        // Salted single key: <pk> OP_CHECKSIGVERIFY OP_0 OP_DROP OP_DEPTH OP_0 OP_EQUAL is NOT salted (empty push);
        // with a 2-byte salt it is.
        let mut ss = vec![33u8];
        ss.extend_from_slice(&[3u8; 33]);
        ss.extend_from_slice(&[0xad, 0x02, 0xab, 0xcd, 0x75, 0x74, 0x00, 0x87]);
        assert_eq!(
            classify_redeem_script(&ss),
            RedeemKind::SaltedSingleKey { salt_bytes: 2 }
        );
    }

    #[test]
    fn hash160_vector() {
        // Hash160 of the empty string.
        assert_eq!(
            hex::encode(hash160(b"")),
            "b472a266d0bd89c13706a4132ccfb16f7c3b9fcb"
        );
    }

    #[test]
    fn both_encodings_exposed() {
        // secp256k1 generator point G, compressed.
        let g = hex::decode("0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798")
            .unwrap();
        let hs = exposed_pubkey_hashes(&g);
        assert_eq!(hs.len(), 2);
        // Hash160 of compressed G (the well-known Bitcoin address 1BgGZ9tcN4rm9KBzDn7KprQz87SZ26SAMH).
        assert_eq!(
            hex::encode(hs[0]),
            "751e76e8199196d454941c45d1b3a323f1433bd6"
        );
        // Hash160 of uncompressed G (1EHNa6Q4Jz2uvNExL497mE43ikXhwF6kZm).
        assert_eq!(
            hex::encode(hs[1]),
            "91b24bf9f5288532960ac687abb035127b1d28a5"
        );
    }
}
