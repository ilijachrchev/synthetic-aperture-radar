"""Record a story page telling its own story: a film file and a frame every half second.

    python scripts/record_flood.py OUT_DIR --url "http://localhost:3220/flood?story" --steady
    python scripts/record_flood.py OUT_DIR --url "http://localhost:3220/flood?story" --seconds 24
    python scripts/record_flood.py OUT_DIR --url "http://localhost:3220/fire?story" --screencast

Opens the page with ?story, which plays the film by itself (the Earth, one move down onto the place, the passes,
then the official map and the measured depths). The page first loads its way in behind a veil; the film starts after it. Writes OUT_DIR/film.mp4 and OUT_DIR/frames/f_<seconds>.jpg, which are real frames of the running app on
real data: they are the storyboard.

Three ways to record, same picture:
  --steady                     frame by frame: the page's clock is moved on by exactly one frame at a time, the
                               recorder waits until everything of that moment is drawn (tiles, radar frames,
                               picture) and takes the picture. Every frame of the film is a new one and they are
                               evenly spaced, however busy the computer is; it only takes longer. For the films.
  the recorder of Playwright   needs its own browser (playwright install chromium). Also leaves OUT_DIR/film.webm.
  --screencast                 the Chrome or Edge of this computer sends its own frames, and the ffmpeg of this
                               computer makes the film. Nothing to download. Chosen by itself when Playwright has
                               no browser of its own. The browser sends a frame only when it gets round to it, so
                               on a busy computer the film stutters (about 17 new frames a second on 14 Nov).

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

# The page's clocks on a leash (--steady). Installed before the page's own scripts: performance.now, Date.now, the
# timers and requestAnimationFrame follow window.__clock instead of the wall. step(ms) moves the clock on, runs the
# timers due by then in their order and then one animation frame; pump() runs what is due without moving the clock.
# CSS transitions and the Web Animations of the page follow the same clock: the recorder stops the document's
# timeline (DevTools protocol, Animation.setPlaybackRate 0) and each step sets the time of every animation.
CLOCK = r"""
(() => {
	if (window.__clock) return
	const t0 = performance.now()
	const d0 = Date.now()
	let now = t0
	let seq = 0
	let nextId = 1
	const timers = new Map()
	let frames = new Map()
	performance.now = () => now
	Date.now = () => d0 + (now - t0)
	window.setTimeout = (fn, ms, ...args) => {
		const id = nextId++
		timers.set(id, { due: now + Math.max(0, Number(ms) || 0), fn, args, every: 0, seq: seq++ })
		return id
	}
	window.setInterval = (fn, ms, ...args) => {
		const id = nextId++
		const every = Math.max(1, Number(ms) || 0)
		timers.set(id, { due: now + every, fn, args, every, seq: seq++ })
		return id
	}
	window.clearTimeout = window.clearInterval = (id) => void timers.delete(id)
	window.requestAnimationFrame = (fn) => {
		const id = nextId++
		frames.set(id, fn)
		return id
	}
	window.cancelAnimationFrame = (id) => void frames.delete(id)
	const call = (fn, args) => {
		try {
			if (typeof fn === 'function') fn(...args)
		} catch (e) {
			console.error(e)
		}
	}
	// the timers due by `until`, in time order; a timer set by one of them runs too if it falls due by then
	const timersUntil = (until) => {
		for (let n = 0; n < 100000; n++) {
			let id = 0
			let best = null
			for (const [k, t] of timers) if (t.due <= until && (!best || t.due < best.due || (t.due === best.due && t.seq < best.seq))) [id, best] = [k, t]
			if (!best) return
			if (best.due > now) now = best.due
			if (best.every) {
				best.due += best.every
				best.seq = seq++
			} else timers.delete(id)
			call(best.fn, best.args)
		}
	}
	const started = new WeakMap()
	const animations = () => {
		for (const a of document.getAnimations()) {
			let start = started.get(a)
			if (start === undefined) started.set(a, (start = now - (Number(a.currentTime) || 0)))
			a.currentTime = now - start
		}
	}
	const frame = () => {
		const due = [...frames.values()]
		frames = new Map()
		for (const fn of due) call(fn, [now])
	}
	window.__clock = {
		step(ms) {
			const until = now + ms
			timersUntil(until)
			now = until
			animations()
			frame()
			return now
		},
		pump() {
			timersUntil(now)
			animations()
			frame()
			return now
		},
	}
})()
"""


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


PUMP = "() => window.__clock.pump()"
# everything this moment shows has arrived; a build from before 14 Nov 21:30 has no complete(): its tiles at least
COMPLETE = """() => {
	const f = window.__flood
	if (!f) return false
	if (f.complete) return f.complete()
	const m = f.map()
	return !!m && m.areTilesLoaded()
}"""
# what a frame still waits for, when it waits too long: the tiles still on their way, by source
MISSING = """() => {
	const m = window.__flood && window.__flood.map()
	if (!m) return 'no map'
	const out = [`zoom ${m.getZoom().toFixed(2)}`]
	for (const [id, tm] of Object.entries(m.style.tileManagers)) {
		const due = Object.values(tm._tiles || {}).filter((t) => t.state !== 'loaded' && t.state !== 'errored')
		if (due.length) out.push(`${id}: ${due.length} tiles ${due.slice(0, 3).map((t) => t.tileID.key).join(' ')}`)
	}
	return out.length > 1 ? out.join(', ') : `${out[0]}, all tiles in: the radar frames or the picture`
}"""


def record_steady(page, cdp, raw, fps, seconds, tail):
    """Frame by frame on the page's own clock (CLOCK): move it on by one frame, wait until everything of that moment
    is drawn, take the picture. Returns the number of frames and how many were taken before all was drawn."""
    step = f"() => window.__clock.step({1000 / fps})"
    # the way in, behind the veil: the clock runs a frame a step, a few milliseconds of real time apart, so the data
    # and the tiles can arrive meanwhile
    give_up = time.time() + 180
    while not page.evaluate("() => !!document.querySelector('.st[data-cinema]:not([data-veil])')"):
        if time.time() > give_up:
            raise RuntimeError("the film did not start within 3 minutes")
        page.evaluate(step)
        page.wait_for_timeout(8)
    n = late = 0
    done_at = None
    while n < seconds * fps:
        if n:
            page.evaluate(step)
        # one more frame at the same moment: an animation of the page may have moved the camera after the map had
        # drawn, and the map asks for the tiles of a view only when it draws it
        page.evaluate(PUMP)
        # what this moment shows arrives in real time (tiles, radar frames): the clock waits for it
        until = time.time() + 6
        while not page.evaluate(COMPLETE):
            if time.time() > until:
                late += 1
                print(f"  frame {n + 1}: not everything drawn after 6 s: {page.evaluate(MISSING)}", flush=True)
                break
            page.wait_for_timeout(10)
            page.evaluate(PUMP)
        page.evaluate(PUMP)
        shot = cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 95})
        n += 1
        with open(os.path.join(raw, f"{n:06d}.jpg"), "wb") as f:
            f.write(base64.b64decode(shot["data"]))
        if n % (fps * 5) == 0:
            print(f"  {n / fps:.0f} s of film", flush=True)
        if done_at is None and page.evaluate("() => window.__waterStoryDone === true"):
            done_at = n
        if done_at is not None and n - done_at >= tail * fps:
            break
    return n, late


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--url", default="http://localhost:3220/flood?story")
    ap.add_argument("--seconds", type=float, default=40, help="stop after this long even if the story has not ended")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--every", type=float, default=0.5, help="seconds between frames")
    ap.add_argument("--theme", default="dark", choices=["light", "dark"], help="day or night")
    ap.add_argument("--skip", type=float, default=None, help="seconds cut from the start of the MP4: by default 1.5 (the first tiles arrive),"
                    " with --steady 0.3 (the map fades in from the veil)")
    ap.add_argument("--steady", action="store_true", help="frame by frame on the page's own clock: a smooth film on any computer (the films)")
    ap.add_argument("--tail", type=float, default=0.7, help="--steady: seconds kept after the story has ended")
    ap.add_argument("--screencast", action="store_true", help="record with the installed Chrome or Edge and the ffmpeg of this computer")
    ap.add_argument("--fps", type=int, default=30, help="frame rate of the MP4 made from a screencast or frame by frame")
    ap.add_argument("--quality", type=int, default=84, help="JPEG quality of the screencast frames: lower lets more frames through")
    ap.add_argument("--keep-raw", action="store_true", help="keep the single frames the film is made of")
    args = ap.parse_args()
    if args.skip is None:
        args.skip = 0.3 if args.steady else 1.5
    w, h = (int(v) for v in args.size.split("x"))
    frames = os.path.join(args.out, "frames")
    raw = os.path.join(args.out, "raw")
    os.makedirs(frames, exist_ok=True)
    mp4 = os.path.join(args.out, "film.mp4")
    have_ffmpeg = bool(shutil.which("ffmpeg"))

    if args.steady:
        if not have_ffmpeg:
            sys.exit("--steady needs ffmpeg on the path to make the film")
        shutil.rmtree(raw, ignore_errors=True)
        os.makedirs(raw)
        with sync_playwright() as p:
            browser, _ = open_browser(p, True)
            context = browser.new_context(viewport={"width": w, "height": h})
            page = context.new_page()
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.add_init_script(f"try {{ localStorage.setItem('theme', '{args.theme}') }} catch (e) {{}}")
            page.add_init_script(CLOCK)
            started = time.time()
            page.goto(args.url, wait_until="domcontentloaded")
            cdp = context.new_cdp_session(page)
            # the transitions and animations of the page wait for the clock too
            cdp.send("Animation.enable")
            cdp.send("Animation.setPlaybackRate", {"playbackRate": 0})
            gpu = page.evaluate("() => { const g = document.createElement('canvas').getContext('webgl2'); const e = g && g.getExtension('WEBGL_debug_renderer_info'); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'unknown' }")
            print(f"steady: drawing with {gpu}", flush=True)
            n, late = record_steady(page, cdp, raw, args.fps, args.seconds, args.tail)
            context.close()
            browser.close()
        print(f"steady: {n} frames ({n / args.fps:.1f} s of film at {args.fps} a second) in {time.time() - started:.0f} s"
              + (f", {late} of them before everything was drawn" if late else ""))
        done = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(args.fps), "-start_number", str(round(args.skip * args.fps) + 1),
                               "-i", "%06d.jpg", "-c:v", "libx264", "-crf", "16",
                               "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", os.path.abspath(mp4)], cwd=raw, check=False)
        if done.returncode == 0:
            print(f"mp4 -> {mp4}")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-vf", f"fps=1/{args.every}", "-q:v", "3", os.path.join(frames, "f_%03d.jpg")], check=False)
            print(f"frames -> {frames}")
        if not args.keep_raw:
            shutil.rmtree(raw, ignore_errors=True)
        if errors:
            print("console errors:", *errors[:10], sep="\n  ")
        return 0 if done.returncode == 0 else 1

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
        page.wait_for_selector(".st[data-cinema]:not([data-veil])", timeout=180000)
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
