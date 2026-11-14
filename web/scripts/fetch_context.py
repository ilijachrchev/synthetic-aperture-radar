"""Satellite context for the pinned stories: a Sentinel-2 cloudless mosaic (EOX, 2020) around each story's radar box,
so the radar and its change sit on the real ground around them.

    python -I scripts/fetch_context.py            (run from web/)

Writes public/img/context/<site>.webp and src/data/context.json:
  { site: { w, h, box: [x0, y0, x1, y1] } }   box = the radar box as fractions of the image (Web Mercator).
Tiles are cached under .cache/eox/ so a rerun fetches nothing. Credit on the page: "Sentinel-2 cloudless by EOX IT
Services GmbH (contains modified Copernicus Sentinel data 2020)".
"""
import io, json, math, os, time, urllib.request
from PIL import Image, ImageEnhance

TILE = 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg'
# the story places: their radar boxes come from the pass data
SITES = ['coast', 'espada', 'lorca', 'panama']
OUT_W, OUT_H = 2200, 1800  # the image, centred on the box
BOX_PX = 660  # the box's longer side in image pixels
CACHE = os.path.join('.cache', 'eox')


def merc(lon, lat):
    """Lon/lat to Web Mercator in [0, 1] (y grows south)."""
    x = (lon + 180) / 360
    s = math.sin(math.radians(lat))
    y = 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)
    return x, y


def tile(z, x, y):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f'{z}_{x}_{y}.jpg')
    if not os.path.exists(p):
        req = urllib.request.Request(TILE.format(z=z, x=x, y=y), headers={'User-Agent': 'space-apps-nisar-context/1.0'})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = r.read()
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(1.5 * (attempt + 1))
        with open(p, 'wb') as f:
            f.write(data)
        time.sleep(0.05)
    return Image.open(p).convert('RGB')


def main():
    sites = json.load(open(os.path.join('src', 'data', 'passes.json'), encoding='utf-8'))['sites']
    os.makedirs(os.path.join('public', 'img', 'context'), exist_ok=True)
    meta = {}
    for site in SITES:
        w, s, e, n = sites[site]['box']
        x0, y0 = merc(w, n)
        x1, y1 = merc(e, s)
        bw, bh = x1 - x0, y1 - y0
        scale = BOX_PX / max(bw, bh)  # output pixels per Mercator unit
        z = max(0, math.ceil(math.log2(scale / 256)))  # fetch at least that sharp, then downsample
        world = 256 * 2 ** z
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        # the output window in Mercator units, then in tile pixels at zoom z
        half_w, half_h = OUT_W / 2 / scale, OUT_H / 2 / scale
        wx0, wy0, wx1, wy1 = cx - half_w, cy - half_h, cx + half_w, cy + half_h
        px0, py0, px1, py1 = wx0 * world, wy0 * world, wx1 * world, wy1 * world
        tx0, ty0, tx1, ty1 = int(px0 // 256), int(py0 // 256), int(px1 // 256), int(py1 // 256)
        mosaic = Image.new('RGB', ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                mosaic.paste(tile(z, tx % 2 ** z, ty), ((tx - tx0) * 256, (ty - ty0) * 256))
        crop = mosaic.crop((round(px0 - tx0 * 256), round(py0 - ty0 * 256), round(px1 - tx0 * 256), round(py1 - ty0 * 256)))
        img = crop.resize((OUT_W, OUT_H), Image.LANCZOS)
        # a touch quieter than the raw mosaic, so the radar and its change carry the colour
        img = ImageEnhance.Color(img).enhance(0.78)
        img = ImageEnhance.Contrast(img).enhance(1.06)
        img.save(os.path.join('public', 'img', 'context', f'{site}.webp'), 'WEBP', quality=72, method=6)
        meta[site] = {
            'w': OUT_W,
            'h': OUT_H,
            'box': [round((x0 - wx0) / (wx1 - wx0), 5), round((y0 - wy0) / (wy1 - wy0), 5), round((x1 - wx0) / (wx1 - wx0), 5), round((y1 - wy0) / (wy1 - wy0), 5)],
        }
        kb = os.path.getsize(os.path.join('public', 'img', 'context', f'{site}.webp')) // 1024
        print(site, 'zoom', z, 'tiles', (tx1 - tx0 + 1) * (ty1 - ty0 + 1), 'box', meta[site]['box'], f'{kb} KB')
    with open(os.path.join('src', 'data', 'context.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent='\t')
        f.write('\n')


if __name__ == '__main__':
    main()
