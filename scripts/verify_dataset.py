#!/usr/bin/env python3
"""Check the published dataset in web/data for internal consistency.

    python3 scripts/verify_dataset.py [DATA_DIR]

Exits non-zero on the first failed invariant. Run in CI so a bad data refresh
can never reach the dashboard.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "web" / "data"
failures = []


def check(ok, msg):
    print(("ok   " if ok else "FAIL ") + msg)
    if not ok:
        failures.append(msg)


def load(name):
    return json.loads((DATA / name).read_text())


S = load("summary.json")
T = S["transparent"]
R = S["risk"]
P = S["shielded"]["zat"]
X = S["cross_check"]

check(S["schema"] == 1, "schema version is 1")
check(S["scan"]["missing_prevouts"] == 0, "every transparent input resolved (0 missing prevouts)")
check(X["match"] and X["difference_zat"] == 0, "cross-check against Zebra matches to the zatoshi")
check(
    X["shorline_transparent_zat"] == X["zebra_transparent_zat"] == T["total_zat"],
    "cross-check totals equal the transparent total",
)
check(
    sum(c["zat"] for c in T["categories"]) == T["total_zat"],
    "the eight transparent categories sum to the transparent total",
)
check(len(T["categories"]) == 8, "all eight categories present")
fates = ["exposed", "hash_protected", "unknown", "stranded", "lockbox", "recoverable"]
check(
    sum(R[f + "_zat"] for f in fates) + R["unspendable_zat"] == R["total_zat"],
    "six fates + unspendable sum to total supply",
)
check(
    R["stranded_zat"] == P["sprout"] + P["sapling"] + P["orchard"],
    "stranded = Sprout + Sapling + Orchard",
)
check(R["recoverable_zat"] == P["ironwood"], "recoverable = Ironwood")
check(R["lockbox_zat"] == P["lockbox"], "lockbox matches value pools")
check(
    sum(S["exposed_by_reason"].values()) == R["exposed_zat"],
    "exposed-by-reason sums to exposed total",
)
check(
    sum(y["zat"] for y in S["exposed_by_reveal_year"]) == R["exposed_zat"],
    "exposed-by-reveal-year sums to exposed total",
)
check(
    sum(b["exposed_zat"] for b in S["dormancy"]) == R["exposed_zat"],
    "dormancy exposed buckets sum to exposed total",
)
ps = S["p2sh_survey"]
check(ps["failed"] == 0 and ps["classified"] == ps["addresses_with_balance"], "P2SH survey classified every address")

ts = load("timeseries.json")
check(bool(ts), "timeseries.json is non-empty")

top = load("top.json")
for cat in T["categories"]:
    entries = top.get(cat["id"], [])
    check(
        len(entries) <= cat["addresses"] and sum(e["zat"] for e in entries) <= cat["zat"],
        f"top.json[{cat['id']}] is a subset of the category",
    )
    check(
        all(a["zat"] >= b["zat"] for a, b in zip(entries, entries[1:])),
        f"top.json[{cat['id']}] is sorted by value",
    )

sv = load("p2sh_survey.json")
check(len(sv["entries"]) == ps["classified"], "p2sh_survey.json entry count matches summary")

print()
if failures:
    print(f"{len(failures)} invariant(s) failed")
    sys.exit(1)
print("dataset is consistent")
