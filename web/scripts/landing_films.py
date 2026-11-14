"""Make the films the landing page plays on its monitor: each story page telling its own story, small enough for the web.

    python scripts/landing_films.py                                  # encode the recordings in web/.cache/film
    python scripts/landing_films.py --record http://localhost:3221   # record the three stories first, then encode

The recordings are the real pages (/flood?story, /fire?story, /rice?story) filmed by scripts/record_flood.py, so the
films show the numbers of the day they were recorded: run this again after the layers are baked again.

For each story it writes into web/public/films/:
  <page>.mp4        1280 x 720, H.264, no sound, made to start playing before it has fully arrived
  <page>.jpg        the first frame, shown until the film starts
  <page>-still.jpg  a frame from late in the film, for people who ask for less motion (the film does not play for them)

Recording needs a running build of the app and a free graphics card: a busy computer drops frames, so each story is
recorded a few times and the smoothest take is kept. Encoding needs only ffmpeg on the path.
Written with SI assistance (Claude Code), reviewed by the team.
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
# page: (file name of the recording, where in the film the still is taken, as a share of its length)
STORIES = {"flood": ("dana_flood", 0.64), "fire": ("espada_fire", 0.8), "rice": ("rice_season", 0.9)}
GOOD = 30  # frames a second: a take this smooth is kept without trying again


def run(*cmd):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8")


def record(base, cache, takes):
    """Film each story page a few times and keep the smoothest take."""
    for page, (name, _) in STORIES.items():
        best = (0.0, None)
        for k in range(takes):
            take = cache / f"_{page}_{k}"
            shutil.rmtree(take, ignore_errors=True)
            done = run(sys.executable, WEB / "scripts" / "record_flood.py", take, "--url", f"{base}/{page}?story", "--seconds", "70", "--screencast", "--quality", "90")
            m = re.search(r"screencast: (\d+) frames in ([\d.]+) s \((\d+) a second\)", done.stdout + done.stderr)
            if not m or not (take / "film.mp4").exists():
                print(f"{page} take {k} failed: {(done.stdout + done.stderr)[-300:]}", flush=True)
                continue
            rate = float(m.group(3))
            print(f"{page} take {k}: {m.group(1)} frames in {m.group(2)} s, {rate:.0f} a second", flush=True)
            if rate > best[0]:
                best = (rate, take)
            if rate >= GOOD:
                break
        if best[1]:
            shutil.copyfile(best[1] / "film.mp4", cache / f"{name}.mp4")
            print(f"{page}: kept the take at {best[0]:.0f} frames a second", flush=True)
        for k in range(takes):
            shutil.rmtree(cache / f"_{page}_{k}", ignore_errors=True)


def encode(cache, out, width, crf):
    """The web film and its two pictures."""
    out.mkdir(parents=True, exist_ok=True)
    height = round(width * 9 / 16 / 2) * 2
    scale = f"scale={width}:{height}:flags=lanczos"
    for page, (name, late) in STORIES.items():
        src = cache / f"{name}.mp4"
        if not src.exists():
            print(f"{page}: no recording at {src}, skipped")
            continue
        film = out / f"{page}.mp4"
        done = run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", scale, "-c:v", "libx264", "-preset", "medium", "-crf", crf, "-g", "60",
                   "-threads", "4", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", film)
        if done.returncode:
            sys.exit(f"ffmpeg failed on {src}: {done.stderr[-400:]}")
        seconds = float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src).stdout.strip())
        for target, at in ((out / f"{page}.jpg", 0.15), (out / f"{page}-still.jpg", seconds * late)):
            run("ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", src, "-frames:v", "1", "-vf", scale, "-q:v", "4", target)
        print(f"{page}: {film.name} {film.stat().st_size / 1e6:.1f} MB, {seconds:.1f} s, still at {seconds * late:.1f} s", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", metavar="URL", help="record the story pages of the app running at this address first")
    ap.add_argument("--takes", type=int, default=4, help="how many times a story is recorded at most")
    ap.add_argument("--cache", type=Path, default=WEB / ".cache" / "film", help="where the recordings are kept (not in git)")
    ap.add_argument("--out", type=Path, default=WEB / "public" / "films")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--crf", default="27", help="quality of the web film: lower is better and larger")
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is not on the path")
    args.cache.mkdir(parents=True, exist_ok=True)
    if args.record:
        record(args.record.rstrip("/"), args.cache, args.takes)
    encode(args.cache, args.out, args.width, args.crf)


if __name__ == "__main__":
    sys.exit(main())
