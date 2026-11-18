# Brag Plan: Shorline

## What is this app?
Shorline replays the entire Zcash chain and measures how much ZEC a quantum computer could steal or strand: 7.24M ZEC (42.5% of supply) sits behind public keys already on-chain. It is verified to the zatoshi against Zebra.

## The angle
"Q-Day, explained like a lock." It's a neobrutalist explainer: problem, concepts, solution, proof, results, uniqueness and impact. Every jargon term (private and public key, hash, t-address, Shor's algorithm, discrete log, address reuse, shielded pools, ZIP 2005/2007, Ironwood, lightwalletd, UTXO set, zatoshi, value pool, multisig, salt, fork, k-anonymity, FROST) is introduced with a one-line real-life analogy and a card on screen.

## Hook (first 2-3 seconds)
A grid of padlocks springs open all at once, then a tilted Q-DAY stamp slams down. The voice says: "Imagine a machine that could pick every lock on Earth at once."

## Key moments (the middle)
- Keys → lock → fingerprint cards (private key / public key / t-address = hash)
- A coin card flipping from HASH-PROTECTED to EXPOSED on its first spend
- The verification: two 12,037,446.98852579 ZEC cards and an EXACT MATCH stamp
- The answer: a 7.24M ZEC count-up, then the six-part fate bar building
- The real exposure history drawn on (data from timeseries.json), plus "1.0M ZEC flipped in 9 days"
- The salt slot machine (2^32 salts, 39/39 rediscovered, +9 hidden) and the Ycash fork split
- The live dashboard and a simulated address check (typing → CHECK → EXPOSED)

## Outro / punchline
Three action cards (sweep to Ironwood / ZIP 318 / FROST), then the inverted close-frame: "SHORLINE: Know your exposure before Q-Day."

## User flow worth showing
Open the dashboard → paste an address → see "Exposed · 259,122.13 ZEC · key revealed block 3,140,430". This is a real lookup from the live site (screenshot plus simulated typing).

## Tone
- Preset: polished
- Creative direction: neobrutalist explainer (zine / sticker-book), confident and clear, never jokey about the risk
- Interpretation: medium pace; every term gets a card; motion is snappy-in, then a hold for reading

## Format: landscape — 1920x1080, 30 fps
## Duration: explicit long-form (user asked for a full explainer with all concepts). Scenes flex to the Kokoro narration: about 270 s

## Visual identity
- Look: Hyperframes `blockframe` preset (user asked for neobrutal). 4px black borders, 8px hard shadows, square corners, pastel grounds cycling (cream / blue / pink / yellow / offwhite / green), black close-frame with a yellow shadow
- Display: Inter 900 uppercase, negative tracking. Labels: Space Mono (closest bundled face to the preset's Space Grotesk)
- Data colours (from the Shorline dashboard, for recognition): exposed #d03b3b · hash-protected #fab219 · unknown #7b6bea · stranded #ec835a · lockbox #2a78d6 · recoverable #0ca30c

## Share copy (draft)
7.24M ZEC (42.5% of supply, ≈$6.8B) already sits behind public keys a quantum computer could break. Shorline measured every zatoshi, and the total matches Zebra exactly.

## Audio direction
- Role: warm bed under the voice + sparse, motion-matched accents
- Music: brag bundled "Happy Beats / Business Moves" Vol. 1 → Vol. 9 crossfade (Sascha Ende, CC BY 4.0), ducked to ~0.12 under narration
- Voice: Kokoro af_heart via `npx hyperframes tts`, one clip per sentence
- SFX posture: sparse. Soft impacts on stamps and reveals, a bong on EXACT MATCH, a bell on the final mark, keypresses and a click in the checker demo, and a switch when coins flip to exposed
- Restraint rule: no effect without a visible cause; no repeated identical hits back to back

## Voiceover script
See `script.json` (47 lines; the caption text plus a pronunciation-tuned TTS text for jargon: "Zee cash", "U T X O", "zip twenty oh five").

## Storyboard (scene → narration lines)
1. Hook: Q-Day (l01–l03): lock grid pops, Q-DAY stamp, title "HOW MUCH ZEC WOULD SURVIVE Q-DAY?"
2. Keys and locks (l04–l07): three cards with one-way arrows
3. Shor's algorithm (l08–l10): three lanes (today impossible / quantum easy / hash still safe) + discrete-log card
4. The catch (l11–l14): an address card's coins flip to exposed on first spend; reuse stat 239,139
5. Zcash's plan (l15–l18): pool blocks; Ironwood RECOVERABLE (ZIP 2005); STRANDED stamps; ZIP 2007 quote card
6. How Shorline works (l19–l22): stream → replay → UTXO set step cards; NO FULL NODE / NO DISK / ~31 MIN
7. Verified (l23–l25): zatoshi definition; twin totals; EXACT MATCH
8. The answer (l26–l30): 7.24M count-up, ≈$6.8B, fate bar
9. Getting worse (l31–l33): history lines draw on; 79% since 2025; 1.0M flipped in 9 days
10. Hidden exposure (l34–l37): salt slot machine; Ycash fork split
11. The dashboard (l38–l40): browser frame with the real dashboard; simulated check; k-anonymity shard diagram
12. Why it's different (l41–l43): five feature cards, keyed to words
13. Who it's for (l44–l45): audience chips, metric stat grid, roadmap ribbon
14. Close (l46–l47): action cards, close-frame, credits
