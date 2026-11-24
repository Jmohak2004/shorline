//! Minimal parser for the transparent inputs of a raw Zcash transaction
//! (v1–v6). Only what is needed to read a P2SH input's redeem script.

use anyhow::{bail, ensure, Result};

pub struct TxIn {
    pub prevout_txid: [u8; 32],
    pub prevout_index: u32,
    pub script_sig: Vec<u8>,
}

struct Reader<'a> {
    b: &'a [u8],
    at: usize,
}

impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8]> {
        ensure!(self.at + n <= self.b.len(), "truncated transaction");
        let s = &self.b[self.at..self.at + n];
        self.at += n;
        Ok(s)
    }
    fn u32(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into()?))
    }
    fn compact_size(&mut self) -> Result<u64> {
        let first = self.take(1)?[0];
        Ok(match first {
            0xfd => u16::from_le_bytes(self.take(2)?.try_into()?) as u64,
            0xfe => u32::from_le_bytes(self.take(4)?.try_into()?) as u64,
            0xff => u64::from_le_bytes(self.take(8)?.try_into()?),
            n => n as u64,
        })
    }
}

/// Parses the transparent inputs. Layouts:
/// * v1/v2: header, tx_in…
/// * v3/v4 (Overwinter/Sapling): header, nVersionGroupId, tx_in…
/// * v5 (ZIP 225) and v6 (ZIP 229): header, nVersionGroupId,
///   nConsensusBranchId, lock_time, nExpiryHeight, tx_in…
pub fn parse_inputs(raw: &[u8]) -> Result<(u32, Vec<TxIn>)> {
    let mut r = Reader { b: raw, at: 0 };
    let header = r.u32()?;
    let overwintered = header >> 31 == 1;
    let version = header & 0x7fff_ffff;
    if overwintered {
        r.u32()?; // nVersionGroupId
        match version {
            3 | 4 => {}
            5 | 6 => {
                r.u32()?; // nConsensusBranchId
                r.u32()?; // lock_time
                r.u32()?; // nExpiryHeight
            }
            v => bail!("unsupported transaction version {v}"),
        }
    } else {
        ensure!(
            version == 1 || version == 2,
            "unsupported pre-Overwinter version {version}"
        );
    }
    let n = r.compact_size()?;
    ensure!(n < 100_000, "implausible input count {n}");
    let mut ins = Vec::with_capacity(n as usize);
    for _ in 0..n {
        let mut prevout_txid = [0u8; 32];
        prevout_txid.copy_from_slice(r.take(32)?);
        let prevout_index = r.u32()?;
        let len = r.compact_size()? as usize;
        let script_sig = r.take(len)?.to_vec();
        r.u32()?; // nSequence
        ins.push(TxIn {
            prevout_txid,
            prevout_index,
            script_sig,
        });
    }
    Ok((version, ins))
}

/// Splits a scriptSig into its data pushes. Returns None if it contains a
/// non-push opcode (a standard P2SH scriptSig is push-only).
pub fn pushes(script: &[u8]) -> Option<Vec<Vec<u8>>> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < script.len() {
        let op = script[i];
        i += 1;
        let len = match op {
            0x00 => {
                out.push(vec![]);
                continue;
            }
            0x01..=0x4b => op as usize,
            0x4c => {
                let l = *script.get(i)? as usize;
                i += 1;
                l
            }
            0x4d => {
                let l = u16::from_le_bytes(script.get(i..i + 2)?.try_into().ok()?) as usize;
                i += 2;
                l
            }
            0x4e => {
                let l = u32::from_le_bytes(script.get(i..i + 4)?.try_into().ok()?) as usize;
                i += 4;
                l
            }
            0x4f | 0x51..=0x60 => {
                out.push(vec![op]);
                continue;
            }
            _ => return None,
        };
        out.push(script.get(i..i + len)?.to_vec());
        i += len;
    }
    Some(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_v4_inputs() {
        // header (v4 overwintered), group id, 1 input, prevout, scriptSig "51", sequence.
        let mut raw = vec![];
        raw.extend_from_slice(&(0x8000_0004u32).to_le_bytes());
        raw.extend_from_slice(&0x892F_2085u32.to_le_bytes());
        raw.push(1);
        raw.extend_from_slice(&[0xab; 32]);
        raw.extend_from_slice(&3u32.to_le_bytes());
        raw.push(1);
        raw.push(0x51);
        raw.extend_from_slice(&0xffff_ffffu32.to_le_bytes());
        let (v, ins) = parse_inputs(&raw).unwrap();
        assert_eq!(v, 4);
        assert_eq!(ins.len(), 1);
        assert_eq!(ins[0].prevout_index, 3);
        assert_eq!(ins[0].script_sig, vec![0x51]);
    }

    #[test]
    fn splits_pushes() {
        let s = [0x00, 0x02, 0xaa, 0xbb, 0x4c, 0x01, 0xcc];
        assert_eq!(
            pushes(&s).unwrap(),
            vec![vec![], vec![0xaa, 0xbb], vec![0xcc]]
        );
        assert!(pushes(&[0xac]).is_none());
    }
}
