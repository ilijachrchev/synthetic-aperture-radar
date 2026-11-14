"""Page grounds baked from real data, by day and by night (written to public/img/ground/).

    python -I scripts/fetch_grounds.py            (run from web/)

terrain-{day,night}.webp  The Valencia basin as a quiet shaded relief from the AWS Terrain Tiles (Terrarium, open
                          data), the sea from its bathymetry, and the rivers traced from the same elevation: water
                          is routed downhill cell by cell (priority flood, then D8), so the Turia and the Poyo
                          ravine that flooded appear where the ground sends them.
radar-{day,night}.webp    A real NISAR pass over Valencia (the flooded paddies of 18 Jun), enlarged, drained to one
                          tone and given the speckle a radar image has at full resolution.
Tiles cache under .cache/terrarium/.
"""
import heapq, io, math, os, time, urllib.request
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

TILE = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
CACHE = os.path.join('.cache', 'terrarium')
OUT = os.path.join('public', 'img', 'ground')
# the basin from the Serranía to the sea, Valencia a little right of centre
LON0, LON1, LAT0, LAT1 = -1.62, 0.42, 38.72, 39.98
Z = 10
W, H = 2400, 1500


def merc(lon, lat):
    s = math.sin(math.radians(lat))
    return (lon + 180) / 360, 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)


def tile(z, x, y):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f'{z}_{x}_{y}.png')
    if not os.path.exists(p):
        req = urllib.request.Request(TILE.format(z=z, x=x, y=y), headers={'User-Agent': 'space-apps-nisar-ground/1.0'})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = r.read()
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(1.5 * (attempt + 1))
        open(p, 'wb').write(data)
    return np.asarray(Image.open(p).convert('RGB'), dtype=np.float64)


def elevation():
    (x0, y0), (x1, y1) = merc(LON0, LAT1), merc(LON1, LAT0)
    world = 256 * 2 ** Z
    px0, py0, px1, py1 = x0 * world, y0 * world, x1 * world, y1 * world
    tx0, ty0, tx1, ty1 = int(px0 // 256), int(py0 // 256), int(px1 // 256), int(py1 // 256)
    rows = []
    for ty in range(ty0, ty1 + 1):
        rows.append(np.concatenate([tile(Z, tx, ty) for tx in range(tx0, tx1 + 1)], axis=1))
    m = np.concatenate(rows, axis=0)
    e = m[..., 0] * 256 + m[..., 1] + m[..., 2] / 256 - 32768
    e = e[int(py0 - ty0 * 256) : int(py1 - ty0 * 256), int(px0 - tx0 * 256) : int(px1 - tx0 * 256)]
    # metres per pixel at the box's middle latitude
    mpp = 156543.03 * math.cos(math.radians((LAT0 + LAT1) / 2)) / 2 ** Z
    return e, mpp


def hillshade(e, mpp, az=315, alt=42, exag=2.2):
    gy, gx = np.gradient(e * exag, mpp)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a, z = math.radians(360 - az + 90), math.radians(90 - alt)
    return np.clip(np.cos(z) * np.cos(slope) + np.sin(z) * np.sin(slope) * np.cos(a - aspect), 0, 1)


def rivers(e, sea, step=3):
    """Route water downhill on a coarser grid: fill the hollows from the sea and the edges inward (priority flood),
    send each cell to its steepest lower neighbour (D8), and add up what flows through every cell."""
    E = e[::step, ::step].copy()
    S = sea[::step, ::step]
    h, w = E.shape
    filled = np.full_like(E, np.inf)
    seen = np.zeros(E.shape, bool)
    q = []
    for y in range(h):
        for x in range(w):
            if S[y, x] or y in (0, h - 1) or x in (0, w - 1):
                filled[y, x] = E[y, x]
                seen[y, x] = True
                heapq.heappush(q, (E[y, x], y, x))
    N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    while q:
        z, y, x = heapq.heappop(q)
        for dy, dx in N8:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not seen[ny, nx]:
                seen[ny, nx] = True
                filled[ny, nx] = max(E[ny, nx], z + 1e-3)
                heapq.heappush(q, (filled[ny, nx], ny, nx))
    down = np.full(E.shape, -1, np.int64)
    for y in range(h):
        for x in range(w):
            if S[y, x]:
                continue
            best, bi = 0.0, -1
            for dy, dx in N8:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    d = (filled[y, x] - filled[ny, nx]) / (1.4142 if dy and dx else 1)
                    if d > best:
                        best, bi = d, ny * w + nx
            down[y, x] = bi
    acc = np.ones(h * w)
    order = np.argsort(-filled, axis=None)
    flat = down.ravel()
    for i in order:
        j = flat[i]
        if j >= 0:
            acc[j] += acc[i]
    return acc.reshape(h, w), down, step


def draw_rivers(size, acc, down, step, sea, colour, scale):
    h, w = acc.shape
    ss = 2  # drawn twice as large, then reduced, for smooth lines
    layer = Image.new('RGBA', (size[0] * ss, size[1] * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    sx, sy = size[0] * ss / (w * step), size[1] * ss / (h * step)
    lo = 260  # cells: about 30 km2 of catchment before a line is drawn
    for y in range(h):
        for x in range(w):
            a = acc[y, x]
            j = down[y, x]
            if a < lo or j < 0:
                continue
            ny, nx = divmod(j, w)
            if sea[min(ny * step, sea.shape[0] - 1), min(nx * step, sea.shape[1] - 1)]:
                pass
            t = min(1.0, math.log(a / lo) / math.log(60))
            width = (0.8 + 2.6 * t) * scale * ss
            alpha = int(255 * (0.28 + 0.6 * t))
            d.line([((x + 0.5) * step * sx, (y + 0.5) * step * sy), ((nx + 0.5) * step * sx, (ny + 0.5) * step * sy)], fill=colour + (alpha,), width=max(1, round(width)))
    return layer.resize(size, Image.LANCZOS)


def terrain():
    e, mpp = elevation()
    sea = e <= 0.5
    hs = hillshade(e, mpp)
    acc, down, step = rivers(e, sea)
    print('terrain grid', e.shape, 'max acc', int(acc.max()))
    size = (W, H)
    res = lambda a: np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize(size, Image.LANCZOS), dtype=np.float64) / 255
    shade = res(hs)
    land = res((~sea).astype(np.float64))
    land = np.asarray(Image.fromarray((land * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)), dtype=np.float64) / 255
    flat = np.clip(1 - shade / 0.72, 0, 1)  # how much a slope turns away from the light
    lit = np.clip((shade - 0.72) / 0.28, 0, 1)
    out = {}
    for name, ground, shadow, light, water, coast, riv in (
        ('day', (251, 250, 247), (40, 52, 58), (255, 255, 255), (234, 247, 250), (0, 131, 194), (0, 131, 194)),
        ('night', (6, 15, 19), (0, 0, 0), (40, 92, 108), (7, 25, 32), (18, 181, 214), (127, 224, 240)),
    ):
        g = np.array(ground, np.float64)
        img = np.empty((H, W, 3))
        k = 0.34 if name == 'day' else 0.55
        for c in range(3):
            v = g[c] + (shadow[c] - g[c]) * flat * k + (light[c] - g[c]) * lit * (0.5 if name == 'day' else 0.45)
            img[..., c] = v * land + water[c] * (1 - land)
        # the coastline: a hairline where land meets the sea
        edge = np.clip(np.abs(np.gradient(land)[0]) + np.abs(np.gradient(land)[1]), 0, 1)
        for c in range(3):
            img[..., c] = img[..., c] * (1 - edge * 0.7) + coast[c] * edge * 0.7
        base = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert('RGBA')
        base.alpha_composite(draw_rivers(size, acc, down, step, sea, riv, 1.0))
        p = os.path.join(OUT, f'terrain-{name}.webp')
        base.convert('RGB').save(p, 'WEBP', quality=80, method=6)
        out[name] = os.path.getsize(p) // 1024
    print('terrain', out, 'KB')


def radar():
    src = Image.open(os.path.join('public', 'radar', 'valencia', sorted(os.listdir(os.path.join('public', 'radar', 'valencia')))[0])).convert('RGBA')
    rgb = np.asarray(src, dtype=np.float64)
    L = (0.3 * rgb[..., 0] + 0.59 * rgb[..., 1] + 0.11 * rgb[..., 2]) / 255
    A = rgb[..., 3] / 255
    # fill the no-data rim with the mean so the enlarged picture has no hard edges
    L = np.where(A > 0.05, L, L[A > 0.05].mean())
    big = (W, int(W * L.shape[0] / L.shape[1]))
    up = np.asarray(Image.fromarray((L * 255).astype(np.uint8)).resize(big, Image.LANCZOS), dtype=np.float64) / 255
    # speckle: radar is coherent, so every resolution cell carries multiplicative gamma noise (about four looks)
    rng = np.random.default_rng(7)
    speck = rng.gamma(4.0, 1 / 4.0, size=up.shape)
    speck = np.asarray(Image.fromarray(np.clip(speck * 96, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6)), dtype=np.float64) / 96
    tex = np.clip(up * speck, 0, 1.6)
    tex = tex[(tex.shape[0] - H) // 2 : (tex.shape[0] - H) // 2 + H] if tex.shape[0] >= H else tex
    # a soft fall off toward the top left, where the hero's headline sits
    yy, xx = np.mgrid[0 : tex.shape[0], 0 : tex.shape[1]]
    fall = np.clip(0.35 + 0.65 * ((xx / tex.shape[1]) * 0.7 + (yy / tex.shape[0]) * 0.3), 0, 1)
    out = {}
    for name, ground, ink, k in (('day', (251, 250, 247), (16, 40, 50), 0.3), ('night', (6, 15, 19), (127, 224, 240), 0.24)):
        g = np.array(ground, np.float64)
        i = np.array(ink, np.float64)
        t = np.clip(tex / 1.2, 0, 1) * fall * k
        img = g[None, None, :] * (1 - t[..., None]) + i[None, None, :] * t[..., None]
        p = os.path.join(OUT, f'radar-{name}.webp')
        Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(p, 'WEBP', quality=82, method=6)
        out[name] = os.path.getsize(p) // 1024
    print('radar', out, 'KB')


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    terrain()
    radar()
