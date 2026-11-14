"""Record the flood page telling its own story: a film file and a frame every half second.

    python scripts/record_flood.py OUT_DIR --url "http://localhost:3220/flood?story" --seconds 24

Opens the page with ?story, which plays the film mode by itself (from space, down to the marsh, the passes, the
swipe). Writes OUT_DIR/film.webm (the browser's own screen recording) and OUT_DIR/frames/f_<seconds>.jpg, which are
real frames of the running app on real data: they are the storyboard.

Needs playwright (pip install playwright, then: playwright install chromium).
Written with SI assistance (Claude Code), reviewed by the team.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--url", default="http://localhost:3220/flood?story")
    ap.add_argument("--seconds", type=float, default=40, help="stop after this long even if the story has not ended")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--every", type=float, default=0.5, help="seconds between frames")
    ap.add_argument("--theme", default="dark", choices=["light", "dark"], help="day or night")
    ap.add_argument("--skip", type=float, default=1.5, help="seconds cut from the start of the MP4, while the first tiles arrive")
    args = ap.parse_args()
    w, h = (int(v) for v in args.size.split("x"))
    frames = os.path.join(args.out, "frames")
    os.makedirs(frames, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"])
        context = browser.new_context(viewport={"width": w, "height": h}, record_video_dir=args.out, record_video_size={"width": w, "height": h})
        opened = time.time()
        page = context.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(f"try {{ localStorage.setItem('theme', '{args.theme}') }} catch (e) {{}}")
        page.goto(args.url, wait_until="domcontentloaded")
        page.wait_for_selector(".fl[data-cinema]", timeout=120000)
        start = time.time()
        lead = start - opened  # the film file also holds the loading of the page: cut it off below
        n = 0
        while time.time() - start < args.seconds and not page.evaluate("window.__waterStoryDone === true"):
            t = time.time() - start
            page.screenshot(path=os.path.join(frames, f"f_{t:05.1f}.jpg"), type="jpeg", quality=88)
            n += 1
            rest = args.every - ((time.time() - start) - t)
            if rest > 0:
                page.wait_for_timeout(rest * 1000)
        video = page.video
        context.close()
        if video:
            shutil.move(video.path(), os.path.join(args.out, "film.webm"))
        browser.close()
        print(f"{n} frames -> {frames}; film -> {os.path.join(args.out, 'film.webm')}")
        if video and shutil.which("ffmpeg"):
            # an MP4 that starts when the story does (plus a moment for the first tiles), for the edit
            mp4 = os.path.join(args.out, "film.mp4")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{lead + args.skip:.2f}", "-i", os.path.join(args.out, "film.webm"),
                            "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", mp4], check=False)
            print(f"mp4 -> {mp4}")
        if errors:
            print("console errors:", *errors[:10], sep="\n  ")


if __name__ == "__main__":
    sys.exit(main())
