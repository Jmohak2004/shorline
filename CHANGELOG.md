# Changelog

## 0.1.0 (submission)

### Survey
* Chain-wide replay of the transparent UTXO set with per-address key-reveal tracking, verified to the zatoshi against Zebra.
* Supply-level fates (exposed, hash-protected, unknown P2SH, stranded, lockbox, recoverable) per ZIP 2005 and ZIP 2007.
* P2SH redeem-script survey, salted-multisig sweep over all 2³² salts, and the Ycash fork cross-check.

### Dashboard
* Hand-built SVG charts, private address checker (t1, t3, ZIP 320 `tex1`), NFC tap-to-check.
* Accessibility pass: skip link, focus styles, reduced motion, no-JS fallback. Print stylesheet.

### Tooling and quality
* `docs/CIRCUIT_SIZING.md` with measured workload for a ZIP 2007 recovery circuit.
* `scripts/verify_dataset.py` (32 invariants) and `scripts/check_links.py`.
* CI: rustfmt, clippy `-D warnings`, tests, live smoke scan, dataset invariants, generated-docs freshness, Node unit tests.
* Address logic extracted to `web/addr.js` with tests pinned to Rust's shard index.
* Explainer video (5:41) with a 66-second live demo of the dashboard checker, `shorline check` and `shorline scan` (sources in `video-src/demo/`), `docs/SUBMISSION.md`, CONTRIBUTING, SECURITY, FAQ.
