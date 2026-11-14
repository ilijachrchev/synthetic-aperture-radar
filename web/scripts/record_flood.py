"""Record a story page telling its own story: a film file and a frame every half second.

    python scripts/record_flood.py OUT_DIR --url "http://localhost:3220/flood?story" --seconds 24
    python scripts/record_flood.py OUT_DIR --url "http://localhost:3220/fire?story" --screencast

Opens the page with ?story, which plays the film mode by itself (from space, down to the marsh, the passes, the
swipe). Writes OUT_DIR/film.mp4 and OUT_DIR/frames/f_<seconds>.jpg, which are real frames of the running app on
real data: they are the storyboard.

Two ways to record, same picture:
  the recorder of Playwright   needs its own browser (playwright install chromium). Also leaves OUT_DIR/film.webm.
  --screencast                 the Chrome or Edge of this computer sends its own frames, and the ffmpeg of this
                               computer makes the film. Nothing to download. Chosen by itself when Playwright has
                               no browser of its own.

Needs playwright (pip install playwright) and, for the MP4, ffmpeg on the path.
Written with SI assistance (Claude Code), reviewed by the team.
"""
import argparse
import base64
import os
import shutil
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

GPU = ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"]


def open_browser(p, screencast):
    """The browser of Playwright, or (with screencast, or when that one is missing) the Chrome or Edge of this computer."""
    if not screencast:
        try:
            return p.chromium.launch(args=GPU), False
        except Exception:
            print("Playwright has no browser of its own here: recording the screencast of the installed browser")
    last = None
    for channel in ("chrome", "msedge"):
        try:
            return p.chromium.launch(channel=channel, args=GPU), True
        except Exception as e:  # not installed: try the next one
            last = e
    raise last


def start_screencast(page, raw, w, h, quality):
    """Ask the browser for its own frames. Each one is written to disk with the time the browser stamps on it."""
    cdp = page.context.new_cdp_session(page)
    times = []

    def on_frame(ev):
        times.append(float(ev["metadata"]["timestamp"]))
        with open(os.path.join(raw, f"{len(times):06d}.jpg"), "wb") as f:
            f.write(base64.b64decode(ev["data"]))
        try:
            cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:  # the page is closing
            pass

    cdp.on("Page.screencastFrame", on_frame)
    cdp.send("Page.startScreencast", {"format": "jpeg", "quality": quality, "maxWidth": w, "maxHeight": h, "everyNthFrame": 1})
    return cdp, times


def assemble(raw, times, mp4, skip, fps):
    """The frames become an MP4 at a constant rate. A frame is held until the next one: the browser only sends a
    frame when the picture changed."""
    if len(times) < 2:
        return False
    t0 = times[0] + skip
    keep = [(i + 1, t) for i, t in enumerate(times) if t >= t0]
    if len(keep) < 2:
        return False
    lines = []
    for k, (i, t) in enumerate(keep[:-1]):
        lines.append(f"file '{i:06d}.jpg'\nduration {max(0.001, keep[k + 1][1] - t):.4f}")
    lines.append(f"file '{keep[-1][0]:06d}.jpg'\nduration {1 / fps:.4f}\nfile '{keep[-1][0]:06d}.jpg'")
    with open(os.path.join(raw, "list.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    done = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "list.txt", "-vf", f"fps={fps}",
                           "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", os.path.abspath(mp4)], cwd=raw, check=False)
    return done.returncode == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--url", default="http://localhost:3220/flood?story")
    ap.add_argument("--seconds", type=float, default=40, help="stop after this long even if the story has not ended")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--every", type=float, default=0.5, help="seconds between frames")
    ap.add_argument("--theme", default="dark", choices=["light", "dark"], help="day or night")
    ap.add_argument("--skip", type=float, default=1.5, help="seconds cut from the start of the MP4, while the first tiles arrive")
    ap.add_argument("--screencast", action="store_true", help="record with the installed Chrome or Edge and the ffmpeg of this computer")
    ap.add_argument("--fps", type=int, default=30, help="frame rate of the MP4 made from a screencast")
    ap.add_argument("--quality", type=int, default=84, help="JPEG quality of the screencast frames: lower lets more frames through")
    ap.add_argument("--keep-raw", action="store_true", help="keep the frames of the screencast")
    args = ap.parse_args()
    w, h = (int(v) for v in args.size.split("x"))
    frames = os.path.join(args.out, "frames")
    raw = os.path.join(args.out, "raw")
    os.makedirs(frames, exist_ok=True)
    mp4 = os.path.join(args.out, "film.mp4")
    have_ffmpeg = bool(shutil.which("ffmpeg"))

    with sync_playwright() as p:
        browser, cast = open_browser(p, args.screencast)
        if cast and not have_ffmpeg:
            sys.exit("a screencast needs ffmpeg on the path to become a film")
        video_opts = {} if cast else {"record_video_dir": args.out, "record_video_size": {"width": w, "height": h}}
        context = browser.new_context(viewport={"width": w, "height": h}, **video_opts)
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
        times = []
        if cast:
            shutil.rmtree(raw, ignore_errors=True)
            os.makedirs(raw)
            cdp, times = start_screencast(page, raw, w, h, args.quality)
        while time.time() - start < args.seconds and not page.evaluate("window.__waterStoryDone === true"):
            t = time.time() - start
            if cast:
                # no screenshots here: each one would hold the picture for a moment and show in the film
                page.wait_for_timeout(120)
                continue
            page.screenshot(path=os.path.join(frames, f"f_{t:05.1f}.jpg"), type="jpeg", quality=88)
            n += 1
            rest = args.every - ((time.time() - start) - t)
            if rest > 0:
                page.wait_for_timeout(rest * 1000)
        if cast:
            page.wait_for_timeout(300)
            try:
                cdp.send("Page.stopScreencast")
            except Exception:
                pass
        video = None if cast else page.video
        context.close()
        if video:
            shutil.move(video.path(), os.path.join(args.out, "film.webm"))
        browser.close()

    if cast:
        took = times[-1] - times[0] if len(times) > 1 else 0
        gaps = sorted(b - a for a, b in zip(times, times[1:]))
        if took:
            print(f"screencast: {len(times)} frames in {took:.1f} s ({len(times) / took:.0f} a second), "
                  f"half of them under {gaps[len(gaps) // 2] * 1000:.0f} ms apart, 95 % under {gaps[int(len(gaps) * 0.95)] * 1000:.0f} ms")
        else:
            print("screencast: no frames")
        if assemble(raw, times, mp4, args.skip, args.fps):
            print(f"mp4 -> {mp4}")
            # the storyboard frames, cut from the film
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-vf", f"fps=1/{args.every}", "-q:v", "3", os.path.join(frames, "f_%03d.jpg")], check=False)
            print(f"frames -> {frames}")
        if not args.keep_raw:
            shutil.rmtree(raw, ignore_errors=True)
    else:
        print(f"{n} frames -> {frames}; film -> {os.path.join(args.out, 'film.webm')}")
        if video and have_ffmpeg:
            # an MP4 that starts when the story does (plus a moment for the first tiles), for the edit
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{lead + args.skip:.2f}", "-i", os.path.join(args.out, "film.webm"),
                            "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", mp4], check=False)
            print(f"mp4 -> {mp4}")
    if errors:
        print("console errors:", *errors[:10], sep="\n  ")


if __name__ == "__main__":
    sys.exit(main())
