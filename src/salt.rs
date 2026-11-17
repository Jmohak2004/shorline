//! Salt sweep: re-identifying "unknown" P2SH addresses that share a revealed
//! key set.
//!
//! Some custodians derive many P2SH addresses from ONE key set by appending a
//! short random salt to the redeem script:
//!
//! ```text
//! OP_m <k1> … <kn> OP_n OP_CHECKMULTISIGVERIFY <salt> OP_DROP OP_DEPTH OP_0 OP_EQUAL
//! ```
//!
//! Once any one of those addresses is spent, the template and its public keys
//! are public. Every *other* address in the family, even one never spent
//! from, is then exposed in practice: an adversary can enumerate the salt
//! space (2^32 for a 4-byte salt) to rebuild its redeem script, and break the
//! already-public keys. ZIP 2007 notes that unseen P2SH funds "can't be
//! definitively classified as recoverable based on public information".
//! This sweep shows that for templated custodial addresses they can be
//! classified as exposed.
//!
//! For each salted template seen in the P2SH survey, every salt value is
//! hashed and matched against all funded, never-spent P2SH addresses. As a
//! self-check, the sweep must also rediscover the template's own revealed
//! addresses.

use crate::report::P2shSurvey;
use crate::report::BASE58;
use crate::script::{self, Kind, RedeemKind};
use anyhow::{Context, Result};
use ripemd::{Digest, Ripemd160};
use rustc_hash::{FxHashMap, FxHashSet};
use serde::Serialize;
use sha2::digest::generic_array::GenericArray;
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::Instant;

const SHA256_IV: [u32; 8] = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
];

/// A salted script with precomputed SHA-256 midstate.
pub struct Template {
    pub script: Vec<u8>,
    pub salt_off: usize,
    pub salt_len: usize,
    midstate: [u32; 8],
    tail: Vec<u8>,
    tail_salt_off: usize,
}

impl Template {
    pub fn new(script: &[u8], salt_off: usize, salt_len: usize) -> Template {
        let mut padded = script.to_vec();
        padded.push(0x80);
        while padded.len() % 64 != 56 {
            padded.push(0);
        }
        padded.extend_from_slice(&((script.len() as u64) * 8).to_be_bytes());
        let first = salt_off / 64;
        let mut mid = SHA256_IV;
        for b in 0..first {
            sha2::compress256(&mut mid, &[*GenericArray::from_slice(&padded[b * 64..(b + 1) * 64])]);
        }
        Template {
            script: script.to_vec(),
            salt_off,
            salt_len,
            midstate: mid,
            tail: padded[first * 64..].to_vec(),
            tail_salt_off: salt_off - first * 64,
        }
    }

    /// Hash160 of the script with `salt` substituted, using the midstate.
    #[inline]
    pub fn hash160_with(&self, buf: &mut [u8], salt: &[u8]) -> [u8; 20] {
        buf[self.tail_salt_off..self.tail_salt_off + salt.len()].copy_from_slice(salt);
        let mut st = self.midstate;
        for c in buf.chunks(64) {
            sha2::compress256(&mut st, std::slice::from_ref(GenericArray::from_slice(c)));
        }
        let mut sha = [0u8; 32];
        for (i, w) in st.iter().enumerate() {
            sha[i * 4..i * 4 + 4].copy_from_slice(&w.to_be_bytes());
        }
        let r = Ripemd160::digest(sha);
        let mut out = [0u8; 20];
        out.copy_from_slice(&r);
        out
    }
}

#[derive(Debug, Serialize, Clone)]
pub struct Match {
    pub address: String,
    pub zat: u64,
    pub salt: String,
}

#[derive(Debug, Serialize)]
pub struct TemplateReport {
    pub redeem: RedeemKind,
    pub script_template: String,
    pub public_keys: Vec<String>,
    pub revealed_addresses: usize,
    pub revealed_zat: u64,
    pub rediscovered_revealed: usize,
    pub unseen_matches: Vec<Match>,
    pub unseen_matched_zat: u64,
    pub salts_searched: u64,
    pub seconds: f64,
}

#[derive(Debug, Serialize)]
pub struct SweepReport {
    pub unseen_p2sh_funded: usize,
    pub unseen_p2sh_zat: u64,
    pub templates: Vec<TemplateReport>,
    pub matched_addresses: usize,
    pub matched_zat: u64,
}

/// Funded P2SH addresses from the lookup shards, by category (2 = unseen, 3 = seen).
fn load_p2sh(data: &Path) -> Result<FxHashMap<[u8; 20], (String, u64, u8)>> {
    let dir = data.join("lookup");
    let alphabet: Vec<char> = BASE58.chars().collect();
    let mut out = FxHashMap::default();
    for entry in std::fs::read_dir(&dir).context("reading lookup/ (run `shorline scan` first)")? {
        let path = entry?.path();
        let name = path.file_stem().and_then(|s| s.to_str()).unwrap_or_default().to_string();
        if !name.starts_with("t3_") {
            continue;
        }
        let idx: usize = name[3..].parse()?;
        let head = format!("t3{}{}", alphabet[idx / 58], alphabet[idx % 58]);
        let shard: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&path)?)?;
        for row in shard["e"].as_array().into_iter().flatten() {
            let cat = row[1].as_u64().unwrap_or(99) as u8;
            let zat = row[2].as_u64().unwrap_or(0);
            let address = format!("{head}{}", row[0].as_str().unwrap_or_default());
            if let Some((Kind::P2sh, h)) = script::decode_taddr(&address) {
                out.insert(h, (address, zat, cat));
            }
        }
    }
    Ok(out)
}

pub fn run(data: &Path, threads: usize, max_salt_bytes: usize) -> Result<()> {
    let survey: P2shSurvey = serde_json::from_str(&std::fs::read_to_string(data.join("p2sh_survey.json"))?)?;
    let p2sh = load_p2sh(data)?;
    let unseen: Vec<(&[u8; 20], &(String, u64, u8))> = p2sh.iter().filter(|(_, v)| v.2 == 2).collect();
    let unseen_zat: u64 = unseen.iter().map(|(_, v)| v.1).sum();
    eprintln!("salt sweep: {} funded unseen P2SH addresses ({} ZEC) as targets", unseen.len(), unseen_zat / 100_000_000);

    // Group revealed salted scripts into templates (salt bytes zeroed).
    let mut groups: FxHashMap<Vec<u8>, (RedeemKind, usize, usize, Vec<(String, u64)>)> = FxHashMap::default();
    for e in &survey.entries {
        if e.redeem_script.is_empty() {
            continue;
        }
        let rs = hex::decode(&e.redeem_script)?;
        let Some((off, len)) = script::salt_position(&rs) else { continue };
        if len > max_salt_bytes {
            eprintln!("  skipping template with {len}-byte salt (> {max_salt_bytes})");
            continue;
        }
        let mut key = rs.clone();
        key[off..off + len].iter_mut().for_each(|b| *b = 0);
        groups
            .entry(key)
            .or_insert_with(|| (e.redeem.clone(), off, len, Vec::new()))
            .3
            .push((e.address.clone(), e.zat));
    }

    // Prefix bitmap + exact set over every funded P2SH hash (unseen and seen).
    let mut bitmap = vec![0u64; 1 << 18];
    let mut targets: FxHashSet<[u8; 20]> = FxHashSet::default();
    for h in p2sh.keys() {
        let i = (h[0] as usize) << 16 | (h[1] as usize) << 8 | h[2] as usize;
        bitmap[i >> 6] |= 1 << (i & 63);
        targets.insert(*h);
    }

    let mut reports = Vec::new();
    for (key, (redeem, off, len, revealed)) in groups {
        let t = Template::new(&key, off, len);
        let total: u64 = 1u64 << (8 * len);
        let next = AtomicU64::new(0);
        let found: Mutex<Vec<([u8; 20], Vec<u8>)>> = Mutex::new(Vec::new());
        let started = Instant::now();
        eprintln!("  template {} ({} revealed addresses): searching {} salts on {threads} threads", redeem.label(), revealed.len(), total);
        std::thread::scope(|sc| {
            for _ in 0..threads {
                sc.spawn(|| {
                    let mut buf = t.tail.clone();
                    let mut local = Vec::new();
                    const STEP: u64 = 1 << 20;
                    loop {
                        let start = next.fetch_add(STEP, Ordering::Relaxed);
                        if start >= total {
                            break;
                        }
                        for s in start..(start + STEP).min(total) {
                            let bytes = s.to_be_bytes();
                            let salt = &bytes[8 - len..];
                            let h = t.hash160_with(&mut buf, salt);
                            let i = (h[0] as usize) << 16 | (h[1] as usize) << 8 | h[2] as usize;
                            if bitmap[i >> 6] & (1 << (i & 63)) != 0 && targets.contains(&h) {
                                local.push((h, salt.to_vec()));
                            }
                        }
                    }
                    found.lock().unwrap().extend(local);
                });
            }
        });
        let secs = started.elapsed().as_secs_f64();
        let found = found.into_inner().unwrap();
        let revealed_set: FxHashSet<&str> = revealed.iter().map(|(a, _)| a.as_str()).collect();
        let mut rediscovered = 0;
        let mut matches = Vec::new();
        for (h, salt) in found {
            let (addr, zat, cat) = &p2sh[&h];
            if revealed_set.contains(addr.as_str()) || *cat == 3 {
                rediscovered += 1;
            } else {
                matches.push(Match { address: addr.clone(), zat: *zat, salt: hex::encode(salt) });
            }
        }
        matches.sort_by(|a, b| b.zat.cmp(&a.zat));
        let keys = script::parse_multisig_keys_any(&key);
        let mut tmpl = hex::encode(&key);
        tmpl.replace_range(off * 2..(off + len) * 2, &"?".repeat(len * 2));
        let r = TemplateReport {
            redeem,
            script_template: tmpl,
            public_keys: keys.iter().map(hex::encode).collect(),
            revealed_addresses: revealed.len(),
            revealed_zat: revealed.iter().map(|(_, z)| z).sum(),
            rediscovered_revealed: rediscovered,
            unseen_matched_zat: matches.iter().map(|m| m.zat).sum(),
            unseen_matches: matches,
            salts_searched: total,
            seconds: secs,
        };
        eprintln!(
            "    {:.0}s: rediscovered {}/{} revealed addresses (self-check); matched {} unseen addresses holding {} ZEC",
            secs,
            r.rediscovered_revealed,
            r.revealed_addresses,
            r.unseen_matches.len(),
            r.unseen_matched_zat as f64 / 1e8
        );
        reports.push(r);
    }
    reports.sort_by(|a, b| b.revealed_zat.cmp(&a.revealed_zat));
    let report = SweepReport {
        unseen_p2sh_funded: unseen.len(),
        unseen_p2sh_zat: unseen_zat,
        matched_addresses: reports.iter().map(|r| r.unseen_matches.len()).sum(),
        matched_zat: reports.iter().map(|r| r.unseen_matched_zat).sum(),
        templates: reports,
    };
    std::fs::write(data.join("salted_exposure.json"), serde_json::to_string_pretty(&report)?)?;
    eprintln!(
        "wrote {}: {} unseen P2SH addresses ({} ZEC) belong to salted families whose keys are already public",
        data.join("salted_exposure.json").display(),
        report.matched_addresses,
        report.matched_zat as f64 / 1e8
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn midstate_hash_matches_plain_hash160() {
        let rs = hex::decode("52210352d50656796dd79e3e3385c29636d849b8705c9c6d9b86a1717adc38e4a567c72102f39d0b69c3b8e06030ef9dc295cf8c848f51e398fe85414e33509afdc7f01fb321027072ba2319ead2b0b387d69d36508f57b397da8d4ac76ea64676ee8a1356dae053af04ffc378b775740087").unwrap();
        let (off, len) = script::salt_position(&rs).unwrap();
        let mut key = rs.clone();
        key[off..off + len].iter_mut().for_each(|b| *b = 0);
        let t = Template::new(&key, off, len);
        let mut buf = t.tail.clone();
        assert_eq!(t.hash160_with(&mut buf, &[0xff, 0xc3, 0x78, 0xb7]), script::hash160(&rs));
        let (_, h) = script::decode_taddr("t3hdTwzcVVGEqDdNKJTBfWvWyaFYNJv7KkA").unwrap();
        assert_eq!(t.hash160_with(&mut buf, &[0xff, 0xc3, 0x78, 0xb7]), h);
    }
}
