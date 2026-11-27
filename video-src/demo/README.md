# Live-demo scene

Scene 12 of the explainer (about 66 s, spliced in after "The live dashboard"). It shows the product being used:

1. the real deployed dashboard, then the address checker on an exposed and a hash-protected address;
2. `shorline check` live against the chain;
3. `shorline scan --end 20000` replaying blocks with `missing=0`.

What is real: the dashboard is the live site driven by a headless browser, and the terminal text in
`captured/` is unedited output of the commands shown (the scan output path is shortened to `demo`, and the
scan is sped up on screen and labelled "SPED UP"). Narration uses the same Kokoro voice (`af_heart`) as the rest of the video.

```bash
# voice: synthesize demo_script.json lines to WORKDIR/voice/dNN.wav with the Kokoro model
# capture: WORKDIR/check.txt and WORKDIR/scan.txt (copies are in captured/)
python3 make_demo.py WORKDIR            # records and muxes WORKDIR/demo.mp4
python3 make_demo.py WORKDIR --mux-only # re-mux from an existing recording
```

The scene is joined to the main render with ffmpeg at the end of scene 11 (221.28 s of the original render).
