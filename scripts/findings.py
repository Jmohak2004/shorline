#!/usr/bin/env python3
"""Regenerate the findings block in README.md and docs/FINDINGS.md from
web/data/summary.json (+ top.json). Run after every `shorline scan`:

    python3 scripts/findings.py
"""
import datetime as dt
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
import os
DATA = pathlib.Path(os.environ.get("SHORLINE_DATA", ROOT / "web" / "data"))
S = json.loads((DATA / "summary.json").read_text())
TOP = json.loads((DATA / "top.json").read_text())


def zec(z):
    return f"{z / 1e8:,.0f}"


def zec2(z):
    return f"{z / 1e8:,.2f}"


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "n/a"


def day(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%d %b %Y")


R = S["risk"]
T = S["transparent"]
cats = {c["id"]: c for c in T["categories"]}
total = R["total_zat"]
ttotal = T["total_zat"]
h = S["chain"]["height"]
when = day(S["chain"]["time"])
cc = S.get("cross_check")
ps = S.get("p2sh_survey")
reuse = S["reuse"]

fates = [
    ("Exposed", "exposed_zat", "Public key or redeem script already on-chain: spends can be forged by a discrete-log-breaking adversary"),
    ("Hash-protected", "hash_protected_zat", "t1, never spent from: safe until spent; recoverable only if a ZIP 2007 circuit ships"),
    ("Unknown P2SH", "unknown_zat", "t3, script never revealed: unclassifiable from public data"),
    ("Stranded", "stranded_zat", "Sprout + Sapling + Orchard: inaccessible once disabled unless migrated (ZIP 2005)"),
    ("Lockbox", "lockbox_zat", "NU6 dev-fund lockbox: consensus-held, no key"),
    ("Recoverable", "recoverable_zat", "Ironwood notes (ZIP 2005)"),
]

lines = []
lines.append(f"### Headline findings: block {h:,} ({when})")
lines.append("")
lines.append("| Fate | ZEC | Share of supply | Meaning |")
lines.append("|---|---:|---:|---|")
for name, key, meaning in fates:
    lines.append(f"| **{name}** | {zec(R[key])} | {pct(R[key], total)} | {meaning} |")
lines.append(f"| *Total* | *{zec(total)}* | *100%* | |")
lines.append("")

exp = R["exposed_zat"]
hidden = R["hash_protected_zat"]
bullets = []
bullets.append(
    f"**{zec(exp)} ZEC ({pct(exp, total)} of all ZEC, {pct(exp, ttotal)} of transparent ZEC) is exposed today.** "
    "Its public keys are already on-chain, so a large enough quantum computer could forge spends of it.")
bullets.append(
    f"**{zec(hidden)} ZEC ({pct(hidden, ttotal)} of transparent ZEC) is only hash-protected.** "
    "It is safe from Shor's algorithm until its owners spend, and recoverable after Q-Day only if ZIP 2007's transparent recovery circuit is built.")
if R["stranded_zat"]:
    bullets.append(
        f"**{zec(R['stranded_zat'])} ZEC is stranded in Sprout, Sapling and Orchard**, against {zec(R['recoverable_zat'])} ZEC "
        f"already in Ironwood. Under ZIP 2005 the stranded funds would be inaccessible once those protocols are disabled.")
yrs = sorted(S["exposed_by_reveal_year"], key=lambda y: -y["zat"])
if yrs:
    old = sum(y["zat"] for y in S["exposed_by_reveal_year"] if y["year"] <= 2018)
    bullets.append(
        f"**{zec(old)} ZEC of the exposed total has had its key public since 2018 or earlier.** "
        f"The peak reveal year is {yrs[0]['year']} ({zec(yrs[0]['zat'])} ZEC still at those addresses).")
dorm = {d["bucket"]: d for d in S["dormancy"]}
if "6y+" in dorm:
    d6 = dorm["6y+"]["exposed_zat"] + dorm.get("4-6y", {"exposed_zat": 0})["exposed_zat"]
    bullets.append(
        f"**{zec(d6)} exposed ZEC hasn't moved in over 4 years.** Lost keys can't migrate, so this is Zcash's version of the \"Satoshi coins\" problem.")
tsj = json.loads((DATA / "timeseries.json").read_text())
ci = {c: i for i, c in enumerate(tsj["columns"])}
rows = [r for r in tsj["rows"] if r[ci["time"]] > 0]
E = lambda r: r[ci["p2pkh_exposed"]] + r[ci["p2sh_seen"]] + r[ci["p2pk"]] + r[ci["bare_multisig"]]
best = None
for i in range(10, len(rows)):
    moved = min(E(rows[i]) - E(rows[i - 10]), rows[i - 10][ci["p2pkh_hidden"]] - rows[i][ci["p2pkh_hidden"]])
    if best is None or moved > best[0]:
        best = (moved, rows[i - 10], rows[i])
recent = sum(y["zat"] for y in S["exposed_by_reveal_year"] if y["year"] >= 2025)
bullets.append(
    f"**Exposure is accelerating, not shrinking.** {zec(recent)} ZEC ({pct(recent, exp)} of exposed value) had its key revealed in 2025–2026"
    + (f". In one 10,000-block window, {day(best[1][ci['time']])} to {day(best[2][ci['time']])}, {zec(best[0])} ZEC flipped from hash-protected to exposed as large holders spent from never-spent addresses and left the rest behind." if best and best[0] > 0 else "."))
r30 = reuse.get("sent_to_exposed_last_30d")
if r30:
    bullets.append(
        f"**Address reuse keeps feeding it:** {reuse['exposed_addresses_with_balance_that_received_after_reveal']:,} funded addresses kept receiving after their key went public, "
        f"and {zec(r30['zat'])} ZEC of payment volume in the last 30 days went to already-exposed addresses. That is gross flow, so coins cycling through reused hot wallets count on every pass.")
if ps:
    by = {x["type"]: x for x in ps["by_redeem_type"]}
    ms = sum(x["zat"] for t, x in by.items() if "multisig" in t)
    salted = sum(x["zat"] for t, x in by.items() if t.startswith("salted_multisig"))
    w = [x for t, x in by.items() if t in ("p2pkh_wrapped", "p2pk_wrapped")]
    wa, wz = sum(x["addresses"] for x in w), sum(x["zat"] for x in w)
    bullets.append(
        f"**ZIP 2007's P2SH question, answered with data:** all {ps['classified']:,} of {ps['addresses_with_balance']:,} funded P2SH addresses with revealed scripts were classified. "
        f"Multisig holds {zec(ms)} ZEC, of which {zec(salted)} ZEC sits in one custodian's *salted* 2-of-3 template. "
        + (f"P2SH-wrapped P2PKH/P2PK do occur, but only at {wa} addresses holding {zec2(wz)} ZEC." if wa else "No funded address uses P2SH-wrapped P2PKH or P2PK."))
spath = DATA / "salted_exposure.json"
if spath.exists():
    SX = json.loads(spath.read_text())
    if SX.get("templates"):
        t0 = SX["templates"][0]
        bullets.append(
            f"**Unseen P2SH isn't always unknowable:** one 2-of-3 key set backs {t0['revealed_addresses']} revealed addresses ({zec(t0['revealed_zat'])} ZEC), each differing only by a "
            f"{t0['redeem']['salt_bytes']}-byte salt. Hashing all {t0['salts_searched']:,} salts against every funded never-spent P2SH address rediscovered "
            f"{t0['rediscovered_revealed']}/{t0['revealed_addresses']} (self-check) and found {SX['matched_addresses']} never-spent family members holding {zec2(SX['matched_zat'])} ZEC. They are exposed in practice.")
ypath = DATA / "ycash_exposure.json"
if ypath.exists():
    Y = json.loads(ypath.read_text())
    if Y.get("checked"):
        bullets.append(
            f"**Hidden on Zcash, exposed on Ycash:** {zec(Y['revealed_zat'])} ZEC at {Y['revealed_count']:,} addresses look hash-protected on Zcash, "
            f"but their keys were published by spends on the 2019 Ycash fork. That is {pct(Y['revealed_zat'], Y['checked_zat'])} of the "
            f"{zec(Y['checked_zat'])} ZEC of pre-fork hash-protected value checked. The on-chain survey understates exposure.")
if cc:
    bullets.append(
        f"**Verified:** Shorline's independently replayed UTXO set totals {zec2(cc['shorline_transparent_zat'])} ZEC at block {cc['height']:,}, "
        + ("**exactly** equal to" if cc["match"] else f"{cc['difference_zat']} zat away from")
        + f" the transparent value pool reported by Zebra ({cc['node_build']}). Every one of {S['scan']['inputs']:,} transparent inputs resolved "
        f"({S['scan']['missing_prevouts']} unmatched).")
for b in bullets:
    lines.append(f"* {b}")
lines.append("")
lines.append(f"Data: [`web/data/`](web/data) · full write-up: [docs/FINDINGS.md](docs/FINDINGS.md) · reproduce with `cargo run --release -- scan`.")
block = "\n".join(lines)

readme = (ROOT / "README.md").read_text()
readme = re.sub(r"<!-- FINDINGS:START -->.*?<!-- FINDINGS:END -->",
                "<!-- FINDINGS:START -->\n" + block + "\n<!-- FINDINGS:END -->", readme, flags=re.S)
(ROOT / "README.md").write_text(readme)

# ---- docs/FINDINGS.md ------------------------------------------------------
f = []
f.append(f"# Findings: block {h:,} ({when})")
f.append("")
f.append("Generated by `scripts/findings.py` from the published dataset. The method is in [METHODOLOGY.md](METHODOLOGY.md).")
f.append("")
f.append(block.replace("web/data", "../web/data").replace("docs/FINDINGS.md", "FINDINGS.md"))
f.append("")
f.append("## Transparent value by ZIP 2007 category")
f.append("")
f.append("| Category | ZEC | Share of transparent | Funded entities | UTXOs |")
f.append("|---|---:|---:|---:|---:|")
for c in T["categories"]:
    f.append(f"| `{c['id']}` | {zec2(c['zat'])} | {pct(c['zat'], ttotal)} | {c['addresses']:,} | {c['utxos']:,} |")
f.append("")
f.append("## Exposed ZEC by the year its key was revealed")
f.append("")
f.append("| Year | Exposed ZEC still there |")
f.append("|---|---:|")
for y in S["exposed_by_reveal_year"]:
    f.append(f"| {y['year']} | {zec(y['zat'])} |")
f.append("")
f.append("## Dormancy (time since the address last moved)")
f.append("")
f.append("| Since last activity | Exposed ZEC | Hash-protected ZEC |")
f.append("|---|---:|---:|")
for d in S["dormancy"]:
    f.append(f"| {d['bucket']} | {zec(d['exposed_zat'])} | {zec(d['hidden_zat'])} |")
f.append("")
if ps:
    f.append("## P2SH redeem scripts (funded addresses whose script is revealed)")
    f.append("")
    f.append("| Redeem script | Addresses | ZEC |")
    f.append("|---|---:|---:|")
    for x in sorted(ps["by_redeem_type"], key=lambda x: -x["zat"]):
        f.append(f"| {x['type']} | {x['addresses']:,} | {zec2(x['zat'])} |")
    f.append("")
f.append("## Largest exposed balances")
f.append("")
f.append("| # | Address | ZEC | Key revealed | Last active |")
f.append("|---:|---|---:|---|---|")
allx = []
for k in ("p2pkh_exposed", "p2sh_seen", "p2pk", "bare_multisig"):
    allx += TOP.get(k, [])
allx.sort(key=lambda e: -e["zat"])
for i, e in enumerate(allx[:20], 1):
    rv = day(e["revealed_time"]) if e.get("revealed_time") else "at creation"
    f.append(f"| {i} | `{e['address']}` | {zec(e['zat'])} | {rv} | {day(e['last_seen_time'])} |")
f.append("")
f.append("## Scan")
f.append("")
sc = S["scan"]
f.append(f"* Blocks replayed: {sc['blocks']:,}; transactions: {sc['transactions']:,}; transparent inputs: {sc['inputs']:,}; outputs: {sc['outputs']:,}")
f.append(f"* Live UTXOs at tip: {sc['utxos']:,}; distinct script owners ever seen: {sc['entities']:,}; unmatched inputs: {sc['missing_prevouts']}")
f.append(f"* Wall-clock: {sc['seconds'] / 60:.0f} min from public lightwalletd ({', '.join(S['sources']['lightwalletd'])})")
(ROOT / "docs" / "FINDINGS.md").write_text("\n".join(f) + "\n")
print(block)
