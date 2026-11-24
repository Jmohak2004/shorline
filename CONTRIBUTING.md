# Contributing

Thanks for helping. Shorline is a measurement tool, so correctness comes first.

## Setup

```bash
git clone https://github.com/Jmohak2004/shorline && cd shorline
cargo test --release
```

Rust 1.80+ is required. No `protoc` and no full node are needed.

## Before you open a pull request

```bash
cargo fmt
cargo clippy --release --all-targets -- -D warnings
cargo test --release
python3 scripts/verify_dataset.py   # dataset invariants
python3 scripts/check_links.py      # relative links in the docs
```

CI runs the same checks.

## Rules of the road

* **Never hand-edit generated files.** `README.md` (between the `FINDINGS` markers), `docs/FINDINGS.md` and
  `docs/CIRCUIT_SIZING.md` come from `scripts/findings.py` and `scripts/circuit_sizing.py`. CI fails if they are stale.
* **Any change to classification logic needs a test** in the module it touches (`engine.rs`, `script.rs`, `rawtx.rs`).
* **A change that moves a published number needs a re-scan.** Re-run `scan`, then the generators, and say so in the PR.
* **Keep the address checker private.** The browser must only ever fetch a shard shared by many addresses.
  Nothing that identifies the checked address may leave the page.
* Keep the dashboard dependency-free (plain HTML, CSS and JS).

## Reporting a problem

Open an issue with the template. For anything that could mislead people about their funds, say so in the title.
