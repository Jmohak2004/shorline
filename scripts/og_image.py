#!/usr/bin/env python3
"""Render web/og.png (1200x630 social card) from web/data/summary.json."""
import json
import os
import pathlib

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = pathlib.Path(os.environ.get("SHORLINE_DATA", ROOT / "web" / "data"))
S = json.loads((DATA / "summary.json").read_text())
R = S["risk"]

W, H = 1200, 630
BG, INK, INK2, MUTED, GRID = "#121211", "#f0efec", "#c3c2b7", "#9a988f", "#2c2c2a"
FATES = [
    ("Exposed", "exposed_zat", "#d03b3b", "#ffffff"),
    ("Hash-protected", "hash_protected_zat", "#fab219", "#0b0b0b"),
    ("Unknown P2SH", "unknown_zat", "#9085e9", "#ffffff"),
    ("Stranded", "stranded_zat", "#ec835a", "#ffffff"),
    ("Lockbox", "lockbox_zat", "#3987e5", "#ffffff"),
    ("Recoverable", "recoverable_zat", "#0ca30c", "#ffffff"),
]


def font(size, weight="Regular"):
    for path in ("/System/Library/Fonts/SFNS.ttf", "/Library/Fonts/SF-Pro.ttf"):
        if os.path.exists(path):
            f = ImageFont.truetype(path, size)
            try:
                f.set_variation_by_name(weight)
            except Exception:
                pass
            return f
    idx = {"Regular": 0, "Bold": 1, "Semibold": 1, "Medium": 0}.get(weight, 0)
    return ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", size, index=idx)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
X0 = 72

# brand mark
import math
d.rounded_rectangle((X0, 56, X0 + 40, 96), radius=10, fill=INK)
for amp, y, col, wd in ((2.6, 82, (18, 18, 17), 3), (1.8, 89, (120, 120, 116), 2)):
    pts = [(X0 + 6 + i * 0.25, y + math.sin(i * 0.25 / 28 * 2 * math.pi * 1.5) * amp) for i in range(0, 113)]
    d.line(pts, fill=col, width=wd, joint="curve")
d.ellipse((X0 + 25, 64, X0 + 32, 71), fill="#fab219")
d.text((X0 + 54, 60), "Shorline", font=font(30, "Bold"), fill=INK)
d.text((X0 + 200, 66), "Zcash quantum exposure survey", font=font(22), fill=MUTED)

d.text((X0, 132), "How much ZEC would survive Q-Day?", font=font(54, "Bold"), fill=INK)

total = R["total_zat"]
exp = R["exposed_zat"]
num = f"{exp / 1e8 / 1e6:.2f}M ZEC" if exp >= 1e14 else f"{exp / 1e8:,.0f} ZEC"
d.text((X0, 222), num, font=font(112, "Bold"), fill=INK)
nw = d.textlength(num, font=font(112, "Bold"))
cap = f"{100 * exp / total:.1f}% of all ZEC sits behind public keys already on the blockchain."
fc = font(26, "Semibold")
cx, maxw = X0 + nw + 34, W - X0 - (X0 + nw + 34)
words, lines_, cur = cap.split(), [], ""
for wd_ in words:
    t = (cur + " " + wd_).strip()
    if d.textlength(t, font=fc) <= maxw:
        cur = t
    else:
        lines_.append(cur)
        cur = wd_
lines_.append(cur)
for i, ln in enumerate(lines_[:3]):
    d.text((cx, 236 + i * 36 - (len(lines_) - 2) * 14), ln, font=fc, fill=INK2)

# segmented bar
bx0, bx1, by, bh, gap = X0, W - X0, 400, 44, 3
parts = [(n, R[k], c, on) for n, k, c, on in FATES if R.get(k, 0) > 0]
avail = (bx1 - bx0) - gap * (len(parts) - 1)
x = bx0
f_in = font(20, "Bold")
for n, v, c, on in parts:
    w = max(3, avail * v / total)
    d.rounded_rectangle((x, by, x + w, by + bh), radius=6, fill=c)
    label = f"{100 * v / total:.0f}%"
    if w > d.textlength(label, font=f_in) + 22:
        d.text((x + 11, by + 10), label, font=f_in, fill=on)
    x += w + gap

# legend
lx, ly = bx0, by + bh + 22
f_leg = font(21, "Medium")
for n, v, c, on in parts:
    d.rounded_rectangle((lx, ly + 6, lx + 14, ly + 20), radius=3, fill=c)
    d.text((lx + 22, ly), n, font=f_leg, fill=INK2)
    lx += 22 + d.textlength(n, font=f_leg) + 30

foot = f"Block {S['chain']['height']:,} · full UTXO replay from genesis"
cc = S.get("cross_check")
if cc and cc.get("match"):
    foot += " · verified to the zatoshi against Zebra"
d.line((X0, 548, W - X0, 548), fill=GRID, width=1)
d.text((X0, 566), foot, font=font(21), fill=MUTED)
rt = "ZIP 2005 · ZIP 2007"
if d.textlength(foot, font=font(21)) + d.textlength(rt, font=font(21)) + 40 < W - 2 * X0:
    d.text((W - X0 - d.textlength(rt, font=font(21)), 566), rt, font=font(21), fill=MUTED)

out = ROOT / "web" / "og.png"
img.save(out, optimize=True)
print("wrote", out)
