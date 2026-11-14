"""Take real screenshots of the story pages at chosen moments, for the storyboard and for checking the picture.

    python scripts/shoot_flood.py OUT_DIR
    python scripts/shoot_flood.py OUT_DIR --story fire --cinema --size 1920x1080
    python scripts/shoot_flood.py OUT_DIR --shots before after official --base http://localhost:3221

Every frame is the running app drawing real data: nothing is composited afterwards. A shot is a moment on the time
strip plus what is switched on; the page exposes window.__flood for exactly this (see story-app.tsx).

Needs playwright (pip install playwright). It uses the browser of Playwright (playwright install chromium) and,
when that is missing, the Chrome or Edge of this computer.
Written with SI assistance (Claude Code), reviewed by the team.
"""
import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright

# name: what to set before the shutter. "at" is a UTC time, or the index of a radar pass (-1 is the last one);
# "series" picks the radar; "js" runs after.
SHOTS = {
    "flood": {
        "far": {"at": 0, "js": "__flood.far(); __flood.say('Valencia coast, Spain')"},
        "before": {"at": 0},
        "storm": {"at": "2026-10-19T02:00:00Z"},
        "after": {"at": -1},
        "official": {"at": -1, "js": "__flood.official(true)"},
        "depth": {"at": -1, "js": "__flood.official(true); __flood.depth(true)"},
        "exact": {"at": -1, "js": "__flood.exact(true)"},
        "sentinel1": {"series": "s1", "at": "2026-10-22T06:09:36Z"},
        "sentinel1_weeks": {"series": "s1", "at": -1},
        "menu": {"at": -1, "js": "__flood.menu(true)"},
    },
    "fire": {
        "before": {"at": "2026-07-24T05:07:19Z"},
        "burning": {"at": "2026-07-25T19:00:00Z"},
        "estimate": {"at": "2026-08-06T12:00:00Z"},
        "first": {"at": "2026-08-17T05:07:18Z"},
        "october": {"at": "2026-10-16T05:07:18Z"},
        "official": {"at": "2026-10-16T05:07:18Z", "js": "__flood.official(true)"},
    },
    "rice": {
        "summer": {"at": "2026-08-29T18:53:18Z"},
        "filling": {"at": "2026-10-11T12:00:00Z"},
        "october": {"at": -1},
    },
}
RESET = "__flood.official(false); __flood.depth(false); __flood.exact(false); __flood.menu(false); __flood.photo('clear'); __flood.home()"


def launch(p, headed=False, channel=None):
    """The browser of Playwright if it is installed, else the Chrome or Edge of this computer (no download needed)."""
    args = ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"]
    last = None
    for name in ([channel] if channel else [None, "chrome", "msedge"]):
        try:
            return p.chromium.launch(headless=not headed, channel=name, args=args)
        except Exception as e:  # no such browser on this computer: try the next one
            last = e
    raise last


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--story", default="flood", choices=sorted(SHOTS))
    ap.add_argument("--base", default="http://localhost:3220")
    ap.add_argument("--shots", nargs="*")
    ap.add_argument("--size", default="1440x900")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--theme", default="dark", choices=["light", "dark"], help="day or night")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--channel", choices=["chrome", "msedge"], help="use this installed browser, not the one of Playwright")
    ap.add_argument("--cinema", action="store_true", help="film mode: only what the story needs on screen")
    args = ap.parse_args()
    w, h = (int(v) for v in args.size.split("x"))
    os.makedirs(args.out, exist_ok=True)
    story = SHOTS[args.story]
    shots = args.shots or list(story)
    url = f"{args.base}/{args.story}?still"

    with sync_playwright() as p:
        browser = launch(p, args.headed, args.channel)
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=args.scale)
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(f"try {{ localStorage.setItem('theme', '{args.theme}') }} catch (e) {{}}")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_function("window.__flood && document.querySelector('.st[data-ready]')", timeout=90000)
        first = page.evaluate("__flood.current")
        for name in shots:
            shot = story[name]
            want = shot.get("series", first)
            page.evaluate(f"__flood.series({json.dumps(want)})")
            page.wait_for_function(f"window.__flood && __flood.current === {json.dumps(want)}", timeout=30000)
            page.evaluate(RESET)
            page.evaluate(f"__flood.cinema({'true' if args.cinema else 'false'})")
            at = shot["at"]
            page.evaluate(f"__flood.seek(__flood.times.at({at}))" if isinstance(at, int) else f"__flood.seek({json.dumps(at)})")
            if shot.get("js"):
                page.evaluate(shot["js"])
            page.wait_for_timeout(600)
            try:
                page.wait_for_function("__flood.settled()", timeout=30000)
            except Exception:
                print(f"  {name}: did not settle, shooting anyway")
            page.wait_for_timeout(1900)  # picture fades, shapes fade, columns rise, tiles
            path = os.path.join(args.out, f"{name}.png")
            page.screenshot(path=path)
            print(f"  {name} -> {path}", flush=True)
        if errors:
            print("console errors:", *errors[:10], sep="\n  ")
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
