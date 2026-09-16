"""Share cards: 1200×630 PNG pictures for messenger and social previews.

Three kinds, one visual language (deep green, gold, a column of seven
generation rings — the "yetti ota" idea the whole campaign is built on):

  * avlod  — "#YettiOtam": how many of seven generations a tree reaches;
  * test   — a quiz result;
  * tree   — the preview of an open (SEO) tree page.

A private tree never shows names on a card: only counts. The share links
carry a signed token, so cards cannot be enumerated by id.
"""

import os
from functools import lru_cache
from io import BytesIO

from django.conf import settings
from django.core import signing
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
BG_TOP = (14, 38, 31)
BG_BOTTOM = (24, 62, 50)
GOLD = (233, 200, 105)
GOLD_DIM = (150, 128, 70)
CREAM = (246, 239, 224)
SOFT = (176, 202, 188)
LINE = (58, 92, 78)

SALTS = {"avlod": "eshajara.share.avlod", "test": "eshajara.share.test"}


# ------------------------------------------------------------------ tokens --

def make_token(kind, pk):
    return signing.dumps(pk, salt=SALTS[kind], compress=True)


def read_token(kind, token):
    try:
        return int(signing.loads(token, salt=SALTS[kind]))
    except (signing.BadSignature, TypeError, ValueError):
        return None


# ------------------------------------------------------------------- fonts --

_FONT_DIRS = [os.path.join(settings.BASE_DIR, "static", "fonts")]
_CANDIDATES = {
    "serif": ["serif-bold.ttf", "C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/palab.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"],
    "sans": ["sans.ttf", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"],
    "sans-bold": ["sans-bold.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
}


@lru_cache(maxsize=64)
def font(kind, size):
    for name in _CANDIDATES[kind]:
        paths = [name] if os.path.isabs(name) or ":" in name else [os.path.join(d, name) for d in _FONT_DIRS]
        for path in paths:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except OSError:
                    continue
    return ImageFont.load_default()


def clean(text):
    """The Uzbek ʻ ʼ letters are missing from many system fonts."""
    return (text or "").replace("ʻ", "'").replace("ʼ", "'").replace("‘", "'").replace("’", "'")


def wrap(draw, text, fnt, width, max_lines=2):
    words, lines, line = clean(text).split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= width:
            line = trial
            continue
        if line:
            lines.append(line)
        line = word
        if len(lines) == max_lines:
            break
    if line and len(lines) < max_lines:
        lines.append(line)
    consumed = " ".join(lines)
    if len(consumed) < len(" ".join(words)) and lines:
        last = lines[-1]
        while last and draw.textlength(last + "…", font=fnt) > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def fit_font(draw, text, kind, width, start, smallest, max_lines=2):
    size = start
    while size > smallest:
        fnt = font(kind, size)
        lines = wrap(draw, text, fnt, width, max_lines=max_lines + 1)
        if len(lines) <= max_lines and not lines[-1].endswith("…"):
            return fnt, lines
        size -= 4
    fnt = font(kind, smallest)
    return fnt, wrap(draw, text, fnt, width, max_lines=max_lines)


# ---------------------------------------------------------------- drawing --

def _canvas():
    img = Image.new("RGB", (W, H), BG_TOP)
    px = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        px.line([(0, y), (W, y)], fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
    # quiet concentric rings, like a tree's growth rings, in the far corner
    for i, r in enumerate(range(120, 900, 70)):
        px.ellipse([W - 150 - r, H + 60 - r, W - 150 + r, H + 60 + r], outline=(30 + i, 70 + i, 56 + i), width=2)
    return img, ImageDraw.Draw(img)


def _leaf(draw, x, y, s, color):
    draw.polygon([(x, y + s), (x + s * 0.15, y + s * 0.35), (x + s * 0.85, y), (x + s * 0.6, y + s * 0.7)], fill=color)
    draw.line([(x, y + s), (x + s * 0.62, y + s * 0.34)], fill=BG_TOP, width=max(2, int(s / 12)))


def _brand(draw, host):
    draw.rounded_rectangle([64, 52, 112, 100], radius=12, fill=GOLD)
    _leaf(draw, 76, 62, 26, BG_TOP)
    draw.text((126, 58), "e-Shajara", font=font("serif", 34), fill=CREAM)
    if host:
        f = font("sans-bold", 26)
        tw = draw.textlength(host, font=f)
        draw.text((W - 64 - tw, H - 74), host, font=f, fill=GOLD)


def _generation_column(draw, filled, total=7, x=1010, top=104, bottom=486):
    """Seven rings from the oldest generation (top) down; the known ones are gold."""
    step = (bottom - top) / (total - 1)
    numerals = ["I", "II", "III", "IV", "V", "VI", "VII"]
    for i in range(total - 1):
        y1, y2 = top + i * step + 30, top + (i + 1) * step - 30
        on = i + 1 < filled
        draw.line([(x, y1), (x, y2)], fill=GOLD if on else LINE, width=4)
    for i in range(total):
        cy = top + i * step
        on = i < filled
        r = 28
        if on:
            draw.ellipse([x - r, cy - r, x + r, cy + r], fill=GOLD)
        else:
            draw.ellipse([x - r, cy - r, x + r, cy + r], outline=LINE, width=4)
        f = font("serif", 22)
        label = numerals[i]
        tw = draw.textlength(label, font=f)
        draw.text((x - tw / 2, cy - 14), label, font=f, fill=BG_TOP if on else SOFT)


def _chip(draw, x, y, text, fill=None, color=GOLD):
    f = font("sans-bold", 24)
    tw = draw.textlength(text, font=f)
    draw.rounded_rectangle([x, y, x + tw + 36, y + 46], radius=23, fill=fill, outline=None if fill else color, width=2)
    draw.text((x + 18, y + 8), text, font=f, fill=color)
    return x + tw + 36


def _png(img):
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ------------------------------------------------------------------ cards --

def avlod_card(generations, people, title=None, host=""):
    img, d = _canvas()
    _brand(d, host)
    known = max(0, min(generations, 7))
    _chip(d, 64, 150, "#YettiOtam")
    d.text((64, 222), "Yetti otangni bilasanmi?", font=font("sans", 34), fill=SOFT)
    if generations >= 7:
        headline = f"Men {generations} avlodimni bilaman"
    else:
        headline = f"Men 7 avloddan {known} tasini bilaman"
    hf, lines = fit_font(d, headline, "serif", 820, 76, 52)
    y = 276
    for line in lines:
        d.text((64, y), line, font=hf, fill=CREAM)
        y += int(hf.size * 1.12)
    sub = clean(title) if title else "Oila shajaram"
    sub = f"{sub} · {people} kishi"
    d.text((64, y + 16), wrap(d, sub, font("sans", 32), 820, 1)[0], font=font("sans", 32), fill=SOFT)
    d.text((64, H - 74), "Siz-chi? Shajarangizni tuzing", font=font("sans-bold", 26), fill=CREAM)
    _generation_column(d, known)
    return _png(img)


def test_card(score, total, title=None, learning=False, host=""):
    img, d = _canvas()
    _brand(d, host)
    pct = round(100 * score / total) if total else 0
    kicker = "O'zingizni sinang" if learning else "Oilangizni qanchalik bilasiz?"
    _chip(d, 64, 150, kicker)
    verdict = ("A'lo natija!" if pct >= 90 else "Yaxshi natija" if pct >= 70
               else "Yomon emas" if pct >= 50 else "Qayta urinib ko'raman")
    d.text((64, 224), verdict, font=font("sans", 34), fill=SOFT)
    name = clean(title) if title else "oilam shajarasi"
    hf, lines = fit_font(d, f"«{name}» bo'yicha {score}/{total}", "serif", 700, 72, 48)
    y = 276
    for line in lines:
        d.text((64, y), line, font=hf, fill=CREAM)
        y += int(hf.size * 1.12)
    d.text((64, y + 16), f"{total} ta savoldan {score} tasiga to'g'ri javob", font=font("sans", 32), fill=SOFT)
    d.text((64, H - 74), "Siz nechta topasiz?", font=font("sans-bold", 26), fill=CREAM)

    cx, cy, r = 965, 315, 150
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=LINE, width=26)
    if pct:
        d.arc([cx - r, cy - r, cx + r, cy + r], start=-90, end=-90 + 360 * pct / 100, fill=GOLD, width=26)
    f = font("serif", 84)
    label = f"{pct}%"
    tw = d.textlength(label, font=f)
    d.text((cx - tw / 2, cy - 56), label, font=f, fill=CREAM)
    return _png(img)


def tree_card(tree, people, generations, stories=0, host=""):
    img, d = _canvas()
    _brand(d, host)
    kicker = " · ".join(x for x in (clean(tree.era), "Ta'limiy shajara" if tree.is_learning else "Shajara") if x)
    _chip(d, 64, 150, kicker)
    hf, lines = fit_font(d, tree.name, "serif", 820, 80, 50)
    y = 222
    for line in lines:
        d.text((64, y), line, font=hf, fill=CREAM)
        y += int(hf.size * 1.12)
    if tree.subject:
        d.text((64, y + 6), wrap(d, tree.subject, font("sans", 32), 820, 1)[0], font=font("sans", 32), fill=SOFT)
    x = 64
    for value, label in ((people, "shaxs"), (generations, "avlod"), (stories, "hikoya")):
        if not value:
            continue
        vf, lf = font("serif", 46), font("sans", 24)
        v = str(value)
        vw = d.textlength(v, font=vf)
        lw = d.textlength(label, font=lf)
        box = max(vw, lw) + 44
        d.rounded_rectangle([x, 440, x + box, 540], radius=18, outline=LINE, width=2)
        d.text((x + (box - vw) / 2, 450), v, font=vf, fill=GOLD)
        d.text((x + (box - lw) / 2, 505), label, font=lf, fill=SOFT)
        x += box + 18
    _generation_column(d, min(generations, 7))
    return _png(img)

