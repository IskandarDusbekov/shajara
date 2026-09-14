"""A schematic antique-style map of Central Asia and its neighbours, drawn
with Pillow, for the sample historical maps.

Coastlines, rivers and ranges are hand-simplified approximations — right
enough to follow a campaign from Samarkand to Delhi or Ankara, not a survey.
The picture says so in its corner. Coordinates are (longitude, latitude) in
a plain equirectangular projection.
"""

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

LON_MIN, LON_MAX, LAT_MIN, LAT_MAX = 28.0, 82.0, 22.0, 56.0
W, H = 3000, 2400
MARGIN = 90

PAPER = (236, 222, 186)
INK = (74, 52, 30)
INK_SOFT = (120, 92, 60)
WATER = (205, 212, 190)
WATER_EDGE = (110, 120, 110)
RIVER = (96, 118, 128)
MOUNTAIN = (122, 94, 62)

SEAS = {
    "Kaspiy dengizi": [(47.5, 45.6), (49.2, 46.5), (51.2, 47.1), (53.0, 46.9), (53.2, 45.3), (51.3, 44.6), (50.3, 44.4),
                       (51.2, 43.1), (52.7, 42.6), (52.9, 41.6), (53.9, 40.8), (53.0, 40.0), (53.4, 39.0), (53.9, 37.4),
                       (52.0, 36.7), (50.4, 37.2), (49.0, 37.6), (48.9, 38.4), (49.4, 40.2), (50.3, 40.4), (49.5, 40.8),
                       (48.6, 41.8), (47.6, 43.0), (47.4, 43.9), (46.7, 44.6)],
    "Orol dengizi": [(58.2, 46.5), (60.0, 46.6), (61.3, 45.8), (61.1, 44.5), (59.9, 43.6), (58.8, 43.5), (58.3, 44.5),
                     (58.3, 45.6)],
    "Qora dengiz": [(28.0, 44.0), (28.6, 44.3), (29.6, 45.3), (30.8, 46.5), (32.5, 46.1), (33.6, 44.5), (35.3, 45.0),
                    (36.6, 45.3), (38.2, 44.7), (39.7, 43.6), (41.5, 42.2), (41.5, 41.5), (40.1, 40.9), (37.9, 41.1),
                    (36.2, 41.6), (35.0, 42.0), (33.3, 42.0), (31.3, 41.2), (29.2, 41.2), (28.0, 41.6)],
    "O‘rta yer dengizi": [(28.0, 36.7), (30.5, 36.3), (32.5, 36.1), (34.6, 36.8), (36.0, 36.8), (35.8, 35.8),
                          (35.9, 34.6), (35.1, 33.1), (34.5, 31.6), (33.0, 31.1), (30.5, 31.5), (28.0, 31.0)],
    "Qizil dengiz": [(32.5, 30.0), (34.9, 29.5), (36.3, 26.5), (38.7, 22.0), (37.0, 22.0), (33.5, 27.5)],
    "Arab dengizi": [(48.0, 30.0), (50.2, 30.1), (51.5, 27.9), (54.0, 26.6), (56.3, 27.1), (57.3, 25.8), (59.0, 25.4),
                     (61.5, 25.2), (64.5, 25.3), (66.6, 25.4), (67.3, 24.8), (68.5, 23.6), (70.2, 22.5), (70.5, 22.0),
                     (59.6, 22.0), (59.8, 22.5), (58.7, 23.6), (57.0, 23.9), (56.4, 24.9), (56.3, 26.3), (55.3, 25.3),
                     (54.0, 24.1), (52.0, 24.0), (51.2, 25.4), (50.3, 26.0), (49.6, 27.1),
                     (48.5, 28.5)],
    "Balxash": [(73.8, 46.0), (74.0, 46.5), (76.0, 46.7), (79.0, 46.6), (78.5, 45.9), (75.5, 45.8)],
    "Issiqko‘l": [(76.2, 42.5), (78.2, 42.9), (78.5, 42.3), (76.5, 42.2)],
}
SEA_LABELS = {
    "Kaspiy dengizi": (51.0, 42.2, 38), "Orol dengizi": (59.7, 45.1, 26), "Qora dengiz": (34.2, 43.2, 38),
    "O‘rta yer dengizi": (31.2, 33.5, 30), "Arab dengizi": (62.5, 23.2, 38), "Fors ko‘rfazi": (51.0, 27.6, 24),
}
RIVERS = {
    "Amudaryo": [(73.5, 37.2), (71.5, 37.6), (70.0, 37.5), (68.3, 37.1), (67.5, 37.2), (66.0, 37.8), (65.0, 38.4),
                 (63.5, 39.4), (62.0, 40.5), (61.0, 41.4), (60.3, 42.3), (59.6, 43.4), (59.4, 43.9)],
    "Sirdaryo": [(72.9, 40.9), (71.5, 40.9), (70.5, 40.7), (69.6, 40.3), (68.8, 40.8), (68.5, 41.9), (68.2, 42.9),
                 (67.0, 44.0), (65.5, 44.8), (63.5, 45.9), (61.3, 46.0)],
    "Zarafshon": [(70.0, 39.4), (68.0, 39.5), (67.0, 39.65), (66.0, 39.8), (65.0, 39.9), (64.2, 39.6), (63.8, 39.4)],
    "Volga": [(45.5, 56.0), (46.0, 52.5), (47.5, 51.5), (46.0, 50.0), (44.5, 48.7), (46.0, 47.5), (47.8, 46.4), (48.3, 46.0)],
    "Jayiq": [(58.5, 51.5), (55.0, 51.7), (52.0, 51.2), (51.4, 50.0), (51.8, 48.5), (51.9, 47.0)],
    "Dajla": [(41.0, 37.8), (42.5, 37.0), (43.1, 36.3), (44.4, 33.3), (45.8, 32.5), (47.0, 31.0), (48.0, 30.4)],
    "Furot": [(38.8, 39.0), (38.5, 37.0), (38.2, 36.0), (40.1, 34.9), (41.5, 34.4), (43.3, 32.6), (45.0, 31.9),
              (46.5, 31.0), (47.5, 30.6), (48.0, 30.4)],
    "Hind": [(77.5, 34.5), (75.0, 35.6), (73.0, 34.5), (72.0, 33.0), (71.5, 31.5), (70.5, 29.0), (69.3, 27.5),
             (68.3, 25.5), (67.5, 24.1)],
    "Jamna": [(77.5, 30.5), (77.2, 28.6), (78.0, 27.2), (79.5, 26.0), (81.8, 25.4)],
    "Gang": [(78.5, 30.0), (79.5, 28.5), (81.0, 26.5), (82.0, 25.3)],
    "Terek": [(44.6, 42.8), (45.5, 43.6), (46.8, 43.6), (47.5, 43.9)],
    "Ili": [(81.5, 43.9), (79.5, 44.0), (77.5, 44.2), (76.0, 45.3), (75.0, 45.9)],
}
RANGES = {
    "Tyanshan": [(69.5, 42.0), (72.0, 42.4), (75.0, 41.6), (78.0, 42.0), (81.5, 42.6)],
    "Pomir": [(72.0, 38.9), (73.5, 38.3), (75.0, 37.9)],
    "Hindukush": [(67.5, 35.4), (69.5, 35.7), (71.5, 36.2), (73.0, 36.6)],
    "Himolay": [(74.0, 34.8), (76.5, 33.5), (79.0, 31.5), (81.5, 30.2)],
    "Zagros": [(45.0, 35.6), (47.5, 33.6), (50.5, 31.2), (53.0, 29.5), (56.0, 27.8)],
    "Kavkaz": [(38.5, 44.0), (41.5, 43.2), (44.5, 42.7), (47.5, 41.6), (49.5, 40.8)],
    "Ko‘pettog‘": [(54.0, 38.6), (57.0, 37.9), (59.5, 37.2), (61.0, 36.6)],
    "Alburz": [(49.0, 36.9), (51.5, 36.2), (54.0, 36.5)],
    "Toros": [(30.0, 37.2), (33.0, 36.9), (36.0, 37.6), (38.5, 38.1)],
    "Hisor": [(67.0, 39.0), (68.5, 39.2), (70.0, 39.3)],
}
LANDS = {
    "MOVAROUNNAHR": (66.3, 41.2), "XUROSON": (59.5, 35.3), "DASHTI QIPCHOQ": (62.0, 49.5), "HINDISTON": (75.0, 24.6),
    "ERON": (55.0, 32.3), "ARABISTON": (43.5, 25.0), "KICHIK OSIYO": (33.5, 39.4), "OLTIN O‘RDA": (50.0, 50.8),
    "XORAZM": (57.5, 41.6), "FARG‘ONA": (72.3, 40.0), "SHOM": (38.2, 33.2), "IROQ": (43.5, 31.2),
}


def project(lon, lat):
    x = MARGIN + (lon - LON_MIN) / (LON_MAX - LON_MIN) * (W - 2 * MARGIN)
    y = MARGIN + (LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * (H - 2 * MARGIN)
    return x, y


def fraction(lat, lon):
    """The (x, y) fraction of the image for a place — what MapPlace stores."""
    x, y = project(lon, lat)
    return round(x / W, 5), round(y / H, 5)


def _font(size, italic=False, bold=False):
    names = []
    if bold:
        names += ["C:/Windows/Fonts/palab.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"]
    if italic:
        names += ["C:/Windows/Fonts/palai.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"]
    names += ["C:/Windows/Fonts/pala.ttf", "C:/Windows/Fonts/georgia.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"]
    for path in names:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _smooth(points, steps=10):
    """Catmull-Rom through the points, so rivers and coasts don't look ruled."""
    if len(points) < 3:
        return points
    pts = [points[0]] + points + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for t in range(steps):
            t /= steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3) for k in (0, 1)))
    out.append(points[-1])
    return out


def _spaced_text(draw, xy, text, font, fill, spacing=8):
    x, y = xy
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x -= total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill, anchor="lm")
        x += w + spacing


def draw_basemap(path, title="Markaziy Osiyo va qo‘shni o‘lkalar", seed=7):
    rng = random.Random(seed)
    img = Image.new("RGB", (W, H), PAPER)

    # paper: blotches and a darker edge
    stains = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(stains)
    for _ in range(90):
        cx, cy, r = rng.randint(0, W), rng.randint(0, H), rng.randint(60, 380)
        sd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=rng.randint(6, 22))
    stains = stains.filter(ImageFilter.GaussianBlur(60))
    img = Image.composite(Image.new("RGB", (W, H), (205, 184, 140)), img, stains)
    edge = Image.new("L", (W, H), 0)
    ImageDraw.Draw(edge).rectangle((0, 0, W, H), outline=110, width=160)
    edge = edge.filter(ImageFilter.GaussianBlur(90))
    img = Image.composite(Image.new("RGB", (W, H), (176, 146, 100)), img, edge)
    noise = Image.effect_noise((W // 3, H // 3), 24).resize((W, H)).filter(ImageFilter.GaussianBlur(1))
    img = Image.blend(img, Image.merge("RGB", (noise, noise, noise)).point(lambda v: 200 + v // 5), 0.08)

    d = ImageDraw.Draw(img, "RGBA")

    # graticule
    for lon in range(30, 82, 5):
        x, _ = project(lon, LAT_MIN)
        for yy in range(MARGIN, H - MARGIN, 18):
            d.line((x, yy, x, yy + 7), fill=INK_SOFT + (70,), width=2)
    for lat in range(25, 56, 5):
        _, y = project(LON_MIN, lat)
        for xx in range(MARGIN, W - MARGIN, 18):
            d.line((xx, y, xx + 7, y), fill=INK_SOFT + (70,), width=2)

    # seas and lakes with a ripple line inside the coast
    for name, coast in SEAS.items():
        pts = [project(*p) for p in _smooth(coast + [coast[0]], 6)]
        d.polygon(pts, fill=WATER + (255,))
        d.line(pts + [pts[0]], fill=WATER_EDGE + (255,), width=4, joint="curve")
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        for k in (0.9, 0.8):
            inner = [(cx + (px - cx) * k, cy + (py - cy) * k) for px, py in pts]
            d.line(inner + [inner[0]], fill=WATER_EDGE + (60,), width=2)

    # rivers
    for name, course in RIVERS.items():
        pts = [project(*p) for p in _smooth(course, 10)]
        n = len(pts)
        for i in range(n - 1):
            width = 2 + int(4 * i / n)
            d.line((pts[i], pts[i + 1]), fill=RIVER + (230,), width=width)

    # mountain ranges as little hachured peaks
    peak_font = None
    for name, ridge in RANGES.items():
        pts = [project(*p) for p in _smooth(ridge, 12)]
        for i in range(0, len(pts), 3):
            x, y = pts[i]
            x += rng.uniform(-14, 14)
            y += rng.uniform(-14, 14)
            s = rng.uniform(16, 26)
            d.polygon([(x - s, y + s * 0.6), (x, y - s * 0.8), (x + s, y + s * 0.6)], fill=(214, 194, 150, 255))
            d.line([(x - s, y + s * 0.6), (x, y - s * 0.8), (x + s, y + s * 0.6)], fill=MOUNTAIN + (255,), width=3)
            d.line([(x, y - s * 0.8), (x + s * 0.35, y + s * 0.6)], fill=MOUNTAIN + (140,), width=2)

    # labels
    land_font = _font(46, bold=True)
    for text, (lon, lat) in LANDS.items():
        _spaced_text(d, project(lon, lat), text, land_font, INK_SOFT + (150,), spacing=10)
    for text, (lon, lat, size) in SEA_LABELS.items():
        f = _font(size + 8, italic=True)
        d.text(project(lon, lat), text, font=f, fill=(70, 88, 96, 230), anchor="mm")
    river_font = _font(28, italic=True)
    for name, course in RIVERS.items():
        mid = course[len(course) // 2]
        d.text(project(mid[0], mid[1] + 0.45), name, font=river_font, fill=RIVER + (230,), anchor="mm")
    range_font = _font(28, italic=True)
    for name, ridge in RANGES.items():
        mid = ridge[len(ridge) // 2]
        d.text(project(mid[0], mid[1] - 1.0), name, font=range_font, fill=MOUNTAIN + (220,), anchor="mm")

    # compass rose
    cx, cy, r = project(77.0, 51.0)[0], project(77.0, 51.0)[1], 150
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=INK + (200,), width=3)
    d.ellipse((cx - r * 0.8, cy - r * 0.8, cx + r * 0.8, cy + r * 0.8), outline=INK + (120,), width=2)
    for ang in range(0, 360, 45):
        a = math.radians(ang)
        long_ray = ang % 90 == 0
        tip = r * (1.0 if long_ray else 0.62)
        side = 22 if long_ray else 14
        tx, ty = cx + math.sin(a) * tip, cy - math.cos(a) * tip
        lx, ly = cx + math.sin(a - math.pi / 2) * side, cy - math.cos(a - math.pi / 2) * side
        rx, ry = cx + math.sin(a + math.pi / 2) * side, cy - math.cos(a + math.pi / 2) * side
        d.polygon([(tx, ty), (lx, ly), (cx, cy)], fill=INK + (230,))
        d.polygon([(tx, ty), (rx, ry), (cx, cy)], fill=(214, 194, 150, 255), outline=INK + (230,))
    d.text((cx, cy - r - 36), "SH", font=_font(40, bold=True), fill=INK, anchor="mm")

    # title cartouche
    f_title, f_sub = _font(64, bold=True), _font(34, italic=True)
    box = (MARGIN + 60, MARGIN + 50, MARGIN + 60 + 1120, MARGIN + 50 + 210)
    d.rounded_rectangle(box, radius=26, fill=(240, 228, 196, 235), outline=INK + (230,), width=4)
    d.rounded_rectangle((box[0] + 12, box[1] + 12, box[2] - 12, box[3] - 12), radius=18, outline=INK + (120,), width=2)
    d.text(((box[0] + box[2]) / 2, box[1] + 82), title, font=f_title, fill=INK, anchor="mm")
    d.text(((box[0] + box[2]) / 2, box[1] + 150), "sxematik namunaviy xarita · e-Shajara platformasi", font=f_sub,
           fill=INK_SOFT, anchor="mm")

    # frame with degree ticks
    d.rectangle((MARGIN - 30, MARGIN - 30, W - MARGIN + 30, H - MARGIN + 30), outline=INK + (255,), width=6)
    d.rectangle((MARGIN - 14, MARGIN - 14, W - MARGIN + 14, H - MARGIN + 14), outline=INK + (180,), width=2)
    tick = _font(24)
    for lon in range(30, 82, 5):
        x, _ = project(lon, LAT_MIN)
        d.text((x, H - MARGIN + 58), f"{lon}°", font=tick, fill=INK_SOFT, anchor="mm")
    for lat in range(25, 56, 5):
        _, y = project(LON_MIN, lat)
        d.text((MARGIN - 58, y), f"{lat}°", font=tick, fill=INK_SOFT, anchor="mm")

    img.save(path, format="JPEG", quality=88, optimize=True)
    return W, H
