# Security and privacy

## Scope

Shorline reads public blockchain data. It never handles keys, seeds or signatures, and it cannot move funds.

## Privacy of the address checker

The dashboard checker downloads one shard covering every funded address that shares a short hash prefix and
searches it locally. The host sees which *shard* was requested, never which address. Deep links and NFC tags carry
the address after the `#`, which browsers do not send to servers. The CLI `check` command contacts a public
lightwalletd server directly and does reveal the queried address to that server.

## Reporting a vulnerability

Please open a private security advisory on GitHub (Security tab → *Report a vulnerability*). Include the version,
what you observed and how to reproduce it. Misclassification bugs that could understate or overstate exposure are
in scope.

## Data integrity

`scripts/verify_dataset.py` checks the published dataset's invariants, and every full scan is cross-checked against
Zebra's value pools. A mismatch is printed as `MISMATCH` in the scan log and recorded in `summary.json`, and CI fails `verify_dataset.py` on it.
