//! Cross-chain exposure through the Ycash fork.
//!
//! Ycash forked from Zcash at height 570,000 (July 2019) with a copy of the
//! entire UTXO set, so every Zcash `t1`/`t3` address that held funds before
//! the fork also held them on Ycash, under the *same keys*. If the owner ever
//! spent those coins on Ycash, the spend published the public key (or redeem
//! script) on the Ycash chain, and the matching ZEC is exposed even if it has
//! never moved on Zcash.
//!
//! For each Zcash address that looks hash-protected (or is an unseen P2SH)
//! and was funded before the fork, we list its post-fork Ycash transactions
//! and look for an input whose scriptSig carries a public key / redeem script
//! whose Hash160 equals the address hash. A match is cryptographic proof the
//! key is public.

use crate::net;
use crate::rawtx;
use crate::report::BASE58;
use crate::rpc;
use crate::script::{self, Kind};
use anyhow::{Context, Result};
use futures::StreamExt;
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::path::Path;
use std::time::Duration;

/// Ycash Base58Check prefixes (`s1…` P2PKH, `s3…` P2SH).
const S1_PREFIX: [u8; 2] = [0x1C, 0x28];
const S3_PREFIX: [u8; 2] = [0x1C, 0x2D];

#[derive(Clone, Debug)]
pub struct Candidate {
    pub address: String,
    pub kind: Kind,
    pub hash: [u8; 20],
    pub zat: u64,
    pub category: u8,
    pub first_seen: u32,
}

#[derive(Clone, Debug, Serialize)]
pub struct Revealed {
    pub address: String,
    pub ycash_address: String,
    pub zat: u64,
    pub category: &'static str,
    pub ycash_height: u64,
    pub ycash_txid: String,
}

#[derive(Debug, Serialize)]
pub struct YcashReport {
    pub fork_height: u64,
    pub server: String,
    pub ycash_tip: u64,
    pub zcash_snapshot_height: u64,
    pub candidates: usize,
    pub candidates_zat: u64,
    pub checked: usize,
    pub checked_zat: u64,
    pub failed: usize,
    pub revealed_count: usize,
    pub revealed_zat: u64,
    pub revealed: Vec<Revealed>,
}

pub fn ycash_address(kind: Kind, hash: &[u8; 20]) -> String {
    let prefix = if kind == Kind::P2pkh {
        S1_PREFIX
    } else {
        S3_PREFIX
    };
    let mut p = prefix.to_vec();
    p.extend_from_slice(hash);
    bs58::encode(p).with_check().into_string()
}

/// Loads funded addresses from the lookup shards written by `scan`.
pub fn load_candidates(data: &Path, fork: u64) -> Result<(u64, Vec<Candidate>)> {
    let dir = data.join("lookup");
    let index: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(dir.join("index.json"))
            .context("reading lookup/index.json (run `shorline scan` first)")?,
    )?;
    let height = index["height"].as_u64().unwrap_or(0);
    let alphabet: Vec<char> = BASE58.chars().collect();
    let mut out = Vec::new();
    for entry in std::fs::read_dir(&dir)? {
        let path = entry?.path();
        let name = path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or_default()
            .to_string();
        if name == "index" || !name.contains('_') {
            continue;
        }
        let (prefix, idx) = name.split_once('_').unwrap();
        let idx: usize = idx.parse()?;
        let head = format!("{prefix}{}{}", alphabet[idx / 58], alphabet[idx % 58]);
        let shard: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&path)?)?;
        for row in shard["e"].as_array().into_iter().flatten() {
            let cat = row[1].as_u64().unwrap_or(99) as u8;
            let zat = row[2].as_u64().unwrap_or(0);
            let first = row[4].as_u64().unwrap_or(u64::MAX);
            // 0 = p2pkh_hidden, 2 = p2sh_unseen
            if (cat == 0 || cat == 2) && first < fork && zat > 0 {
                let address = format!("{head}{}", row[0].as_str().unwrap_or_default());
                if let Some((kind, hash)) = script::decode_taddr(&address) {
                    out.push(Candidate {
                        address,
                        kind,
                        hash,
                        zat,
                        category: cat,
                        first_seen: first as u32,
                    });
                }
            }
        }
    }
    out.sort_by(|a, b| b.zat.cmp(&a.zat));
    Ok((height, out))
}

fn txid_v4(raw: &[u8]) -> String {
    let mut h = Sha256::digest(Sha256::digest(raw)).to_vec();
    h.reverse();
    hex::encode(h)
}

/// Returns the first post-fork Ycash spend that reveals the candidate's key.
async fn find_reveal(
    c: &mut net::Client,
    cand: &Candidate,
    fork: u64,
    tip: u64,
) -> Result<Option<(u64, String)>> {
    let filter = rpc::TransparentAddressBlockFilter {
        address: ycash_address(cand.kind, &cand.hash),
        range: Some(rpc::BlockRange {
            start: Some(rpc::BlockId {
                height: fork,
                hash: vec![],
            }),
            end: Some(rpc::BlockId {
                height: tip,
                hash: vec![],
            }),
            pool_types: vec![],
        }),
    };
    let mut stream = c.get_taddress_txids(filter).await?.into_inner();
    let mut best: Option<(u64, String)> = None;
    while let Some(t) = stream.message().await? {
        let Ok((_, ins)) = rawtx::parse_inputs(&t.data) else {
            continue;
        };
        for i in ins {
            let Some(pushes) = rawtx::pushes(&i.script_sig) else {
                continue;
            };
            let Some(last) = pushes.last() else { continue };
            let hit = match cand.kind {
                Kind::P2pkh => {
                    (last.len() == 33 || last.len() == 65) && script::hash160(last) == cand.hash
                }
                _ => script::hash160(last) == cand.hash,
            };
            if hit && best.as_ref().map_or(true, |(h, _)| t.height < *h) {
                best = Some((t.height, txid_v4(&t.data)));
            }
        }
    }
    Ok(best)
}

pub async fn run(
    data: &Path,
    server: &str,
    fork: u64,
    top: usize,
    concurrency: usize,
) -> Result<()> {
    let (snap, all) = load_candidates(data, fork)?;
    let candidates_zat: u64 = all.iter().map(|c| c.zat).sum();
    let chosen: Vec<Candidate> = if top == 0 {
        all.clone()
    } else {
        all.iter().take(top).cloned().collect()
    };
    let checked_zat: u64 = chosen.iter().map(|c| c.zat).sum();
    eprintln!(
        "Ycash cross-check: {} candidate addresses funded before {fork} ({} ZEC); checking {} ({} ZEC)",
        all.len(),
        candidates_zat / 100_000_000,
        chosen.len(),
        checked_zat / 100_000_000
    );
    let client = net::connect(server).await?;
    let mut c0 = client.clone();
    let tip = net::tip(&mut c0).await?;
    let total = chosen.len();
    let mut done = 0usize;
    let mut failed = 0usize;
    let mut revealed = Vec::new();
    let mut results = futures::stream::iter(chosen.into_iter().map(|cand| {
        let mut c = client.clone();
        async move {
            for attempt in 0..3u32 {
                match find_reveal(&mut c, &cand, fork, tip).await {
                    Ok(r) => return (cand, Ok(r)),
                    Err(e) if attempt == 2 => return (cand, Err(e)),
                    Err(_) => tokio::time::sleep(Duration::from_millis(800 << attempt)).await,
                }
            }
            unreachable!()
        }
    }))
    .buffer_unordered(concurrency.max(1));
    while let Some((cand, r)) = results.next().await {
        done += 1;
        match r {
            Ok(Some((h, txid))) => revealed.push(Revealed {
                ycash_address: ycash_address(cand.kind, &cand.hash),
                address: cand.address,
                zat: cand.zat,
                category: if cand.category == 0 {
                    "p2pkh_hidden"
                } else {
                    "p2sh_unseen"
                },
                ycash_height: h,
                ycash_txid: txid,
            }),
            Ok(None) => {}
            Err(e) => {
                failed += 1;
                if failed <= 5 {
                    eprintln!("  ! {}: {e:#}", cand.address);
                }
            }
        }
        if done % 250 == 0 || done == total {
            let z: u64 = revealed.iter().map(|r| r.zat).sum();
            eprintln!("  {done}/{total} checked | revealed on Ycash: {} addresses, {} ZEC | failed {failed}", revealed.len(), z / 100_000_000);
        }
    }
    revealed.sort_by(|a, b| b.zat.cmp(&a.zat));
    let report = YcashReport {
        fork_height: fork,
        server: server.to_string(),
        ycash_tip: tip,
        zcash_snapshot_height: snap,
        candidates: all.len(),
        candidates_zat,
        checked: total,
        checked_zat,
        failed,
        revealed_count: revealed.len(),
        revealed_zat: revealed.iter().map(|r| r.zat).sum(),
        revealed,
    };
    std::fs::write(
        data.join("ycash_exposure.json"),
        serde_json::to_string_pretty(&report)?,
    )?;
    eprintln!(
        "wrote {}: {} addresses / {} ZEC that look hash-protected on Zcash had their keys revealed on Ycash",
        data.join("ycash_exposure.json").display(),
        report.revealed_count,
        report.revealed_zat as f64 / 1e8
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ycash_prefixes() {
        let h = [0u8; 20];
        assert!(ycash_address(Kind::P2pkh, &h).starts_with("s1"));
        assert!(ycash_address(Kind::P2sh, &[0xff; 20]).starts_with("s3"));
        // A real pair: the same key on both chains.
        let (k, hash) = script::decode_taddr("t1cesdj5WMe8K6tYKobNp1qufxWeMNSRJXt").unwrap();
        assert_eq!(
            ycash_address(k, &hash),
            "s1fz1r6A27fQ9LUTrHBQvBniPKsYX2e5dx4"
        );
    }
}
