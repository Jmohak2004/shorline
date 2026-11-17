//! Shorline: a quantum-exposure survey of the Zcash chain.
//!
//! `shorline scan`  replays every transparent input/output from genesis via
//!                  public lightwalletd servers, classifies all value by
//!                  quantum exposure (ZIP 2005 threat model, ZIP 2007 scope),
//!                  cross-checks the result against Zebra's transparent value
//!                  pool, and writes the dataset behind the dashboard.
//! `shorline check` classifies individual t-addresses live.

mod engine;
mod net;
mod pools;
mod rawtx;
mod report;
mod script;
mod salt;
mod ycash;

pub mod rpc {
    tonic::include_proto!("cash.z.wallet.sdk.rpc");
}

use anyhow::{bail, Context, Result};
use clap::{Parser, Subcommand};
use engine::{Engine, NEVER};
use futures::StreamExt;
use report::{CrossCheck, P2shSurvey, P2shSurveyEntry};
use script::{classify_redeem_script, Kind};
use std::collections::{BTreeSet, HashMap};
use std::path::PathBuf;
use std::time::{Duration, Instant};

const DEFAULT_SERVERS: [&str; 4] = [
    "https://zec.rocks:443",
    "https://na.zec.rocks:443",
    "https://eu.zec.rocks:443",
    "https://ap.zec.rocks:443",
];

#[derive(Parser)]
#[command(name = "shorline", version, about = "Quantum-exposure survey of the Zcash chain (ZIP 2005 / ZIP 2007)")]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Replay the chain from genesis and write the exposure dataset.
    Scan {
        /// lightwalletd servers (repeatable). Must serve transparent data in GetBlockRange.
        #[arg(long = "server")]
        servers: Vec<String>,
        /// Stop at this height (default: chain tip, then catch up to the pools source).
        #[arg(long)]
        end: Option<u64>,
        /// Blocks per request.
        #[arg(long, default_value_t = 2000)]
        chunk: u64,
        /// Concurrent chunk downloads.
        #[arg(long, default_value_t = 4)]
        concurrency: usize,
        /// Record category totals every N blocks.
        #[arg(long, default_value_t = 1000)]
        sample_every: u32,
        /// Output directory.
        #[arg(long, default_value = "data")]
        out: PathBuf,
        /// Zebra `getblockchaininfo` JSON endpoint used for shielded pools and the cross-check.
        #[arg(long, default_value = pools::DEFAULT_POOLS_URL)]
        pools_url: String,
        /// Skip the value-pool fetch and cross-check.
        #[arg(long)]
        no_pools: bool,
        /// Skip fetching first-spend transactions of funded P2SH addresses.
        #[arg(long)]
        no_p2sh_survey: bool,
        /// Skip writing the per-address lookup shards.
        #[arg(long)]
        no_lookup: bool,
        /// Entries per category in top.json.
        #[arg(long, default_value_t = 100)]
        top: usize,
    },
    /// Classify t-addresses live against a lightwalletd server.
    Check {
        /// t1… / t3… addresses.
        #[arg(required = true)]
        addresses: Vec<String>,
        #[arg(long, default_value = DEFAULT_SERVERS[0])]
        server: String,
    },
    /// Check hash-protected addresses funded before the 2019 Ycash fork for
    /// keys revealed by spends on the Ycash chain (run after `scan`).
    Ycash {
        /// Dataset directory written by `scan` (needs lookup/).
        #[arg(long, default_value = "web/data")]
        data: PathBuf,
        #[arg(long, default_value = "https://lite.ycash.xyz:9067")]
        server: String,
        /// Height at which Ycash diverged from Zcash.
        #[arg(long, default_value_t = 570_000)]
        fork: u64,
        /// Check the N largest candidates (0 = all).
        #[arg(long, default_value_t = 0)]
        top: usize,
        #[arg(long, default_value_t = 8)]
        concurrency: usize,
    },
    /// Re-fetch and re-classify the redeem scripts in p2sh_survey.json
    /// (refreshes the survey without re-running the full scan).
    Resurvey {
        #[arg(long, default_value = "web/data")]
        data: PathBuf,
        #[arg(long, default_value = DEFAULT_SERVERS[0])]
        server: String,
        #[arg(long, default_value_t = 12)]
        concurrency: usize,
    },
    /// Brute-force the salt space of salted P2SH templates and match every
    /// funded, never-spent P2SH address against families whose keys are public.
    SaltSweep {
        #[arg(long, default_value = "web/data")]
        data: PathBuf,
        /// Worker threads (default: all cores).
        #[arg(long)]
        threads: Option<usize>,
        /// Only sweep templates whose salt is at most this many bytes.
        #[arg(long, default_value_t = 4)]
        max_salt_bytes: usize,
    },
    /// Print server information.
    Info {
        #[arg(long = "server")]
        servers: Vec<String>,
    },
}

fn zec(zat: u64) -> String {
    format!("{}.{:08}", zat / 100_000_000, zat % 100_000_000)
}

fn zec_short(zat: u64) -> String {
    let v = zat as f64 / 1e8;
    if v >= 1e6 {
        format!("{:.3}M", v / 1e6)
    } else if v >= 1e3 {
        format!("{:.1}k", v / 1e3)
    } else {
        format!("{v:.2}")
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.cmd {
        Cmd::Info { servers } => {
            let servers = if servers.is_empty() { DEFAULT_SERVERS.iter().map(|s| s.to_string()).collect() } else { servers };
            for s in servers {
                match net::connect(&s).await {
                    Ok(mut c) => match net::info(&mut c).await {
                        Ok(i) => println!(
                            "{s}: {} {} chain={} height={} protocol={}",
                            i.vendor, i.version, i.chain_name, i.block_height, i.lightwallet_protocol_version
                        ),
                        Err(e) => println!("{s}: error {e:#}"),
                    },
                    Err(e) => println!("{s}: error {e:#}"),
                }
            }
            Ok(())
        }
        Cmd::Check { addresses, server } => check(addresses, server).await,
        Cmd::Ycash { data, server, fork, top, concurrency } => ycash::run(&data, &server, fork, top, concurrency).await,
        Cmd::Resurvey { data, server, concurrency } => resurvey(&data, &server, concurrency).await,
        Cmd::SaltSweep { data, threads, max_salt_bytes } => {
            let threads = threads.unwrap_or_else(|| std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4));
            tokio::task::spawn_blocking(move || salt::run(&data, threads, max_salt_bytes)).await?
        }
        Cmd::Scan {
            servers,
            end,
            chunk,
            concurrency,
            sample_every,
            out,
            pools_url,
            no_pools,
            no_p2sh_survey,
            no_lookup,
            top,
        } => {
            let servers = if servers.is_empty() { DEFAULT_SERVERS.iter().map(|s| s.to_string()).collect() } else { servers };
            scan(ScanArgs {
                servers,
                end,
                chunk,
                concurrency,
                sample_every,
                out,
                pools_url: if no_pools { None } else { Some(pools_url) },
                p2sh_survey: !no_p2sh_survey,
                lookup: !no_lookup,
                top,
            })
            .await
        }
    }
}

struct ScanArgs {
    servers: Vec<String>,
    end: Option<u64>,
    chunk: u64,
    concurrency: usize,
    sample_every: u32,
    out: PathBuf,
    pools_url: Option<String>,
    p2sh_survey: bool,
    lookup: bool,
    top: usize,
}

async fn scan(a: ScanArgs) -> Result<()> {
    let started = Instant::now();
    let mut clients = Vec::new();
    let mut used = Vec::new();
    for s in &a.servers {
        match net::connect(s).await {
            Ok(mut c) => match net::info(&mut c).await {
                Ok(i) => {
                    eprintln!("connected {s}: {} {} height={}", i.vendor, i.version, i.block_height);
                    if i.chain_name != "main" {
                        bail!("{s} serves chain {:?}; Shorline targets mainnet", i.chain_name);
                    }
                    clients.push(c);
                    used.push(s.clone());
                }
                Err(e) => eprintln!("skipping {s}: {e:#}"),
            },
            Err(e) => eprintln!("skipping {s}: {e:#}"),
        }
    }
    if clients.is_empty() {
        bail!("no lightwalletd server reachable");
    }
    let tip = net::tip(&mut clients[0]).await?;
    let end = a.end.unwrap_or(tip).min(tip);
    eprintln!("scanning blocks 0..={end} in chunks of {} with {} parallel downloads", a.chunk, a.concurrency);

    let mut chunks = Vec::new();
    let mut s = 0u64;
    while s <= end {
        let e = (s + a.chunk - 1).min(end);
        chunks.push((s, e));
        s = e + 1;
    }
    let mut engine = Engine::new(a.sample_every);
    let n_chunks = chunks.len();
    let shared = clients.clone();
    let mut stream = futures::stream::iter(chunks.into_iter().enumerate().map(move |(i, (s, e))| {
        let cl = shared.clone();
        tokio::spawn(async move { net::fetch_with_retry(cl, i, s, e).await })
    }))
    .buffered(a.concurrency.max(1));

    let mut done = 0usize;
    let mut last_report = Instant::now();
    while let Some(joined) = stream.next().await {
        let blocks = joined.context("download task panicked")??;
        for b in &blocks {
            engine.process_block(b)?;
        }
        done += 1;
        if last_report.elapsed() > Duration::from_secs(15) || done == n_chunks {
            last_report = Instant::now();
            let h = engine.height.unwrap_or(0);
            let el = started.elapsed().as_secs_f64();
            eprintln!(
                "h={h:>8} ({:5.1}%) {:6.0} blk/s | utxos={} entities={} | exposed={} hidden={} p2sh?={} total={} ZEC | missing={}",
                100.0 * h as f64 / end.max(1) as f64,
                engine.n_blocks as f64 / el,
                engine.utxo_count(),
                engine.addr_count(),
                zec_short(engine.cat_zat[1] + engine.cat_zat[3] + engine.cat_zat[4] + engine.cat_zat[5]),
                zec_short(engine.cat_zat[0]),
                zec_short(engine.cat_zat[2]),
                zec_short(engine.total_zat()),
                engine.missing_prevouts,
            );
        }
    }
    drop(stream);

    // ---- catch up to the pools source and cross-check -------------------------
    let mut pools_snapshot = None;
    let mut cross = None;
    if let Some(url) = &a.pools_url {
        for attempt in 0..40 {
            let u = url.clone();
            let p = match tokio::task::spawn_blocking(move || pools::fetch(&u)).await? {
                Ok(p) => p,
                Err(e) => {
                    eprintln!("pools fetch failed ({e:#}); retrying");
                    tokio::time::sleep(Duration::from_secs(10)).await;
                    continue;
                }
            };
            let h = engine.height.unwrap_or(0);
            if p.height == h {
                let ours = engine.total_zat();
                let theirs = p.get("transparent");
                let c = CrossCheck {
                    height: h,
                    zebra_transparent_zat: theirs,
                    shorline_transparent_zat: ours,
                    difference_zat: ours as i128 - theirs as i128,
                    matches: ours == theirs,
                    node_build: p.node_build.clone(),
                };
                eprintln!(
                    "cross-check @{h}: Zebra transparent pool = {} ZEC, Shorline UTXO set = {} ZEC => {}",
                    zec(theirs),
                    zec(ours),
                    if c.matches { "EXACT MATCH".to_string() } else { format!("MISMATCH by {} zat", c.difference_zat) }
                );
                cross = Some(c);
                pools_snapshot = Some(p);
                break;
            } else if p.height > h {
                let lwd_tip = net::tip(&mut clients[0]).await?;
                if lwd_tip >= p.height as u64 {
                    eprintln!("catching up {}..={} to match the pools source", h + 1, p.height);
                    let blocks = net::fetch_with_retry(clients.clone(), attempt, h as u64 + 1, p.height as u64).await?;
                    for b in &blocks {
                        engine.process_block(b)?;
                    }
                } else {
                    tokio::time::sleep(Duration::from_secs(10)).await;
                }
            } else {
                eprintln!("pools source at {} is behind our tip {h}; waiting", p.height);
                tokio::time::sleep(Duration::from_secs(15)).await;
            }
        }
        if cross.is_none() {
            eprintln!("warning: could not align with the pools source; writing without cross-check");
        }
    }
    engine.push_sample();

    // ---- P2SH redeem-script survey (ZIP 2007 open question) -----------------
    let p2sh = if a.p2sh_survey { Some(p2sh_survey(&engine, &clients).await) } else { None };

    let meta = report::Meta {
        servers: used,
        pools_url: a.pools_url.clone(),
        seconds: started.elapsed().as_secs_f64(),
        top_n: a.top,
        write_lookup: a.lookup,
    };
    report::write_all(&a.out, &engine, pools_snapshot.as_ref(), cross.as_ref(), p2sh.as_ref(), &meta)?;
    eprintln!("wrote dataset to {} in {:.0}s", a.out.display(), meta.seconds);
    Ok(())
}

async fn p2sh_survey(engine: &Engine, clients: &[net::Client]) -> P2shSurvey {
    let mut targets = Vec::new();
    for (id, kind, hash, st) in engine.iter_ids() {
        if kind == Kind::P2sh && st.balance > 0 && st.revealed != NEVER {
            if let Some(r) = engine.p2sh_first_spend.get(&id) {
                targets.push((script::encode_taddr(kind, &hash).unwrap(), st.balance, r.clone()));
            }
        }
    }
    eprintln!("P2SH survey: fetching first-spend transactions for {} funded, revealed t3 addresses", targets.len());
    let n = targets.len();
    let results: Vec<Option<P2shSurveyEntry>> = futures::stream::iter(targets.into_iter().enumerate().map(|(i, (addr, zat, r))| {
        let mut c = clients[i % clients.len()].clone();
        async move {
            for _ in 0..3 {
                match net::get_transaction(&mut c, &r.txid).await {
                    Ok(raw) => {
                        let Ok((_, ins)) = rawtx::parse_inputs(&raw.data) else { return None };
                        let input = ins.get(r.vin_index as usize)?;
                        if input.prevout_txid != r.prevout_txid || input.prevout_index != r.prevout_index {
                            return None;
                        }
                        let pushes = rawtx::pushes(&input.script_sig)?;
                        let redeem = pushes.last()?;
                        return Some(P2shSurveyEntry {
                            address: addr,
                            zat,
                            redeem: classify_redeem_script(redeem),
                            redeem_script: hex::encode(redeem),
                            first_spend_txid: report::display_txid(&r.txid),
                            first_spend_height: r.height,
                        });
                    }
                    Err(_) => tokio::time::sleep(Duration::from_millis(500)).await,
                }
            }
            None
        }
    }))
    .buffer_unordered(8)
    .collect()
    .await;
    let mut entries: Vec<P2shSurveyEntry> = results.into_iter().flatten().collect();
    entries.sort_by(|a, b| b.zat.cmp(&a.zat));
    let classified = entries.len();
    eprintln!("P2SH survey: classified {classified} of {n}");
    P2shSurvey { addresses_with_balance: n, classified, failed: n - classified, entries }
}

/// Live classification of t-addresses: fetches every block containing a
/// transaction that touches the address, rebuilds its outputs, and checks
/// whether any of them has ever been spent (which reveals the public key).
async fn check(addresses: Vec<String>, server: String) -> Result<()> {
    let mut c = net::connect(&server).await?;
    let tip = net::tip(&mut c).await?;
    for addr in addresses {
        let Some((kind, hash)) = script::decode_taddr(&addr) else {
            println!("{addr}: not a mainnet t1/t3 address");
            if addr.starts_with("u1") || addr.starts_with("zs1") {
                println!("  shielded address: on-chain exposure is not observable. If funds are in Sapling/Orchard, migrate them to");
                println!("  Ironwood (ZIP 2005 recoverable). Note a future quantum adversary who knows this address could decrypt");
                println!("  notes sent to it (ZIP 2005 threat model), so avoid publishing long-lived shielded addresses.");
            }
            continue;
        };
        let spk = script::script_for(kind, &hash);

        // Current balance: one call.
        let utxos = c
            .get_address_utxos(rpc::GetAddressUtxosArg { addresses: vec![addr.clone()], start_height: 0, max_entries: 0 })
            .await?
            .into_inner()
            .address_utxos;
        let balance: u64 = utxos.iter().map(|u| u.value_zat.max(0) as u64).sum();

        // Exposure: walk the address's history oldest-first, in windows that
        // can be retried independently, and stop at the first spend (that is
        // the moment its key / script became public).
        let mut outs: HashMap<(Vec<u8>, u32), u64> = HashMap::new();
        let mut first_spend: Option<(u64, Vec<u8>)> = None;
        let mut tx_heights_seen = 0usize;
        // Windows to list, oldest first. A window that keeps failing (the
        // server fetches every raw transaction, which can time out for busy
        // addresses) is split in half and retried.
        let mut pending: Vec<(u64, u64)> = vec![(1, tip)];
        'windows: while let Some((w, wend)) = pending.pop() {
            if wend - w + 1 > 100_000 {
                let mid = w + (wend - w) / 2;
                pending.push((mid + 1, wend));
                pending.push((w, mid));
                continue;
            }
            let filter = rpc::TransparentAddressBlockFilter {
                address: addr.clone(),
                range: Some(rpc::BlockRange {
                    start: Some(rpc::BlockId { height: w, hash: vec![] }),
                    end: Some(rpc::BlockId { height: wend, hash: vec![] }),
                    pool_types: vec![],
                }),
            };
            let mut heights = BTreeSet::new();
            let mut ok = false;
            for attempt in 0..2 {
                heights.clear();
                let res: Result<()> = async {
                    let resp = match c.get_taddress_transactions(filter.clone()).await {
                        Ok(r) => r,
                        Err(_) => c.get_taddress_txids(filter.clone()).await?,
                    };
                    let mut stream = resp.into_inner();
                    while let Some(t) = stream.message().await? {
                        heights.insert(t.height);
                    }
                    Ok(())
                }
                .await;
                match res {
                    Ok(()) => {
                        ok = true;
                        break;
                    }
                    Err(e) => {
                        eprintln!("  (blocks {w}-{wend}: {e}; retrying)");
                        tokio::time::sleep(Duration::from_secs(2 << attempt)).await;
                    }
                }
            }
            if !ok {
                if wend - w + 1 <= 500 {
                    bail!("could not list transactions for {addr} in blocks {w}-{wend}");
                }
                let mid = w + (wend - w) / 2;
                pending.push((mid + 1, wend));
                pending.push((w, mid));
                continue;
            }
            tx_heights_seen += heights.len();
            for &h in &heights {
                let b = c.get_block(rpc::BlockId { height: h, hash: vec![] }).await?.into_inner();
                for tx in &b.vtx {
                    for vin in &tx.vin {
                        if outs.remove(&(vin.prevout_txid.clone(), vin.prevout_index)).is_some() {
                            first_spend = Some((h, tx.txid.clone()));
                            break 'windows;
                        }
                    }
                    for (i, o) in tx.vout.iter().enumerate() {
                        if o.script_pub_key == spk {
                            outs.insert((tx.txid.clone(), i as u32), o.value);
                        }
                    }
                }
            }
        }
        let kind_s = if kind == Kind::P2pkh { "P2PKH (t1)" } else { "P2SH (t3)" };
        println!("{addr}");
        println!("  type:     {kind_s}");
        println!("  balance:  {} ZEC in {} UTXOs", zec(balance), utxos.len());
        if first_spend.is_none() {
            println!("  history:  {tx_heights_seen} blocks with activity, no spend from this address");
        }
        match first_spend {
            Some((h, by)) => {
                let mut id = [0u8; 32];
                id.copy_from_slice(&by[..32]);
                println!("  status:   EXPOSED: {} revealed at height {h} by tx {}", if kind == Kind::P2pkh { "public key" } else { "redeem script" }, report::display_txid(&id));
                if balance > 0 {
                    println!("  risk:     a discrete-log-breaking (quantum) adversary can derive the key and forge spends of these funds.");
                    println!("  action:   move funds to a fresh Ironwood shielded address (ZIP 2005 recoverable) and never reuse this address.");
                } else {
                    println!("  risk:     nothing at stake right now, but anything sent to this address is exposed on arrival.");
                    println!("  action:   never receive funds at this address again.");
                }
            }
            None if kind == Kind::P2pkh => {
                println!("  status:   HASH-PROTECTED: public key never revealed on-chain.");
                println!("  risk:     safe from Shor's algorithm until spent; spending reveals the key. Recoverable after Q-day only if");
                println!("            ZIP 2007's transparent recovery circuit is deployed.");
                println!("  action:   migrate to Ironwood in one sweep; do not leave change at this address.");
            }
            None => {
                println!("  status:   UNKNOWN: redeem script never revealed, so it cannot be classified from public data.");
                println!("  action:   if this is a multisig, migrate to a FROST multisig in the Ironwood pool.");
            }
        }
    }
    Ok(())
}

/// Re-fetches each surveyed P2SH address's first-spend transaction, finds the
/// input whose last scriptSig push hashes to the address, and re-classifies it.
async fn resurvey(data: &std::path::Path, server: &str, concurrency: usize) -> Result<()> {
    let path = data.join("p2sh_survey.json");
    let old: P2shSurvey = serde_json::from_str(&std::fs::read_to_string(&path)?)?;
    let client = net::connect(server).await?;
    let n = old.entries.len();
    eprintln!("resurvey: re-fetching {n} first-spend transactions");
    let results: Vec<Option<P2shSurveyEntry>> = futures::stream::iter(old.entries.into_iter().map(|e| {
        let mut c = client.clone();
        async move {
            let (_, hash) = script::decode_taddr(&e.address)?;
            let mut txid: [u8; 32] = hex::decode(&e.first_spend_txid).ok()?.try_into().ok()?;
            txid.reverse();
            for _ in 0..4 {
                match net::get_transaction(&mut c, &txid).await {
                    Ok(raw) => {
                        let (_, ins) = rawtx::parse_inputs(&raw.data).ok()?;
                        for i in ins {
                            let Some(p) = rawtx::pushes(&i.script_sig) else { continue };
                            let Some(rs) = p.last() else { continue };
                            if script::hash160(rs) == hash {
                                return Some(P2shSurveyEntry { redeem: classify_redeem_script(rs), redeem_script: hex::encode(rs), ..e });
                            }
                        }
                        return None;
                    }
                    Err(_) => tokio::time::sleep(Duration::from_millis(700)).await,
                }
            }
            None
        }
    }))
    .buffer_unordered(concurrency.max(1))
    .collect()
    .await;
    let mut entries: Vec<P2shSurveyEntry> = results.into_iter().flatten().collect();
    entries.sort_by(|a, b| b.zat.cmp(&a.zat));
    let classified = entries.len();
    let survey = P2shSurvey { addresses_with_balance: old.addresses_with_balance, classified, failed: old.addresses_with_balance - classified, entries };
    std::fs::write(&path, serde_json::to_string_pretty(&survey)?)?;
    let sp = data.join("summary.json");
    let mut summary: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&sp)?)?;
    summary["p2sh_survey"] = report::p2sh_summary(&survey);
    std::fs::write(&sp, serde_json::to_string_pretty(&summary)?)?;
    eprintln!("resurvey: classified {classified} of {}", survey.addresses_with_balance);
    for t in summary["p2sh_survey"]["by_redeem_type"].as_array().into_iter().flatten() {
        eprintln!("  {:<28} {:>6} addresses {:>16} ZEC", t["type"].as_str().unwrap_or(""), t["addresses"], zec(t["zat"].as_u64().unwrap_or(0)));
    }
    Ok(())
}
