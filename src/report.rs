//! Turns the engine state into the published dataset:
//! `summary.json`, `timeseries.json`, `top.json`, `p2sh_survey.json`, and
//! the privacy-preserving `lookup/` shards used by the web address checker.

use crate::engine::{AddrState, Cat, Engine, RevealReason, CAT_IDS, NEVER, N_CATS};
use crate::pools::Pools;
use crate::script::{encode_taddr, Kind, RedeemKind};
use anyhow::Result;
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

pub const BASE58: &str = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

#[derive(Clone, Debug, Serialize)]
pub struct CrossCheck {
    pub height: u32,
    pub zebra_transparent_zat: u64,
    pub shorline_transparent_zat: u64,
    pub difference_zat: i128,
    #[serde(rename = "match")]
    pub matches: bool,
    pub node_build: String,
}

#[derive(Clone, Debug, Serialize, serde::Deserialize)]
pub struct P2shSurveyEntry {
    pub address: String,
    pub zat: u64,
    pub redeem: RedeemKind,
    /// The redeem script, hex.
    #[serde(default)]
    pub redeem_script: String,
    pub first_spend_txid: String,
    pub first_spend_height: u32,
}

#[derive(Clone, Debug, Default, Serialize, serde::Deserialize)]
pub struct P2shSurvey {
    pub addresses_with_balance: usize,
    pub classified: usize,
    pub failed: usize,
    pub entries: Vec<P2shSurveyEntry>,
}

pub struct Meta {
    pub servers: Vec<String>,
    pub pools_url: Option<String>,
    pub seconds: f64,
    pub top_n: usize,
    pub write_lookup: bool,
}

/// Summary of the P2SH redeem-script survey, grouped by script type.
pub fn p2sh_summary(s: &P2shSurvey) -> Value {
    let mut by: BTreeMap<String, (u64, u64)> = BTreeMap::new();
    for en in &s.entries {
        let x = by.entry(en.redeem.label()).or_default();
        x.0 += 1;
        x.1 += en.zat;
    }
    json!({
        "addresses_with_balance": s.addresses_with_balance,
        "classified": s.classified,
        "failed": s.failed,
        "by_redeem_type": by.iter().map(|(k, (n, v))| json!({"type": k, "addresses": n, "zat": v})).collect::<Vec<_>>(),
    })
}

/// Proleptic Gregorian year of a Unix timestamp (H. Hinnant's algorithm).
pub fn year_of(unix: u32) -> i32 {
    let days = (unix as i64).div_euclid(86_400);
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (yoe + era * 400 + if m <= 2 { 1 } else { 0 }) as i32
}

pub fn display_txid(txid: &[u8; 32]) -> String {
    let mut r = *txid;
    r.reverse();
    hex::encode(r)
}

fn label(kind: Kind, hash: &[u8; 20]) -> String {
    encode_taddr(kind, hash).unwrap_or_else(|| format!("script:{}", hex::encode(hash)))
}

fn reason_str(r: u8) -> Option<&'static str> {
    match r {
        x if x == RevealReason::Spend as u8 => Some("spend"),
        x if x == RevealReason::PubkeyInOutput as u8 => Some("pubkey_in_output"),
        _ => None,
    }
}

fn is_exposed(c: Cat) -> bool {
    matches!(c, Cat::P2pkhExposed | Cat::P2shSeen | Cat::P2pk | Cat::BareMultisig)
}

pub fn write_all(
    out: &Path,
    e: &Engine,
    pools: Option<&Pools>,
    cross: Option<&CrossCheck>,
    p2sh: Option<&P2shSurvey>,
    meta: &Meta,
) -> Result<()> {
    fs::create_dir_all(out)?;
    let height = e.height.unwrap_or(0);
    let tip_time = e.times.get(height as usize).copied().unwrap_or(0);
    let time_of = |h: u32| e.times.get(h as usize).copied().unwrap_or(0);

    // ---- per-entity aggregates -------------------------------------------
    let mut addr_counts = [0u64; N_CATS];
    let mut per_cat: Vec<Vec<(u64, Kind, [u8; 20], &AddrState)>> = vec![Vec::new(); N_CATS];
    let mut exposure_by_year: BTreeMap<i32, u64> = BTreeMap::new();
    let mut dormancy: BTreeMap<&'static str, [u64; 2]> = BTreeMap::new(); // [exposed, hidden]
    let mut reveal_reason_zat = [0u64; 3];
    let mut exposed_reused = (0u64, 0u64); // (addresses with balance that received after reveal, zat they received after reveal)
    let buckets = ["0-1y", "1-2y", "2-4y", "4-6y", "6y+"];
    for b in buckets {
        dormancy.insert(b, [0, 0]);
    }
    for (kind, hash, a) in e.iter_addrs() {
        if a.balance == 0 {
            continue;
        }
        let c = a.cat();
        addr_counts[c as usize] += 1;
        per_cat[c as usize].push((a.balance, kind, hash, a));
        let age_years = (tip_time.saturating_sub(time_of(a.last_seen))) as f64 / (365.25 * 86_400.0);
        let bucket = match age_years {
            y if y < 1.0 => buckets[0],
            y if y < 2.0 => buckets[1],
            y if y < 4.0 => buckets[2],
            y if y < 6.0 => buckets[3],
            _ => buckets[4],
        };
        if is_exposed(c) {
            let rh = if a.revealed == NEVER { a.first_seen } else { a.revealed };
            *exposure_by_year.entry(year_of(time_of(rh))).or_default() += a.balance;
            dormancy.get_mut(bucket).unwrap()[0] += a.balance;
            reveal_reason_zat[a.reveal_reason.min(2) as usize] += a.balance;
            if a.received_after_reveal > 0 {
                exposed_reused.0 += 1;
                exposed_reused.1 += a.received_after_reveal;
            }
        } else if c == Cat::P2pkhHidden {
            dormancy.get_mut(bucket).unwrap()[1] += a.balance;
        }
    }

    let z = |c: Cat| e.cat_zat[c as usize];
    let exposed = z(Cat::P2pkhExposed) + z(Cat::P2shSeen) + z(Cat::P2pk) + z(Cat::BareMultisig);
    let transparent_total = e.total_zat();

    let (stranded, recoverable, lockbox, shielded_detail) = match pools {
        Some(p) => (
            p.get("sprout") + p.get("sapling") + p.get("orchard"),
            p.get("ironwood"),
            p.get("lockbox"),
            json!({
                "height": p.height,
                "zat": p.zat,
            }),
        ),
        None => (0, 0, 0, Value::Null),
    };

    // Flow into already-exposed addresses over the last 30 days.
    let cutoff = tip_time.saturating_sub(30 * 86_400);
    let base = e.samples.iter().rev().find(|s| s.time <= cutoff).map(|s| (s.height, s.sent_to_exposed));
    let sent_30d = base.map(|(h, v)| json!({"since_height": h, "zat": e.sent_to_exposed - v}));

    let categories: Vec<Value> = (0..N_CATS)
        .map(|i| {
            json!({
                "id": CAT_IDS[i],
                "zat": e.cat_zat[i],
                "utxos": e.cat_utxos[i],
                "addresses": addr_counts[i],
            })
        })
        .collect();

    let summary = json!({
        "schema": 1,
        "tool": concat!("shorline ", env!("CARGO_PKG_VERSION")),
        "generated_at": std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)?.as_secs(),
        "chain": {
            "height": height,
            "hash": if e.tip_hash.len() == 32 { let mut h = e.tip_hash.clone(); h.reverse(); hex::encode(h) } else { hex::encode(&e.tip_hash) },
            "time": tip_time,
        },
        "sources": { "lightwalletd": meta.servers, "value_pools": meta.pools_url },
        "scan": {
            "blocks": e.n_blocks,
            "transactions": e.n_tx,
            "inputs": e.n_vin,
            "outputs": e.n_vout,
            "utxos": e.utxo_count(),
            "entities": e.addr_count(),
            "missing_prevouts": e.missing_prevouts,
            "seconds": meta.seconds,
        },
        "transparent": { "total_zat": transparent_total, "categories": categories },
        "shielded": shielded_detail,
        "cross_check": cross,
        "risk": {
            "exposed_zat": exposed,
            "hash_protected_zat": z(Cat::P2pkhHidden),
            "unknown_zat": z(Cat::P2shUnseen),
            "stranded_zat": stranded,
            "recoverable_zat": recoverable,
            "lockbox_zat": lockbox,
            "unspendable_zat": z(Cat::NullData) + z(Cat::Nonstandard),
            "total_zat": transparent_total + stranded + recoverable + lockbox,
        },
        "exposed_by_reveal_year": exposure_by_year.iter().map(|(y, v)| json!({"year": y, "zat": v})).collect::<Vec<_>>(),
        "exposed_by_reason": {
            "spend": reveal_reason_zat[RevealReason::Spend as usize],
            "pubkey_in_output": reveal_reason_zat[RevealReason::PubkeyInOutput as usize],
        },
        "dormancy": buckets.iter().map(|b| json!({"bucket": b, "exposed_zat": dormancy[b][0], "hidden_zat": dormancy[b][1]})).collect::<Vec<_>>(),
        "reuse": {
            "sent_to_exposed_total_zat": e.sent_to_exposed,
            "sent_to_exposed_last_30d": sent_30d,
            "exposed_addresses_with_balance_that_received_after_reveal": exposed_reused.0,
        },
        "p2sh_survey": p2sh.map(p2sh_summary),
    });
    fs::write(out.join("summary.json"), serde_json::to_string_pretty(&summary)?)?;

    // ---- time series --------------------------------------------------------
    let rows: Vec<Value> = e
        .samples
        .iter()
        .map(|s| {
            let mut r = vec![json!(s.height), json!(s.time)];
            r.extend(s.zat.iter().map(|v| json!(v)));
            r.push(json!(s.sent_to_exposed));
            Value::Array(r)
        })
        .collect();
    let columns: Vec<String> = ["height", "time"]
        .iter()
        .chain(CAT_IDS.iter())
        .chain(["sent_to_exposed"].iter())
        .map(|s| s.to_string())
        .collect();
    let ts = json!({ "columns": columns, "rows": rows });
    fs::write(out.join("timeseries.json"), serde_json::to_string(&ts)?)?;

    // ---- top holders per category ---------------------------------------------
    let mut top = serde_json::Map::new();
    for (i, list) in per_cat.iter_mut().enumerate() {
        list.sort_unstable_by(|a, b| b.0.cmp(&a.0));
        let items: Vec<Value> = list
            .iter()
            .take(meta.top_n)
            .map(|(bal, kind, hash, a)| {
                json!({
                    "address": label(*kind, hash),
                    "zat": bal,
                    "utxos": a.utxos,
                    "first_seen": a.first_seen,
                    "last_seen": a.last_seen,
                    "last_seen_time": time_of(a.last_seen),
                    "revealed": if a.revealed == NEVER { Value::Null } else { json!(a.revealed) },
                    "revealed_time": if a.revealed == NEVER { Value::Null } else { json!(time_of(a.revealed)) },
                    "reason": reason_str(a.reveal_reason),
                    "received_after_reveal_zat": a.received_after_reveal,
                })
            })
            .collect();
        top.insert(CAT_IDS[i].to_string(), Value::Array(items));
    }
    fs::write(out.join("top.json"), serde_json::to_string_pretty(&Value::Object(top))?)?;

    if let Some(s) = p2sh {
        fs::write(out.join("p2sh_survey.json"), serde_json::to_string_pretty(s)?)?;
    }

    if meta.write_lookup {
        write_lookup(out, e, height)?;
    }
    Ok(())
}

/// Shard index for an address: the two Base58 characters after the
/// `t1`/`t3` prefix. Looking an address up downloads only its shard, so a
/// static host learns just a two-character prefix shared by hundreds of
/// other funded addresses (k-anonymity), never the address itself.
pub fn shard_of(addr: &str) -> Option<String> {
    let b = addr.as_bytes();
    if b.len() < 4 {
        return None;
    }
    let i = BASE58.find(b[2] as char)?;
    let j = BASE58.find(b[3] as char)?;
    Some(format!("{}_{:04}", &addr[..2], i * 58 + j))
}

fn write_lookup(out: &Path, e: &Engine, height: u32) -> Result<()> {
    let dir = out.join("lookup");
    if dir.exists() {
        fs::remove_dir_all(&dir)?;
    }
    fs::create_dir_all(&dir)?;
    let mut shards: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    let mut n = 0u64;
    for (kind, hash, a) in e.iter_addrs() {
        if a.balance == 0 || !kind.has_address() {
            continue;
        }
        let addr = encode_taddr(kind, &hash).unwrap();
        let Some(s) = shard_of(&addr) else { continue };
        shards.entry(s).or_default().push(json!([
            &addr[4..],
            a.cat() as usize,
            a.balance,
            if a.revealed == NEVER { -1i64 } else { a.revealed as i64 },
            a.first_seen,
            a.last_seen,
        ]));
        n += 1;
    }
    let count = shards.len();
    for (s, entries) in shards {
        fs::write(dir.join(format!("{s}.json")), serde_json::to_string(&json!({"h": height, "e": entries}))?)?;
    }
    fs::write(
        dir.join("index.json"),
        serde_json::to_string_pretty(&json!({
            "height": height,
            "entries": n,
            "shards": count,
            "row": ["address_suffix", "category_index", "balance_zat", "revealed_height_or_-1", "first_seen", "last_seen"],
            "categories": CAT_IDS,
        }))?,
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn years() {
        assert_eq!(year_of(0), 1970);
        assert_eq!(year_of(1_477_641_360), 2016); // Zcash launch, 2016-10-28
        assert_eq!(year_of(1_798_761_600), 2027); // 2027-01-01T00:00:00Z
    }

    #[test]
    fn shards() {
        assert_eq!(shard_of("t11111"), Some("t1_0000".into()));
        assert_eq!(shard_of("t1zz11"), Some(format!("t1_{:04}", 57 * 58 + 57)));
        assert_eq!(shard_of("t1"), None);
    }
}
