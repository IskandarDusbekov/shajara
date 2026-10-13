"""The tree as a printed book.

Laid out the way family chronicles and dynasty histories are printed:

    cover            title, the founder, a stats line, compiler, QR check code
    foreword         what the book holds and how to read the numbers
    contents
    lineage register every descendant line, numbered d'Aboville style
                     (1 — founder, 1.2 — his second child, 1.2.1 — that
                     child's first child), indented by generation
    chapters         one per generation, made of families. Each family has
                     its own section: a small drawing (parents joined, their
                     children below), a full entry for the parent of the line
                     and every spouse, and a table of the children that links
                     to each child's own family further on. Families are in
                     the contents and in the PDF's bookmarks.
    sources          for learning trees
    colophon         who compiled it, when, and how to verify the copy

Built with reportlab's platypus directly: HTML-to-PDF converters can't do
running headers, a contents page with page numbers, or decorated frames.
"""

import datetime
import math
import os
import re
import threading
from collections import defaultdict
from functools import lru_cache
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Flowable, Frame, Image, KeepTogether, NextPageTemplate, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from .models import REGION_CHOICES
from .tree import compute_levels, level_label

PAGE_W, PAGE_H = A4

# ----------------------------------------------------------------- styles --
# The book comes in the same styles as the picture (tree-export.js). Pages
# stay light so they print well; only the cover may be dark.

BOOK_THEMES = {
    "classic": {
        "label": "Klassik", "frame": "double",
        "paper": "#fbf7ec", "ink": "#2b2118", "muted": "#7a6a55", "accent": "#a47b32", "accent_soft": "#d9c49a",
        "title": "#6b2a22", "rule": "#e6d9bd", "bar": "#6b2a22", "bar_num": "#e9cf94", "bar_sub": "#f3e6c9",
        "row_alt": "#f7f0de", "main_fill": "#f4ead2", "female": "#b56f7c",
        "cover": {"kind": "classic", "bg": "#fbf7ec", "title": "#6b2a22", "text": "#2b2118", "muted": "#7a6a55", "accent": "#a47b32"},
    },
    "emerald": {
        "label": "Zumrad", "frame": "double",
        "paper": "#fbfaf4", "ink": "#1d2a22", "muted": "#5f7466", "accent": "#a8842a", "accent_soft": "#d8c58e",
        "title": "#14513a", "rule": "#dde6da", "bar": "#14513a", "bar_num": "#e9cf94", "bar_sub": "#d9eadf",
        "row_alt": "#eef5ef", "main_fill": "#e3f0e6", "female": "#b56f7c",
        "cover": {"kind": "emerald", "bg": "#123a2a", "title": "#f3e3b5", "text": "#f1ead9", "muted": "#b9c9b8", "accent": "#d6b25e"},
    },
    "samarkand": {
        "label": "Samarqand", "frame": "tiles",
        "paper": "#fbf8f0", "ink": "#1d2747", "muted": "#5d6a86", "accent": "#23807c", "accent_soft": "#a9d3d1",
        "title": "#1f3c88", "rule": "#dfe3ee", "bar": "#1f3c88", "bar_num": "#e6c876", "bar_sub": "#dce4f6",
        "row_alt": "#eef3fb", "main_fill": "#e5edfb", "female": "#b56f7c",
        "cover": {"kind": "samarkand", "bg": "#f8f4ea", "title": "#1f3c88", "text": "#1d2747", "muted": "#5d6a86", "accent": "#c9a347"},
    },
    "modern": {
        "label": "Zamonaviy", "frame": "none",
        "paper": "#ffffff", "ink": "#18322a", "muted": "#5f7f6d", "accent": "#1a7a46", "accent_soft": "#bfdcc9",
        "title": "#123d27", "rule": "#e3efe7", "bar": "#1a7a46", "bar_num": "#cfeedd", "bar_sub": "#e4f5ea",
        "row_alt": "#f3faf5", "main_fill": "#e4f5ea", "female": "#d68a9b",
        "cover": {"kind": "modern", "bg": "#ffffff", "title": "#123d27", "text": "#18322a", "muted": "#5f7f6d", "accent": "#1a7a46"},
    },
    "ink": {
        "label": "Oq-qora", "frame": "thin",
        "paper": "#ffffff", "ink": "#111111", "muted": "#555555", "accent": "#333333", "accent_soft": "#bbbbbb",
        "title": "#111111", "rule": "#dddddd", "bar": "#222222", "bar_num": "#dddddd", "bar_sub": "#eeeeee",
        "row_alt": "#f4f4f4", "main_fill": "#eeeeee", "female": "#777777",
        "cover": {"kind": "ink", "bg": "#ffffff", "title": "#111111", "text": "#111111", "muted": "#555555", "accent": "#333333"},
    },
}
BOOK_STYLE_ORDER = ["classic", "emerald", "samarkand", "modern", "ink"]

# The colours below are read by every drawing function; build_book() points
# them at the chosen style for the length of one build (under _BUILD_LOCK).
THEME = BOOK_THEMES["classic"]
INK = MUTED = GOLD = GOLD_SOFT = WINE = PAPER = RULE = None
BAR = BAR_SUB = ROW_ALT = MAIN_FILL = FEMALE = None
A_HEX = M_HEX = BN_HEX = ""
_BUILD_LOCK = threading.Lock()


def use_theme(name):
    global THEME, INK, MUTED, GOLD, GOLD_SOFT, WINE, PAPER, RULE, BAR, BAR_SUB, ROW_ALT, MAIN_FILL, FEMALE
    global A_HEX, M_HEX, BN_HEX
    THEME = BOOK_THEMES.get(name) or BOOK_THEMES["classic"]
    h = colors.HexColor
    INK, MUTED, GOLD, GOLD_SOFT = h(THEME["ink"]), h(THEME["muted"]), h(THEME["accent"]), h(THEME["accent_soft"])
    WINE, PAPER, RULE = h(THEME["title"]), h(THEME["paper"]), h(THEME["rule"])
    BAR, BAR_SUB, ROW_ALT = h(THEME["bar"]), h(THEME["bar_sub"]), h(THEME["row_alt"])
    MAIN_FILL, FEMALE = h(THEME["main_fill"]), h(THEME["female"])
    A_HEX, M_HEX, BN_HEX = THEME["accent"], THEME["muted"], THEME["bar_num"]


use_theme("classic")

MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust",
          "sentabr", "oktabr", "noyabr", "dekabr"]


# ------------------------------------------------------------------ fonts --

FONT_SETS = [
    # (regular, bold, italic, bold italic) — the first set found is used.
    ("serif.ttf", "serif-bold.ttf", "serif-italic.ttf", "serif-bolditalic.ttf"),   # static/fonts
    ("C:/Windows/Fonts/pala.ttf", "C:/Windows/Fonts/palab.ttf", "C:/Windows/Fonts/palai.ttf", "C:/Windows/Fonts/palabi.ttf"),
    ("C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/georgiai.ttf", "C:/Windows/Fonts/georgiaz.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf", "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf"),
    ("/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf",
     "/usr/share/fonts/truetype/noto/NotoSerif-Italic.ttf", "/usr/share/fonts/truetype/noto/NotoSerif-BoldItalic.ttf"),
]


@lru_cache(maxsize=1)
def book_fonts():
    """Register a serif family once. A book font dropped into static/fonts
    wins; otherwise a system serif; reportlab's own Vera as the last resort."""
    font_dir = getattr(settings, "SHAJARA_PDF_FONT_DIR", None) or os.path.join(settings.BASE_DIR, "static", "fonts")
    reportlab_fonts = os.path.join(os.path.dirname(pdfmetrics.__file__), "..", "fonts")
    sets = [tuple(os.path.join(font_dir, f) for f in FONT_SETS[0])] + FONT_SETS[1:] + [
        tuple(os.path.join(reportlab_fonts, f) for f in ("Vera.ttf", "VeraBd.ttf", "VeraIt.ttf", "VeraBI.ttf"))
    ]
    for files in sets:
        if all(os.path.exists(f) for f in files):
            names = ("BookSerif", "BookSerif-Bold", "BookSerif-Italic", "BookSerif-BoldItalic")
            for name, path in zip(names, files):
                pdfmetrics.registerFont(TTFont(name, path))
            pdfmetrics.registerFontFamily("BookSerif", normal=names[0], bold=names[1], italic=names[2], boldItalic=names[3])
            face = pdfmetrics.getFont(names[0]).face
            return {"names": names, "glyphs": set(face.charToGlyph)}
    return {"names": ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"), "glyphs": set()}


def plain(text):
    """Like clean(), for strings drawn straight onto the canvas (no markup)."""
    glyphs = book_fonts()["glyphs"]
    text = str(text or "")
    for ch, alt in (("ʻ", "‘"), ("ʼ", "’")):
        if glyphs and ord(ch) not in glyphs:
            text = text.replace(ch, alt)
    return text


def clean(text):
    """Escape for reportlab's markup and swap characters the font lacks."""
    glyphs = book_fonts()["glyphs"]
    text = str(text or "")
    for ch, alt in (("ʻ", "‘"), ("ʼ", "’"), ("∞", "×"), ("№", "No."), ("→", "»")):
        if glyphs and ord(ch) not in glyphs:
            text = text.replace(ch, alt)
    return escape(text)


# ----------------------------------------------------------------- styles --

def make_styles():
    r, b, i, bi = book_fonts()["names"]
    s = {}
    s["body"] = ParagraphStyle("body", fontName=r, fontSize=10.5, leading=15.5, textColor=INK, alignment=TA_JUSTIFY)
    s["body_left"] = ParagraphStyle("body_left", parent=s["body"], alignment=TA_LEFT)
    s["small"] = ParagraphStyle("small", parent=s["body"], fontSize=8.8, leading=12, textColor=MUTED, alignment=TA_LEFT)
    s["center_small"] = ParagraphStyle("center_small", parent=s["small"], alignment=TA_CENTER)
    s["kicker"] = ParagraphStyle("kicker", fontName=b, fontSize=9, leading=12, textColor=GOLD, alignment=TA_CENTER,
                                 spaceAfter=6)
    s["cover_title"] = ParagraphStyle("cover_title", fontName=b, fontSize=30, leading=36, textColor=WINE,
                                      alignment=TA_CENTER)
    s["cover_sub"] = ParagraphStyle("cover_sub", fontName=i, fontSize=13, leading=18, textColor=INK, alignment=TA_CENTER)
    s["cover_meta"] = ParagraphStyle("cover_meta", fontName=r, fontSize=10.5, leading=15, textColor=MUTED,
                                     alignment=TA_CENTER)
    s["h1"] = ParagraphStyle("h1", fontName=b, fontSize=22, leading=28, textColor=WINE, alignment=TA_CENTER,
                             spaceAfter=4)
    s["chapter_no"] = ParagraphStyle("chapter_no", fontName=b, fontSize=40, leading=44, textColor=GOLD,
                                     alignment=TA_CENTER)
    s["chapter_intro"] = ParagraphStyle("chapter_intro", fontName=i, fontSize=10.5, leading=15, textColor=MUTED,
                                        alignment=TA_CENTER)
    s["h2"] = ParagraphStyle("h2", fontName=b, fontSize=14, leading=19, textColor=WINE, spaceBefore=10, spaceAfter=6)
    s["num"] = ParagraphStyle("num", fontName=b, fontSize=8.5, leading=11, textColor=GOLD)
    s["name"] = ParagraphStyle("name", fontName=b, fontSize=15, leading=19, textColor=INK)
    s["years"] = ParagraphStyle("years", fontName=i, fontSize=10.5, leading=14, textColor=MUTED)
    s["label"] = ParagraphStyle("label", fontName=b, fontSize=8.6, leading=12.5, textColor=GOLD)
    s["value"] = ParagraphStyle("value", fontName=r, fontSize=10, leading=13.5, textColor=INK)
    s["bio"] = ParagraphStyle("bio", parent=s["body"], fontName=r, spaceBefore=4)
    s["story"] = ParagraphStyle("story", fontName=i, fontSize=10, leading=14.5, textColor=INK, alignment=TA_JUSTIFY)
    s["story_meta"] = ParagraphStyle("story_meta", fontName=r, fontSize=8.5, leading=11, textColor=MUTED,
                                     alignment=TA_LEFT)
    s["reg"] = ParagraphStyle("reg", fontName=r, fontSize=9.8, leading=13.2, textColor=INK)
    s["toc1"] = ParagraphStyle("toc1", fontName=b, fontSize=11, leading=18, textColor=WINE, leftIndent=0, spaceBefore=6)
    s["toc2"] = ParagraphStyle("toc2", fontName=r, fontSize=9.8, leading=14, textColor=INK, leftIndent=16)
    s["family_title"] = ParagraphStyle("family_title", fontName=b, fontSize=15.5, leading=20, textColor=colors.white)
    s["family_sub"] = ParagraphStyle("family_sub", fontName=i, fontSize=9.5, leading=13, textColor=BAR_SUB)
    s["cell"] = ParagraphStyle("cell", fontName=r, fontSize=9.6, leading=12.5, textColor=INK)
    s["cell_head"] = ParagraphStyle("cell_head", fontName=b, fontSize=8.4, leading=11, textColor=GOLD)
    # the cover has its own colours (it may be dark)
    cv = {k: colors.HexColor(v) for k, v in THEME["cover"].items() if k != "kind"}
    s["c_kicker"] = ParagraphStyle("c_kicker", parent=s["kicker"], textColor=cv["accent"])
    s["c_title"] = ParagraphStyle("c_title", parent=s["cover_title"], textColor=cv["title"])
    s["c_sub"] = ParagraphStyle("c_sub", parent=s["cover_sub"], textColor=cv["text"])
    s["c_root"] = ParagraphStyle("c_root", parent=s["cover_sub"], fontName=b, fontSize=16, leading=21, textColor=cv["title"])
    s["c_meta"] = ParagraphStyle("c_meta", parent=s["cover_meta"], textColor=cv["muted"])
    s["c_foot"] = ParagraphStyle("c_foot", parent=s["body_left"], textColor=cv["text"])
    s["c_accent"] = cv["accent"]
    # «at a glance» numbers and the reading guide
    s["stat_num"] = ParagraphStyle("stat_num", fontName=b, fontSize=22, leading=26, textColor=WINE, alignment=TA_CENTER)
    s["stat_label"] = ParagraphStyle("stat_label", fontName=r, fontSize=8.6, leading=11, textColor=MUTED, alignment=TA_CENTER)
    s["guide"] = ParagraphStyle("guide", parent=s["body_left"], fontSize=10, leading=14.5, leftIndent=12, bulletIndent=0,
                                spaceAfter=4)
    return s


# --------------------------------------------------------- decorations --

class Ornament(Flowable):
    """A centred gold divider: two rules and a diamond, as between sections
    of an old book."""

    def __init__(self, width=5.5 * cm, space=8, color=None):
        super().__init__()
        self.w, self.space, self.color = width, space, color

    def wrap(self, avail_w, avail_h):
        self.avail = avail_w
        return avail_w, 10 + 2 * self.space

    def draw(self):
        c = self.canv
        cx, y = self.avail / 2, self.space + 5
        c.setStrokeColor(self.color or GOLD)
        c.setFillColor(self.color or GOLD)
        c.setLineWidth(0.7)
        c.line(cx - self.w / 2, y, cx - 7, y)
        c.line(cx + 7, y, cx + self.w / 2, y)
        p = c.beginPath()
        p.moveTo(cx, y + 4); p.lineTo(cx + 4, y); p.lineTo(cx, y - 4); p.lineTo(cx - 4, y); p.close()
        c.drawPath(p, stroke=0, fill=1)
        for dx in (-self.w / 2 - 3, self.w / 2 + 3):
            c.circle(cx + dx, y, 1.3, stroke=0, fill=1)


class Rule(Flowable):
    def __init__(self, color=None, width=0.6, space=6):
        super().__init__()
        self.color, self.lw, self.space = color, width, space

    def wrap(self, avail_w, avail_h):
        self.avail = avail_w
        return avail_w, 2 * self.space

    def draw(self):
        self.canv.setStrokeColor(self.color or RULE)
        self.canv.setLineWidth(self.lw)
        self.canv.line(0, self.space, self.avail, self.space)


class FamilyMark(Flowable):
    """Zero-size marker at the start of a family section: a contents line,
    a PDF bookmark and a link target for the children tables."""

    def __init__(self, title, key):
        super().__init__()
        self.title, self.key = title, key

    def wrap(self, *args):
        return 0, 0

    def draw(self):
        self.canv.bookmarkPage(self.key)


class ChapterMark(Flowable):
    """Zero-size marker: tells the page decorator which chapter it is in, and
    the contents page where that chapter starts."""

    def __init__(self, title, toc=True):
        super().__init__()
        self.title, self.toc = title, toc

    def wrap(self, *args):
        return 0, 0

    def draw(self):
        self.canv.bookmarkPage(self.key)

    @property
    def key(self):
        return "bob-" + re.sub(r"[^A-Za-z0-9]+", "-", self.title)[:40]


def qr_drawing(url, size=2.6 * cm):
    widget = QrCodeWidget(url)
    widget.barFillColor = INK
    x0, y0, x1, y1 = widget.getBounds()
    d = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    d.add(widget)
    return d


class BookTemplate(BaseDocTemplate):
    def __init__(self, buf, book, **kw):
        super().__init__(buf, pagesize=A4, leftMargin=2.3 * cm, rightMargin=2.3 * cm,
                         topMargin=2.5 * cm, bottomMargin=2.4 * cm, **kw)
        self.book = book
        self.chapter = ""
        body = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="body")
        cover = Frame(2.6 * cm, 3.0 * cm, PAGE_W - 5.2 * cm, PAGE_H - 6.0 * cm, id="cover")
        wide = Frame(2.0 * cm, 2.2 * cm, PAGE_H - 4.0 * cm, PAGE_W - 4.6 * cm, id="wide")
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[cover], onPage=self.draw_cover_page),
            PageTemplate(id="body", frames=[body], onPage=self.draw_body_page, onPageEnd=self.draw_running_head),
            # the whole tree on a landscape sheet
            PageTemplate(id="wide", frames=[wide], onPage=self.draw_body_page, onPageEnd=self.draw_running_head,
                         pagesize=landscape(A4)),
        ])

    def beforeDocument(self):
        self.chapter = ""

    def afterFlowable(self, flowable):
        if isinstance(flowable, ChapterMark):
            self.chapter = flowable.title
            if flowable.toc:
                self.notify("TOCEntry", (0, clean(flowable.title), self.page, flowable.key))
                self.canv.addOutlineEntry(plain(flowable.title), flowable.key, level=0, closed=True)
        elif isinstance(flowable, FamilyMark):
            self.notify("TOCEntry", (1, clean(flowable.title), self.page, flowable.key))
            self.canv.addOutlineEntry(plain(flowable.title), flowable.key, level=1)

    # page furniture
    def _paper(self, c, inset):
        W, H = c._pagesize
        kind = THEME["frame"]
        c.saveState()
        c.setFillColor(PAPER)
        c.rect(0, 0, W, H, stroke=0, fill=1)
        if kind in ("double", "tiles"):
            c.setStrokeColor(WINE if kind == "tiles" else GOLD)
            c.setLineWidth(1.2)
            c.rect(inset, inset, W - 2 * inset, H - 2 * inset, stroke=1, fill=0)
            c.setStrokeColor(GOLD)
            c.setLineWidth(0.4)
            c.rect(inset + 4, inset + 4, W - 2 * inset - 8, H - 2 * inset - 8, stroke=1, fill=0)
            if kind == "tiles":
                for x, y in ((inset, inset), (W - inset, inset), (inset, H - inset), (W - inset, H - inset)):
                    star8(c, x, y, 7, fill=GOLD, stroke=WINE)
        elif kind == "thin":
            c.setStrokeColor(INK)
            c.setLineWidth(0.6)
            c.rect(inset, inset, W - 2 * inset, H - 2 * inset, stroke=1, fill=0)
        else:   # modern: a band of colour along the top edge only
            c.setFillColor(GOLD)
            c.rect(0, H - 0.35 * cm, W, 0.35 * cm, stroke=0, fill=1)
        c.restoreState()

    def draw_cover_page(self, c, doc):
        draw_cover(c)

    def draw_body_page(self, c, doc):
        self._paper(c, 1.25 * cm)

    def draw_running_head(self, c, doc):
        """Drawn once the page is full, so it names the chapter the page is in."""
        W, H = c._pagesize
        r, b, i, bi = book_fonts()["names"]
        m = 2.3 * cm if W < H else 2.0 * cm
        c.saveState()
        c.setFillColor(MUTED)
        c.setFont(i, 8.5)
        c.drawString(m, H - 1.85 * cm, self.book["title_plain"][:70])
        if self.chapter:
            c.setFont(r, 8)
            c.drawRightString(W - m, H - 1.85 * cm, plain(self.chapter)[:60])
        c.setStrokeColor(GOLD_SOFT)
        c.setLineWidth(0.5)
        c.line(m, H - 2.0 * cm, W - m, H - 2.0 * cm)
        c.setFillColor(GOLD)
        c.setFont(b, 9.5)
        label = str(doc.page)
        c.drawCentredString(W / 2, 1.75 * cm, label)
        w = pdfmetrics.stringWidth(label, b, 9.5)
        c.setStrokeColor(GOLD)
        c.line(W / 2 - w / 2 - 22, 1.84 * cm, W / 2 - w / 2 - 6, 1.84 * cm)
        c.line(W / 2 + w / 2 + 6, 1.84 * cm, W / 2 + w / 2 + 22, 1.84 * cm)
        c.setFillColor(MUTED)
        c.setFont(r, 7)
        c.drawString(m, 1.75 * cm, f"Tekshirish kodi: {self.book['code']}")
        c.restoreState()


def star8(c, x, y, r, fill=None, stroke=None, width=0.6):
    """Eight-pointed star (two overlapping squares) — the khatam of Samarkand tiles."""
    inner = r * math.cos(math.pi / 4) / math.cos(math.pi / 8)
    p = c.beginPath()
    for k in range(16):
        a = k * math.pi / 8 - math.pi / 2
        rr = inner if k % 2 else r
        (p.moveTo if k == 0 else p.lineTo)(x + rr * math.cos(a), y + rr * math.sin(a))
    p.close()
    c.saveState()
    if fill is not None:
        c.setFillColor(fill)
    if stroke is not None:
        c.setStrokeColor(stroke)
        c.setLineWidth(width)
    c.drawPath(p, stroke=1 if stroke is not None else 0, fill=1 if fill is not None else 0)
    c.restoreState()


def _diamond(c, x, y, d, color):
    c.setFillColor(color)
    p = c.beginPath()
    p.moveTo(x, y + d); p.lineTo(x + d, y); p.lineTo(x, y - d); p.lineTo(x - d, y); p.close()
    c.drawPath(p, stroke=0, fill=1)


def draw_cover(c):
    """The cover sheet behind the title text, one look per style."""
    W, H = PAGE_W, PAGE_H
    cv = {k: (colors.HexColor(v) if k != "kind" else v) for k, v in THEME["cover"].items()}
    kind, acc = cv["kind"], cv["accent"]
    c.saveState()
    c.setFillColor(cv["bg"])
    c.rect(0, 0, W, H, stroke=0, fill=1)
    corners = ((1.2 * cm, 1.2 * cm), (W - 1.2 * cm, 1.2 * cm), (1.2 * cm, H - 1.2 * cm), (W - 1.2 * cm, H - 1.2 * cm))

    if kind == "emerald":
        c.radialGradient(W / 2, H * 0.62, H * 0.75, [colors.HexColor("#1d5640"), colors.HexColor("#0b2219")], extend=True)
        c.setStrokeColor(acc)
        c.setLineWidth(1.6)
        c.rect(1.2 * cm, 1.2 * cm, W - 2.4 * cm, H - 2.4 * cm, stroke=1, fill=0)
        c.setLineWidth(0.5)
        c.rect(1.55 * cm, 1.55 * cm, W - 3.1 * cm, H - 3.1 * cm, stroke=1, fill=0)
        c.setDash(0.1, 5)
        c.setLineCap(1)
        c.setLineWidth(1.1)
        c.rect(1.9 * cm, 1.9 * cm, W - 3.8 * cm, H - 3.8 * cm, stroke=1, fill=0)
        c.setDash()
        for x, y in corners:
            c.setFillColor(colors.HexColor("#0d271c"))
            c.circle(x, y, 13, stroke=1, fill=1)
            star8(c, x, y, 8, fill=acc)
    elif kind == "samarkand":
        lapis, turq, band = colors.HexColor("#1f3c88"), colors.HexColor("#3aa7a3"), 1.7 * cm
        for y0 in (H - 1.2 * cm - band, 1.2 * cm):
            c.setFillColor(lapis)
            c.rect(1.2 * cm, y0, W - 2.4 * cm, band, stroke=0, fill=1)
            n = max(1, round((W - 2.4 * cm) / band))
            tw = (W - 2.4 * cm) / n
            for k in range(n):
                cx, cy = 1.2 * cm + tw * (k + 0.5), y0 + band / 2
                star8(c, cx, cy, band * 0.36, fill=turq, stroke=acc, width=0.9)
                star8(c, cx, cy, band * 0.17, fill=cv["bg"])
                c.setFillColor(acc)
                c.circle(1.2 * cm + tw * k, cy, 2.2, stroke=0, fill=1)
            c.setStrokeColor(acc)
            c.setLineWidth(1.4)
            c.rect(1.2 * cm, y0, W - 2.4 * cm, band, stroke=1, fill=0)
        c.setStrokeColor(lapis)
        c.setLineWidth(0.8)
        c.rect(1.2 * cm, 1.2 * cm, W - 2.4 * cm, H - 2.4 * cm, stroke=1, fill=0)
        c.setStrokeColor(turq)
        c.setLineWidth(0.5)
        c.rect(1.5 * cm, 1.2 * cm + band + 0.3 * cm, W - 3.0 * cm, H - 2.4 * cm - 2 * band - 0.6 * cm, stroke=1, fill=0)
    elif kind == "modern":
        c.setFillColor(acc)
        c.rect(0, 0, 1.5 * cm, H, stroke=0, fill=1)
        c.setFillColor(colors.HexColor("#c99a2e"))
        c.rect(1.5 * cm, 0, 0.12 * cm, H, stroke=0, fill=1)
        c.setStrokeColor(colors.HexColor("#d7e9de"))
        c.setLineWidth(1)
        c.roundRect(2.3 * cm, 1.4 * cm, W - 3.7 * cm, H - 2.8 * cm, 14, stroke=1, fill=0)
    elif kind == "ink":
        c.setStrokeColor(acc)
        c.setLineWidth(1.4)
        c.rect(1.2 * cm, 1.2 * cm, W - 2.4 * cm, H - 2.4 * cm, stroke=1, fill=0)
        c.setLineWidth(0.4)
        c.rect(1.45 * cm, 1.45 * cm, W - 2.9 * cm, H - 2.9 * cm, stroke=1, fill=0)
    else:   # classic
        c.setStrokeColor(acc)
        c.setLineWidth(1.2)
        c.rect(1.2 * cm, 1.2 * cm, W - 2.4 * cm, H - 2.4 * cm, stroke=1, fill=0)
        c.setLineWidth(0.4)
        c.rect(1.2 * cm + 4, 1.2 * cm + 4, W - 2.4 * cm - 8, H - 2.4 * cm - 8, stroke=1, fill=0)
        for x, y in corners:
            _diamond(c, x, y, 7, acc)
        # corner brackets
        c.setLineWidth(0.8)
        a, l = 1.9 * cm, 1.6 * cm
        for x, y, sx, sy in ((a, a, 1, 1), (W - a, a, -1, 1), (a, H - a, 1, -1), (W - a, H - a, -1, -1)):
            c.line(x, y + sy * l, x, y)
            c.line(x, y, x + sx * l, y)
    c.restoreState()


class FamilyDiagram(Flowable):
    """A family at a glance: the parents side by side joined by a marriage
    line, their children in a row (or rows) below, each box with the
    person's number and years."""

    BOX_W, BOX_H, GAP_X, ROW_GAP = 3.3 * cm, 1.2 * cm, 0.35 * cm, 0.9 * cm

    def __init__(self, lineage, parents, children, main):
        super().__init__()
        self.lin, self.parents, self.children, self.main = lineage, parents, children, main

    def _layout(self, avail):
        per_row = max(1, int((avail + self.GAP_X) // (self.BOX_W + self.GAP_X)))
        rows = [self.children[i:i + per_row] for i in range(0, len(self.children), per_row)] if self.children else []
        return per_row, rows

    def wrap(self, avail_w, avail_h):
        self.avail = avail_w
        _, rows = self._layout(avail_w)
        h = self.BOX_H + 0.3 * cm
        if rows:
            h += len(rows) * (self.BOX_H + self.ROW_GAP)
        self.width, self.height = avail_w, h
        return avail_w, h

    def _box(self, c, x, y, pid, kind):
        r, b, i, bi = book_fonts()["names"]
        p = self.lin.people[pid]
        fill = {"main": MAIN_FILL, "spouse": colors.white, "child": colors.white}[kind]
        stroke = FEMALE if p.gender == "ayol" else GOLD
        c.setFillColor(fill)
        c.setStrokeColor(stroke)
        c.setLineWidth(1.3 if kind == "main" else 0.8)
        c.roundRect(x, y, self.BOX_W, self.BOX_H, 5, stroke=1, fill=1)
        name = plain(p.full_name)
        size = 9.2
        while pdfmetrics.stringWidth(name, b, size) > self.BOX_W - 10 and size > 6.8:
            size -= 0.3
        while pdfmetrics.stringWidth(name, b, size) > self.BOX_W - 10 and len(name) > 4:
            name = name[:-2].rstrip() + "…"
        c.setFillColor(INK)
        c.setFont(b, size)
        c.drawCentredString(x + self.BOX_W / 2, y + self.BOX_H - 15, name)
        meta = " · ".join(t for t in (
            ("№ " + self.lin.number[pid]) if pid in self.lin.number else "",
            plain(life_span(p)),
        ) if t)
        if meta:
            c.setFillColor(MUTED)
            c.setFont(r, 7.2)
            c.drawCentredString(x + self.BOX_W / 2, y + 8, plain(clean_plain_number(meta)))

    def draw(self):
        c = self.canv
        per_row, rows = self._layout(self.avail)
        top_y = self.height - self.BOX_H
        n = len(self.parents)
        total = n * self.BOX_W + (n - 1) * self.GAP_X * 2
        x0 = (self.avail - total) / 2
        centers = []
        c.setStrokeColor(GOLD)
        c.setLineWidth(1)
        for k, pid in enumerate(self.parents):
            x = x0 + k * (self.BOX_W + self.GAP_X * 2)
            centers.append(x + self.BOX_W / 2)
            if k:
                c.line(x - self.GAP_X * 2, top_y + self.BOX_H / 2, x, top_y + self.BOX_H / 2)
        for k, pid in enumerate(self.parents):
            x = x0 + k * (self.BOX_W + self.GAP_X * 2)
            self._box(c, x, top_y, pid, "main" if pid == self.main else "spouse")
        if not rows:
            return
        trunk_x = self.avail / 2
        start_y = top_y if n == 1 else top_y + self.BOX_H / 2
        if n > 1:   # the marriage mark between the first two
            c.setFillColor(PAPER)
            mx = x0 + self.BOX_W + self.GAP_X
            c.circle(mx, top_y + self.BOX_H / 2, 4.5, stroke=1, fill=1)
            trunk_x = mx
        y = top_y
        c.setStrokeColor(GOLD)
        for row in rows:
            row_y = y - self.ROW_GAP - self.BOX_H
            bus_y = row_y + self.BOX_H + self.ROW_GAP / 2
            w = len(row) * self.BOX_W + (len(row) - 1) * self.GAP_X
            rx = (self.avail - w) / 2
            mids = [rx + j * (self.BOX_W + self.GAP_X) + self.BOX_W / 2 for j in range(len(row))]
            c.line(trunk_x, start_y if y == top_y else y + self.BOX_H / 2, trunk_x, bus_y)
            c.line(min(mids + [trunk_x]), bus_y, max(mids + [trunk_x]), bus_y)
            for j, pid in enumerate(row):
                c.line(mids[j], bus_y, mids[j], row_y + self.BOX_H)
                self._box(c, mids[j] - self.BOX_W / 2, row_y, pid, "child")
            start_y = bus_y
            y = row_y


class TreeOverview(Flowable):
    """The whole family on one landscape sheet: every line of descent from
    the founder down, each person with their spouse beside them, the
    generations in rows. Scaled to fit; build_book splits a very wide tree
    into one sheet per branch."""

    BW, BH, SP, GAP, ROW = 68.0, 42.0, 6.0, 10.0, 30.0

    def __init__(self, lineage, roots, avail_h=None):
        super().__init__()
        self.lin, self.roots = lineage, roots
        self.avail_h = avail_h
        self._measure()

    # -- structure ------------------------------------------------------
    def kids(self, pid):
        num = self.lin.number.get(pid)
        if not num:
            return []
        return [k for k in self.lin.children.get(pid, []) if self.lin.number.get(k, "").rpartition(".")[0] == num]

    def unit(self, pid):
        """The person and the spouses who married into the line."""
        return [pid] + [s for s in self.lin.spouses[pid] if self.lin.married_to.get(s) == pid or s not in self.lin.number]

    def unit_w(self, pid):
        n = len(self.unit(pid))
        return n * self.BW + (n - 1) * self.SP

    def _measure(self):
        self.sw = {}

        def width(pid):
            kids = self.kids(pid)
            inner = sum(width(k) for k in kids) + self.GAP * max(0, len(kids) - 1)
            self.sw[pid] = max(self.unit_w(pid), inner)
            return self.sw[pid]

        self.total_w = sum(width(r) for r in self.roots) + self.GAP * 2 * max(0, len(self.roots) - 1)
        lv = self.lin.levels
        seen = [lv[p] for p in self.sw]
        self.top, self.rows = min(seen), max(seen) - min(seen) + 1
        self.total_h = self.rows * self.BH + (self.rows - 1) * self.ROW

    def scale_for(self, avail_w, avail_h):
        return min(1.0, avail_w / max(1.0, self.total_w), avail_h / max(1.0, self.total_h))

    # -- flowable -------------------------------------------------------
    def wrap(self, avail_w, avail_h):
        h = min(self.avail_h or avail_h, avail_h)
        # a small family may grow a little to fill the sheet
        self.s = min(1.5, avail_w / max(1.0, self.total_w), (h - 4) / max(1.0, self.total_h))
        self.width, self.height = avail_w, h
        return self.width, self.height

    def draw(self):
        c = self.canv
        s = self.s
        c.saveState()
        # centred on the sheet, a little above the middle
        c.translate((self.width - self.total_w * s) / 2, max(2, (self.height - self.total_h * s) * 0.55))
        c.scale(s, s)
        self.pos = {}

        def place(pid, left):
            kids = self.kids(pid)
            inner = sum(self.sw[k] for k in kids) + self.GAP * max(0, len(kids) - 1)
            x = left + (self.sw[pid] - inner) / 2
            for k in kids:
                place(k, x)
                x += self.sw[k] + self.GAP
            self.pos[pid] = left + self.sw[pid] / 2 - self.unit_w(pid) / 2

        x = 0.0
        for r in self.roots:
            place(r, x)
            x += self.sw[r] + self.GAP * 2

        def y_of(pid):
            row = self.lin.levels[pid] - self.top
            return self.total_h - self.BH - row * (self.BH + self.ROW)

        # lines first, boxes on top
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.1)
        for pid, ux in self.pos.items():
            kids = self.kids(pid)
            members = self.unit(pid)
            y = y_of(pid)
            if len(members) > 1:
                c.line(ux + self.BW, y + self.BH / 2, ux + self.BW + self.SP, y + self.BH / 2)
            if not kids:
                continue
            sx = ux + (self.BW + self.SP / 2 if len(members) > 1 else self.BW / 2)
            sy = y + (self.BH / 2 if len(members) > 1 else 0)
            mids = [self.pos[k] + self.BW / 2 for k in kids]
            bus = y - self.ROW / 2
            child_top = y_of(kids[0]) + self.BH
            bus = min(bus, child_top + self.ROW / 2)
            c.line(sx, sy, sx, bus)
            c.line(min(mids + [sx]), bus, max(mids + [sx]), bus)
            for k, mx in zip(kids, mids):
                c.line(mx, bus, mx, y_of(k) + self.BH)
        for pid, ux in self.pos.items():
            y = y_of(pid)
            for j, m in enumerate(self.unit(pid)):
                self._box(c, ux + j * (self.BW + self.SP), y, m, main=(j == 0))
            if len(self.unit(pid)) > 1:
                c.setFillColor(PAPER)
                c.setStrokeColor(GOLD)
                c.circle(ux + self.BW + self.SP / 2, y + self.BH / 2, 3.2, stroke=1, fill=1)
        c.restoreState()

    def _box(self, c, x, y, pid, main):
        r, b, i, bi = book_fonts()["names"]
        p = self.lin.people[pid]
        is_root = self.lin.root.id == pid
        c.setFillColor(BAR if is_root else (MAIN_FILL if main else colors.white))
        c.setStrokeColor(FEMALE if p.gender == "ayol" else GOLD)
        c.setLineWidth(1.4 if is_root else 0.9)
        c.roundRect(x, y, self.BW, self.BH, 6, stroke=1, fill=1)

        def fit(text, font, size, low):
            text = plain(text)
            while pdfmetrics.stringWidth(text, font, size) > self.BW - 6 and size > low:
                size -= 0.25
            while pdfmetrics.stringWidth(text, font, size) > self.BW - 6 and len(text) > 3:
                text = text[:-2].rstrip() + "…"
            return text, size

        # first name large, surname under it — narrow boxes keep a wide family readable
        first, fs = fit(p.first_name, b, 9.4, 6.6)
        c.setFillColor(colors.white if is_root else INK)
        c.setFont(b, fs)
        c.drawCentredString(x + self.BW / 2, y + self.BH - 13, first)
        if p.last_name:
            last, ls = fit(p.last_name, r, 7.2, 5.8)
            c.setFont(r, ls)
            c.drawCentredString(x + self.BW / 2, y + self.BH - 23, last)
        meta = " · ".join(t for t in (self.lin.number.get(pid, ""), plain(life_span(p))) if t)
        if meta:
            meta, ms = fit(meta, r, 6.2, 5.0)
            c.setFillColor(BAR_SUB if is_root else MUTED)
            c.setFont(r, ms)
            c.drawCentredString(x + self.BW / 2, y + 6, meta)


def overview_sheets(lineage, avail_w, avail_h):
    """One sheet for the whole tree if it stays readable; otherwise one per
    branch of the founder's children (and their own children if still too wide)."""
    tops = [pid for pid, _, depth in lineage.register if depth == 0]
    whole = TreeOverview(lineage, tops)
    if whole.scale_for(avail_w, avail_h) >= 0.55 or not tops:
        return [(None, whole)]
    sheets = []

    def split(pid, path):
        view = TreeOverview(lineage, [pid])
        kids = view.kids(pid)
        if view.scale_for(avail_w, avail_h) >= 0.55 or not kids:
            sheets.append((path, view))
            return
        for k in kids:
            split(k, path + [k])

    for t in tops:
        split(t, [t])
    return sheets


def clean_plain_number(text):
    glyphs = book_fonts()["glyphs"]
    return text if not glyphs or ord("№") in glyphs else text.replace("№", "No.")


def family_key(num):
    return "oila-" + num.replace(".", "-")


# ------------------------------------------------------------- the data --

def _year(value):
    m = re.search(r"\d{3,4}", value or "")
    return int(m.group()) if m else None


def year_text(value):
    """'~1956' -> 'taxm. 1956'."""
    value = (value or "").strip()
    if not value:
        return ""
    return f"taxm. {value[1:]}" if value.startswith("~") else value


def life_span(p):
    born, died = year_text(p.display_year), year_text(p.death_year)
    if born and died:
        return f"{born} – {died}"
    if born:
        return f"t. {born}"
    if died:
        return f"v. {died}"
    return ""


def long_date(d):
    return f"{d.year}-yil {d.day}-{MONTHS[d.month - 1]}"


ORDINALS = ["Birinchi", "Ikkinchi", "Uchinchi", "To‘rtinchi", "Beshinchi", "Oltinchi", "Yettinchi",
            "Sakkizinchi", "To‘qqizinchi", "O‘ninchi"]


def ordinal_generation(n):
    return f"{ORDINALS[n - 1]} avlod" if n <= len(ORDINALS) else f"{n}-avlod"


def roman(n):
    out = ""
    for value, sym in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= value:
            out += sym
            n -= value
    return out


class Lineage:
    """The tree's people and links, gathered once for the whole book."""

    def __init__(self, root):
        self.levels, self.people, families = compute_levels(root)
        self.root = root
        self.father, self.mother = {}, {}
        self.children = defaultdict(list)
        self.spouses = defaultdict(list)
        for fam in families.values():
            kids = [c.id for c in fam.children.all() if c.id in self.people]
            for k in kids:
                if fam.father_id in self.people:
                    self.father[k] = fam.father_id
                if fam.mother_id in self.people:
                    self.mother[k] = fam.mother_id
            for parent in (fam.father_id, fam.mother_id):
                if parent in self.people:
                    for k in kids:
                        if k not in self.children[parent]:
                            self.children[parent].append(k)
            if fam.father_id in self.people and fam.mother_id in self.people:
                if fam.mother_id not in self.spouses[fam.father_id]:
                    self.spouses[fam.father_id].append(fam.mother_id)
                if fam.father_id not in self.spouses[fam.mother_id]:
                    self.spouses[fam.mother_id].append(fam.father_id)
        for pid in self.children:
            self.children[pid].sort(key=lambda k: (_year(self.people[k].display_year) or 9999, k))
        self.number = {}
        self.married_to = {}
        self.register = []     # (pid, number, depth) in reading order
        self._number()

    def has_parents(self, pid):
        return pid in self.father or pid in self.mother

    def _number(self):
        people = self.people
        married_in = {
            pid for pid in people
            if not self.has_parents(pid) and any(self.has_parents(s) for s in self.spouses[pid])
        }
        tops = [pid for pid in people if not self.has_parents(pid) and pid not in married_in]
        tops.sort(key=lambda pid: (self.levels[pid], people[pid].gender != "erkak", pid))

        def walk(pid, num, depth):
            self.number[pid] = num
            self.register.append((pid, num, depth))
            i = 0
            for kid in self.children[pid]:
                if kid in self.number:
                    continue
                i += 1
                walk(kid, f"{num}.{i}", depth + 1)

        n = 0
        for pid in tops:
            if pid in self.number or any(s in self.number and s in tops for s in self.spouses[pid]):
                continue
            n += 1
            walk(pid, str(n), 0)
        for pid in sorted(people, key=lambda p: (self.levels[p], p)):   # anything unreachable
            if pid not in self.number and pid not in married_in and not any(s in self.number for s in self.spouses[pid]):
                n += 1
                walk(pid, str(n), 0)
        for pid in people:
            if pid not in self.number:
                partner = next((s for s in self.spouses[pid] if s in self.number), None)
                if partner:
                    self.married_to[pid] = partner

    def ref(self, pid):
        """'Shohruh (No. 1.2)' — how a relative is named inside an entry."""
        p = self.people[pid]
        num = self.number.get(pid)
        if num:
            return f"{clean(p.full_name)} <font color='{A_HEX}'>({clean('№')} {num})</font>"
        return clean(p.full_name)

    def label_for(self, pid):
        if pid in self.number:
            return f"{clean('№')} {self.number[pid]}"
        partner = self.married_to.get(pid)
        if partner:
            return f"{clean('№')} {self.number[partner]} ning turmush o‘rtog‘i"
        return ""


# ---------------------------------------------------------- the builder --

def place_text(p):
    region = dict(REGION_CHOICES).get(p.birth_region, p.birth_region) if p.birth_region else ""
    return ", ".join(x for x in (p.birth_village, p.birth_district, region) if x)


def build_book(tree, *, code, verify_url, tree_url, contributors, sources=(), style="classic"):
    """Return the PDF bytes for `tree`, in one of BOOK_THEMES."""
    with _BUILD_LOCK:
        use_theme(style)
        try:
            return _build_book(tree, code=code, verify_url=verify_url, tree_url=tree_url,
                               contributors=contributors, sources=sources)
        finally:
            use_theme("classic")


def _build_book(tree, *, code, verify_url, tree_url, contributors, sources):
    fam = Lineage(tree.root_person)
    st = make_styles()
    people = fam.people
    levels = fam.levels
    today = datetime.date.today()
    gens = sorted(set(levels.values()))
    years = [y for y in (_year(p.display_year) for p in people.values()) if y]
    places = {p.birth_region or p.birth_district for p in people.values() if p.birth_region or p.birth_district}
    men = sum(1 for p in people.values() if p.gender == "erkak")
    learning = tree.kind == "talimiy"
    book = {"title_plain": plain(tree.name), "code": code}

    story = []
    P = Paragraph

    # ------------------------------------------------------------- cover --
    root = tree.root_person
    founder_id = next((pid for pid, _, depth in fam.register if depth == 0), root.id)
    # the cover names where the line starts (the tree's root may be a grandchild)
    founder = root if learning else people.get(founder_id, root)
    ca = st["c_accent"]
    story += [
        Spacer(1, 3.6 * cm),
        P("TA‘LIMIY SHAJARA" if learning else "OILAVIY SHAJARA", st["c_kicker"]),
        Ornament(7 * cm, color=ca),
        Spacer(1, 0.5 * cm),
        P(clean(tree.name), st["c_title"]),
        Spacer(1, 0.35 * cm),
    ]
    if learning and (tree.subject or tree.era):
        story.append(P(clean(" · ".join(x for x in (tree.subject, tree.era) if x)), st["c_sub"]))
    elif tree.description:
        story.append(P(clean(tree.description[:180]), st["c_sub"]))
    story += [
        Spacer(1, 0.9 * cm),
        Ornament(4 * cm, color=ca),
        Spacer(1, 0.6 * cm),
        P("Nasl boshi" if not learning else "Bosh shaxs", st["c_kicker"]),
        P(clean(founder.full_name), st["c_root"]),
    ]
    if life_span(founder):
        story.append(P(clean(life_span(founder)), st["c_meta"]))
    story += [
        Spacer(1, 1.0 * cm),
        P(f"{len(people)} shaxs &nbsp;·&nbsp; {len(gens)} avlod"
          + (f" &nbsp;·&nbsp; {min(years)}–{max(years)} yillar" if years else ""), st["c_meta"]),
        Spacer(1, 3.4 * cm),
    ]
    compiler = tree.owner.get_full_name() or tree.owner.username
    cover_foot = Table(
        [[qr_drawing(verify_url, 2.2 * cm),
          P(f"<b>Tuzuvchi:</b> {clean(compiler)}<br/>"
            f"<b>Tuzilgan sana:</b> {long_date(today)}<br/>"
            f"<b>Tekshirish kodi:</b> {code}<br/>"
            f"<font size='8'>QR-kodni skanerlab, hujjat haqiqiyligini tekshiring</font>",
            st["c_foot"])]],
        colWidths=[2.7 * cm, 9 * cm],
    )
    cover_foot.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # a white plate keeps the QR readable on a dark cover
        ("BACKGROUND", (0, 0), (0, 0), colors.white), ("BOX", (0, 0), (0, 0), 0.6, ca),
        ("LEFTPADDING", (0, 0), (0, 0), 3), ("RIGHTPADDING", (0, 0), (0, 0), 3),
        ("TOPPADDING", (0, 0), (0, 0), 3), ("BOTTOMPADDING", (0, 0), (0, 0), 3),
        ("LEFTPADDING", (1, 0), (1, 0), 12),
    ]))
    story += [cover_foot, NextPageTemplate("body"), PageBreak()]

    # ---------------------------------------------------------- foreword --
    story += [ChapterMark("So‘z boshi"), P("So‘z boshi", st["h1"]), Ornament(), Spacer(1, 6)]
    intro = (
        f"Ushbu kitob «{clean(tree.name)}» shajarasi asosida tuzildi. Unda "
        f"<b>{len(people)}</b> nafar shaxs — {men} erkak va {len(people) - men} ayol — "
        f"<b>{len(gens)}</b> avlod bo‘yicha jamlangan."
    )
    if years:
        intro += f" Kiritilgan eng qadimgi yil — {min(years)}, eng so‘nggisi — {max(years)}."
    if places:
        intro += f" Shaxslar {len(places)} ta turli joyda tug‘ilgan."
    families_total = sum(1 for pid in people if fam.children.get(pid) and pid in fam.number)
    tiles = [(len(people), "shaxs"), (len(gens), "avlod"), (families_total, "oila"),
             (min(years) if years else "—", "eng qadimgi yil")]
    stats = Table([[P(str(n), st["stat_num"]) for n, _ in tiles], [P(t, st["stat_label"]) for _, t in tiles]],
                  colWidths=[None] * 4)
    stats.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MAIN_FILL),
        ("LINEAFTER", (0, 0), (-2, -1), 2, PAPER),
        ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
    ]))
    story += [Spacer(1, 4), stats, Spacer(1, 12), P(intro, st["body"])]
    if tree.description:
        story += [Spacer(1, 6), P(clean(tree.description), st["body"])]

    def guide_line(text):
        return P(text, st["guide"], bulletText="•")

    guide = [
        P("Kitobdan qanday foydalanish kerak", st["h2"]),
        guide_line("<b>Shajara chizmasi</b> — keyingi sahifalarda butun oila bir qarashda: har bir avlod alohida "
                   "qatorda, turmush o‘rtoqlar yonma-yon, farzandlar pastda."),
        guide_line("<b>Boblar</b> — har bir bob bitta avlod. Har bir oila uchun kichik chizma, ota-onaning "
                   "ma’lumoti va farzandlar jadvali bor."),
        guide_line(f"<b>Raqamlar</b> — har bir kishining o‘z raqami bor: <b>1</b> — nasl boshi, <b>1.2</b> — uning "
                   f"ikkinchi farzandi, <b>1.2.1</b> — o‘sha farzandning birinchi farzandi. Nuqta qancha ko‘p bo‘lsa, "
                   f"avlod shuncha keyin. Turmush o‘rtoqlar juftining raqami bilan ko‘rsatiladi."),
        guide_line("<b>Kimnidir topish</b> — «Nasl ro‘yxati»dan ismni toping, raqami bo‘yicha boblardan uning oilasiga "
                   "o‘ting. Elektron nusxada raqamlar bosiladigan havola."),
        guide_line("<b>Qisqartmalar:</b> t. — tug‘ilgan; v. — vafot etgan; taxm. — taxminiy yil."),
    ]
    box = Table([[guide]], colWidths=[None])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ROW_ALT), ("BOX", (0, 0), (-1, -1), 0.6, GOLD_SOFT),
        ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story += [Spacer(1, 12), box, PageBreak()]

    # ----------------------------------------------------------- contents --
    toc = TableOfContents(dotsMinLevel=0)
    toc.levelStyles = [st["toc1"], st["toc2"]]
    story += [ChapterMark("Mundarija", toc=False), P("Mundarija", st["h1"]), Ornament(), Spacer(1, 8), toc]

    # ----------------------------------------------------------- overview --
    wide_w, wide_h = PAGE_H - 4.0 * cm, PAGE_W - 4.6 * cm
    sheets = overview_sheets(fam, wide_w, wide_h - 2.2 * cm)
    story += [NextPageTemplate("wide"), PageBreak()]
    for n, (path, view) in enumerate(sheets):
        if n:
            story.append(PageBreak())
        if path is None:
            caption = f"Butun oila bir qarashda · {len(people)} kishi, {len(gens)} avlod"
        else:
            caption = f" {clean('→')} ".join(clean(people[p].first_name) for p in path) + " shoxi"
        story += ([ChapterMark("Shajara chizmasi")] if n == 0 else []) + [
            P("Shajara chizmasi", ParagraphStyle("ov_h", parent=st["h1"], fontSize=17, leading=21, spaceAfter=0)),
            P(caption, st["chapter_intro"]), Spacer(1, 6),
            TreeOverview(fam, view.roots, avail_h=wide_h - 2.2 * cm),
        ]
    story += [NextPageTemplate("body"), PageBreak()]

    # ----------------------------------------------------------- register --
    story += [ChapterMark("Nasl ro‘yxati"), P("Nasl ro‘yxati", st["h1"]), Ornament(),
              P("Shajaradagi barcha nasl chiziqlari — har bir qator bir shaxs, chekinish avlodni bildiradi.",
                st["chapter_intro"]), Spacer(1, 10)]
    for pid, num, depth in fam.register:
        p = people[pid]
        line = f"<font color='{A_HEX}'><b>{num}</b></font>&nbsp;&nbsp;<b>{clean(p.full_name)}</b>"
        if life_span(p):
            line += f" <font color='{M_HEX}'><i>({clean(life_span(p))})</i></font>"
        partners = [s for s in fam.spouses[pid] if fam.married_to.get(s) == pid or s not in fam.number]
        if partners:
            line += f" &nbsp;<font color='{M_HEX}'>∞ " + ", ".join(clean(people[s].full_name) for s in partners) + "</font>"
        story.append(P(clean_inf(line), ParagraphStyle(f"reg{min(depth, 9)}", parent=st["reg"],
                                                         leftIndent=min(depth, 9) * 0.55 * cm)))

    # ------------------------------------------------------------ chapters --
    for chapter_no, lvl in enumerate(gens, start=1):
        heads = [pid for pid, _, _ in fam.register if levels[pid] == lvl]
        # anyone at this level the register didn't reach and who didn't marry in
        heads += [pid for pid in people if levels[pid] == lvl and pid not in fam.number and pid not in fam.married_to]
        families_here = sum(1 for pid in heads if fam.spouses[pid] or fam.children.get(pid))
        relative = level_label(lvl, root.full_name)
        title = f"{roman(chapter_no)}. {ordinal_generation(chapter_no)}"
        people_here = sum(1 for pid in people if levels[pid] == lvl)
        story += [
            PageBreak() if chapter_no == 1 else CondPageBreak(16 * cm),
            ChapterMark(f"{title} — {relative}"),
            Spacer(1, 0.6 * cm),
            P(roman(chapter_no), st["chapter_no"]),
            P("BOB", st["kicker"]),
            P(clean(ordinal_generation(chapter_no)), st["h1"]),
            Ornament(6 * cm),
            P((f"{clean(root.full_name)}ga nisbatan: {clean(relative)} · " if lvl != 0 else
               (f"{clean(root.full_name)} avlodi · " if not learning else ""))
              + f"{people_here} kishi" + (f", {families_here} ta oila" if families_here else ""), st["chapter_intro"]),
            Spacer(1, 14),
        ]
        # A person with neither spouse nor children is already a row in their
        # parents' table; only those with more to tell get a short entry,
        # gathered at the end of the chapter instead of a family section each.
        singles = [pid for pid in heads if not fam.spouses[pid] and not fam.children.get(pid)]
        for pid in heads:
            if pid not in singles:
                story += family_section(fam, pid, st, tree)
        described = [pid for pid in singles if has_story(people[pid]) or not (fam.father.get(pid) or fam.mother.get(pid))]
        if described:
            story += [CondPageBreak(6 * cm), Paragraph("Oilasi kiritilmagan shaxslar", st["h2"]),
                      Paragraph("Bu avlodning turmush o‘rtog‘i va farzandlari hali kiritilmagan vakillari.", st["small"]),
                      Spacer(1, 6)]
            for idx, pid in enumerate(described):
                story += [Paragraph(f'<a name="shaxs-{pid}"/>', st["small"])] + person_entry(fam, pid, st, tree)
                if idx < len(described) - 1:
                    story.append(Rule(space=5))

    # ------------------------------------------------------------- sources --
    if learning:
        story += [PageBreak(), ChapterMark("Manbalar"), P("Manbalar", st["h1"]), Ornament(), Spacer(1, 8)]
        if sources:
            for n, src in enumerate(sources, start=1):
                story.append(P(f"<font color='{A_HEX}'><b>{n}.</b></font> {clean(src)}", st["body_left"]))
                story.append(Spacer(1, 3))
        else:
            story.append(P("Manbalar ko‘rsatilmagan.", st["body"]))

    # ------------------------------------------------------------ colophon --
    story += [PageBreak(), ChapterMark("Tuzuvchilar va tasdiqlash"), P("Tuzuvchilar va tasdiqlash", st["h1"]),
              Ornament(), Spacer(1, 10)]
    rows = [[P("Tuzuvchi", st["label"]), P(f"{clean(compiler)} (@{clean(tree.owner.username)})", st["value"])]]
    for name, role in contributors:
        rows.append([P(clean(role), st["label"]), P(clean(name), st["value"])])
    rows += [
        [P("Shajara turi", st["label"]), P("Ta‘limiy" if learning else "Oilaviy", st["value"])],
        [P("Tuzilgan sana", st["label"]), P(long_date(today), st["value"])],
        [P("Shaxslar / avlodlar", st["label"]), P(f"{len(people)} / {len(gens)}", st["value"])],
        [P("Tekshirish kodi", st["label"]), P(f"<b>{code}</b>", st["value"])],
    ]
    t = Table(rows, colWidths=[4.2 * cm, 11.5 * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [t, Spacer(1, 18)]
    verify = Table(
        [[qr_drawing(verify_url, 3.2 * cm),
          P("<b>Hujjat haqiqiyligini tekshirish</b><br/>"
            "QR-kodni telefon kamerasi bilan skanerlang yoki quyidagi manzilni oching. Sahifada ushbu nusxa "
            "qachon, qaysi shajaradan va kim tomonidan tuzilgani ko‘rsatiladi.<br/>"
            f"<font color='{A_HEX}'>{clean(verify_url)}</font>", st["body_left"])]],
        colWidths=[3.8 * cm, 11.9 * cm],
    )
    verify.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [verify, Spacer(1, 18), Rule(),
              P("Ma’lumotlar shajara a’zolari tomonidan kiritilgan. Tarixiy sanalar va voqealar uchun "
                + ("yuqoridagi manbalarga murojaat qiling." if learning else "oilaviy hujjatlar bilan solishtiring."),
                st["small"]),
              P(f"e-Shajara platformasi · {clean(tree_url)}", st["small"])]

    buf = BytesIO()
    doc = BookTemplate(buf, book, title=book["title_plain"], author=compiler, subject="e-Shajara kitobi",
                       creator="e-Shajara")
    doc.multiBuild(story)
    return buf.getvalue(), {"people": len(people), "generations": len(gens)}


def clean_inf(markup):
    glyphs = book_fonts()["glyphs"]
    return markup if not glyphs or 0x221E in glyphs else markup.replace("∞", "×")


def book_image(field, max_w, max_h):
    """A picture for the page, shrunk first so the PDF stays small; None if the file is gone."""
    try:
        from PIL import Image as PILImage
        with field.open("rb") as fh:
            img = PILImage.open(fh)
            img = img.convert("RGB")
            img.thumbnail((1000, 1000))
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=80)
        buf.seek(0)
        w, h = img.size
        k = min(max_w / w, max_h / h)
        flow = Image(buf, width=w * k, height=h * k)
        return flow
    except Exception:
        return None


def photo_grid(photos, st, width=15.7 * cm, cols=3):
    """Pictures in rows of three, each with its caption and year underneath."""
    cell_w = width / cols
    cells = []
    for ph in photos:
        img = book_image(ph.image, cell_w - 0.5 * cm, 4.6 * cm)
        if img is None:
            continue
        note = " · ".join(clean(x) for x in (ph.caption, ph.when) if x)
        cells.append([img, Paragraph(note, st["center_small"])] if note else [img])
    if not cells:
        return []
    rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
    rows[-1] += [""] * (cols - len(rows[-1]))
    t = Table(rows, colWidths=[cell_w] * cols)
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [t]


def has_story(p):
    """Anything worth a paragraph beyond the name and years."""
    return bool(p.bio or p.occupation or p.birth_region or p.birth_district or p.location or p.photo
                or p.patronymic or p.stories.exists() or p.photos.exists())


def family_section(fam, pid, st, tree):
    """One family: a coloured title bar, the drawing, the parents' entries
    and the children table."""
    people = fam.people
    p = people[pid]
    num = fam.number.get(pid, "")
    spouses = fam.spouses[pid]
    kids = fam.children.get(pid, [])
    names = [p.full_name] + [people[s].full_name for s in spouses]
    if spouses or kids:
        title = " va ".join(names[:3]) + (" oilasi" if spouses else "")
    else:
        title = p.full_name
    toc_title = (f"{num}. " if num else "") + title

    origin = [x for x in (fam.father.get(pid), fam.mother.get(pid)) if x]
    if origin:
        sub = "Ota-onasi: " + " va ".join(plain(people[x].full_name) for x in origin)
        onum = fam.number.get(origin[0])
        if onum:
            sub += f" (№ {onum}-oila)"
    elif pid == tree.root_person_id or not origin:
        sub = "Shajarada ota-onasi ko‘rsatilmagan"
    if kids:
        sub += f" · {len(kids)} farzand"

    bar = Table(
        [[Paragraph(f"<font color='{BN_HEX}'>{clean('№')} {num}</font>&nbsp;&nbsp;{clean(title)}" if num else clean(title),
                    st["family_title"])],
         [Paragraph(clean(sub), st["family_sub"])]],
        colWidths=[None],
    )
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAR),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 9), ("BOTTOMPADDING", (0, -1), (-1, -1), 9),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
    ]))

    out = [CondPageBreak(7 * cm), FamilyMark(toc_title, family_key(num) if num else f"shaxs-{pid}"),
           Paragraph(f'<a name="{family_key(num) if num else f"shaxs-{pid}"}"/>', st["small"]), bar, Spacer(1, 10)]
    if spouses or kids:
        parents = ([pid] + spouses) if p.gender == "erkak" else (spouses[:1] + [pid] + spouses[1:])
        out += [FamilyDiagram(fam, parents, kids, pid), Spacer(1, 12)]

    out += person_entry(fam, pid, st, tree, show_children=False)
    for s_id in spouses:
        if s_id in fam.number and fam.number[s_id] != num:
            # a spouse with their own line gets their own section; just point to it
            out.append(Paragraph(
                f"Turmush o‘rtog‘i <b>{clean(people[s_id].full_name)}</b> haqida: "
                f"<a href='#{family_key(fam.number[s_id])}' color='{A_HEX}'>{clean('№')} {fam.number[s_id]}-oila</a>",
                st["body_left"]))
            continue
        out += [Rule(space=5)] + person_entry(fam, s_id, st, tree, show_children=False)

    if kids:
        head = [Paragraph(h, st["cell_head"]) for h in ("№", "Farzandi", "Yillari", "Keyingi avlodda")]
        rows = [head]
        for k in kids:
            kp = people[k]
            knum = fam.number.get(k, "")
            if fam.spouses[k] or fam.children.get(k):
                nxt = f"<a href='#{family_key(knum)}' color='{A_HEX}'>{knum}-oila {clean('→')}</a>" if knum else "—"
            elif has_story(kp):
                nxt = f"<a href='#shaxs-{k}' color='{A_HEX}'>ma’lumot {clean('→')}</a>"
            else:
                nxt = f"<font color='{M_HEX}'>oilasi kiritilmagan</font>"
            mother_note = ""
            if len(spouses) > 1:
                other = fam.mother.get(k) if p.gender == "erkak" else fam.father.get(k)
                if other and other in people:
                    mother_note = f"<br/><font size='8' color='{M_HEX}'>{'onasi' if p.gender == 'erkak' else 'otasi'}: {clean(people[other].full_name)}</font>"
            rows.append([
                Paragraph(f"<b>{knum}</b>", st["cell"]),
                Paragraph(f"<b>{clean(kp.full_name)}</b>{mother_note}", st["cell"]),
                Paragraph(clean(life_span(kp)) or "—", st["cell"]),
                Paragraph(nxt, st["cell"]),
            ])
        table = Table(rows, colWidths=[2.0 * cm, 6.4 * cm, 3.4 * cm, 3.9 * cm], repeatRows=1)
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, GOLD),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        out += [Spacer(1, 8), Paragraph("Farzandlari", st["h2"]), table]
    out += [Spacer(1, 6), Ornament(3.5 * cm, space=8)]
    return out


def person_entry(fam, pid, st, tree, show_children=True):
    p = fam.people[pid]
    rows = []

    def fact(label, value):
        if value:
            rows.append([Paragraph(label, st["label"]), Paragraph(value, st["value"])])

    if p.patronymic:
        fact("Otasining ismi", clean(p.patronymic))
    fact("Tug‘ilgan joyi", clean(place_text(p)))
    if p.birth_date:
        fact("Tug‘ilgan sanasi", long_date(p.birth_date))
    fact("Kasbi", clean(p.occupation))
    fact("Yashash joyi", clean(p.location))
    parents = [x for x in (fam.father.get(pid), fam.mother.get(pid)) if x]
    fact("Ota-onasi", " va ".join(fam.ref(x) for x in parents))
    fact("Turmush o‘rtog‘i", ", ".join(fam.ref(x) for x in fam.spouses[pid]))
    kids = fam.children.get(pid, [])
    if show_children:
        fact("Farzandlari", ", ".join(fam.ref(x) for x in kids))

    head = [
        Paragraph(fam.label_for(pid), st["num"]),
        Paragraph(clean(p.full_name) + (f" <font size='9' color='{A_HEX}'>· bosh shaxs</font>"
                                         if pid == tree.root_person_id else ""), st["name"]),
    ]
    if life_span(p):
        head.append(Paragraph(clean(life_span(p)), st["years"]))
    head.append(Spacer(1, 4))

    facts = None
    if rows:
        facts = Table(rows, colWidths=[3.3 * cm, None])
        facts.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ]))

    photo = None
    if p.photo:
        try:
            path = p.photo.path
            if os.path.exists(path):
                img = Image(path)
                ratio = img.imageHeight / float(img.imageWidth or 1)
                w = 3.4 * cm
                img.drawWidth, img.drawHeight = w, min(w * ratio, 4.6 * cm)
                photo = img
        except Exception:
            photo = None

    top = head + ([facts] if facts else [])
    if photo:
        frame = Table([[top, photo]], colWidths=[None, 3.8 * cm])
        frame.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"), ("BOX", (1, 0), (1, 0), 0.6, GOLD_SOFT),
        ]))
        block = [frame]
    else:
        block = top

    out = [CondPageBreak(4.5 * cm), KeepTogether(block)]
    if p.bio:
        out += [Spacer(1, 4)] + [Paragraph(clean(par), st["bio"]) for par in p.bio.split("\n") if par.strip()]
    stories = list(p.stories.select_related("author").order_by("created_at"))
    pictures = list(p.photos.all())
    if stories:
        out.append(Spacer(1, 6))
        out.append(Paragraph("Xotiralar", st["label"]))
        for s in stories:
            author = s.author.get_full_name() or s.author.username if s.author else "Noma’lum"
            # Paragraphs, not a table cell: a long memory must be able to run
            # onto the next page.
            quote_style = ParagraphStyle("quote", parent=st["story"], leftIndent=12, borderPadding=0)
            parts = [par for par in s.text.split("\n") if par.strip()] or [s.text]
            out.append(Spacer(1, 3))
            if s.title or s.when:
                head = f"<b>{clean(s.title)}</b>" if s.title else ""
                if s.when:
                    head += f"{' · ' if head else ''}<font color='{M_HEX}'><i>{clean(s.when)}</i></font>"
                out.append(Paragraph(head, ParagraphStyle("quote_head", parent=st["body_left"], leftIndent=12, spaceAfter=2)))
            for n, par in enumerate(parts):
                mark = f"<font color='{A_HEX}'><b>“</b></font> " if n == 0 else ""
                out.append(Paragraph(mark + clean(par), quote_style))
            out += photo_grid([ph for ph in pictures if ph.story_id == s.id], st)
            out.append(Paragraph(f"— {clean(author)}, {s.created_at:%d.%m.%Y}",
                                 ParagraphStyle("quote_meta", parent=st["story_meta"], leftIndent=12, spaceAfter=3)))
    gallery = [ph for ph in pictures if not ph.story_id]
    if gallery:
        out += [Spacer(1, 6), Paragraph("Suratlar", st["label"]), Spacer(1, 3)] + photo_grid(gallery, st)
    out.append(Spacer(1, 4))
    return out
