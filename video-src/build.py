#!/usr/bin/env python3
"""Builds the Shorline explainer as a HyperFrames project (blockframe / neobrutalist look).

Inputs: script.json (narration), voice_timing.json (measured Kokoro clip lengths and pauses),
series.json (real exposure history from web/data/timeseries.json).
Output: composition/index.html, composition/compositions/*.html
"""
import json, re, math, pathlib, subprocess, html

BASE = pathlib.Path(__file__).resolve().parent
COMP = BASE / "composition"
SC = json.loads((BASE / "script.json").read_text())
TIM = json.loads((BASE / "voice_timing.json").read_text())
SERIES = json.loads((BASE / "series.json").read_text())

GAP, LEAD, TAIL, CLOSE_HOLD = 0.30, 0.45, 0.55, 3.4
W, H = 1920, 1080

# ---------------------------------------------------------------- palette
BLACK, WHITE, OFF = "#000000", "#FFFFFF", "#FFFDF5"
PINK, BLUE, GREEN, YELLOW, CREAM = "#FE90E8", "#C0F7FE", "#99E885", "#F7CB46", "#FFDC8B"
EXP, HASHC, UNK, STR, LOCK, REC = "#d03b3b", "#fab219", "#7b6bea", "#ec835a", "#2a78d6", "#0ca30c"

# ---------------------------------------------------------------- timing
def word_times(cap, dur, pauses):
    words = cap.split()
    segs, t = [], 0.0
    for s, e in pauses:
        if s > t:
            segs.append((t, s))
        t = e
    segs.append((t, dur))
    weight = lambda w: max(1, len(re.sub(r"[^A-Za-z0-9$%]", "", w))) + 1.6
    # chunk words at punctuation; if chunk count == segment count, align chunk i to segment i
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[,.:;?!]$", w):
            chunks.append(cur); cur = []
    if cur:
        chunks.append(cur)
    out = []
    if len(chunks) == len(segs):
        for ch, (a, b) in zip(chunks, segs):
            tot = sum(weight(w) for w in ch); acc = 0
            for w in ch:
                st = a + (b - a) * acc / tot; acc += weight(w); en = a + (b - a) * acc / tot
                out.append([w, st, en])
        return out
    speech = sum(b - a for a, b in segs)
    def to_abs(x):
        acc = 0
        for a, b in segs:
            if x <= acc + (b - a) + 1e-9:
                return a + (x - acc)
            acc += b - a
        return segs[-1][1]
    tot = sum(weight(w) for w in words); acc = 0
    for w in words:
        st = to_abs(speech * acc / tot); acc += weight(w); en = to_abs(speech * acc / tot)
        out.append([w, st, en])
    return out

scenes, t = [], 0.0
for i, s in enumerate(SC["scenes"]):
    local, lines = LEAD, []
    for j, l in enumerate(s["lines"]):
        tm = TIM[l["id"]]
        wt = word_times(l["cap"], tm["dur"], tm["pauses"])
        lines.append(dict(l, start=local, end=local + tm["dur"], dur=tm["dur"],
                          words=[[w, local + a, local + b] for w, a, b in wt]))
        local += tm["dur"] + (GAP if j < len(s["lines"]) - 1 else 0)
    dur = round(local + TAIL + (CLOSE_HOLD if i == len(SC["scenes"]) - 1 else 0), 3)
    scenes.append(dict(s, abs=round(t, 3), dur=dur, lines=lines))
    t += dur
TOTAL = round(t, 3)

class Cue:
    def __init__(self, sc):
        self.sc = sc
        self.L = {l["id"]: l for l in sc["lines"]}
    def s(self, lid, d=0.0):
        return round(self.L[lid]["start"] + d, 3)
    def e(self, lid, d=0.0):
        return round(self.L[lid]["end"] + d, 3)
    def w(self, lid, needle, d=0.0, nth=0):
        hits = [ws for ws in self.L[lid]["words"]
                if needle.lower() in re.sub(r"[^A-Za-z0-9$%.\-']", "", ws[0]).lower()]
        if not hits:
            raise SystemExit(f"word '{needle}' not in {lid}: {self.L[lid]['cap']}")
        return round(hits[nth][1] + d, 3)

# ---------------------------------------------------------------- shared CSS
SHARED_CSS = """
#root{position:absolute;inset:0;overflow:hidden;font-family:'Inter',sans-serif;color:#000;}
.ground{position:absolute;inset:0;}
.dots{position:absolute;inset:0;background-image:radial-gradient(#000 1.4px,transparent 1.6px);background-size:26px 26px;opacity:.16;}
.abs{position:absolute;}
.pill{position:absolute;display:inline-flex;align-items:center;gap:12px;border:3px solid #000;border-radius:999px;box-shadow:4px 4px 0 #000;padding:9px 22px 8px;font:700 21px/1 'Space Mono',monospace;letter-spacing:.08em;text-transform:uppercase;background:#fff;color:#000;white-space:nowrap;}
.hxl{font:900 112px/0.95 'Inter',sans-serif;letter-spacing:-0.03em;text-transform:uppercase;}
.hlg{font:900 74px/1.0 'Inter',sans-serif;letter-spacing:-0.025em;text-transform:uppercase;}
.hmd{font:800 44px/1.1 'Inter',sans-serif;letter-spacing:-0.01em;text-transform:uppercase;}
.card{position:absolute;background:#fff;border:4px solid #000;box-shadow:8px 8px 0 #000;}
.cards{position:absolute;background:#fff;border:3px solid #000;box-shadow:5px 5px 0 #000;}
.ctitle{font:900 40px/1.05 'Inter',sans-serif;letter-spacing:-0.015em;text-transform:uppercase;}
.body{font:500 28px/1.38 'Inter',sans-serif;}
.mono{font-family:'Space Mono',monospace;}
.lbl{font:700 20px/1 'Space Mono',monospace;letter-spacing:.08em;text-transform:uppercase;}
.stat{font:900 92px/0.95 'Inter',sans-serif;letter-spacing:-0.03em;}
.stamp{position:absolute;border:4px solid #000;box-shadow:8px 8px 0 #000;font:900 46px/1 'Inter',sans-serif;letter-spacing:-0.02em;text-transform:uppercase;padding:16px 26px 14px;white-space:nowrap;}
.star{clip-path:polygon(50% 0%,61% 26%,90% 10%,79% 39%,100% 50%,79% 61%,90% 90%,61% 74%,50% 100%,39% 74%,10% 90%,21% 61%,0% 50%,21% 39%,10% 10%,39% 26%);}
.stripes{background:repeating-linear-gradient(45deg,#000 0 12px,var(--sc,#F7CB46) 12px 26px);border:3px solid #000;}
.isq{position:absolute;border:3px solid #000;box-shadow:4px 4px 0 #000;display:flex;align-items:center;justify-content:center;}
.tr{position:absolute;inset:0;z-index:50;}
.chip{display:inline-flex;align-items:center;gap:12px;font:700 22px/1 'Space Mono',monospace;text-transform:uppercase;letter-spacing:.04em;}
.sw{width:22px;height:22px;border:3px solid #000;display:inline-block;}
.arrow{position:absolute;height:12px;background:#000;}
.arrow::after{content:'';position:absolute;right:-18px;top:-12px;border-left:22px solid #000;border-top:18px solid transparent;border-bottom:18px solid transparent;}
"""

def pill(id_, text, x, y, bg=WHITE, color=BLACK, extra=""):
    return f'<div class="pill" id="{id_}" style="left:{x}px;top:{y}px;background:{bg};color:{color};{extra}">{text}</div>'

def eyebrow(sid, text, bg=WHITE):
    return pill(f"{sid}-eyebrow", text, 110, 62, bg)

def J(src, **kw):
    for k, v in kw.items():
        src = src.replace("{{" + k + "}}", str(v))
    return src

# ---------------------------------------------------------------- transitions
# transition INTO scene i (index into scenes); the previous scene renders the matching "out".
TRANS = {1: "slabX", 2: "slabX", 3: "slabX", 4: "slabY", 5: "slabX", 6: "slabX", 7: "iris",
         8: "slabX", 9: "slabY", 10: "slabX", 11: "slabX", 12: "slabY", 13: "iris"}

def trans_in(sid, kind, ground):
    if kind == "slabX":
        return (f'<div class="tr" id="{sid}-tin" style="background:#000"></div>',
                f'tl.fromTo("#{sid}-tin",{{xPercent:0}},{{xPercent:101,duration:0.42,ease:"power3.inOut"}},0.02);')
    if kind == "slabY":
        return (f'<div class="tr" id="{sid}-tin" style="background:{ground};border-top:8px solid #000;border-bottom:8px solid #000"></div>',
                f'tl.fromTo("#{sid}-tin",{{yPercent:0}},{{yPercent:-104,duration:0.5,ease:"power3.inOut"}},0.05);')
    if kind == "iris":
        return ("", f'tl.fromTo("#{sid}-stage",{{clipPath:"circle(0% at 50% 50%)"}},{{clipPath:"circle(80% at 50% 50%)",duration:0.6,ease:"power2.inOut"}},0.02);')
    return ("", "")

def trans_out(sid, kind, next_ground, dur):
    t0 = round(dur - 0.36, 3)
    if kind == "slabX":
        return (f'<div class="tr" id="{sid}-tout" style="background:#000"></div>',
                f'tl.fromTo("#{sid}-tout",{{xPercent:-101}},{{xPercent:0,duration:0.32,ease:"power3.in"}},{t0});')
    if kind == "slabY":
        return (f'<div class="tr" id="{sid}-tout" style="background:{next_ground};border-top:8px solid #000;border-bottom:8px solid #000"></div>',
                f'tl.fromTo("#{sid}-tout",{{yPercent:104}},{{yPercent:0,duration:0.34,ease:"power3.in"}},{round(dur-0.37,3)});')
    if kind == "iris":
        return (f'<div class="tr" id="{sid}-tout" style="background:#000"></div>',
                f'tl.fromTo("#{sid}-tout",{{opacity:0}},{{opacity:1,duration:0.26,ease:"power2.in"}},{round(dur-0.3,3)});')
    return ("", "")

# helpers for JS snippets -------------------------------------------------------
def pop(sel, t, d=0.38, fromScale=0.6, rot=0, ease="back.out(1.7)"):
    return f'tl.fromTo("{sel}",{{opacity:0,scale:{fromScale},rotation:{rot-6 if rot else 0}}},{{opacity:1,scale:1,rotation:{rot},duration:{d},ease:"{ease}"}},{t});'

def slam(sel, t, rot=-6, fromScale=1.9):
    return f'tl.fromTo("{sel}",{{opacity:0,scale:{fromScale},rotation:{rot}}},{{opacity:1,scale:1,rotation:{rot},duration:0.3,ease:"power4.out"}},{t});'

def blurin(sel, t, d=0.22, y=0):
    return f'tl.fromTo("{sel}",{{opacity:0,filter:"blur(10px)",y:{y}}},{{opacity:1,filter:"blur(0px)",y:0,duration:{d},ease:"power3.out"}},{t});'

def slide(sel, t, x=0, y=60, d=0.5, rot=0):
    return f'tl.fromTo("{sel}",{{opacity:0,x:{x},y:{y},rotation:{rot}}},{{opacity:1,x:0,y:0,rotation:{rot},duration:{d},ease:"expo.out"}},{t});'

def fadeout(sel, t, d=0.2):
    return f'tl.to("{sel}",{{opacity:0,duration:{d},ease:"power2.in"}},{t});'

def counter(sel, t, d, to, fmt, ir=True):
    irs = "" if ir else ",immediateRender:false"
    return (f'(function(){{const el=document.querySelector("{sel}");const o={{v:0}};'
            f'tl.fromTo(o,{{v:0}},{{v:{to},duration:{d},ease:"power2.out"{irs},onUpdate:function(){{const v=o.v;el.textContent={fmt};}}}},{t});'
            f'}})();')

def words_in(prefix, words, times, d=0.16):
    out = []
    for i, t in enumerate(times):
        out.append(f'tl.fromTo("#{prefix}{i}",{{opacity:0,filter:"blur(8px)"}},{{opacity:1,filter:"blur(0px)",duration:{d},ease:"power3.out"}},{t});')
    return "\n".join(out)

SFX = []  # (abs_time, file, volume)
def sfx(sc, t, f, v=0.5):
    SFX.append((round(sc["abs"] + t, 3), f, v))

# ---------------------------------------------------------------- icons (pure CSS)
def icon_key(x, y, s=1.0, bg=YELLOW, id_=""):
    return (f'<div class="isq" id="{id_}" style="left:{x}px;top:{y}px;width:{int(118*s)}px;height:{int(118*s)}px;background:{bg}">'
            f'<div style="position:relative;width:86px;height:40px;transform:scale({s})">'
            f'<div style="position:absolute;left:0;top:2px;width:36px;height:36px;border:9px solid #000;box-sizing:border-box"></div>'
            f'<div style="position:absolute;left:32px;top:14px;width:54px;height:11px;background:#000"></div>'
            f'<div style="position:absolute;left:62px;top:24px;width:9px;height:14px;background:#000"></div>'
            f'<div style="position:absolute;left:76px;top:24px;width:9px;height:10px;background:#000"></div></div></div>')

def icon_lock(x, y, bg=PINK, id_="", s=1.0, shackle_id=""):
    return (f'<div class="isq" id="{id_}" style="left:{x}px;top:{y}px;width:{int(118*s)}px;height:{int(118*s)}px;background:{bg}">'
            f'<div style="position:relative;width:60px;height:66px;transform:scale({s})">'
            f'<div id="{shackle_id}" style="position:absolute;left:12px;top:0;width:36px;height:34px;border:9px solid #000;border-bottom:none;box-sizing:border-box"></div>'
            f'<div style="position:absolute;left:0;top:28px;width:60px;height:38px;background:#000"></div>'
            f'<div style="position:absolute;left:26px;top:38px;width:8px;height:16px;background:' + bg + '"></div></div></div>')

def icon_print(x, y, bg=GREEN, id_=""):
    rings = "".join(f'<div style="position:absolute;left:{6*i}px;top:{6*i}px;width:{68-12*i}px;height:{68-12*i}px;border:4px solid #000;box-sizing:border-box"></div>' for i in range(4))
    return (f'<div class="isq" id="{id_}" style="left:{x}px;top:{y}px;width:118px;height:118px;background:{bg}">'
            f'<div style="position:relative;width:68px;height:68px">{rings}</div></div>')

def logo_mark(x, y, size=96, id_=""):
    return (f'<div id="{id_}" class="abs" style="left:{x}px;top:{y}px;width:{size}px;height:{size}px;background:#000;border:4px solid #000;box-shadow:6px 6px 0 {YELLOW}">'
            f'<svg viewBox="0 0 32 32" width="{size-8}" height="{size-8}"><path d="M5 19c3.2 0 3.2-3 6.4-3s3.2 3 6.4 3 3.2-3 6.4-3 3.2 3 3.8 3" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="square"/>'
            f'<path d="M5 24c3.2 0 3.2-2 6.4-2s3.2 2 6.4 2 3.2-2 6.4-2 3.2 2 3.8 2" fill="none" stroke="#fff" stroke-opacity=".5" stroke-width="2.2"/><rect x="20" y="6" width="6" height="6" fill="{YELLOW}"/></svg></div>')

# ---------------------------------------------------------------- scenes
def scene_s01(sc, C):
    sid = "s01"; m, js = [], []
    m.append('<div class="dots"></div>')
    m.append(eyebrow(sid, "Shorline · Zcash quantum exposure survey"))
    js.append(blurin(f"#{sid}-eyebrow", 0.35))
    # lock grid
    cols = [PINK, BLUE, GREEN, WHITE, YELLOW, PINK, WHITE, BLUE, GREEN, YELLOW, BLUE, PINK]
    cells = []
    for i in range(12):
        r, c = divmod(i, 4)
        x, y = 0 + c * 200, 0 + r * 190
        cells.append(f'<div class="abs" id="{sid}-lk{i}" style="left:{x}px;top:{y}px;width:160px;height:170px">'
                     f'<div id="{sid}-sh{i}" class="abs" style="left:40px;top:6px;width:80px;height:78px;border:16px solid #000;border-bottom:none;box-sizing:border-box;transform-origin:100% 100%"></div>'
                     f'<div class="abs" style="left:10px;top:66px;width:140px;height:98px;background:{cols[i]};border:4px solid #000;box-shadow:6px 6px 0 #000"></div>'
                     f'<div class="abs" style="left:72px;top:96px;width:16px;height:16px;background:#000"></div>'
                     f'<div class="abs" style="left:76px;top:108px;width:8px;height:26px;background:#000"></div></div>')
    m.append(f'<div class="abs" id="{sid}-lockwrap" style="left:570px;top:205px;width:800px;height:570px">{"".join(cells)}'
             f'<div class="stamp" id="{sid}-qday" style="left:130px;top:200px;background:#000;color:#fff;font-size:150px;padding:18px 40px 10px;box-shadow:14px 14px 0 {PINK}" data-layout-allow-overlap data-layout-allow-occlusion>Q-DAY</div></div>')
    for i in range(12):
        js.append(pop(f"#{sid}-lk{i}", round(0.15 + 0.035 * i, 3), d=0.34, fromScale=0.4))
    pick = C.w("l01", "every", 0.0)
    for i in range(12):
        js.append(f'tl.fromTo("#{sid}-sh{i}",{{y:0,rotation:0}},{{y:-30,rotation:-22,duration:0.26,ease:"back.out(2.4)"}},{round(pick + 0.05 * ((i * 7) % 12), 3)});')
    sfx(sc, pick, "sfx/glitch_002.ogg", 0.35)
    qt = C.w("l02", "q-day")
    js.append(slam(f"#{sid}-qday", qt, rot=-8))
    sfx(sc, qt + 0.03, "sfx/impactSoft_medium_001.ogg", 0.6)
    t3 = C.s("l03")
    js.append(f'tl.fromTo("#{sid}-lockwrap",{{x:0,y:0,scale:1}},{{x:520,y:40,scale:0.6,duration:0.7,ease:"power3.inOut"}},{t3});')
    # headline keyed to the spoken question
    title = [("HOW", "how"), ("MUCH", "much"), ("ZEC", "zec"), ("WOULD", "would"), ("SURVIVE", "survive"), ("Q-DAY?", "it")]
    spans = []
    for i, (wd, _) in enumerate(title):
        if wd == "Q-DAY?":
            spans.append(f'<span id="{sid}-tw{i}" style="display:inline-block;background:{PINK};border:4px solid #000;box-shadow:8px 8px 0 #000;padding:6px 18px 0;margin-top:10px">{wd}</span>')
        else:
            spans.append(f'<span id="{sid}-tw{i}" style="display:inline-block;margin-right:28px">{wd}</span>')
    m.append(f'<div class="abs hxl" id="{sid}-title" style="left:110px;top:200px;width:940px;font-size:128px">{spans[0]}{spans[1]}<br>{spans[2]}{spans[3]}<br>{spans[4]}<br>{spans[5]}</div>')
    for i, (_, nd) in enumerate(title):
        js.append(f'tl.fromTo("#{sid}-tw{i}",{{opacity:0,filter:"blur(10px)"}},{{opacity:1,filter:"blur(0px)",duration:0.18,ease:"power3.out"}},{C.w("l03", nd, -0.05)});')
    m.append(f'<div class="abs star" id="{sid}-star" style="left:1560px;top:70px;width:250px;height:250px;background:{YELLOW};display:flex;align-items:center;justify-content:center"><div style="font:900 30px/1 Inter;text-transform:uppercase;transform:rotate(-8deg)">Shorline</div></div>')
    m.append(f'<div class="abs" id="{sid}-starb" style="left:1560px;top:70px;width:250px;height:250px;border:0" data-layout-ignore></div>')
    js.append(pop(f"#{sid}-star", C.w("l03", "shorline"), rot=10))
    sfx(sc, C.w("l03", "shorline"), "sfx/drop_002.ogg", 0.5)
    return m, js

def scene_s02(sc, C):
    sid = "s02"; m, js = [], []
    m.append(eyebrow(sid, "01 · Keys, locks & fingerprints"))
    js.append(blurin(f"#{sid}-eyebrow", 0.4))
    m.append(f'<div class="abs hlg" id="{sid}-title" style="left:110px;top:140px">Every coin has two keys</div>')
    js.append(blurin(f"#{sid}-title", C.s("l04")))
    cards = [
        ("l05", 110, YELLOW, "key", "Private key", "Your secret. It is what lets you <b>spend</b> your coins.", "NEVER SHARE IT", PINK, -2),
        ("l06", 710, PINK, "lock", "Public key", "The <b>shape of your lock</b>. Anyone may see it.", "LIKE A LOCK'S SHAPE", BLUE, 2),
        ("l07", 1310, GREEN, "print", "T-address", "A <b>fingerprint</b> of your lock, made by a <b>hash</b>.", "HASH160 · t1…", YELLOW, -2),
    ]
    for k, (lid, x, bg, ic, title, body, tag, tagbg, rot) in enumerate(cards):
        icon = {"key": icon_key(34, 34, bg=bg), "lock": icon_lock(34, 34, bg=bg), "print": icon_print(34, 34, bg=bg)}[ic]
        extra = ""
        if ic == "print":
            extra = f'<div class="abs mono" style="left:34px;top:332px;font-size:24px;font-weight:700">t1gsBrGZ…Wip5kH8</div>'
        m.append(f'<div class="card" id="{sid}-c{k}" style="left:{x}px;top:300px;width:500px;height:470px;transform:rotate({rot}deg)">{icon}'
                 f'<div class="abs ctitle" style="left:34px;top:178px;font-size:46px">{title}</div>'
                 f'<div class="abs body" style="left:34px;top:240px;width:430px">{body}</div>{extra}'
                 f'<div class="pill" style="left:34px;top:392px;background:{tagbg};font-size:19px">{tag}</div></div>')
        js.append(f'tl.fromTo("#{sid}-c{k}",{{opacity:0,y:90,rotation:{rot*3}}},{{opacity:1,y:0,rotation:{rot},duration:0.55,ease:"expo.out"}},{C.s(lid)});')
        sfx(sc, C.s(lid) + 0.12, "sfx/drop_002.ogg", 0.45)
    for k, x in enumerate((618, 1218)):
        m.append(f'<div class="arrow" id="{sid}-a{k}" style="left:{x}px;top:520px;width:62px"></div>')
        m.append(pill(f"{sid}-ow{k}", "one-way", x - 30, 452, WHITE, BLACK, "font-size:16px;padding:6px 12px 5px"))
        js.append(f'tl.fromTo("#{sid}-a{k}",{{scaleX:0,transformOrigin:"0% 50%"}},{{scaleX:1,duration:0.3,ease:"power3.out"}},{C.s(["l06","l07"][k], 0.35)});')
        js.append(pop(f"#{sid}-ow{k}", C.s(["l06", "l07"][k], 0.5)))
    return m, js

def lane(sid, k, y, label, lbg, lcol, a, b, badge, bbg, bcol):
    return (f'<div class="cards" id="{sid}-ln{k}" style="left:110px;top:{y}px;width:1700px;height:150px">'
            f'<div class="pill" style="left:24px;top:48px;background:{lbg};color:{lcol}">{label}</div>'
            f'<div class="abs" style="left:560px;top:38px;padding:14px 22px;border:3px solid #000;background:#fff;font:900 32px/1 Inter;text-transform:uppercase">{a}</div>'
            f'<div class="arrow" style="left:880px;top:68px;width:90px"></div>'
            f'<div class="abs" style="left:1000px;top:38px;padding:14px 22px;border:3px solid #000;background:#fff;font:900 32px/1 Inter;text-transform:uppercase">{b}</div>'
            f'<div class="abs" id="{sid}-bd{k}" style="left:1340px;top:26px;width:330px;height:94px;border:4px solid #000;box-shadow:6px 6px 0 #000;background:{bbg};color:{bcol};display:flex;align-items:center;justify-content:center;font:900 30px/1.05 Inter;text-transform:uppercase;text-align:center">{badge}</div></div>')

def scene_s03(sc, C):
    sid = "s03"; m, js = [], []
    m.append(eyebrow(sid, "02 · Shor's algorithm"))
    js.append(blurin(f"#{sid}-eyebrow", 0.4))
    m.append(f'<div class="abs hlg" id="{sid}-title" style="left:110px;top:140px">From lock back to key?</div>')
    js.append(blurin(f"#{sid}-title", 0.5))
    m.append(lane(sid, 0, 300, "Today's computers", WHITE, BLACK, "Public key", "Private key", "Practically<br>impossible", GREEN, BLACK))
    m.append(lane(sid, 1, 480, "Quantum + Shor's", BLACK, WHITE, "Public key", "Private key", "Easy:<br>key stolen", EXP, WHITE))
    m.append(lane(sid, 2, 660, "Quantum vs. hash", BLACK, WHITE, "Fingerprint", "Public key", "Can't reverse:<br>still safe", GREEN, BLACK))
    js.append(slide(f"#{sid}-ln0", C.s("l08"), x=-80, y=0))
    js.append(pop(f"#{sid}-bd0", C.w("l08", "impossible"), fromScale=0.5))
    js.append(slide(f"#{sid}-ln1", C.s("l09"), x=-80, y=0))
    sfx(sc, C.s("l09", 0.05), "sfx/glitch_002.ogg", 0.4)
    js.append(slam(f"#{sid}-bd1", C.w("l09", "easy"), rot=-3, fromScale=1.6))
    sfx(sc, C.w("l09", "easy", 0.03), "sfx/impactSoft_medium_004.ogg", 0.55)
    m.append(f'<div class="card" id="{sid}-dl" style="left:1290px;top:110px;width:520px;height:160px;background:{YELLOW};transform:rotate(3deg)" data-layout-allow-overlap>'
             f'<div class="abs lbl" style="left:24px;top:22px">Jargon</div>'
             f'<div class="abs ctitle" style="left:24px;top:52px;font-size:36px">Discrete logarithm</div>'
             f'<div class="abs body" style="left:24px;top:100px;font-size:24px;width:470px">the hard math that guards the key</div></div>')
    js.append(pop(f"#{sid}-dl", C.w("l09", "discrete", -0.1), rot=3))
    js.append(slide(f"#{sid}-ln2", C.s("l10"), x=-80, y=0))
    js.append(pop(f"#{sid}-bd2", C.w("l10", "safe", -0.15), fromScale=0.5))
    sfx(sc, C.w("l10", "safe"), "sfx/drop_002.ogg", 0.45)
    return m, js

def scene_s04(sc, C):
    sid = "s04"; m, js = [], []
    m.append(eyebrow(sid, "03 · The catch"))
    js.append(blurin(f"#{sid}-eyebrow", 0.4))
    m.append(f'<div class="abs hlg" id="{sid}-title" style="left:110px;top:140px">Spending reveals the lock</div>')
    js.append(blurin(f"#{sid}-title", C.s("l11")))
    coins = "".join(f'<div class="abs" id="{sid}-coin{i}" style="left:{40 + i*150}px;top:200px;width:124px;height:124px;border:4px solid #000;box-shadow:5px 5px 0 #000;background:{GREEN};display:flex;align-items:center;justify-content:center;font:900 32px/1 Inter">ZEC</div>' for i in range(6))
    m.append(f'<div class="card" id="{sid}-addr" style="left:110px;top:280px;width:980px;height:520px">'
             f'<div class="abs lbl" style="left:40px;top:34px">Transparent address</div>'
             f'<div class="abs mono" style="left:40px;top:70px;font-size:30px;font-weight:700">t1gsBrGZGMyDGZw2icGnMpVBuEGVWip5kH8</div>'
             f'<div class="abs" id="{sid}-bh" style="left:40px;top:120px;padding:8px 16px;border:3px solid #000;background:{HASHC};font:900 26px/1 Inter;text-transform:uppercase">Hash-protected</div>'
             f'<div class="abs" id="{sid}-be" style="left:40px;top:120px;padding:8px 16px;border:3px solid #000;background:{EXP};color:#fff;font:900 26px/1 Inter;text-transform:uppercase;opacity:0">Exposed</div>'
             f'{coins}'
             f'<div class="abs" id="{sid}-new" style="left:790px;top:360px;width:124px;height:124px;border:4px solid #000;box-shadow:5px 5px 0 #000;background:{EXP};color:#fff;display:flex;align-items:center;justify-content:center;font:900 32px/1 Inter">ZEC</div>'
             f'<div class="abs lbl" id="{sid}-newl" style="left:40px;top:400px;width:700px;line-height:1.4">New funds sent here → exposed on arrival</div></div>')
    js.append(slide(f"#{sid}-addr", C.s("l11", 0.1), y=80))
    for i in range(6):
        js.append(pop(f"#{sid}-coin{i}", C.s("l11", 0.25 + 0.06 * i), fromScale=0.4))
    # first spend: coin 5 flies out
    ts = C.w("l12", "spend")
    js.append(f'tl.fromTo("#{sid}-coin5",{{x:0,opacity:1}},{{x:700,opacity:0,duration:0.5,ease:"power3.in",immediateRender:false}},{ts});')
    sfx(sc, ts, "sfx/card-slide-1.ogg", 0.4)
    tp = C.w("l12", "public")
    m.append(f'<div class="stamp" id="{sid}-rev" style="left:1150px;top:300px;background:#000;color:#fff;font-size:40px;line-height:1.08;white-space:normal;width:660px" data-layout-allow-overlap>Public key revealed:<br>on-chain forever</div>')
    js.append(slam(f"#{sid}-rev", tp, rot=-3))
    sfx(sc, tp + 0.03, "sfx/impactSoft_medium_002.ogg", 0.55)
    js.append(f'tl.fromTo("#{sid}-be",{{opacity:0}},{{opacity:1,duration:0.15}},{tp});')
    js.append(f'tl.fromTo("#{sid}-bh",{{opacity:1}},{{opacity:0,duration:0.15}},{tp});')
    tl13 = C.s("l13")
    for i in range(5):
        js.append(f'tl.fromTo("#{sid}-coin{i}",{{backgroundColor:"{GREEN}",color:"#000",rotationY:0}},{{backgroundColor:"{EXP}",color:"#fff",rotationY:360,duration:0.4,ease:"power2.inOut"}},{round(tl13 + 0.12 * i, 3)});')
    sfx(sc, tl13, "sfx/switch_002.ogg", 0.45)
    tn = C.w("l13", "anything")
    js.append(f'tl.fromTo("#{sid}-new",{{y:-420,opacity:0}},{{y:0,opacity:1,duration:0.5,ease:"bounce.out"}},{tn});')
    js.append(blurin(f"#{sid}-newl", tn + 0.3))
    m.append(f'<div class="card" id="{sid}-reuse" style="left:1150px;top:560px;width:660px;height:240px;background:{PINK};transform:rotate(2deg)">'
             f'<div class="pill" style="left:28px;top:-24px;font-size:18px">Address reuse</div>'
             f'<div class="abs stat" style="left:28px;top:40px;font-size:86px">239,139</div>'
             f'<div class="abs body" style="left:28px;top:136px;width:600px;font-size:25px">funded addresses kept receiving after their key went public</div></div>')
    js.append(slide(f"#{sid}-reuse", C.s("l14"), y=80, rot=2))
    sfx(sc, C.s("l14", 0.1), "sfx/drop_002.ogg", 0.4)
    return m, js

def scene_s05(sc, C):
    sid = "s05"; m, js = [], []
    m.append('<div class="dots"></div>')
    m.append(eyebrow(sid, "04 · Zcash's quantum plan"))
    js.append(blurin(f"#{sid}-eyebrow", 0.5))
    m.append(f'<div class="abs hlg" id="{sid}-title" style="left:110px;top:140px">Zcash is preparing</div>')
    js.append(blurin(f"#{sid}-title", C.s("l15")))
    pools = [("Transparent", "t1… / t3…"), ("Sprout", "2016 · shielded"), ("Sapling", "2018 · shielded"), ("Orchard", "2022 · shielded"), ("Ironwood", "2026 · NU6.3")]
    for k, (n, sub) in enumerate(pools):
        x = 110 + k * 345
        m.append(f'<div class="card" id="{sid}-p{k}" style="left:{x}px;top:260px;width:320px;height:190px">'
                 f'<div class="abs ctitle" style="left:22px;top:40px;font-size:38px">{n}</div>'
                 f'<div class="abs lbl" style="left:22px;top:104px;font-size:19px">{sub}</div></div>')
        js.append(pop(f"#{sid}-p{k}", C.s("l15", 0.15 + 0.08 * k), fromScale=0.7))
    t16 = C.w("l16", "ironwood")
    js.append(f'tl.fromTo("#{sid}-p4",{{backgroundColor:"#ffffff"}},{{backgroundColor:"{REC}",duration:0.3}},{t16});')
    m.append(pill(f"{sid}-rec", "Recoverable after Q-Day · ZIP 2005", 1150, 476, GREEN))
    js.append(pop(f"#{sid}-rec", C.w("l16", "2005")))
    sfx(sc, C.w("l16", "2005"), "sfx/drop_002.ogg", 0.45)
    t17 = C.w("l17", "sprout")
    for k in (1, 2, 3):
        js.append(f'tl.fromTo("#{sid}-p{k}",{{backgroundColor:"#ffffff"}},{{backgroundColor:"{STR}",duration:0.25}},{round(C.w("l17", ["sprout","sapling","orchard"][k-1]) , 3)});')
    m.append(f'<div class="stamp" id="{sid}-str" style="left:640px;top:300px;background:#fff;font-size:64px" data-layout-allow-overlap data-layout-allow-occlusion>Stranded</div>')
    js.append(slam(f"#{sid}-str", C.w("l17", "stranded", -0.05), rot=-7))
    sfx(sc, C.w("l17", "stranded"), "sfx/impactSoft_medium_001.ogg", 0.55)
    js.append(f'tl.fromTo("#{sid}-p0",{{backgroundColor:"#ffffff"}},{{backgroundColor:"{UNK}",duration:0.3}},{C.s("l18")});')
    m.append(pill(f"{sid}-z7", "ZIP 2007: which t-coins can be saved?", 110, 476, WHITE))
    js.append(pop(f"#{sid}-z7", C.w("l18", "2007")))
    m.append(f'<div class="card" id="{sid}-q" style="left:110px;top:560px;width:1150px;height:250px;background:#fff">'
             f'<div class="pill" style="left:30px;top:-24px;background:{BLUE}">zcash/zips #1302 · next step</div>'
             f'<div class="abs" style="left:34px;top:46px;width:1080px;font:900 46px/1.12 Inter;letter-spacing:-0.02em;text-transform:uppercase">“Survey the chain to see what proportion of funds are currently recoverable.”</div></div>')
    js.append(slide(f"#{sid}-q", C.w("l18", "survey", -0.1), y=70))
    m.append(f'<div class="stamp" id="{sid}-none" style="left:1310px;top:640px;background:{PINK};font-size:40px;line-height:1.05;white-space:normal;width:500px" data-layout-allow-overlap>No one had<br>published it</div>')
    js.append(slam(f"#{sid}-none", C.w("l18", "published", -0.15), rot=5))
    sfx(sc, C.w("l18", "published"), "sfx/impactSoft_medium_004.ogg", 0.55)
    return m, js

def scene_s06(sc, C):
    sid = "s06"; m, js = [], []
    m.append(eyebrow(sid, "05 · How Shorline works"))
    js.append(blurin(f"#{sid}-eyebrow", 0.35))
    m.append(logo_mark(110, 128, 104, f"{sid}-logo"))
    m.append(f'<div class="abs hlg" id="{sid}-title" style="left:250px;top:144px">So we built Shorline</div>')
    js.append(pop(f"#{sid}-logo", C.s("l19"), rot=0))
    js.append(blurin(f"#{sid}-title", C.s("l19", 0.08)))
    steps = [
        ("Stream", "Every block since 2016 from public lightwalletd", "3,583,893 blocks", PINK, ("l20", "streams")),
        ("Replay", "A Rust engine re-applies every transparent input and output", "191,264,244 outputs", YELLOW, ("l21", "rust")),
        ("UTXO set", "The list of unspent coins, rebuilt in memory", "27,200,690 live", BLUE, ("l21", "utxo")),
        ("Key reveals", "The exact block each address's key went public", "9,470,343 owners", WHITE, ("l21", "moment")),
    ]
    for k, (t_, body, num, bg, (lid, wd)) in enumerate(steps):
        x = 110 + k * 430
        m.append(f'<div class="card" id="{sid}-st{k}" style="left:{x}px;top:300px;width:380px;height:380px">'
                 f'<div class="abs" style="left:24px;top:24px;width:70px;height:70px;border:3px solid #000;background:{bg};font:900 36px/70px Inter;text-align:center">{k+1}</div>'
                 f'<div class="abs ctitle" style="left:24px;top:116px;font-size:40px">{t_}</div>'
                 f'<div class="abs body" style="left:24px;top:170px;width:330px;font-size:25px">{body}</div>'
                 f'<div class="abs mono" id="{sid}-n{k}" style="left:24px;top:316px;font-size:22px;font-weight:700;text-transform:uppercase">{num}</div></div>')
        js.append(f'tl.fromTo("#{sid}-st{k}",{{opacity:0,y:70}},{{opacity:1,y:0,duration:0.5,ease:"expo.out"}},{C.w(lid, wd, -0.1)});')
        sfx(sc, C.w(lid, wd), "sfx/card-slide-1.ogg" if k % 2 else "sfx/drop_002.ogg", 0.38)
        if k < 3:
            m.append(f'<div class="abs" id="{sid}-cn{k}" style="left:{x+388}px;top:484px;width:46px;height:12px;background:#000"></div>')
            js.append(f'tl.fromTo("#{sid}-cn{k}",{{scaleX:0,transformOrigin:"0% 50%"}},{{scaleX:1,duration:0.25}},{C.w(steps[k+1][4][0], steps[k+1][4][1], -0.2)});')
    js.append(counter(f"#{sid}-n1", C.w("l21", "rust", 0.3), 2.2, 191264244, 'Math.round(v).toLocaleString("en-US")+" outputs"'))
    for k, (txt, bg, wd) in enumerate((("No full node", WHITE, "node"), ("No disk", PINK, "disk"), ("~31 minutes", YELLOW, "thirty"))):
        m.append(f'<div class="stamp" id="{sid}-sp{k}" style="left:{110 + k*560}px;top:720px;background:{bg};font-size:44px">{txt}</div>')
        js.append(slam(f"#{sid}-sp{k}", C.w("l22", wd, -0.08), rot=[-3, 2, -2][k], fromScale=1.6))
        sfx(sc, C.w("l22", wd), "sfx/impactSoft_medium_00%d.ogg" % [1, 2, 4][k], 0.45)
    return m, js

def scene_s07(sc, C):
    sid = "s07"; m, js = [], []
    m.append(eyebrow(sid, "06 · Verified to the zatoshi"))
    js.append(blurin(f"#{sid}-eyebrow", 0.4))
    m.append(f'<div class="abs hlg" id="{sid}-title" style="left:110px;top:140px">It checks itself</div>')
    js.append(blurin(f"#{sid}-title", C.s("l23")))
    m.append(f'<div class="card" id="{sid}-zat" style="left:1210px;top:96px;width:600px;height:190px;background:{YELLOW};transform:rotate(3deg)">'
             f'<div class="abs lbl" style="left:26px;top:22px">Jargon</div>'
             f'<div class="abs ctitle" style="left:26px;top:52px;font-size:40px">1 zatoshi =</div>'
             f'<div class="abs mono" style="left:26px;top:100px;font-size:36px;font-weight:700">0.00000001 ZEC</div>'
             f'<div class="abs body" style="left:26px;top:146px;font-size:22px">the smallest unit, like a cent to a dollar</div></div>')
    js.append(pop(f"#{sid}-zat", C.s("l24"), rot=3))
    for k, (x, lbl, bg) in enumerate(((110, "Zebra node · transparent value pool", WHITE), (1030, "Shorline · replayed UTXO set", WHITE))):
        m.append(f'<div class="card" id="{sid}-v{k}" style="left:{x}px;top:360px;width:780px;height:270px;background:{bg}">'
                 f'<div class="pill" style="left:28px;top:-24px;background:{[BLUE, PINK][k]}">{lbl}</div>'
                 f'<div class="abs" id="{sid}-num{k}" style="left:30px;top:78px;font:900 60px/1 Inter;letter-spacing:-0.03em;font-variant-numeric:tabular-nums">12,037,446.98852579</div>'
                 f'<div class="abs ctitle" style="left:30px;top:180px;font-size:40px">ZEC</div></div>')
    m.append(f'<div class="abs" id="{sid}-eq" style="left:893px;top:440px;font:900 110px/1 Inter">=</div>')
    t25 = C.s("l25")
    js.append(slide(f"#{sid}-v0", t25, x=-90, y=0))
    js.append(slide(f"#{sid}-v1", t25 + 0.35, x=90, y=0))
    js.append(counter(f"#{sid}-num1", t25 + 0.5, 2.3, 1203744698852579, '(Math.floor(v/1e8)).toLocaleString("en-US")+"."+String(Math.floor(v%1e8)).padStart(8,"0")'))
    js.append(pop(f"#{sid}-eq", t25 + 0.4))
    tz = C.w("l25", "zatoshi")
    m.append(f'<div class="stamp" id="{sid}-ok" style="left:560px;top:670px;background:{GREEN};font-size:64px;box-shadow:12px 12px 0 #000" data-layout-allow-overlap>Exact match ✓</div>')
    js.append(slam(f"#{sid}-ok", tz - 0.05, rot=-4))
    sfx(sc, tz, "sfx/bong_001.ogg", 0.65)
    m.append(pill(f"{sid}-zero", "0 unmatched inputs · block 3,583,892", 1210, 700, WHITE))
    js.append(pop(f"#{sid}-zero", tz + 0.45))
    return m, js

def scene_s08(sc, C):
    sid = "s08"; m, js = [], []
    m.append(eyebrow(sid, "07 · The answer"))
    js.append(blurin(f"#{sid}-eyebrow", 0.6))
    m.append(f'<div class="abs" id="{sid}-hero" style="left:104px;top:120px;font:900 250px/0.9 Inter;letter-spacing:-0.045em">7.24M</div>')
    m.append(f'<div class="abs hlg" id="{sid}-zec" style="left:880px;top:268px;font-size:96px">ZEC</div>')
    t27 = C.s("l27")
    js.append(blurin(f"#{sid}-hero", t27 - 0.1))
    js.append(counter(f"#{sid}-hero", t27, 1.5, 7.24, 'v.toFixed(2)+"M"'))
    js.append(blurin(f"#{sid}-zec", t27 + 0.2))
    sfx(sc, t27 + 1.5, "sfx/impactSoft_medium_001.ogg", 0.5)
    m.append(f'<div class="abs star" id="{sid}-pct" style="left:1090px;top:96px;width:300px;height:300px;background:{PINK};display:flex;align-items:center;justify-content:center;flex-direction:column"><div style="font:900 64px/1 Inter;letter-spacing:-0.03em">42.5%</div><div style="font:700 19px/1.1 \'Space Mono\';text-transform:uppercase;text-align:center">of all ZEC</div></div>')
    js.append(pop(f"#{sid}-pct", C.w("l27", "42.5%", -0.1), rot=-8))
    m.append(f'<div class="abs hmd" id="{sid}-sub" style="left:110px;top:400px;width:1100px">Sits behind public keys already on-chain</div>')
    js.append(blurin(f"#{sid}-sub", C.w("l27", "sits", -0.1)))
    m.append(f'<div class="card" id="{sid}-usd" style="left:1430px;top:150px;width:390px;height:250px;background:{YELLOW};transform:rotate(4deg)">'
             f'<div class="abs lbl" style="left:24px;top:24px">At today\'s price</div>'
             f'<div class="abs stat" style="left:24px;top:62px;font-size:84px">≈$6.8B</div>'
             f'<div class="abs mono" style="left:24px;top:170px;font-size:18px;line-height:1.35">$934.28 / ZEC<br>Blockchair · 17 Nov 2026</div></div>')
    js.append(pop(f"#{sid}-usd", C.s("l28"), rot=4))
    sfx(sc, C.s("l28", 0.1), "sfx/drop_002.ogg", 0.45)
    # fate bar
    parts = [("Exposed", 724016638148549, EXP, "#fff", "7.24M"), ("Hash-protected", 436690062005874, HASHC, "#000", "4.37M"),
             ("Unknown P2SH", 43037997681367, UNK, "#000", "430K"), ("Stranded", 74902662466408, STR, "#000", "749K"),
             ("Lockbox", 7696893709512, LOCK, "#fff", "77K"), ("Recoverable", 418383305606669, REC, "#000", "4.18M")]
    total = sum(p[1] for p in parts)
    x, segs, chips = 0, [], []
    width = 1692 - 3 * 5
    times = [C.w("l27", "sits"), C.s("l29", 0.1), C.e("l29", -0.6), C.w("l30", "stranded", -0.2), C.w("l30", "pools"), C.w("l30", "4.18", -0.1)]
    for k, (n, z, col, ink, short) in enumerate(parts):
        wpx = max(8, round(width * z / total))
        label = f'<span style="font:900 30px/1 Inter;color:{ink};padding-left:14px">{round(100*z/total,1)}%</span>' if wpx > 140 else ""
        segs.append(f'<div class="abs" id="{sid}-seg{k}" style="left:{x}px;top:0;width:{wpx}px;height:100%;background:{col};display:flex;align-items:center;border-right:3px solid #000">{label}</div>')
        x += wpx + 3
        chips.append(f'<div class="chip" id="{sid}-ch{k}" style="position:absolute;left:{(k%3)*560}px;top:{(k//3)*52}px"><span class="sw" style="background:{col}"></span>{n} · {short}</div>')
    m.append(f'<div class="abs" id="{sid}-bar" style="left:110px;top:560px;width:1700px;height:96px;border:4px solid #000;box-shadow:8px 8px 0 #000;background:#fff;overflow:hidden">{"".join(segs)}</div>')
    m.append(f'<div class="abs" style="left:114px;top:700px;width:1700px;height:110px">{"".join(chips)}</div>')
    for k, tt in enumerate(times):
        js.append(f'tl.fromTo("#{sid}-seg{k}",{{scaleX:0,transformOrigin:"0% 50%"}},{{scaleX:1,duration:0.45,ease:"power3.out"}},{round(tt,3)});')
        js.append(blurin(f"#{sid}-ch{k}", round(tt + 0.2, 3)))
    return m, js

def scene_s09(sc, C):
    sid = "s09"; m, js = [], []
    m.append(eyebrow(sid, "08 · It's getting worse"))
    js.append(blurin(f"#{sid}-eyebrow", 0.4))
    m.append(f'<div class="abs hlg" id="{sid}-title" style="left:110px;top:140px">Exposure is accelerating</div>')
    js.append(blurin(f"#{sid}-title", C.s("l31")))
    # chart from real series
    pw, ph, px0, py0 = 1050, 420, 70, 40
    t0, t1 = SERIES[0][0], SERIES[-1][0]
    ymax = 10_000_000
    X = lambda tt: px0 + (tt - t0) / (t1 - t0) * pw
    Y = lambda v: py0 + ph - v / ymax * ph
    pe = "M" + " L".join(f"{X(p[0]):.1f} {Y(p[1]):.1f}" for p in SERIES)
    ph_ = "M" + " L".join(f"{X(p[0]):.1f} {Y(p[2]):.1f}" for p in SERIES)
    import datetime as dt
    grid = []
    for v in (0, 2_500_000, 5_000_000, 7_500_000, 10_000_000):
        grid.append(f'<line x1="{px0}" x2="{px0+pw}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#000" stroke-opacity="{0.9 if v==0 else 0.15}" stroke-width="{3 if v==0 else 2}"/>'
                    f'<text x="{px0-12}" y="{Y(v)+7:.1f}" text-anchor="end" font-family="Space Mono" font-size="19" font-weight="700">{"0" if v==0 else (str(v/1e6).rstrip("0").rstrip(".")+"M")}</text>')
    for yr in range(2017, 2027):
        tt = dt.datetime(yr, 1, 1, tzinfo=dt.timezone.utc).timestamp()
        if t0 < tt < t1:
            grid.append(f'<text x="{X(tt):.1f}" y="{py0+ph+30}" text-anchor="middle" font-family="Space Mono" font-size="19" font-weight="700">{yr}</text>')
    f0 = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc).timestamp(); f1 = dt.datetime(2026, 11, 3, tzinfo=dt.timezone.utc).timestamp()
    band = f'<rect id="{sid}-band" x="{X(f0)-6:.1f}" y="{py0}" width="{max(14, X(f1)-X(f0)+12):.1f}" height="{ph}" fill="{PINK}" stroke="#000" stroke-width="3"/>'
    svg = (f'<svg width="1170" height="520" viewBox="0 0 1170 520">{"".join(grid)}{band}'
           f'<path id="{sid}-lh" d="{ph_}" fill="none" stroke="{HASHC}" stroke-width="6" stroke-linejoin="miter" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>'
           f'<path id="{sid}-le" d="{pe}" fill="none" stroke="{EXP}" stroke-width="6" stroke-linejoin="miter" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/></svg>')
    m.append(f'<div class="card" id="{sid}-chart" style="left:110px;top:250px;width:1180px;height:560px">'
             f'<div class="abs" style="left:96px;top:22px;display:flex;gap:30px"><span class="chip"><span class="sw" style="background:{EXP}"></span>Exposed</span><span class="chip"><span class="sw" style="background:{HASHC}"></span>Hash-protected</span></div>'
             f'<div class="abs" style="left:0;top:30px">{svg}</div></div>')
    tc = C.s("l31", 0.1)
    js.append(slide(f"#{sid}-chart", tc - 0.1, y=60))
    js.append(f'tl.fromTo("#{sid}-lh",{{strokeDashoffset:1}},{{strokeDashoffset:0,duration:2.6,ease:"power1.inOut"}},{tc + 0.25});')
    js.append(f'tl.fromTo("#{sid}-le",{{strokeDashoffset:1}},{{strokeDashoffset:0,duration:2.6,ease:"power1.inOut"}},{tc + 0.35});')
    js.append(f'tl.fromTo("#{sid}-band",{{opacity:0}},{{opacity:1,duration:0.25}},{C.w("l33", "nine", -0.1)});')
    m.append(f'<div class="card" id="{sid}-k1" style="left:1340px;top:250px;width:470px;height:250px;background:{YELLOW};transform:rotate(-2deg)">'
             f'<div class="abs stat" style="left:28px;top:30px;font-size:104px">79%</div>'
             f'<div class="abs body" style="left:28px;top:140px;width:420px;font-size:25px">of exposed ZEC had its key revealed since Jan 2025</div></div>')
    js.append(pop(f"#{sid}-k1", C.w("l32", "79%", -0.1), rot=-2))
    sfx(sc, C.w("l32", "79%"), "sfx/drop_002.ogg", 0.45)
    m.append(f'<div class="card" id="{sid}-k2" style="left:1340px;top:550px;width:470px;height:260px;background:{EXP};color:#fff;transform:rotate(2deg)">'
             f'<div class="abs stat" style="left:28px;top:30px;font-size:96px;color:#fff">1.0M ZEC</div>'
             f'<div class="abs body" style="left:28px;top:138px;width:420px;font-size:25px;color:#fff">flipped from safe to exposed in 9 days (25 Oct – 3 Nov 2026)</div></div>')
    js.append(slam(f"#{sid}-k2", C.w("l33", "million", -0.1), rot=2, fromScale=1.5))
    sfx(sc, C.w("l33", "flipped"), "sfx/switch_002.ogg", 0.5)
    return m, js

def scene_s10(sc, C):
    sid = "s10"; m, js = [], []
    m.append('<div class="dots"></div>')
    m.append(eyebrow(sid, "09 · Hidden exposure"))
    js.append(blurin(f"#{sid}-eyebrow", 0.4))
    m.append(f'<div class="abs hlg" id="{sid}-title" style="left:110px;top:140px">What explorers can’t see</div>')
    js.append(blurin(f"#{sid}-title", C.s("l34")))
    # salted multisig card
    m.append(f'<div class="card" id="{sid}-salt" style="left:110px;top:270px;width:940px;height:550px">'
             f'<div class="pill" style="left:30px;top:-24px;background:{YELLOW}">Salted multisig</div>'
             f'<div class="abs mono" style="left:30px;top:44px;width:880px;padding:22px 26px;background:#000;color:#fff;font-size:27px;line-height:1.5;border:3px solid #000">'
             f'OP_2 &lt;K1&gt; &lt;K2&gt; &lt;K3&gt; OP_3 CHECKMULTISIGVERIFY<br>'
             f'<span id="{sid}-slot" style="background:{YELLOW};color:#000;padding:0 8px">SALT 0x????????</span> DROP DEPTH 0 EQUAL</div>'
             f'<div class="abs" style="left:30px;top:226px;display:flex;gap:22px">'
             f'<div class="cards" id="{sid}-f0" style="position:relative;padding:14px 18px;background:{BLUE}"><div class="lbl">Key sets</div><div style="font:900 50px/1 Inter;margin-top:6px">1</div></div>'
             f'<div class="cards" id="{sid}-f1" style="position:relative;padding:14px 18px;background:{PINK}"><div class="lbl">Addresses</div><div style="font:900 50px/1 Inter;margin-top:6px">39</div></div>'
             f'<div class="cards" id="{sid}-f2" style="position:relative;padding:14px 18px;background:{GREEN}"><div class="lbl">ZEC guarded</div><div style="font:900 50px/1 Inter;margin-top:6px">996,041</div></div></div>'
             f'<div class="abs" id="{sid}-cnt" style="left:30px;top:376px;font:900 46px/1 Inter;letter-spacing:-0.02em">0 salts tried</div>'
             f'<div class="abs" style="left:30px;top:446px;display:flex;gap:18px">'
             f'<div class="cards" id="{sid}-r0" style="position:relative;padding:12px 16px;background:{GREEN};font:900 28px/1 Inter;text-transform:uppercase">39/39 rediscovered ✓</div>'
             f'<div class="cards" id="{sid}-r1" style="position:relative;padding:12px 16px;background:{EXP};color:#fff;font:900 28px/1 Inter;text-transform:uppercase">+9 hidden · 168.88 ZEC</div></div></div>')
    js.append(slide(f"#{sid}-salt", C.s("l35", -0.05), y=70))
    for k, wd in enumerate(("three", "39", "996")):
        js.append(pop(f"#{sid}-f{k}", C.w("l35", wd, -0.05)))
    # slot machine for salt + counter
    t36 = C.s("l36")
    js.append('(function(){const el=document.querySelector("#' + sid + '-slot");const o={v:0};'
              f'tl.fromTo(o,{{v:0}},{{v:1,duration:3.4,ease:"none",onUpdate:function(){{let n=Math.floor(o.v*90)+1;let x=(n*2654435761)>>>0;el.textContent="SALT 0x"+x.toString(16).toUpperCase().padStart(8,"0");}}}},{t36});'
              '})();')
    js.append(counter(f"#{sid}-cnt", t36 + 0.1, 3.3, 4294967296, 'Math.round(v).toLocaleString("en-US")+" salts tried · 280 s"', ir=False))
    for k in range(4):
        sfx(sc, t36 + 0.2 + k * 0.75, ["sfx/keypress-003.wav", "sfx/keypress-012.wav", "sfx/keypress-007.wav", "sfx/keypress-018.wav"][k], 0.3)
    js.append(pop(f"#{sid}-r0", C.w("l36", "unmasked", -0.4)))
    js.append(slam(f"#{sid}-r1", C.w("l36", "9", -0.05), rot=-2, fromScale=1.4))
    sfx(sc, C.w("l36", "9"), "sfx/impactSoft_medium_002.ogg", 0.5)
    # Ycash fork card
    blocks = "".join(f'<div class="abs" style="left:{30 + i*58}px;top:220px;width:42px;height:42px;border:3px solid #000;background:{WHITE}"></div>' for i in range(5))
    zc = "".join(f'<div class="abs" style="left:{350 + i*58}px;top:120px;width:42px;height:42px;border:3px solid #000;background:{BLUE}"></div>' for i in range(5))
    yc = "".join(f'<div class="abs" style="left:{350 + i*58}px;top:320px;width:42px;height:42px;border:3px solid #000;background:{PINK}"></div>' for i in range(5))
    m.append(f'<div class="card" id="{sid}-yc" style="left:1100px;top:270px;width:710px;height:550px">'
             f'<div class="pill" style="left:30px;top:-24px;background:{PINK}">Ycash fork · 2019</div>'
             f'{blocks}'
             f'<div class="abs" id="{sid}-br1" style="left:322px;top:236px;width:110px;height:10px;background:#000;transform-origin:0% 50%;transform:rotate(-55deg)"></div>'
             f'<div class="abs" id="{sid}-br2" style="left:322px;top:236px;width:110px;height:10px;background:#000;transform-origin:0% 50%;transform:rotate(55deg)"></div>'
             f'<div id="{sid}-zc">{zc}<div class="abs lbl" style="left:350px;top:84px">Zcash</div></div>'
             f'<div id="{sid}-ycb">{yc}<div class="abs lbl" style="left:350px;top:376px">Ycash</div></div>'
             f'<div class="abs lbl" style="left:30px;top:278px">block 570,000</div>'
             f'<div class="abs" id="{sid}-yres" style="left:30px;top:430px;width:650px;padding:16px 20px;border:4px solid #000;box-shadow:6px 6px 0 #000;background:{EXP};color:#fff;font:900 34px/1.1 Inter;text-transform:uppercase">51 addresses · 4,181 ZEC exposed via Ycash</div></div>')
    t37 = C.s("l37")
    js.append(slide(f"#{sid}-yc", t37 - 0.15, y=70))
    js.append(f'tl.fromTo("#{sid}-zc",{{opacity:0,x:-40}},{{opacity:1,x:0,duration:0.4,ease:"expo.out"}},{C.w("l37","copy",-0.1)});')
    js.append(f'tl.fromTo("#{sid}-ycb",{{opacity:0,x:-40}},{{opacity:1,x:0,duration:0.4,ease:"expo.out"}},{C.w("l37","copy",0.15)});')
    js.append(slam(f"#{sid}-yres", C.w("l37", "51", -0.05), rot=-2, fromScale=1.3))
    sfx(sc, C.w("l37", "51"), "sfx/impactSoft_medium_004.ogg", 0.5)
    return m, js

def scene_s11(sc, C):
    sid = "s11"; m, js = [], []
    m.append(eyebrow(sid, "10 · The live dashboard"))
    js.append(blurin(f"#{sid}-eyebrow", 0.35))
    m.append(f'<div class="card" id="{sid}-win" style="left:110px;top:130px;width:1120px;height:700px;overflow:hidden">'
             f'<div class="abs" style="left:0;top:0;width:1120px;height:54px;background:{YELLOW};border-bottom:4px solid #000">'
             f'<div class="abs" style="left:18px;top:15px;width:20px;height:20px;border:3px solid #000;background:{PINK}"></div>'
             f'<div class="abs" style="left:48px;top:15px;width:20px;height:20px;border:3px solid #000;background:{BLUE}"></div>'
             f'<div class="abs" style="left:78px;top:15px;width:20px;height:20px;border:3px solid #000;background:{GREEN}"></div>'
             f'<div class="abs mono" style="left:130px;top:9px;padding:6px 16px;border:3px solid #000;background:#fff;font-size:19px;font-weight:700">jmohak2004.github.io/shorline</div></div>'
             f'<div class="abs" style="left:0;top:58px;width:1112px;height:634px;overflow:hidden">'
             f'<img id="{sid}-shot" src="assets/img/dashboard-hero.jpg" style="position:absolute;left:0;top:0;width:1112px;height:auto;transform-origin:0% 60%" alt=""></div>'
             # checker overlay (recreated UI, simulated interaction)
             f'<div class="abs" id="{sid}-chk" style="left:0;top:58px;width:1112px;height:634px;background:{OFF}">'
             f'<div class="abs ctitle" style="left:46px;top:40px;font-size:44px">Check an address</div>'
             f'<div class="abs" style="left:46px;top:116px;width:820px;height:70px;border:4px solid #000;background:#fff;box-shadow:5px 5px 0 #000">'
             f'<div class="abs mono" id="{sid}-typed" style="left:18px;top:18px;font-size:27px;font-weight:700;white-space:nowrap"></div></div>'
             f'<div class="abs" id="{sid}-btn" style="left:890px;top:116px;width:170px;height:70px;border:4px solid #000;box-shadow:5px 5px 0 #000;background:#000;color:#fff;font:900 30px/62px Inter;text-align:center;text-transform:uppercase">Check</div>'
             f'<div class="abs" id="{sid}-res" style="left:46px;top:226px;width:1014px;height:350px;border:4px solid #000;box-shadow:8px 8px 0 #000;background:#fff">'
             f'<div class="abs" style="left:30px;top:30px;padding:10px 18px;border:3px solid #000;background:{EXP};color:#fff;font:900 34px/1 Inter;text-transform:uppercase">Exposed</div>'
             f'<div class="abs" style="left:30px;top:104px;font:900 72px/1 Inter;letter-spacing:-0.03em">259,122.13 ZEC</div>'
             f'<div class="abs body" style="left:30px;top:196px;width:950px;font-size:27px">Public key revealed at block 3,140,430 (Nov 2025). Move funds to a fresh Ironwood address and never reuse this one.</div></div></div></div>')
    t38 = C.s("l38")
    js.append(slide(f"#{sid}-win", t38 - 0.1, y=60))
    js.append(f'tl.fromTo("#{sid}-shot",{{scale:1,y:0}},{{scale:1.18,y:-60,duration:3.2,ease:"power1.inOut"}},{t38 + 0.2});')
    t39 = C.s("l39")
    js.append(f'tl.fromTo("#{sid}-chk",{{opacity:0,y:40}},{{opacity:1,y:0,duration:0.35,ease:"expo.out"}},{t39 - 0.2});')
    addr = "t1gsBrGZGMyDGZw2icGnMpVBuEGVWip5kH8"
    ty0, tyd = t39 + 0.15, 1.15
    js.append('(function(){const el=document.querySelector("#' + sid + '-typed");const s="' + addr + '";const o={v:0};'
              f'tl.fromTo(o,{{v:0}},{{v:s.length,duration:{tyd},ease:"none",onUpdate:function(){{el.textContent=s.slice(0,Math.round(o.v));}}}},{ty0});'
              '})();')
    for k in range(6):
        sfx(sc, ty0 + k * 0.19, f"sfx/keypress-0{['03','07','12','18','24','07'][k]}.wav", 0.32)
    tclick = C.w("l39", "shorline", -0.05)
    js.append(f'tl.fromTo("#{sid}-btn",{{scale:1}},{{scale:0.92,duration:0.08,yoyo:true,repeat:1,ease:"power2.out"}},{tclick});')
    sfx(sc, tclick, "sfx/click_003.ogg", 0.6)
    js.append(f'tl.fromTo("#{sid}-res",{{opacity:0,y:40}},{{opacity:1,y:0,duration:0.4,ease:"expo.out"}},{C.w("l39", "exposed", -0.15)});')
    sfx(sc, C.w("l39", "exposed"), "sfx/drop_002.ogg", 0.45)
    # privacy diagram
    t40 = C.s("l40")
    m.append(f'<div class="cards" id="{sid}-pb" style="left:1290px;top:150px;width:520px;height:150px;background:{PINK}">'
             f'<div class="abs ctitle" style="left:24px;top:22px;font-size:36px">Your browser</div>'
             f'<div class="abs body" style="left:24px;top:76px;font-size:23px;width:470px">searches the shard locally</div></div>')
    m.append(f'<div class="abs" id="{sid}-ar" style="left:1530px;top:318px;width:12px;height:70px;background:#000"></div>')
    m.append(f'<div class="cards" id="{sid}-ps" style="left:1290px;top:400px;width:520px;height:170px;background:{WHITE}">'
             f'<div class="abs lbl" style="left:24px;top:22px">Downloads one shard</div>'
             f'<div class="abs mono" style="left:24px;top:56px;font-size:32px;font-weight:700">t1_2312.json</div>'
             f'<div class="abs body" style="left:24px;top:104px;font-size:23px;width:470px">628 funded addresses inside</div></div>')
    m.append(f'<div class="cards" id="{sid}-pk" style="left:1290px;top:610px;width:520px;height:200px;background:{GREEN}">'
             f'<div class="abs lbl" style="left:24px;top:22px">Jargon: k-anonymity</div>'
             f'<div class="abs ctitle" style="left:24px;top:56px;font-size:36px">Hidden in a crowd</div>'
             f'<div class="abs body" style="left:24px;top:104px;font-size:23px;width:470px">the site sees a 628-address group, never your address</div></div>')
    js.append(slide(f"#{sid}-pb", C.w("l40", "browser", -0.1), x=60, y=0))
    js.append(f'tl.fromTo("#{sid}-ar",{{scaleY:0,transformOrigin:"50% 0%"}},{{scaleY:1,duration:0.25}},{C.w("l40", "shard", -0.2)});')
    js.append(slide(f"#{sid}-ps", C.w("l40", "shard", -0.05), x=60, y=0))
    js.append(slide(f"#{sid}-pk", C.w("l40", "k-anonymity", -0.2), x=60, y=0))
    sfx(sc, C.w("l40", "k-anonymity"), "sfx/drop_002.ogg", 0.4)
    return m, js

def scene_s12(sc, C):
    sid = "s12"; m, js = [], []
    m.append(eyebrow(sid, "11 · Why Shorline is different"))
    js.append(blurin(f"#{sid}-eyebrow", 0.35))
    m.append(f'<div class="abs hlg" id="{sid}-title" style="left:110px;top:140px">What makes it different</div>')
    js.append(blurin(f"#{sid}-title", C.s("l41")))
    feats = [
        ("Answers ZIP 2007", "Completes the open task in zcash/zips #1302: survey the whole chain.", PINK, ("l42", "complete")),
        ("Proven to the zatoshi", "Its UTXO total equals Zebra's value pool exactly.", YELLOW, ("l43", "proves")),
        ("Finds hidden exposure", "Salt sweep + Ycash fork analysis.", BLUE, ("l43", "finds")),
        ("Private by design", "k-anonymous lookups that never send your address.", GREEN, ("l43", "protects")),
        ("One command · MIT", "cargo run --release -- scan, on public infrastructure.", WHITE, ("l43", "reproduce")),
    ]
    pos = [(110, 260), (690, 260), (1270, 260), (400, 560), (980, 560)]
    for k, (t_, body, bg, (lid, wd)) in enumerate(feats):
        x, y = pos[k]
        rot = [-2, 1, -1, 2, -2][k]
        m.append(f'<div class="card" id="{sid}-f{k}" style="left:{x}px;top:{y}px;width:540px;height:250px;transform:rotate({rot}deg)">'
                 f'<div class="abs" style="left:24px;top:24px;width:64px;height:64px;border:3px solid #000;background:{bg};font:900 30px/58px Inter;text-align:center">0{k+1}</div>'
                 f'<div class="abs ctitle" style="left:110px;top:28px;width:410px;font-size:34px">{t_}</div>'
                 f'<div class="abs body" style="left:24px;top:120px;width:490px;font-size:25px">{body}</div></div>')
        js.append(f'tl.fromTo("#{sid}-f{k}",{{opacity:0,y:70,rotation:{rot*4}}},{{opacity:1,y:0,rotation:{rot},duration:0.5,ease:"expo.out"}},{C.w(lid, wd, -0.12)});')
        sfx(sc, C.w(lid, wd), "sfx/card-slide-1.ogg" if k % 2 else "sfx/drop_002.ogg", 0.35)
    return m, js

def scene_s13(sc, C):
    sid = "s13"; m, js = [], []
    m.append(eyebrow(sid, "12 · Who it's for & the numbers"))
    js.append(blurin(f"#{sid}-eyebrow", 0.5))
    m.append(f'<div class="abs hlg" id="{sid}-title" style="left:110px;top:140px;font-size:66px">Built for</div>')
    js.append(blurin(f"#{sid}-title", C.s("l44")))
    aud = [("Exchanges & custodians", PINK, "exchanges"), ("Wallet builders", BLUE, "wallet"), ("Zcash protocol team", GREEN, "protocol"), ("Every ZEC holder", WHITE, "2007")]
    for k, (t_, bg, wd) in enumerate(aud):
        m.append(f'<div class="cards" id="{sid}-a{k}" style="left:110px;top:{250 + k*118}px;width:760px;height:96px;background:{bg};font:900 40px/90px Inter;text-transform:uppercase;padding-left:26px;letter-spacing:-0.015em">{t_}</div>')
        js.append(slide(f"#{sid}-a{k}", C.w("l44", wd, -0.1 if k < 3 else 0.2), x=-70, y=0))
    stats = [("860,713", "funded addresses covered", BLUE, ("l45", "860"), -2), ("~31 min", "full-chain refresh", PINK, ("l45", "thirty"), 2),
             ("$0", "infrastructure: static site + public servers", GREEN, ("l45", "free"), -1), ("$6.8B", "exposed value it measures", WHITE, ("l45", "infrastructure"), 2)]
    for k, (n, lbl, bg, (lid, wd), rot) in enumerate(stats):
        x, y = 960 + (k % 2) * 440, 250 + (k // 2) * 270
        m.append(f'<div class="cards" id="{sid}-s{k}" style="left:{x}px;top:{y}px;width:410px;height:240px;background:#fff;transform:rotate({rot}deg)">'
                 f'<div class="abs" style="left:22px;top:22px;width:16px;height:16px;border:2px solid #000;border-radius:50%;background:{bg}"></div>'
                 f'<div class="abs stat" style="left:22px;top:54px;font-size:80px">{n}</div>'
                 f'<div class="abs body" style="left:22px;top:150px;width:370px;font-size:24px">{lbl}</div></div>')
        js.append(pop(f"#{sid}-s{k}", C.w(lid, wd, -0.1), rot=rot, fromScale=0.6))
        sfx(sc, C.w(lid, wd), "sfx/drop_002.ogg", 0.32)
    m.append(f'<div class="abs stripes" id="{sid}-road" style="left:110px;top:800px;width:1700px;height:24px;--sc:{BLUE}"></div>')
    m.append(pill(f"{sid}-next", "Next: wallet mode · daily refresh · ZIP 2007 circuit sizing", 110, 760, BLUE))
    js.append(f'tl.fromTo("#{sid}-road",{{scaleX:0,transformOrigin:"0% 50%"}},{{scaleX:1,duration:0.6,ease:"power3.out"}},{C.e("l45", -1.0)});')
    js.append(pop(f"#{sid}-next", C.e("l45", -0.8)))
    return m, js

def scene_s14(sc, C):
    sid = "s14"; m, js = [], []
    acts = [("01 · Sweep", "Move t-address coins into Ironwood, in one sweep.", "sweep"), ("02 · Migrate", "Sapling / Orchard → Ironwood with a ZIP 318 wallet.", "migrate"), ("03 · Rebuild", "Multisigs → FROST threshold keys (ZIP 312).", "rebuild")]
    for k, (t_, body, wd) in enumerate(acts):
        x = 110 + k * 580
        m.append(f'<div class="abs" id="{sid}-c{k}" style="left:{x}px;top:110px;width:540px;height:250px;background:#fff;border:4px solid #fff;box-shadow:10px 10px 0 {YELLOW}">'
                 f'<div class="abs ctitle" style="left:26px;top:28px;font-size:40px">{t_}</div>'
                 f'<div class="abs body" style="left:26px;top:96px;width:480px;font-size:27px">{body}</div></div>')
        js.append(f'tl.fromTo("#{sid}-c{k}",{{opacity:0,y:60}},{{opacity:1,y:0,duration:0.5,ease:"expo.out"}},{C.w("l46", wd, -0.12)});')
        sfx(sc, C.w("l46", wd), "sfx/drop_002.ogg", 0.32)
    m.append(f'<div class="abs" id="{sid}-close" style="left:330px;top:430px;width:1260px;height:380px;background:#000;border:4px solid #fff;box-shadow:14px 14px 0 {YELLOW}">'
             f'{logo_mark(54, 54, 120, sid + "-lm")}'
             f'<div class="abs" style="left:210px;top:44px;font:900 132px/1 Inter;letter-spacing:-0.04em;color:#fff;text-transform:uppercase">Shorline</div>'
             f'<div class="abs" style="left:214px;top:184px;font:800 40px/1.1 Inter;color:#fff;text-transform:uppercase;letter-spacing:-0.01em">Know your exposure before Q-Day</div>'
             f'<div class="abs mono" style="left:214px;top:262px;padding:10px 18px;border:3px solid #fff;background:{YELLOW};color:#000;font-size:28px;font-weight:700">jmohak2004.github.io/shorline</div>'
             f'<div class="abs mono" style="left:214px;top:330px;color:#fff;font-size:20px">github.com/Jmohak2004/shorline · MIT</div></div>')
    m.append(f'<div class="abs star" id="{sid}-star" style="left:1470px;top:380px;width:190px;height:190px;background:{PINK}"></div>')
    tc = C.s("l47")
    js.append(f'tl.fromTo("#{sid}-close",{{opacity:0,scale:0.85,y:40}},{{opacity:1,scale:1,y:0,duration:0.55,ease:"expo.out"}},{tc - 0.15});')
    js.append(pop(f"#{sid}-star", tc + 0.25, rot=14))
    sfx(sc, tc, "sfx/impactBell_heavy_000.ogg", 0.55)
    m.append(f'<div class="abs mono" id="{sid}-cred" style="left:0;top:960px;width:1920px;text-align:center;color:#fff;font-size:19px;letter-spacing:.04em;text-transform:uppercase">Music: Sascha Ende, ende.app (CC BY 4.0) · Voice: Kokoro TTS · Made with HyperFrames + /brag</div>')
    js.append(blurin(f"#{sid}-cred", C.e("l47", 0.5)))
    return m, js

BUILDERS = [scene_s01, scene_s02, scene_s03, scene_s04, scene_s05, scene_s06, scene_s07, scene_s08, scene_s09, scene_s10, scene_s11, scene_s12, scene_s13, scene_s14]
GROUNDS = [CREAM, BLUE, PINK, YELLOW, OFF, GREEN, BLUE, CREAM, PINK, OFF, BLUE, GREEN, YELLOW, BLACK]

# ---------------------------------------------------------------- write scenes
(COMP / "compositions").mkdir(parents=True, exist_ok=True)
for i, sc in enumerate(scenes):
    sid = sc["id"]
    C = Cue(sc)
    markup, js = BUILDERS[i](sc, C)
    kin = TRANS.get(i)
    kout = TRANS.get(i + 1)
    tin_m, tin_j = trans_in(sid, kin, GROUNDS[i]) if kin else ("", "")
    tout_m, tout_j = trans_out(sid, kout, GROUNDS[i + 1] if i + 1 < len(GROUNDS) else BLACK, sc["dur"]) if kout else ("", "")
    if i == len(scenes) - 1:
        tout_j = f'tl.fromTo("#{sid}-fade",{{opacity:0}},{{opacity:1,duration:0.6,ease:"power2.in"}},{round(sc["dur"]-0.65,3)});'
        tout_m = f'<div class="tr" id="{sid}-fade" style="background:#000"></div>'
    stage_open = f'<div class="abs" id="{sid}-stage" style="inset:0;background:{GROUNDS[i]}">'
    base = f'<div class="ground" style="background:#000"></div>' if kin == "iris" else ""
    doc = f"""<template>
  <style>
{SHARED_CSS}
  </style>
  <div id="root" data-composition-id="{sid}" data-width="{W}" data-height="{H}">
    {base}
    {stage_open}
      {''.join(markup)}
    </div>
    {tin_m}
    {tout_m}
  </div>
  <script>
    (function(){{
    const tl = gsap.timeline({{ paused: true }});
    {tin_j}
    {chr(10).join(js)}
    {tout_j}
    tl.set({{}}, {{}}, {sc['dur']});
    window.__timelines["{sid}"] = tl;
    }})();
  </script>
</template>
"""
    (COMP / "compositions" / f"{sid}.html").write_text(doc)

# ---------------------------------------------------------------- captions
groups = []
for sc in scenes:
    for l in sc["lines"]:
        ws = [[w, sc["abs"] + a, sc["abs"] + b] for w, a, b in l["words"]]
        cur = []
        for k, wd in enumerate(ws):
            cur.append(wd)
            n_chars = sum(len(x[0]) + 1 for x in cur)
            if re.search(r"[.:;?!]$", wd[0]) or (re.search(r",$", wd[0]) and len(cur) >= 3) or len(cur) >= 6 or n_chars > 34:
                groups.append(cur); cur = []
        if cur:
            groups.append(cur)
cap_html, cap_js = [], []
for gi, g in enumerate(groups):
    start = max(0.05, g[0][1] - 0.06)
    nxt = groups[gi + 1][0][1] - 0.06 if gi + 1 < len(groups) else g[-1][2] + 0.6
    end = min(g[-1][2] + 0.5, nxt - 0.02)
    end = max(end, g[-1][2] + 0.05)
    words = "".join(f'<span class="cw" id="cw{gi}_{k}">{html.escape(w[0])}</span>' for k, w in enumerate(g))
    cap_html.append(f'<div class="cg" id="cg{gi}"><div class="cpill">{words}</div></div>')
    line = [f'tl.set("#cg{gi}",{{opacity:1,visibility:"visible"}},{start:.3f});',
            f'tl.fromTo("#cg{gi} .cpill",{{y:14,scale:0.96}},{{y:0,scale:1,duration:0.16,ease:"back.out(2)"}},{start:.3f});']
    for k, w in enumerate(g):
        line.append(f'tl.set("#cw{gi}_{k}",{{className:"cw on"}},{w[1]:.3f});')
        line.append(f'tl.set("#cw{gi}_{k}",{{className:"cw done"}},{(g[k+1][1] if k + 1 < len(g) else w[2]):.3f});')
    line.append(f'tl.set("#cg{gi}",{{opacity:0,visibility:"hidden"}},{end:.3f});')
    cap_js.append(" ".join(line))
captions = f"""<template>
  <style>
    #root {{ position:absolute; inset:0; pointer-events:none; }}
    .cg {{ position:absolute; left:0; right:0; top:884px; height:120px; display:flex; align-items:center; justify-content:center; opacity:0; visibility:hidden; }}
    .cpill {{ max-width:1500px; padding:14px 30px 12px; background:#fff; border:4px solid #000; box-shadow:8px 8px 0 #000; display:flex; flex-wrap:wrap; justify-content:center; gap:0 0.3em;
             font:900 44px/1.15 'Inter',sans-serif; text-transform:uppercase; letter-spacing:-0.015em; color:#000; }}
    .cw {{ display:inline-block; padding:0 0.08em; color:#000; opacity:.45; }}
    .cw.on {{ opacity:1; background:{YELLOW}; box-shadow:0 0 0 0.07em {YELLOW}; }}
    .cw.done {{ opacity:1; }}
  </style>
  <div id="root" data-composition-id="captions" data-width="{W}" data-height="{H}">
    {''.join(cap_html)}
  </div>
  <script>
    (function(){{
    const tl = gsap.timeline({{ paused: true }});
    {chr(10).join(cap_js)}
    tl.set({{}}, {{}}, {TOTAL});
    window.__timelines["captions"] = tl;
    }})();
  </script>
</template>
"""
(COMP / "compositions" / "captions.html").write_text(captions)

# ---------------------------------------------------------------- root
def dur_of(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout)

hosts = []
for i, sc in enumerate(scenes):
    hosts.append(f'<div id="{sc["id"]}" data-composition-id="{sc["id"]}" data-composition-src="compositions/{sc["id"]}.html" data-start="{sc["abs"]}" data-duration="{sc["dur"]}" data-track-index="1" data-track-kind="graphics" data-width="{W}" data-height="{H}"></div>')
hosts.append(f'<div id="captions" data-composition-id="captions" data-composition-src="compositions/captions.html" data-start="0" data-duration="{TOTAL}" data-track-index="2" data-track-kind="captions" data-width="{W}" data-height="{H}" style="z-index:40"></div>')
audio = []
for sc in scenes:
    for l in sc["lines"]:
        audio.append(f'<audio id="vo-{l["id"]}" class="clip" data-start="{round(sc["abs"] + l["start"], 3)}" data-duration="{l["dur"]}" data-track-index="3" data-volume="1" src="assets/voice/{l["id"]}.wav"></audio>')
m1 = COMP / "assets/music/happy-beats-business-moves-vol-1-by-ende-dot-app.mp3"
m9 = COMP / "assets/music/happy-beats-business-moves-vol-9-by-ende-dot-app.mp3"
d1, d9 = dur_of(m1), dur_of(m9)
x1 = round(d1 - 4.0, 3)
dur9 = round(min(d9, TOTAL - x1), 3)
audio.append(f'<audio id="music-a" class="clip" data-start="0" data-duration="{round(d1,3)}" data-track-index="4" data-volume="0.12" data-fade-in="1.5" data-fade-out="4" src="assets/music/happy-beats-business-moves-vol-1-by-ende-dot-app.mp3"></audio>')
audio.append(f'<audio id="music-b" class="clip" data-start="{x1}" data-duration="{dur9}" data-track-index="5" data-volume="0.12" data-fade-in="4" data-fade-out="3.5" src="assets/music/happy-beats-business-moves-vol-9-by-ende-dot-app.mp3"></audio>')
SFX.sort()
lanes_end = [-1.0] * 6
for k, (t_, f, v) in enumerate(SFX):
    d = round(dur_of(COMP / "assets" / f), 3)
    li = next(i for i, e in enumerate(lanes_end) if t_ >= e + 0.01)
    lanes_end[li] = t_ + d
    lane = 6 + li
    audio.append(f'<audio id="sfx-{k:02d}" class="clip" data-start="{t_}" data-duration="{d}" data-track-index="{lane}" data-volume="{v}" src="assets/{f}"></audio>')

index = f"""<!doctype html>
<html lang="en" data-composition-variables='[{{"id":"color-ground","type":"color","label":"Background","default":"{OFF}"}},{{"id":"color-ink","type":"color","label":"Ink","default":"#000000"}},{{"id":"color-accent","type":"color","label":"Accent","default":"{YELLOW}"}},{{"id":"font-display","type":"string","label":"Display font","default":"Inter"}}]'>
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      :root {{ --ground: {OFF}; --ink: #000; --font-display: 'Inter'; }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: #000; }}
      #root {{ position: relative; width: 100%; height: 100%; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{TOTAL}" data-width="{W}" data-height="{H}" data-fps="30">
      {chr(10).join(hosts)}
      {chr(10).join(audio)}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""
(COMP / "index.html").write_text(index)
json.dump({"total": TOTAL, "scenes": [{"id": s["id"], "abs": s["abs"], "dur": s["dur"]} for s in scenes], "sfx": len(SFX), "caption_groups": len(groups)}, open(BASE / "build-summary.json", "w"), indent=1)
print(f"total {TOTAL:.1f}s · {len(scenes)} scenes · {len(groups)} caption groups · {len(SFX)} sfx")
