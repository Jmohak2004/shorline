//! Chain value pools, as reported by a Zebra node's `getblockchaininfo`
//! (`valuePools`). Used for the shielded-pool snapshot and to cross-check
//! the reconstructed transparent UTXO set to the zatoshi.

use anyhow::{Context, Result};
use serde::Serialize;
use std::collections::BTreeMap;

pub const DEFAULT_POOLS_URL: &str = "https://mainnet.zcashexplorer.app/api/v1/blockchain-info";

#[derive(Clone, Debug, Serialize)]
pub struct Pools {
    pub height: u32,
    pub best_block_hash: String,
    pub node_build: String,
    /// Zatoshis per pool id ("transparent", "sprout", "sapling", "orchard", "ironwood", "lockbox", …).
    pub zat: BTreeMap<String, u64>,
}

impl Pools {
    pub fn get(&self, id: &str) -> u64 {
        self.zat.get(id).copied().unwrap_or(0)
    }
}

pub fn fetch(url: &str) -> Result<Pools> {
    let v: serde_json::Value = ureq::get(url)
        .set(
            "User-Agent",
            concat!("shorline/", env!("CARGO_PKG_VERSION")),
        )
        .timeout(std::time::Duration::from_secs(30))
        .call()
        .with_context(|| format!("GET {url}"))?
        .into_json()?;
    let height = v["blocks"].as_u64().context("missing `blocks`")? as u32;
    let mut zat = BTreeMap::new();
    for p in v["valuePools"].as_array().context("missing `valuePools`")? {
        let id = p["id"].as_str().context("pool without id")?.to_string();
        let z = p["chainValueZat"]
            .as_u64()
            .context("pool without chainValueZat")?;
        zat.insert(id, z);
    }
    Ok(Pools {
        height,
        best_block_hash: v["bestblockhash"].as_str().unwrap_or_default().to_string(),
        node_build: v["build"].as_str().unwrap_or_default().to_string(),
        zat,
    })
}
