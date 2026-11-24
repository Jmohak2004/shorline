#!/usr/bin/env python3
"""Check that every relative link and image in the Markdown docs points at a file that exists.

    python3 scripts/check_links.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
bad = 0
files = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md")), *sorted(ROOT.glob("*.md"))]
for md in dict.fromkeys(files):
    in_code = False
    for n, line in enumerate(md.read_text().splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
        if in_code:
            continue
        for target in LINK.findall(line):
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            path = target.split("#")[0]
            if path and not (md.parent / path).exists():
                print(f"{md.relative_to(ROOT)}:{n}: missing {target}")
                bad += 1
print("all relative links resolve" if not bad else f"{bad} broken link(s)")
sys.exit(1 if bad else 0)
