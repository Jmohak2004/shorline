# FAQ

**Does "exposed" mean my funds will be stolen?**
No. It means the public key (or redeem script) is already on the blockchain, so a *future* quantum computer large
enough to run Shor's algorithm could derive the private key. No such machine exists today. Moving the funds to Ironwood
removes the exposure.

**Why is a never-spent `t1` address "hash-protected"?**
Its public key is hidden behind Hash160. Shor's algorithm does not break hash preimages, so the key stays safe until
you spend. Spending reveals it, so change left behind becomes exposed.

**Why is "exposed" a lower bound?**
Keys also leak off-chain (shared xpubs, signed messages, the same key on another chain). Shorline only sees what the
chain shows, plus the Ycash fork, which it checks explicitly.

**Why do the six fates add up to 17.05M ZEC and not 21M?**
They cover supply issued at the snapshot height (block 3,583,892), not the eventual cap.

**Can I trust the totals?**
The replayed transparent set equals Zebra's `valuePools` transparent total to the zatoshi, and
`scripts/verify_dataset.py` checks 32 internal invariants. Reproduce with `cargo run --release -- scan`.

**Does the dashboard learn my address?**
No. The browser downloads a shard shared by hundreds of funded addresses and searches it locally. See
[SECURITY.md](../SECURITY.md). The `shorline check` CLI, by contrast, asks a public lightwalletd directly.

**Why does a gross-flow number like "63M ZEC sent to exposed addresses" exceed the supply?**
It counts every payment, so coins cycling through reused hot wallets are counted on each pass. It measures
behaviour, not balances.

**Does this say anything about shielded privacy?**
No. A quantum adversary decrypting notes sent to a known shielded address is a separate risk and is not measured.

**How do I refresh the data?**
Run `scan --out web/data`, then `python3 scripts/findings.py && python3 scripts/circuit_sizing.py`, attach the lookup
shards to a `data-<height>` release, and re-run the Pages workflow. See the [README](../README.md#run-it-yourself).
