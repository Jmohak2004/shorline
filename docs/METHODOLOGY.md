# Shorline methodology

This document specifies exactly what Shorline measures, how, and where its numbers stop being exact. It is written to be checked: every rule below is implemented in [`src/engine.rs`](../src/engine.rs) and [`src/script.rs`](../src/script.rs) and covered by unit tests.

## 1. The question

[ZIP 2005](https://zips.z.cash/zip-2005) (Ironwood quantum recoverability, Final) describes what an adversary able to compute discrete logarithms could do to each part of Zcash. That includes a cryptographically relevant quantum computer running Shor's algorithm. The discussion for [ZIP 2007](https://zips.z.cash/zip-2007) (quantum recoverability for a subset of transparent addresses, [zcash/zips#1302](https://github.com/zcash/zips/issues/1302)) lists as a next step:

> Survey the chain to see what proportion of funds are currently recoverable and in each category. This includes Ironwood funds if Ironwood has already activated. Note that funds held in P2SH addresses can't be definitively classified as recoverable based on public information. (They can be classified as *non*-recoverable if the corresponding script has been seen.)

Shorline performs that survey and publishes it as a reproducible dataset.

## 2. Data sources

| Data | Source | How |
|---|---|---|
| Every transparent input and output, genesis to tip | Public `lightwalletd` (zec.rocks, ECC lightwalletd v0.6.1) | `GetBlockRange` with `poolTypes = [TRANSPARENT]`. Each `CompactTx` carries `vin` (prevout txid and index) and `vout` (value and scriptPubKey). |
| Shielded and lockbox balances; cross-check value | Zebra 7.0.0 `getblockchaininfo` via `mainnet.zcashexplorer.app/api/v1/blockchain-info` | `valuePools[].chainValueZat` for transparent, sprout, sapling, orchard, ironwood and lockbox. |
| P2SH redeem scripts | lightwalletd `GetTransaction` | The full transaction of the first spend of each funded, revealed `t3` address. |

Nothing is written to disk during the scan. The full history is about 8 GB on the wire and is processed as a stream.

Downloads run in parallel chunks (default 2,000 blocks, 8 in flight across four regional servers) and are re-ordered before processing. Each chunk must return exactly the requested heights. Across chunk boundaries, each block's `prevHash` must equal the previous block's hash, so a gap, duplicate, or fork switch aborts the run instead of corrupting the result.

## 3. The replay engine

The engine processes blocks strictly in order and transactions in block order. Within a transaction it processes inputs before outputs.

**UTXO set.** Keyed by `(first 12 bytes of txid, output index)`. With about 191M transparent outputs ever created, the collision probability of a 96-bit key is below 10⁻¹². The value is `(entity id, zatoshis)`.

**Entities.** One per distinct script owner: `(kind, Hash160)`. Kinds:

| Kind | Script | Owner hash |
|---|---|---|
| P2PKH (`t1`) | `OP_DUP OP_HASH160 <20> OP_EQUALVERIFY OP_CHECKSIG` | pubkey hash |
| P2SH (`t3`) | `OP_HASH160 <20> OP_EQUAL` | script hash |
| P2PK | `<33 or 65-byte key> OP_CHECKSIG` | Hash160(key) |
| Bare multisig | `OP_m <keys…> OP_n OP_CHECKMULTISIG` | Hash160(script) |
| Null data | `OP_RETURN …` (only if it carries value) | none |
| Non-standard | anything else | Hash160(script) |

Each entity tracks: balance, live UTXO count, first-seen height, last-activity height, total received, value received *after* its key was revealed, and **`revealed`**, the height at which its key material first became public.

### 3.1 When does a key become public?

1. **Spend.** Spending a P2PKH output puts the public key in the scriptSig. Spending a P2SH output puts the redeem script there, and with it any public keys the script contains. The first time an input consumes an output belonging to a P2PKH or P2SH entity, that entity's `revealed` is set to the current height. Everything still held there is reclassified from hidden to exposed, and so is everything it receives later. This is exactly ZIP 2005's condition: *"provided that the public key has been revealed (i.e. if the address has been spent from previously …)"*.
2. **Key in an output.** A P2PK output or a top-level multisig output publishes public keys directly. For each such key, Shorline marks the P2PKH address for that key as revealed, **in both SEC1 encodings**. A quantum adversary who learns the curve point can derive both the compressed and uncompressed forms, and Hash160 commits to one encoding. The point is decompressed with `k256` to compute both hashes.
3. P2PK and bare-multisig entities are exposed from the moment they exist.

### 3.2 Categories

| Category id | Meaning | ZIP 2007 status |
|---|---|---|
| `p2pkh_hidden` | t1, key never revealed on-chain | recoverable *in principle*; needs the ZIP 2007 circuit |
| `p2pkh_exposed` | t1, key revealed | not recoverable |
| `p2sh_unseen` | t3, script never revealed | unknown from public data |
| `p2sh_seen` | t3, script revealed | not recoverable |
| `p2pk` | key in output | out of scope (no t-address); exposed |
| `bare_multisig` | keys in output | out of scope; exposed |
| `nulldata` | OP_RETURN carrying value | unspendable |
| `nonstandard` | anything else | other |

Category totals are maintained incrementally. Every output creation, spend and reveal moves zatoshis between categories, so the time series costs nothing extra to compute.

### 3.3 Supply-level fates (the dashboard)

| Fate | Composition | Basis |
|---|---|---|
| Exposed | `p2pkh_exposed + p2sh_seen + p2pk + bare_multisig` | ZIP 2005 threat model: ECDSA spends can be forged once the key is revealed |
| Hash-protected | `p2pkh_hidden` | protected by Hash160 until spent; recoverable only if ZIP 2007 ships |
| Unknown P2SH | `p2sh_unseen` | #1302: "can't be definitively classified" |
| Stranded | Zebra `sprout + sapling + orchard` | ZIP 2005: "inaccessible after their respective protocols are disabled" |
| Lockbox | Zebra `lockbox` | consensus-held; released only by a network upgrade |
| Recoverable | Zebra `ironwood` | ZIP 2005: every Ironwood-pool note is recoverable |

## 4. Verification

Once the stream reaches the tip, Shorline polls the Zebra endpoint and processes further blocks until both report the same height. It then compares:

```
Σ (all live UTXOs in Shorline's replay)  ==  Zebra valuePools["transparent"].chainValueZat
```

This is a strong end-to-end check. Every block, every input resolution, and every output value must be right for the totals to agree to the zatoshi. Any missed block, duplicated block, or mis-keyed outpoint shows up as a difference. The result is published in `summary.json → cross_check`. The engine also counts `missing_prevouts`, the number of inputs whose outpoint was not in the UTXO set, which must be 0.

## 5. The P2SH redeem-script survey

For each `t3` address that currently holds funds and has a revealed script, Shorline records where it was first spent: txid, input index, and the prevout it consumed. After the scan it fetches that transaction and parses its transparent inputs, supporting tx versions 1–2, 3–4 (Overwinter/Sapling), 5 (ZIP 225) and 6 (ZIP 229). It checks that the input really spends the recorded prevout, splits the push-only scriptSig, and classifies the last push (the redeem script) as `m-of-n` multisig, P2SH-wrapped P2PKH, P2SH-wrapped P2PK, or other. This answers #1302's open question: *"Are P2SH-wrapped P2PKH or P2SH-wrapped P2PK actually used at all?"*

### 5.1 Salt sweep (`shorline salt-sweep`)

The survey turned up a custody template that derives many P2SH addresses from **one** key set:

```
OP_2 <k1> <k2> <k3> OP_3 OP_CHECKMULTISIGVERIFY <4-byte salt> OP_DROP OP_DEPTH OP_0 OP_EQUAL
```

Once any address in such a family is spent, its keys and template are public. Every other address in the family is then exposed in practice: an adversary only has to enumerate the salt to rebuild its redeem script. Shorline groups revealed salted scripts by template (the script with the salt zeroed). For each template it hashes **every** salt value (2³² for 4 bytes) and matches the Hash160 against every funded P2SH address.

The first 64-byte SHA-256 block is constant, so its midstate is computed once. Each candidate then costs one SHA-256 compression plus one RIPEMD-160. A 2²⁴-bit prefix bitmap rejects nearly all non-matches before the hash-set lookup. All 4,294,967,296 salts take about 280 s on 10 cores. **Self-check:** the sweep must rediscover the template's own revealed addresses, and on the reference run it rediscovered 39 of 39.

### 5.2 Ycash cross-check (`shorline ycash`)

Ycash forked from Zcash at height **570,000**. That was verified by comparing block hashes: both chains agree through 569,999 and differ from 570,000. Every Zcash address funded before the fork therefore held the same coins on Ycash under the same keys.

For each Zcash address that is still hash-protected or unseen P2SH and was funded before the fork, Shorline:
1. re-encodes it with Ycash's prefixes (`s1` = `0x1C28`, `s3` = `0x1C2D`, found by exhaustive search and confirmed against the live server);
2. lists its post-fork Ycash transactions (`GetTaddressTxids`, `lite.ycash.xyz`);
3. parses every input and checks whether the scriptSig's last push is a public key (or redeem script) whose Hash160 equals the address hash.

A match is cryptographic proof that the key guarding the ZEC is public. The reference run checked the 10,000 largest of 146,632 candidates, covering 355,512 of 389,129 ZEC. 12 queries failed and are reported in `ycash_exposure.json`.

## 6. Published dataset (`web/data/`)

| File | Contents |
|---|---|
| `summary.json` | chain tip, scan statistics, category totals with UTXO and funded-address counts, Zebra pools, cross-check, supply fates, exposure by reveal year, dormancy, address-reuse flows, P2SH survey summary |
| `timeseries.json` | category totals every 1,000 blocks: `[height, time, 8 × category zatoshis, cumulative zatoshis sent to already-exposed addresses]` |
| `top.json` | top 100 funded entities per category |
| `p2sh_survey.json` | every classified funded P2SH address with its redeem script, type and first-spend txid |
| `salted_exposure.json` | salted templates (keys, salt size), self-check counts, and the never-spent addresses matched by the sweep |
| `ycash_exposure.json` | pre-fork addresses whose keys were revealed on Ycash, with the Ycash height and txid as proof |
| `lookup/<t1|t3>_<nnnn>.json` | address-checker shards (published as a release asset, see the README) |

### Address-checker privacy

Shard `t1_<nnnn>` holds every funded address whose characters 3–4 (after the `t1`/`t3` prefix) map to `nnnn = 58·i + j` in the Base58 alphabet. The browser downloads one shard and searches it locally. The static host learns only a two-character prefix shared by every other funded address in that shard (k-anonymity), never the address itself. Shard names are numeric so they don't collide on case-insensitive filesystems.

## 7. Limits

* **Exposed is a lower bound; hash-protected is an upper bound.** Keys can leak off-chain or on other chains, and none of that is visible here. Examples:
  * shared extended public keys
  * `signmessage` signatures
  * the same key used on Bitcoin (a `t1` address and a Bitcoin `1…` address with the same Hash160 share a key)
  * spends of the same pre-July-2019 coins on the **Ycash** fork (height 570,000), which is partly measured by `shorline ycash` (§5.2)
* Compact transaction data has no scriptSigs. So when a *P2PKH* output is spent, Shorline cannot see which pubkey encoding was used, and does not mark the other encoding's address as exposed. A pubkey revealed inside a P2SH multisig spend is likewise not linked to a P2PKH address with the same key. Both cases make the exposed figure smaller, never larger.
* Shielded **privacy** under a quantum adversary is a separate risk. A known shielded address lets the adversary find `ivk` and decrypt notes sent to it. That depends on which addresses were ever published, so it is out of scope.
* Mempool-window attacks are out of scope: revealing a key in a broadcast transaction and racing it before confirmation.
* None of this predicts when, or whether, a cryptographically relevant quantum computer will exist.

## 8. Performance (reference run)

The reference machine is a MacBook (10 cores, 16 GB RAM, ~4 GB free disk). Wall-clock time is network-bound. Peak live UTXO count, RSS and timings are reported in `summary.json → scan` and in the README.
