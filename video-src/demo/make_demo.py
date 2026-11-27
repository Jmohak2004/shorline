#!/usr/bin/env python3
"""Records the "live demo" scene of the Shorline explainer.

It drives the REAL deployed dashboard (https://jmohak2004.github.io/shorline/) in a headless browser,
inside the video's neobrutalist frame, and replays REAL captured terminal output of `shorline check`
and `shorline scan`. Narration is synthesized with the same Kokoro voice as the rest of the video.

    python3 make_demo.py WORKDIR

WORKDIR must contain:  voice/d01.wav ... (from demo_script.json), check.txt, scan.txt
Writes:                WORKDIR/demo.mp4  (1920x1080, 25 fps, narrated, music bed)
"""
import json, pathlib, subprocess, sys, time, wave, html

HERE = pathlib.Path(__file__).resolve().parent
WORK = pathlib.Path(sys.argv[1]).resolve()
SCRIPT = json.loads((HERE / "demo_script.json").read_text())
LINES = SCRIPT["lines"]
SITE = "https://jmohak2004.github.io/shorline/"
FONTS = pathlib.Path.home() / ".cache/hyperframes/fonts"
MUSIC = pathlib.Path("/Users/mohakjaiswal/solsolana /shorline-video/composition/assets/music/happy-beats-business-moves-vol-1-by-ende-dot-app.mp3")

EXPOSED = "t1gsBrGZGMyDGZw2icGnMpVBuEGVWip5kH8"
HIDDEN = "t1b5JTd4QL3VjUyXDTqDu6mST3XkcrsvLTd"
GAP = 0.35  # silence between narration lines


def font(path_glob):
    return next(FONTS.glob(path_glob)).as_uri()


def dur(wav):
    with wave.open(str(wav)) as w:
        return w.getnframes() / w.getframerate()


def real_lines(name, drop_prefixes=("target/", "timeout ")):
    out = []
    for ln in (WORK / name).read_text().splitlines():
        if ln.startswith(drop_prefixes) or ln.startswith(("real", "user", "sys")) or not ln.strip() and not out:
            continue
        out.append(ln)
    while out and not out[-1].strip():
        out.pop()
    return out


CHECK = real_lines("check.txt")
SCAN = [ln.replace(str(WORK / "demoscan"), "demo") for ln in real_lines("scan.txt")]
CHECK_CMD = f"shorline check {EXPOSED[:8]}… {HIDDEN[:8]}…"
SCAN_CMD = "shorline scan --end 20000 --out demo"

PAGE = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:Inter;font-weight:100 900;src:url({font('inter/900-normal-*.woff2')})}}
@font-face{{font-family:'Space Mono';font-weight:700;src:url({font('space-mono/700-normal-*.woff2')})}}
@font-face{{font-family:'Space Mono';font-weight:400;src:url({font('space-mono/400-normal-*.woff2')})}}
*{{box-sizing:border-box;margin:0}}
body{{width:1920px;height:1080px;overflow:hidden;background:#C0F7FE;font-family:Inter,sans-serif;position:relative}}
.dots{{position:absolute;inset:0;background-image:radial-gradient(#000 1.4px,transparent 1.6px);background-size:26px 26px;opacity:.16}}
.pill{{position:absolute;display:inline-flex;align-items:center;border:3px solid #000;border-radius:999px;box-shadow:4px 4px 0 #000;padding:9px 22px 8px;font:700 21px/1 'Space Mono',monospace;background:#fff;text-transform:uppercase;letter-spacing:.04em}}
#live{{left:110px;top:54px;background:#FE90E8}}
#step{{left:330px;top:54px}}
#win{{position:absolute;left:110px;top:118px;width:1700px;height:770px;background:#fff;border:4px solid #000;box-shadow:10px 10px 0 #000;overflow:hidden}}
#bar{{height:56px;border-bottom:4px solid #000;background:#F7CB46;display:flex;align-items:center;gap:10px;padding:0 18px}}
.dot{{width:18px;height:18px;border:3px solid #000;border-radius:50%;background:#fff}}
#url{{margin-left:14px;flex:1;height:34px;border:3px solid #000;background:#fff;border-radius:999px;padding:0 18px;font:700 18px/28px 'Space Mono',monospace;white-space:nowrap;overflow:hidden}}
#frame{{position:absolute;left:0;top:56px;width:1128px;height:471px;transform:scale(1.5);transform-origin:0 0;border:0;background:#fff}}
#term{{position:absolute;left:0;top:56px;width:1692px;height:706px;background:#101010;color:#E8E8E8;padding:26px 34px;font:400 22px/1.42 'Space Mono',monospace;white-space:pre-wrap;overflow-wrap:anywhere;display:none;overflow:hidden}}
#term .p{{color:#99E885}} #term .ok{{color:#99E885}} #term .bad{{color:#ff8a80;font-weight:700}} #term .warn{{color:#F7CB46}} #term .hl{{background:#F7CB46;color:#000;font-weight:700;padding:0 6px}} #term .dim{{color:#8c8c8c}}
#cap{{position:absolute;left:110px;top:926px;width:1700px;min-height:104px;background:#fff;border:4px solid #000;box-shadow:8px 8px 0 #000;padding:22px 30px;font:800 35px/1.25 Inter,sans-serif;letter-spacing:-.01em;display:flex;align-items:center}}
#stamp{{position:absolute;right:170px;top:215px;background:#99E885;border:4px solid #000;box-shadow:8px 8px 0 #000;font:900 44px/1 Inter,sans-serif;text-transform:uppercase;padding:16px 26px 14px;transform:rotate(-4deg) scale(.6);opacity:0;transition:all .25s cubic-bezier(.2,1.6,.4,1);z-index:5}}
#stamp.on{{opacity:1;transform:rotate(-4deg) scale(1)}}
#fast{{position:absolute;right:30px;top:12px;background:#F7CB46;border:3px solid #000;padding:4px 12px;font:700 17px 'Space Mono',monospace;display:none}}
#fade{{position:absolute;inset:0;background:#000;opacity:1;transition:opacity .45s;z-index:20;pointer-events:none}}
</style></head><body>
<div class="dots"></div>
<div class="pill" id="live">● Live demo</div><div class="pill" id="step">STEP 1</div>
<div id="win"><div id="bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span><div id="url">{SITE.replace('https://','')}</div><span id="fast">SPED UP</span></div>
<iframe id="frame" src="{SITE}"></iframe><div id="term"></div></div>
<div id="stamp">0 missing inputs ✓</div>
<div id="cap"></div><div id="fade"></div>
</body></html>"""


def main():
    from playwright.sync_api import sync_playwright

    wavs = [WORK / "voice" / f"{l['id']}.wav" for l in LINES]
    durs = [dur(w) for w in wavs]
    vdir = WORK / "rec"
    for f in vdir.glob("*"):
        f.unlink()
    (WORK / "page.html").write_text(PAGE)

    starts = []
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(vdir),
                             record_video_size={"width": 1920, "height": 1080}, color_scheme="light")
        page = ctx.new_page()
        ctx_t = time.monotonic()
        page.goto((WORK / "page.html").as_uri())
        page.wait_for_function("document.querySelector('#frame') !== null")
        fr = next(f for f in page.frames if f != page.main_frame)
        fr.wait_for_function("document.querySelector('#hero-number') && document.querySelector('#hero-number').textContent.includes('ZEC')", timeout=60000)
        page.wait_for_timeout(600)
        page.evaluate("document.getElementById('fade').style.opacity=0")
        t0 = time.monotonic()
        offset = t0 - ctx_t

        def now():
            return time.monotonic() - t0

        def set_line(i):
            l = LINES[i]
            page.evaluate("([s,c])=>{document.getElementById('step').textContent=s;document.getElementById('cap').textContent=c}", [l["step"], l["cap"]])
            starts.append(now())
            return now() + durs[i]

        def wait_until(t):
            d = t - now()
            if d > 0:
                page.wait_for_timeout(int(d * 1000))

        def scroll_to(sel, block="start"):
            fr.evaluate("([s,b])=>document.querySelector(s).scrollIntoView({behavior:'smooth',block:b})", [sel, block])

        def term_show(on, title=None):
            page.evaluate("([on,t])=>{document.getElementById('term').style.display=on?'block':'none';document.getElementById('frame').style.visibility=on?'hidden':'visible';if(t)document.getElementById('url').textContent=t}", [on, title or SITE.replace('https://', '')])

        def term_type(cmd, per_ms):
            page.evaluate("(c)=>{const t=document.getElementById('term');t.innerHTML+='<span class=p>$ </span><span id=cur></span>\\n'}", cmd)
            for ch in cmd:
                page.evaluate("(c)=>{document.getElementById('cur').textContent+=c}", ch)
                page.wait_for_timeout(per_ms)
            page.evaluate("()=>{document.getElementById('cur').removeAttribute('id')}")

        def classify(ln):
            e = html.escape(ln)
            if "EXPOSED" in ln:
                return e.replace("EXPOSED", "<span class=bad>EXPOSED</span>", 1)
            if "HASH-PROTECTED" in ln:
                return e.replace("HASH-PROTECTED", "<span class=ok>HASH-PROTECTED</span>", 1)
            if "missing=0" in ln:
                return e.replace("missing=0", "<span class=hl>missing=0</span>")
            if ln.lstrip().startswith("!"):
                return f"<span class=warn>{e}</span>"
            if ln.startswith(("t1", "connected", "scanning", "wrote")):
                return f"<span class=dim>{e}</span>" if ln.startswith(("connected", "scanning")) else f"<b>{e}</b>"
            return e

        def term_print(lines, total_s):
            step = max(40, int(total_s * 1000 / max(1, len(lines))))
            for ln in lines:
                page.evaluate("(h)=>{const t=document.getElementById('term');t.innerHTML+=h+'\\n'}", classify(ln))
                page.wait_for_timeout(step)

        def focus_input(clear=False):
            fr.evaluate("(c)=>{const i=document.querySelector('#check-input');if(c)i.value='';i.focus({preventScroll:true})}", clear)

        # d01-d02: the app
        end = set_line(0); wait_until(end + GAP)
        end = set_line(1); scroll_to("#fate"); wait_until(end + GAP)
        # d03: type + check the exposed address
        end = set_line(2); scroll_to("#check"); page.wait_for_timeout(900)
        focus_input(); page.keyboard.type(EXPOSED, delay=48); wait_until(end - 0.5)
        page.keyboard.press("Enter"); wait_until(end + GAP)
        end = set_line(3); fr.wait_for_selector("#check-result .state"); scroll_to("#check-result", "center"); wait_until(end + GAP)
        end = set_line(4); fr.evaluate("document.querySelector('#check-result .advice').scrollIntoView({behavior:'smooth',block:'center'})"); wait_until(end + GAP)
        # d06-d08: hash-protected address
        end = set_line(5); focus_input(clear=True); page.keyboard.type(HIDDEN, delay=40); wait_until(end - 0.2)
        page.keyboard.press("Enter"); wait_until(end + GAP)
        end = set_line(6); scroll_to("#check-result", "center"); wait_until(end + GAP)
        end = set_line(7); fr.evaluate("document.querySelector('#check-result').lastElementChild.scrollIntoView({behavior:'smooth',block:'end'})"); wait_until(end + GAP)
        # d09-d10: CLI check
        end = set_line(8); term_show(True, "Terminal: shorline"); term_type(CHECK_CMD, 38); wait_until(end + GAP)
        end = set_line(9); term_print(CHECK, max(2.5, durs[9] - 0.8)); wait_until(end + GAP)
        # d11-d13: CLI scan
        end = set_line(10)
        page.evaluate("()=>{document.getElementById('term').innerHTML='';document.getElementById('fast').style.display='inline-block'}")
        term_type(SCAN_CMD, 45); term_print(SCAN[:4], 1.4); wait_until(end + GAP)
        end = set_line(11); term_print(SCAN[4:-1], max(2.0, durs[11] - 1.0)); wait_until(end + GAP)
        end = set_line(12); term_print(SCAN[-1:], 0.3); page.evaluate("document.getElementById('stamp').classList.add('on')")
        wait_until(end + 1.2)
        page.evaluate("document.getElementById('fade').style.opacity=1")
        page.wait_for_timeout(600)
        total = now()
        ctx.close(); br.close()

    (WORK / "timeline.json").write_text(json.dumps({"offset": offset, "total": total, "starts": starts, "durs": durs}))
    mux()


def mux():
    """Video (trimmed to the first frame of the timeline) + narration at its real offsets + music bed."""
    tl = json.loads((WORK / "timeline.json").read_text())
    offset, total, starts = tl["offset"], tl["total"], tl["starts"]
    wavs = [WORK / "voice" / f"{l['id']}.wav" for l in LINES]
    webm = next((WORK / "rec").glob("*.webm"))
    n = len(wavs)
    inputs, filt = ["-ss", f"{offset:.3f}", "-t", f"{total:.2f}", "-i", str(webm)], []
    for i, w in enumerate(wavs):
        inputs += ["-i", str(w)]
        ms = int(starts[i] * 1000)
        filt.append(f"[{i+1}:a]aresample=48000,pan=stereo|c0=c0|c1=c0,adelay={ms}|{ms}[v{i}]")
    inputs += ["-stream_loop", "-1", "-i", str(MUSIC)]
    filt.append("".join(f"[v{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0:dropout_transition=0[voice]")
    filt.append(f"[{n+1}:a]aresample=48000,volume=0.10,atrim=0:{total:.2f},afade=t=in:d=0.6,afade=t=out:st={total-1.2:.2f}:d=1.2[mus]")
    filt.append(f"[voice][mus]amix=inputs=2:normalize=0:duration=longest,atrim=0:{total:.2f}[aout]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[aout]",
                    "-r", "30", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}", str(WORK / "demo.mp4")], check=True)
    print("wrote", WORK / "demo.mp4", f"{total:.1f}s")


if __name__ == "__main__":
    mux() if len(sys.argv) > 2 and sys.argv[2] == "--mux-only" else main()
