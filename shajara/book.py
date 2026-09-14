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
import os
import re
from collections import defaultdict
from functools import lru_cache
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
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

INK = colors.HexColor("#2b2118")
MUTED = colors.HexColor("#7a6a55")
GOLD = colors.HexColor("#a47b32")
GOLD_SOFT = colors.HexColor("#d9c49a")
WINE = colors.HexColor("#6b2a22")
PAPER = colors.HexColor("#fbf7ec")
RULE = colors.HexColor("#e6d9bd")

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
    for ch, alt in (("ʻ", "‘"), ("ʼ", "’"), ("∞", "×"), ("№", "No.")):
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
    s["family_sub"] = ParagraphStyle("family_sub", fontName=i, fontSize=9.5, leading=13, textColor=colors.HexColor("#f3e6c9"))
    s["cell"] = ParagraphStyle("cell", fontName=r, fontSize=9.6, leading=12.5, textColor=INK)
    s["cell_head"] = ParagraphStyle("cell_head", fontName=b, fontSize=8.4, leading=11, textColor=GOLD)
    return s


# --------------------------------------------------------- decorations --

class Ornament(Flowable):
    """A centred gold divider: two rules and a diamond, as between sections
    of an old book."""

    def __init__(self, width=5.5 * cm, space=8):
        super().__init__()
        self.w, self.space = width, space

    def wrap(self, avail_w, avail_h):
        self.avail = avail_w
        return avail_w, 10 + 2 * self.space

    def draw(self):
        c = self.canv
        cx, y = self.avail / 2, self.space + 5
        c.setStrokeColor(GOLD)
        c.setFillColor(GOLD)
        c.setLineWidth(0.7)
        c.line(cx - self.w / 2, y, cx - 7, y)
        c.line(cx + 7, y, cx + self.w / 2, y)
        p = c.beginPath()
        p.moveTo(cx, y + 4); p.lineTo(cx + 4, y); p.lineTo(cx, y - 4); p.lineTo(cx - 4, y); p.close()
        c.drawPath(p, stroke=0, fill=1)
        for dx in (-self.w / 2 - 3, self.w / 2 + 3):
            c.circle(cx + dx, y, 1.3, stroke=0, fill=1)


class Rule(Flowable):
    def __init__(self, color=RULE, width=0.6, space=6):
        super().__init__()
        self.color, self.lw, self.space = color, width, space

    def wrap(self, avail_w, avail_h):
        self.avail = avail_w
        return avail_w, 2 * self.space

    def draw(self):
        self.canv.setStrokeColor(self.color)
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
        cover = Frame(2.6 * cm, 2.6 * cm, PAGE_W - 5.2 * cm, PAGE_H - 5.2 * cm, id="cover")
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[cover], onPage=self.draw_cover_page),
            PageTemplate(id="body", frames=[body], onPage=self.draw_body_page, onPageEnd=self.draw_running_head),
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
        c.saveState()
        c.setFillColor(PAPER)
        c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.2)
        c.rect(inset, inset, PAGE_W - 2 * inset, PAGE_H - 2 * inset, stroke=1, fill=0)
        c.setLineWidth(0.4)
        c.rect(inset + 4, inset + 4, PAGE_W - 2 * inset - 8, PAGE_H - 2 * inset - 8, stroke=1, fill=0)
        c.restoreState()

    def draw_cover_page(self, c, doc):
        self._paper(c, 1.2 * cm)
        c.saveState()
        c.setFillColor(GOLD)
        for x, y in ((1.2 * cm, 1.2 * cm), (PAGE_W - 1.2 * cm, 1.2 * cm),
                     (1.2 * cm, PAGE_H - 1.2 * cm), (PAGE_W - 1.2 * cm, PAGE_H - 1.2 * cm)):
            p = c.beginPath()
            p.moveTo(x, y + 7); p.lineTo(x + 7, y); p.lineTo(x, y - 7); p.lineTo(x - 7, y); p.close()
            c.drawPath(p, stroke=0, fill=1)
        c.restoreState()

    def draw_body_page(self, c, doc):
        self._paper(c, 1.25 * cm)

    def draw_running_head(self, c, doc):
        """Drawn once the page is full, so it names the chapter the page is in."""
        r, b, i, bi = book_fonts()["names"]
        c.saveState()
        c.setFillColor(MUTED)
        c.setFont(i, 8.5)
        c.drawString(2.3 * cm, PAGE_H - 1.85 * cm, self.book["title_plain"][:70])
        if self.chapter:
            c.setFont(r, 8)
            c.drawRightString(PAGE_W - 2.3 * cm, PAGE_H - 1.85 * cm, plain(self.chapter)[:60])
        c.setStrokeColor(GOLD_SOFT)
        c.setLineWidth(0.5)
        c.line(2.3 * cm, PAGE_H - 2.0 * cm, PAGE_W - 2.3 * cm, PAGE_H - 2.0 * cm)
        c.setFillColor(GOLD)
        c.setFont(b, 9.5)
        label = str(doc.page)
        c.drawCentredString(PAGE_W / 2, 1.75 * cm, label)
        w = pdfmetrics.stringWidth(label, b, 9.5)
        c.setStrokeColor(GOLD)
        c.line(PAGE_W / 2 - w / 2 - 22, 1.84 * cm, PAGE_W / 2 - w / 2 - 6, 1.84 * cm)
        c.line(PAGE_W / 2 + w / 2 + 6, 1.84 * cm, PAGE_W / 2 + w / 2 + 22, 1.84 * cm)
        c.setFillColor(MUTED)
        c.setFont(r, 7)
        c.drawString(2.3 * cm, 1.75 * cm, f"Tekshirish kodi: {self.book['code']}")
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
        fill = {"main": colors.HexColor("#f4ead2"), "spouse": colors.white, "child": colors.white}[kind]
        stroke = colors.HexColor("#b56f7c") if p.gender == "ayol" else GOLD
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
            return f"{clean(p.full_name)} <font color='#a47b32'>({clean('№')} {num})</font>"
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


def build_book(tree, *, code, verify_url, tree_url, contributors, sources=()):
    """Return the PDF bytes for `tree`."""
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
    story += [
        Spacer(1, 2.2 * cm),
        P("TA‘LIMIY SHAJARA" if learning else "OILAVIY SHAJARA", st["kicker"]),
        Ornament(7 * cm),
        Spacer(1, 0.5 * cm),
        P(clean(tree.name), st["cover_title"]),
        Spacer(1, 0.35 * cm),
    ]
    if learning and (tree.subject or tree.era):
        story.append(P(clean(" · ".join(x for x in (tree.subject, tree.era) if x)), st["cover_sub"]))
    elif tree.description:
        story.append(P(clean(tree.description[:180]), st["cover_sub"]))
    story += [
        Spacer(1, 0.9 * cm),
        Ornament(4 * cm),
        Spacer(1, 0.6 * cm),
        P("Nasl boshi" if not learning else "Bosh shaxs", st["kicker"]),
        P(f"<b>{clean(root.full_name)}</b>", ParagraphStyle("root", parent=st["cover_sub"], fontSize=16, leading=21,
                                                        fontName=book_fonts()["names"][1])),
    ]
    if life_span(root):
        story.append(P(clean(life_span(root)), st["cover_meta"]))
    story += [
        Spacer(1, 1.0 * cm),
        P(f"{len(people)} shaxs &nbsp;·&nbsp; {len(gens)} avlod"
          + (f" &nbsp;·&nbsp; {min(years)}–{max(years)} yillar" if years else ""), st["cover_meta"]),
        Spacer(1, 6.2 * cm),
    ]
    compiler = tree.owner.get_full_name() or tree.owner.username
    cover_foot = Table(
        [[qr_drawing(verify_url, 2.4 * cm),
          P(f"<b>Tuzuvchi:</b> {clean(compiler)}<br/>"
            f"<b>Tuzilgan sana:</b> {long_date(today)}<br/>"
            f"<b>Tekshirish kodi:</b> {code}<br/>"
            f"<font size='8' color='#7a6a55'>QR-kodni skanerlab, hujjat haqiqiyligini tekshiring</font>",
            st["body_left"])]],
        colWidths=[2.9 * cm, 9 * cm],
    )
    cover_foot.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
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
    story.append(P(intro, st["body"]))
    if tree.description:
        story += [Spacer(1, 6), P(clean(tree.description), st["body"])]
    story += [
        Spacer(1, 10),
        P("Kitobdan qanday foydalanish kerak", st["h2"]),
        P("Har bir shaxs o‘z <b>raqami</b> bilan belgilangan. <b>1</b> — nasl boshi; <b>1.2</b> — uning ikkinchi "
          "farzandi; <b>1.2.1</b> — o‘sha farzandning birinchi farzandi. Raqamdagi nuqtalar soni avlodni "
          "ko‘rsatadi, shuning uchun istalgan shaxsning kimdan tarqalganini raqamidan bilib olish mumkin. "
          "Turmush o‘rtoqlar o‘z juftining raqami bilan ko‘rsatilgan.", st["body"]),
        Spacer(1, 6),
        P("<b>Qisqartmalar:</b> t. — tug‘ilgan; v. — vafot etgan; taxm. — taxminiy yil.", st["body"]),
        P("Avval «Nasl ro‘yxati» butun shajarani bir qarashda ko‘rsatadi, keyingi boblarda esa har bir "
          "avlodning har bir vakili haqida batafsil ma’lumot beriladi.", st["body"]),
        PageBreak(),
    ]

    # ----------------------------------------------------------- contents --
    toc = TableOfContents(dotsMinLevel=0)
    toc.levelStyles = [st["toc1"], st["toc2"]]
    story += [ChapterMark("Mundarija", toc=False), P("Mundarija", st["h1"]), Ornament(), Spacer(1, 8), toc,
              PageBreak()]

    # ----------------------------------------------------------- register --
    story += [ChapterMark("Nasl ro‘yxati"), P("Nasl ro‘yxati", st["h1"]), Ornament(),
              P("Shajaradagi barcha nasl chiziqlari — har bir qator bir shaxs, chekinish avlodni bildiradi.",
                st["chapter_intro"]), Spacer(1, 10)]
    for pid, num, depth in fam.register:
        p = people[pid]
        line = f"<font color='#a47b32'><b>{num}</b></font>&nbsp;&nbsp;<b>{clean(p.full_name)}</b>"
        if life_span(p):
            line += f" <font color='#7a6a55'><i>({clean(life_span(p))})</i></font>"
        partners = [s for s in fam.spouses[pid] if fam.married_to.get(s) == pid or s not in fam.number]
        if partners:
            line += " &nbsp;<font color='#7a6a55'>∞ " + ", ".join(clean(people[s].full_name) for s in partners) + "</font>"
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
            P(f"{clean(root.full_name)}ga nisbatan: {clean(relative)} · {people_here} kishi"
              + (f", {families_here} ta oila" if families_here else ""), st["chapter_intro"]),
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
                story.append(P(f"<font color='#a47b32'><b>{n}.</b></font> {clean(src)}", st["body_left"]))
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
            f"<font color='#a47b32'>{clean(verify_url)}</font>", st["body_left"])]],
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


def has_story(p):
    """Anything worth a paragraph beyond the name and years."""
    return bool(p.bio or p.occupation or p.birth_region or p.birth_district or p.location or p.photo
                or p.patronymic or p.stories.exists())


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
        [[Paragraph(f"<font color='#e9cf94'>{clean('№')} {num}</font>&nbsp;&nbsp;{clean(title)}" if num else clean(title),
                    st["family_title"])],
         [Paragraph(clean(sub), st["family_sub"])]],
        colWidths=[None],
    )
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WINE),
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
                f"<a href='#{family_key(fam.number[s_id])}' color='#a47b32'>{clean('№')} {fam.number[s_id]}-oila</a>",
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
                nxt = f"<a href='#{family_key(knum)}' color='#a47b32'>{knum}-oila →</a>" if knum else "—"
            elif has_story(kp):
                nxt = f"<a href='#shaxs-{k}' color='#a47b32'>ma’lumot →</a>"
            else:
                nxt = "<font color='#7a6a55'>oilasi kiritilmagan</font>"
            mother_note = ""
            if len(spouses) > 1:
                other = fam.mother.get(k) if p.gender == "erkak" else fam.father.get(k)
                if other and other in people:
                    mother_note = f"<br/><font size='8' color='#7a6a55'>{'onasi' if p.gender == 'erkak' else 'otasi'}: {clean(people[other].full_name)}</font>"
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
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f0de")]),
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
        Paragraph(clean(p.full_name) + (" <font size='9' color='#a47b32'>· bosh shaxs</font>"
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
            for n, par in enumerate(parts):
                mark = "<font color='#a47b32'><b>“</b></font> " if n == 0 else ""
                out.append(Paragraph(mark + clean(par), quote_style))
            out.append(Paragraph(f"— {clean(author)}, {s.created_at:%d.%m.%Y}",
                                 ParagraphStyle("quote_meta", parent=st["story_meta"], leftIndent=12, spaceAfter=3)))
    out.append(Spacer(1, 4))
    return out
