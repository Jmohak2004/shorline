//! lightwalletd gRPC access: parallel, order-preserving chunked block
//! download with retries and server rotation.

use crate::rpc::compact_tx_streamer_client::CompactTxStreamerClient;
use crate::rpc::{BlockId, BlockRange, ChainSpec, CompactBlock, Empty, LightdInfo, PoolType, RawTransaction, TxFilter};
use anyhow::{anyhow, Context, Result};
use std::time::Duration;
use tonic::transport::{Channel, ClientTlsConfig};

pub type Client = CompactTxStreamerClient<Channel>;

pub async fn connect(url: &str) -> Result<Client> {
    let mut ep = Channel::from_shared(url.to_string())
        .with_context(|| format!("invalid server URL {url}"))?
        .connect_timeout(Duration::from_secs(20))
        .timeout(Duration::from_secs(900))
        .http2_keep_alive_interval(Duration::from_secs(30))
        .keep_alive_while_idle(true);
    if url.starts_with("https://") {
        ep = ep.tls_config(ClientTlsConfig::new().with_webpki_roots())?;
    }
    let ch = ep.connect().await.with_context(|| format!("connecting to {url}"))?;
    Ok(CompactTxStreamerClient::new(ch).max_decoding_message_size(256 << 20))
}

pub async fn info(c: &mut Client) -> Result<LightdInfo> {
    Ok(c.get_lightd_info(Empty {}).await?.into_inner())
}

pub async fn tip(c: &mut Client) -> Result<u64> {
    Ok(c.get_latest_block(ChainSpec {}).await?.into_inner().height)
}

/// Fetches blocks `[start, end]` with transparent data, verifying that
/// exactly the requested heights come back in order.
pub async fn fetch_range(c: &mut Client, start: u64, end: u64) -> Result<Vec<CompactBlock>> {
    let req = BlockRange {
        start: Some(BlockId { height: start, hash: vec![] }),
        end: Some(BlockId { height: end, hash: vec![] }),
        pool_types: vec![PoolType::Transparent as i32],
    };
    let mut stream = c.get_block_range(req).await?.into_inner();
    let mut out = Vec::with_capacity((end - start + 1) as usize);
    while let Some(b) = stream.message().await? {
        let want = start + out.len() as u64;
        if b.height != want {
            return Err(anyhow!("server returned height {} where {} was expected", b.height, want));
        }
        out.push(b);
    }
    if out.len() as u64 != end - start + 1 {
        return Err(anyhow!("short range: got {} of {} blocks from {start}", out.len(), end - start + 1));
    }
    Ok(out)
}

/// Fetches a chunk, rotating over servers with exponential backoff.
pub async fn fetch_with_retry(clients: Vec<Client>, first: usize, start: u64, end: u64) -> Result<Vec<CompactBlock>> {
    let mut last_err = None;
    for attempt in 0..12u32 {
        let idx = (first + attempt as usize) % clients.len();
        let mut c = clients[idx].clone();
        match fetch_range(&mut c, start, end).await {
            Ok(v) => return Ok(v),
            Err(e) => {
                eprintln!("  ! chunk {start}-{end} attempt {} on server #{idx} failed: {e:#}", attempt + 1);
                last_err = Some(e);
                tokio::time::sleep(Duration::from_millis(500 * 2u64.pow(attempt.min(6)))).await;
            }
        }
    }
    Err(last_err.unwrap_or_else(|| anyhow!("unreachable")))
}

/// Fetches a full transaction by txid (protocol byte order).
pub async fn get_transaction(c: &mut Client, txid: &[u8; 32]) -> Result<RawTransaction> {
    let req = TxFilter { block: None, index: 0, hash: txid.to_vec() };
    Ok(c.get_transaction(req).await?.into_inner())
}
