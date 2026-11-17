# Demo video script (about 2.5 minutes)

Record the screen at 1080p with a voice-over. Keep the browser at around 1280 px wide. Use the live dashboard: https://jmohak2004.github.io/shorline/

Numbers marked ⟨…⟩ are on the dashboard. Read them from the page on the day you record, because the dataset can be refreshed.

---

**0:00–0:15 · Hook** (dashboard hero on screen)

> "If a large quantum computer showed up tomorrow, how much Zcash could it take? Nobody had measured it. So I built Shorline, and the answer is ⟨hero number⟩ ZEC, about ⟨x⟩% of all ZEC, sitting behind public keys that are already on the blockchain."

**0:15–0:40 · Why it matters** (scroll to the segmented bar)

> "Zcash is already preparing for this. ZIP 2005 shipped the Ironwood pool in July, which makes shielded funds recoverable after a quantum break. ZIP 2007 asks the same question for transparent funds. Its discussion thread lists one next step: survey the chain and measure how much falls in each category. Shorline is that survey. Every ZEC lands in one of six buckets: exposed, hash-protected, unknown P2SH, stranded in old shielded pools, the lockbox, and recoverable Ironwood."

**0:40–1:05 · How it works** (scroll to "Verified to the zatoshi")

> "It needs no full node and no disk. A Rust engine streams all ⟨3.58 million⟩ blocks from public lightwalletd servers and replays every transparent input and output, ⟨number⟩ of them, to rebuild the UTXO set. It records the moment each address's public key first hits the chain. Then it checks itself: the rebuilt total matches the Zebra node's transparent value pool exactly, to the zatoshi."

**1:05–1:30 · What it found** (history chart, hover the crosshair, then the reveal-year and dormancy charts)

> "This is transparent ZEC over ten years. Red is exposed: every time an address is reused, its key goes public for good. ⟨x⟩ ZEC has had its key public since 2018 or earlier, and ⟨y⟩ exposed ZEC hasn't moved in four years. That's Zcash's version of the Satoshi-coins problem. And it's still growing: ⟨z⟩ ZEC landed on already-exposed addresses in the last 30 days alone."

**1:30–1:50 · The Ycash twist** (Ycash section)

> "Then a cross-chain twist. Ycash forked from Zcash in 2019 and copied everyone's balances, keys included. When people spent their Ycash, they published the same keys that guard their ZEC. Shorline checks this cryptographically. ⟨n⟩ ZEC that looks safe on Zcash is actually exposed through Ycash."

**1:50–2:10 · ZIP 2007 answers + address checker** (ZIP 2007 tables, then type an address into the checker)

> "It also answers the ZIP 2007 thread's open question about which P2SH scripts are actually used. And anyone can check an address. The lookup runs in your browser against a shard shared by hundreds of other addresses, so the site never learns which one you checked."

**2:10–2:30 · Call to action** (What to do / GitHub README)

> "If you hold transparent ZEC, sweep it into Ironwood. If you're on Sapling or Orchard, migrate with a ZIP 318 wallet. If you run a multisig, rebuild it with FROST. Shorline is MIT-licensed and fully reproducible with one command. Link below."

---

**B-roll ideas:** the terminal running `cargo run --release -- scan` (progress lines with `missing=0`); the `check` command on an address; the "EXACT MATCH" cross-check line in the log.
