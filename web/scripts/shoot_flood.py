"""Take real screenshots of the flood page at chosen moments, for the storyboard and for checking the picture.

    python scripts/shoot_flood.py OUT_DIR --url http://localhost:3220/flood
    python scripts/shoot_flood.py OUT_DIR --shots before peak --size 1920x1080

Every frame is the running app drawing real data: nothing is composited afterwards. A shot is a moment on the time
axis plus what is switched on; the page exposes window.__flood for exactly this (see flood-app.tsx).

Needs playwright (pip install playwright, then: playwright install chromium).
Written with SI assistance (Claude Code), reviewed by the team.
"""
import argparse
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

MARSH = [-0.066, 38.87]
NISAR = "nisar_066_D_069"

# name: what to set before the shutter. "at" is a UTC time on the axis; "series" picks the radar; "js" runs after.
SHOTS = {
    "nisar_before": {"at": "2026-10-16T18:53:18Z"},
    "storm_space": {"at": "2026-10-18T12:00:00Z", "camera": {"center": [-0.6, 39.3], "zoom": 6.4}},
    "storm_cloud": {"at": "2026-10-18T14:00:00Z"},
    "rain_rising": {"at": "2026-10-19T02:00:00Z"},
    "ems_peak": {"at": "2026-10-21T12:00:00Z"},
    "nisar_after": {"at": "2026-10-28T18:53:18Z"},
    "nisar_after_close": {"at": "2026-10-28T18:53:18Z", "camera": {"center": [-0.07, 38.868], "zoom": 13.7}},
    "nisar_exact": {"at": "2026-10-28T18:53:18Z", "camera": {"center": [-0.07, 38.868], "zoom": 13.7}, "js": "__flood.exact(true)"},
    "s1_before": {"series": "s1", "at": "2026-10-17T17:53:23Z"},
    "s1_first_pass": {"series": "s1", "at": "2026-10-22T06:09:36Z"},
    "s1_close": {"series": "s1", "at": "2026-10-22T06:09:36Z", "camera": {"center": [-0.07, 38.868], "zoom": 13.7}},
    "s1_three_weeks": {"series": "s1", "at": "2026-11-10T17:53:23Z"},
    "compare": {"at": "2026-10-28T18:53:18Z", "js": "__flood.optical('2026-10-21'); __flood.compare(true, 0.44)"},
    "optical_only": {"at": "2026-10-28T18:53:18Z", "js": "__flood.optical('2026-10-21'); __flood.water(false); __flood.outlines(false)"},
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--url", default="http://localhost:3220/flood")
    ap.add_argument("--shots", nargs="*", default=list(SHOTS))
    ap.add_argument("--size", default="1440x900")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--palette", default="2")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--cinema", action="store_true", help="film mode: only what the story needs on screen")
    args = ap.parse_args()
    w, h = (int(v) for v in args.size.split("x"))
    os.makedirs(args.out, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed, args=["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"])
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=args.scale)
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(f"try {{ localStorage.setItem('palette', '{args.palette}') }} catch (e) {{}}")
        page.goto(args.url, wait_until="domcontentloaded")
        page.wait_for_function("window.__flood && document.querySelector('.fl[data-ready]')", timeout=90000)
        for name in args.shots:
            shot = SHOTS[name]
            page.evaluate("__flood.compare(false); __flood.water(true); __flood.outlines(true); __flood.exact(false); __flood.optical('auto')")
            want = shot.get("series", NISAR)
            page.evaluate(f"__flood.cinema({'true' if args.cinema else 'false'})")
            page.evaluate(f"__flood.series({json.dumps(want)})")
            page.wait_for_function(f"window.__flood && __flood.current === {json.dumps(want)}", timeout=30000)
            cam = shot.get("camera", {"center": MARSH, "zoom": 12.45})
            page.evaluate(f"__flood.camera({json.dumps(cam['center'])}, {cam['zoom']})")
            page.evaluate(f"__flood.seek({json.dumps(shot['at'])})")
            if shot.get("js"):
                page.evaluate(shot["js"])
            page.wait_for_timeout(500)
            try:
                page.wait_for_function("__flood.settled()", timeout=30000)
            except Exception:
                print(f"  {name}: did not settle, shooting anyway")
            page.wait_for_timeout(1600)  # picture fades, outline fades, tiles
            path = os.path.join(args.out, f"{name}.png")
            page.screenshot(path=path)
            print(f"  {name} -> {path}", flush=True)
        if errors:
            print("console errors:", *errors[:10], sep="\n  ")
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
