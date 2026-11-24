# Launch posts (drafts)

Numbers come from the snapshot at block 3,583,892. Re-check them against the dashboard before posting.

---

## Telegram submission (t.me/ZcashIN)

> **Shorline: how much ZEC would survive Q-Day?** (ZcashIND *Build on Zcash* bounty submission)
>
> A verifiable, chain-wide quantum-exposure survey of Zcash. It replays every transparent input and output since genesis (~190M of them) from public lightwalletd, tracks when each address's public key hit the chain, and classifies all 17.05M ZEC per ZIP 2005 / ZIP 2007. It is verified to the zatoshi against Zebra's value pool.
>
> • 7.24M ZEC (42.5% of supply) sits behind public keys already on-chain
> • 4,181 ZEC looks safe on Zcash but its keys leaked through the 2019 Ycash fork
> • It answers the open "survey the chain" step in zcash/zips#1302
>
> Repo (MIT): https://github.com/Jmohak2004/shorline
> Dashboard: https://jmohak2004.github.io/shorline/
> Demo video: https://github.com/Jmohak2004/shorline/blob/main/docs/video/shorline-explainer.mp4
> Thread: ⟨link⟩
>
> Categories: Infrastructure, Education and Adoption.

---

## X thread

**1/**
How much Zcash would survive Q-Day?

I replayed every transparent transaction since 2016 to find out.

7.24M ZEC (42.5% of supply) sits behind public keys that are already on the blockchain. 🧵

[og.png]

**2/**
Why it matters: a big enough quantum computer breaks discrete logs.

For transparent ZEC, ZIP 2005 is explicit: spends can be forged *once the public key has been revealed*, and every time you spend from a t-address, its key goes on-chain forever.

**3/**
@Zcash is already preparing. Ironwood (ZIP 2005) makes shielded funds recoverable after Q-Day. ZIP 2007 asks the same for transparent funds, and its discussion lists one next step:

"Survey the chain to see what proportion of funds are currently recoverable."

So I built that survey: Shorline.

**4/**
How it works:
• streams all 3.58M blocks from public lightwalletd
• replays ~190M transparent inputs and outputs in Rust, with no full node and no disk
• tracks when each address's key first hit the chain

The result matches Zebra's transparent value pool exactly, to the zatoshi ✅

**5/**
Every ZEC, by quantum fate:
🔴 Exposed 7.24M
🟡 Hash-protected (t1, never spent) 4.37M
🟣 Unknown P2SH 430K
🟠 Stranded in Sprout/Sapling/Orchard 749K
🔵 Lockbox 77K
🟢 Recoverable (Ironwood) 4.18M

**6/**
The twist: Ycash forked from Zcash in 2019 and copied every balance, keys included.

Anyone who spent their Ycash published the same key that guards their ZEC. 4,181 ZEC looks safe on Zcash but is exposed through Ycash, and Shorline proves each one cryptographically.

**7/**
More from the data:
• 270,623 ZEC has had its key public since 2018 or earlier
• 169,432 exposed ZEC hasn't moved in 4+ years (Zcash's "Satoshi coins")
• 1.0M ZEC flipped from hash-protected to exposed in a single 9-day window (25 Oct to 3 Nov 2026)
• 239,139 funded addresses kept receiving after their key went public

**8/**
What to do:
• t-addresses: sweep fully into Ironwood and never leave change behind
• Sapling/Orchard: migrate with a ZIP 318 wallet
• multisigs: rebuild as FROST (ZIP 312)

Check your address privately in the browser (k-anonymous shard lookup):
https://jmohak2004.github.io/shorline/

**9/**
Open source (MIT), reproducible with one command:
https://github.com/Jmohak2004/shorline

Built for the @ZcashIND Build on Zcash bounty. Feedback welcome from @ZecHub, @ZcashFoundation and the ZIP authors 🙏

---

## Zcash Community Forum post (Ecosystem / General)

**Title:** Shorline: a chain-wide quantum-exposure survey of Zcash (answers the ZIP 2007 "survey the chain" step)

Body: the README's "Headline findings" block, plus the dashboard link, the methodology link, and an invitation to check the numbers. Close with: *"If anyone from the ZIP 2007 effort wants different category cuts (for example by script template, or a snapshot at a specific height), I'm happy to add them."*

---

## Comment for zcash/zips#1302 (post only if you choose to)

> Re: *"Survey the chain to see what proportion of funds are currently recoverable and in each category"*: I ran this survey at block 3,583,892 and published the code and data (MIT): https://github.com/Jmohak2004/shorline
>
> Method: a full replay of transparent inputs and outputs from lightwalletd compact data. The reconstructed UTXO total matches Zebra's transparent `valuePool` exactly. Results (zatoshi-exact figures in `web/data/summary.json`):
>
> | Category | ZEC |
> |---|---:|
> | P2PKH, key never revealed (recoverable in principle) | 4,366,901 |
> | P2PKH, key revealed | 5,859,028 |
> | P2SH, script never seen | 430,380 |
> | P2SH, script seen | 1,380,350 |
> | P2PK / bare multisig | 788.48 / 0.0002 |
>
> On the open question about P2SH redeem-script usage: for the 5,571 funded t3 addresses with revealed scripts, the redeem scripts are standard 2-of-3 multisig (3,825 addresses, 232,721 ZEC), 2-of-2 (408, 139,317 ZEC), one 7-of-12 (12,244 ZEC), and a salted 2-of-3 template sharing one key set (39 addresses, 996,041 ZEC). P2SH-wrapped P2PKH (8 addresses, 0.55 ZEC) and P2SH-wrapped P2PK (4, 0.02 ZEC) exist but are negligible. A brute-force of the salted template's 2^32 salt space also re-identified 9 never-spent "unseen" P2SH addresses (168.88 ZEC) as belonging to that already-revealed key set.
>
> Two caveats. First, 4,181 ZEC at P2PKH addresses with no on-chain reveal on Zcash had its keys revealed by spends on the Ycash fork (height 570,000), so "never revealed" should probably be defined across chains that share pre-fork history. Second, P2PK and bare-multisig outputs also expose the P2PKH address of each contained key, in both SEC1 encodings. Shorline counts those as revealed.
