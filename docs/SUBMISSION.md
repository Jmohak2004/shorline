# Submission: ZcashIND *Build on Zcash*

**Project:** Shorline, a verifiable chain-wide quantum-exposure survey of Zcash
**Categories:** Infrastructure, Education and Adoption
**Repo (MIT):** https://github.com/Jmohak2004/shorline
**Live dashboard:** https://jmohak2004.github.io/shorline/
**Explainer video (4:35):** [docs/video/shorline-explainer.mp4](video/shorline-explainer.mp4)

## One paragraph

ZIP 2005 shipped a post-quantum recovery path for the Ironwood pool, and ZIP 2007 asks which *transparent* funds
could be recovered the same way. Its discussion ([zcash/zips#1302](https://github.com/zcash/zips/issues/1302))
names the first step: *survey the chain and see what proportion of funds are in each category.* Shorline is that
survey. It replays all 3.58M blocks, rebuilds the transparent UTXO set, records when every address's public key
first appeared on-chain, and assigns every one of 17.05M ZEC to a fate. It matches Zebra's transparent value pool
**to the zatoshi**.

## What a judge can verify in five minutes

| Claim | How to check it |
|---|---|
| The numbers are exact | Dashboard section *Verified to the zatoshi*, or `web/data/summary.json` → `cross_check` (`difference_zat: 0`) |
| The dataset is self-consistent | `python3 scripts/verify_dataset.py` (32 checks, runs in CI) |
| The code builds and passes | `cargo test --release` (14 tests), `cargo clippy -- -D warnings`, `cargo fmt --check` |
| The survey is reproducible | `cargo run --release -- scan --end 60000` (about one minute), or the full scan in about an hour |
| Any address can be checked live | `cargo run --release -- check t1gsBrGZGMyDGZw2icGnMpVBuEGVWip5kH8` |
| The address checker is private | Open the dashboard network tab: one shard file is fetched, never the address |
| Docs match the data | CI regenerates README, FINDINGS and CIRCUIT_SIZING and fails on any diff |

## Headline results (block 3,583,892)

* **7.24M ZEC (42.5% of supply) is exposed**: its public key is already on-chain.
* **4.37M ZEC (25.6%) is hash-protected**: recoverable only if a ZIP 2007 circuit ships.
* **0.75M ZEC (4.4%) is stranded** in Sprout, Sapling and Orchard, against 4.18M ZEC already in Ironwood.
* **Exposure is accelerating:** 78.9% of exposed value had its key revealed in 2025 to 2026.
* **4,181 ZEC looks safe on Zcash but its keys leaked through the 2019 Ycash fork.**
* **Salted multisig families can be broken:** hashing all 2³² salts found 9 more exposed addresses (168.88 ZEC) in a custodian's family.

## What is new compared with a block explorer

1. **Key-reveal tracking.** Exposure is a property of *history* (has this address ever been spent from?), not of the current UTXO set.
2. **Supply-level fates.** Transparent and shielded value are put on one scale, per ZIP 2005 and ZIP 2007.
3. **Self-verification.** The replay is checked against an independent node, so the numbers are not trust-me.
4. **Cross-chain and brute-force analyses.** Ycash key leaks and the salted-multisig sweep find exposure the chain alone does not show.
5. **Actionable for users.** A private address checker, a live CLI check and NFC tap-to-check, with plain guidance on what to do next.

## Requirement mapping

| Bounty theme | Delivered |
|---|---|
| Infrastructure | A reproducible Rust survey engine, a published JSON dataset with a documented schema, CI with smoke tests against live lightwalletd, a Pages-deployed dashboard |
| Education | A 4:35 explainer video defining every term, a dashboard that explains each result, a methodology document and a ZIP 2007 circuit-sizing note |
| Adoption | A privacy-preserving address checker, NFC tap-to-check, and per-audience guidance (holders, treasuries, exchanges) |

## Honest limits

*Exposed* is a lower bound and *hash-protected* an upper bound. Unseen P2SH addresses cannot be classified.
Shielded-note privacy against a quantum adversary is not measured. Nothing here predicts when a cryptographically
relevant quantum computer will exist. See [METHODOLOGY §7](METHODOLOGY.md#7-limits).

## Not done (stated rather than hidden)

Bitcoin key-reuse cross-check, a UFVK wallet mode, and incremental daily refresh are on the
[roadmap](../README.md#roadmap). They are not part of this submission.
