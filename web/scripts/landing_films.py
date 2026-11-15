"""Make the films of the landing: the guided tour its monitor plays, and the story pages telling their own stories.

    python scripts/landing_films.py                                              # encode the recordings in web/.cache/film
    python scripts/landing_films.py --record http://localhost:3221               # record them all first, then encode
    python scripts/landing_films.py --record http://localhost:3221 --only tour   # just the monitor's film

The recordings are the real pages filmed by scripts/record_flood.py: the guided tour's steps 2 and 3 playing by
themselves (/explore?film, about 18 s) and the story pages (/flood?story, /fire?story, /rice?story). The films show
the numbers of the day they were recorded: run this again after the layers are baked again.

For each story it writes into web/public/films/:
  <page>.mp4        1280 x 720, H.264, no sound, made to start playing before it has fully arrived
  <page>.jpg        the first frame, shown until the film starts
  <page>-still.jpg  a frame from late in the film, for people who ask for less motion (the film does not play for them)

Recording needs a running build of the app. It is done frame by frame on the page's own clock (record_flood.py
--steady): every frame of a film is a new one and they are evenly spaced, on a busy computer too, it only takes longer
(a few minutes a story). Encoding needs only ffmpeg on the path.
Written with SI assistance (Claude Code), reviewed by the team.
"""
import argparse
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
# film: (file name of the recording, where in the film the still is taken as a share of its length, the address it
# is recorded from, its longest length in s, day or night)
STORIES = {
    "tour": ("guided_tour", 0.9, "/explore?film", 30, "light"),
    "flood": ("dana_flood", 0.64, "/flood?story", 70, "dark"),
    "fire": ("espada_fire", 0.8, "/fire?story", 70, "dark"),
    "rice": ("rice_season", 0.9, "/rice?story", 70, "dark"),
}


def run(*cmd):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8")


def record(base, cache, fps, only):
    """Film each page frame by frame. One take is enough: every frame is drawn before it is taken."""
    for page, (name, _, path, seconds, theme) in STORIES.items():
        if only and page not in only:
            continue
        take = cache / f"_{page}"
        shutil.rmtree(take, ignore_errors=True)
        print(f"{page}: recording frame by frame at {fps} a second", flush=True)
        done = run(sys.executable, WEB / "scripts" / "record_flood.py", take, "--url", f"{base}{path}", "--seconds", seconds, "--steady", "--fps", fps, "--theme", theme)
        for line in (done.stdout + done.stderr).splitlines():
            if line.startswith(("steady:", "  frame", "console")):
                print(f"  {line.strip()}", flush=True)
        if not (take / "film.mp4").exists():
            sys.exit(f"{page}: the recording failed: {(done.stdout + done.stderr)[-400:]}")
        shutil.copyfile(take / "film.mp4", cache / f"{name}.mp4")
        shutil.rmtree(take, ignore_errors=True)


def encode(cache, out, width, crf, only):
    """The web film and its two pictures."""
    out.mkdir(parents=True, exist_ok=True)
    height = round(width * 9 / 16 / 2) * 2
    scale = f"scale={width}:{height}:flags=lanczos"
    for page, (name, late, *_) in STORIES.items():
        if only and page not in only:
            continue
        src = cache / f"{name}.mp4"
        if not src.exists():
            print(f"{page}: no recording at {src}, skipped")
            continue
        film = out / f"{page}.mp4"
        rate = run("ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "default=nw=1:nk=1", src).stdout.split()
        fps = round(float(Fraction(rate[0]))) if rate else 30
        # a key frame every two seconds, so the film can start anywhere quickly
        done = run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", scale, "-c:v", "libx264", "-preset", "slow", "-crf", crf, "-g", 2 * fps,
                   "-threads", "4", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", film)
        if done.returncode:
            sys.exit(f"ffmpeg failed on {src}: {done.stderr[-400:]}")
        seconds = float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src).stdout.strip())
        for target, at in ((out / f"{page}.jpg", 0.15), (out / f"{page}-still.jpg", seconds * late)):
            run("ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", src, "-frames:v", "1", "-vf", scale, "-q:v", "4", target)
        print(f"{page}: {film.name} {film.stat().st_size / 1e6:.1f} MB, {seconds:.1f} s, still at {seconds * late:.1f} s", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", metavar="URL", help="record the pages of the app running at this address first")
    ap.add_argument("--fps", type=int, default=30, help="frames a second of the recordings")
    ap.add_argument("--cache", type=Path, default=WEB / ".cache" / "film", help="where the recordings are kept (not in git)")
    ap.add_argument("--out", type=Path, default=WEB / "public" / "films")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--crf", default="27", help="quality of the web film: lower is better and larger")
    ap.add_argument("--only", nargs="*", choices=list(STORIES), help="just these films (tour, flood, fire, rice)")
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is not on the path")
    args.cache.mkdir(parents=True, exist_ok=True)
    if args.record:
        record(args.record.rstrip("/"), args.cache, args.fps, args.only)
    encode(args.cache, args.out, args.width, args.crf, args.only)


if __name__ == "__main__":
    sys.exit(main())
