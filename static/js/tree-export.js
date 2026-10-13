/* Download the tree as a picture.

   The picture is redrawn from the live board (window.ShajaraBoard), so it
   shows the arrangement the reader made. It is a poster: a title band, the
   tree, and a footer with the compiler, the date and a QR check code the
   server issues for every copy.

   The reader picks a style (classic parchment, emerald and gold, Samarkand
   tiles, modern, black-and-white) and a size: fitted to the tree, or a paper
   sheet (A4/A3/A2) ready to print at 300 DPI and put in a frame. A live
   thumbnail in the menu shows the choice before anything is downloaded.

     SVG — vector: zoom in as far as you like, every name stays sharp.
     PNG — a large, crisp raster for messengers and printing shops.

   An owner or editor also refreshes the tree's share preview on the way,
   which invite links show when they are pasted into Telegram. */
(function () {
  "use strict";

  var shell = document.querySelector(".map-shell");
  var btn = document.getElementById("map-export-btn");
  var menu = document.getElementById("export-menu");
  var status = document.getElementById("export-status");
  if (!shell || !btn || !menu || !window.ShajaraBoard) return;

  var previewImg = document.getElementById("export-preview");
  var themeBox = document.getElementById("export-themes");
  var paperBox = document.getElementById("export-paper");
  var paperHint = document.getElementById("export-paper-hint");

  var SERIF = "'Palatino Linotype', 'Book Antiqua', Palatino, Georgia, 'Times New Roman', serif";
  var SANS = "'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif";
  var DPI = 300;
  var busy = false;

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function slug(s) {
    return (s || "shajara").toLowerCase().replace(/[ʻʼ‘’'`]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "shajara";
  }

  function setStatus(text, bad) {
    status.textContent = text || "";
    status.hidden = !text;
    status.classList.toggle("is-bad", !!bad);
  }

  function n(v) { return Math.round(v * 10) / 10; }

  // --------------------------------------------------------- ornaments --
  function diamond(o, x, y, d, fill) {
    o.push('<path d="M' + n(x) + " " + n(y - d) + " l" + n(d) + " " + n(d) + " l" + n(-d) + " " + n(d) + " l" + n(-d) + " " + n(-d) + 'z" fill="' + fill + '"/>');
  }

  // Eight-pointed star (two overlapping squares) — the khatam of Samarkand tiles.
  function starPoints(x, y, r) {
    var pts = [], inner = r * Math.cos(Math.PI / 4) / Math.cos(Math.PI / 8);
    for (var i = 0; i < 16; i++) {
      var a = i * Math.PI / 8 - Math.PI / 2, rr = i % 2 ? inner : r;
      pts.push(n(x + rr * Math.cos(a)) + "," + n(y + rr * Math.sin(a)));
    }
    return pts.join(" ");
  }
  function star(o, x, y, r, fill, stroke, sw) {
    o.push('<polygon points="' + starPoints(x, y, r) + '" fill="' + fill + '"' +
      (stroke ? ' stroke="' + stroke + '" stroke-width="' + n(sw) + '" stroke-linejoin="round"' : "") + "/>");
  }

  function rect(o, x, y, w, h, attrs) {
    o.push('<rect x="' + n(x) + '" y="' + n(y) + '" width="' + n(w) + '" height="' + n(h) + '" ' + attrs + "/>");
  }

  /* Each style: colours for every part of the poster, the frame it draws
     around the sheet, the small mark under the title, and how far its frame
     reaches in (inset, in title-band units). */
  var THEMES = {
    classic: {
      label: "Klassik", swatch: ["#fbf7ec", "#a47b32", "#6b2a22"],
      font: SERIF, bg: "#fbf7ec", base: "#fbf7ec",
      kicker: "#a47b32", title: "#6b2a22", sub: "#7a6a55", ink: "#2b2118", muted: "#7a6a55", rule: "#d9c49a", accent: "#a47b32",
      line: "#a47b32", lineW: 2.2, knotBg: "#fbf7ec", rx: 12,
      card: { fill: "#fffdf8", stroke: "#a47b32", name: "#2b2118", year: "#7a6a55", sw: 1.6 },
      cardF: { fill: "#fffdf8", stroke: "#b56f7c", name: "#2b2118", year: "#7a6a55", sw: 1.6 },
      root: { fill: "#6b2a22", stroke: "#a47b32", name: "#fbf1dc", year: "#e7d2a8", sw: 2.4, inner: "#d9b46a" },
      frame: function (o, W, H, k) {
        rect(o, 22, 22, W - 44, H - 44, 'fill="none" stroke="#a47b32" stroke-width="2.4"');
        rect(o, 31, 31, W - 62, H - 62, 'fill="none" stroke="#a47b32" stroke-width="0.9"');
        [[22, 22], [W - 22, 22], [22, H - 22], [W - 22, H - 22]].forEach(function (p) { diamond(o, p[0], p[1], 9, "#a47b32"); });
        // corner brackets inside the double rule
        var a = 44, l = 46 * k;
        [[a, a, 1, 1], [W - a, a, -1, 1], [a, H - a, 1, -1], [W - a, H - a, -1, -1]].forEach(function (c) {
          o.push('<path d="M' + n(c[0]) + " " + n(c[1] + c[3] * l) + " V" + n(c[1]) + " H" + n(c[0] + c[2] * l) +
            '" fill="none" stroke="#c9a96a" stroke-width="1.4"/>');
          diamond(o, c[0] + c[2] * 9, c[1] + c[3] * 9, 3.2, "#a47b32");
        });
      },
      mark: function (o, x, y, d) { diamond(o, x, y, d, "#a47b32"); }
    },

    emerald: {
      label: "Zumrad", swatch: ["#0f2e21", "#d6b25e", "#d6b25e"],
      font: SERIF, bg: "url(#pbg)", base: "#0f2a1e",
      defs: function () {
        return '<radialGradient id="pbg" cx="50%" cy="45%" r="75%"><stop offset="0" stop-color="#1a4532"/><stop offset="1" stop-color="#0a1f16"/></radialGradient>';
      },
      kicker: "#d6b25e", title: "#f3e3b5", sub: "#b9c9b8", ink: "#f1ead9", muted: "#a9bdae", rule: "rgba(214,178,94,0.45)", accent: "#d6b25e",
      line: "#c9a24f", lineW: 2.2, knotBg: "#123526", rx: 12,
      card: { fill: "#143a2a", stroke: "#c9a24f", name: "#f5ecd4", year: "#b6c8b8", sw: 1.5 },
      cardF: { fill: "#163b2e", stroke: "#e0a9a0", name: "#f5ecd4", year: "#b6c8b8", sw: 1.5 },
      root: { fill: "#d6b25e", stroke: "#f3e3b5", name: "#1b2a1f", year: "#3d4a33", sw: 2.4, inner: "#9a7a2e" },
      frame: function (o, W, H, k) {
        rect(o, 24, 24, W - 48, H - 48, 'fill="none" stroke="#d6b25e" stroke-width="2.6"');
        rect(o, 36, 36, W - 72, H - 72, 'fill="none" stroke="#d6b25e" stroke-width="1"');
        rect(o, 48, 48, W - 96, H - 96, 'fill="none" stroke="#d6b25e" stroke-width="1.4" stroke-dasharray="0.1 7" stroke-linecap="round" opacity="0.7"');
        var r = 15 * Math.min(k, 1.6);
        [[30, 30], [W - 30, 30], [30, H - 30], [W - 30, H - 30]].forEach(function (p) {
          o.push('<circle cx="' + n(p[0]) + '" cy="' + n(p[1]) + '" r="' + n(r) + '" fill="#0d261b" stroke="#d6b25e" stroke-width="1.6"/>');
          star(o, p[0], p[1], r * 0.62, "#d6b25e");
        });
      },
      mark: function (o, x, y, d) { star(o, x, y, d * 1.3, "#d6b25e"); }
    },

    samarkand: {
      label: "Samarqand", swatch: ["#f7f3ea", "#1f3c88", "#3aa7a3"],
      font: SERIF, bg: "#f8f4ea", base: "#f8f4ea", inset: 46,
      kicker: "#2a8f8b", title: "#1f3c88", sub: "#5d6a86", ink: "#1d2747", muted: "#5d6a86", rule: "#c8b787", accent: "#c9a347",
      line: "#2f6fa8", lineW: 2.2, knotBg: "#f8f4ea", rx: 12,
      card: { fill: "#ffffff", stroke: "#1f3c88", name: "#1d2747", year: "#5d6a86", sw: 1.6 },
      cardF: { fill: "#fffaf5", stroke: "#2a9d9a", name: "#1d2747", year: "#5d6a86", sw: 1.6 },
      root: { fill: "#1f3c88", stroke: "#c9a347", name: "#fdf6e3", year: "#cfd9f2", sw: 2.6, inner: "#c9a347" },
      tiles: function (W, H, k) {
        var B = 44 * k, m = 18;
        var nw = Math.max(1, Math.round((W - 2 * m) / B)), nh = Math.max(1, Math.round((H - 2 * m) / B));
        return { m: m, tw: (W - 2 * m) / nw, th: (H - 2 * m) / nh };
      },
      defs: function (W, H, k) {
        var t = this.tiles(W, H, k), s = [];
        s.push('<pattern id="girih" patternUnits="userSpaceOnUse" x="' + t.m + '" y="' + t.m + '" width="' + n(t.tw) + '" height="' + n(t.th) + '">');
        s.push('<g transform="scale(' + (t.tw / 100).toFixed(4) + " " + (t.th / 100).toFixed(4) + ')">');
        s.push('<rect width="100" height="100" fill="#1f3c88"/>');
        [[0, 0], [100, 0], [0, 100], [100, 100]].forEach(function (p) { s.push('<circle cx="' + p[0] + '" cy="' + p[1] + '" r="13" fill="#c9a347"/>'); });
        s.push('<polygon points="' + starPoints(50, 50, 36) + '" fill="#3aa7a3" stroke="#e6c876" stroke-width="3.5" stroke-linejoin="round"/>');
        s.push('<polygon points="' + starPoints(50, 50, 17) + '" fill="#f8f4ea"/>');
        s.push('<circle cx="50" cy="50" r="5" fill="#1f3c88"/>');
        s.push("</g></pattern>");
        return s.join("");
      },
      frame: function (o, W, H, k) {
        var t = this.tiles(W, H, k), m = t.m;
        o.push('<path fill-rule="evenodd" fill="url(#girih)" d="M' + m + " " + m + " H" + n(W - m) + " V" + n(H - m) + " H" + m + "Z M" +
          n(m + t.tw) + " " + n(m + t.th) + " V" + n(H - m - t.th) + " H" + n(W - m - t.tw) + " V" + n(m + t.th) + 'Z"/>');
        rect(o, m, m, W - 2 * m, H - 2 * m, 'fill="none" stroke="#c9a347" stroke-width="2.4"');
        rect(o, m + t.tw, m + t.th, W - 2 * (m + t.tw), H - 2 * (m + t.th), 'fill="none" stroke="#c9a347" stroke-width="2.4"');
        var g = 9 * k;
        rect(o, m + t.tw + g, m + t.th + g, W - 2 * (m + t.tw + g), H - 2 * (m + t.th + g), 'fill="none" stroke="#2a9d9a" stroke-width="1"');
      },
      mark: function (o, x, y, d) { star(o, x, y, d * 1.6, "#3aa7a3", "#c9a347", d * 0.25); }
    },

    modern: {
      label: "Zamonaviy", swatch: ["#ffffff", "#1a7a46", "#e4f5ea"],
      font: SANS, bg: "#ffffff", base: "#ffffff", inset: 6,
      kicker: "#1a7a46", title: "#123d27", sub: "#5f7f6d", ink: "#123d27", muted: "#5f7f6d", rule: "#d7e9de", accent: "#1a7a46",
      line: "#8cbfa0", lineW: 2.4, knotBg: "#ffffff", rx: 16, shadow: "rgba(15,61,39,0.16)",
      card: { fill: "#f1faf4", stroke: "#bfdcc9", name: "#123d27", year: "#5f7f6d", sw: 1.4 },
      cardF: { fill: "#fdf3f5", stroke: "#ebc3cc", name: "#3d1f27", year: "#86606a", sw: 1.4 },
      root: { fill: "#1a7a46", stroke: "#1a7a46", name: "#ffffff", year: "#cfeedd", sw: 1.4 },
      frame: function (o, W, H, k) {
        rect(o, 0, 0, W, 12 * k, 'fill="#1a7a46"');
        rect(o, 0, H - 5 * k, W, 5 * k, 'fill="#c99a2e"');
        rect(o, 26, 26 + 12 * k, W - 52, H - 52 - 17 * k, 'rx="22" fill="none" stroke="#d7e9de" stroke-width="1.5"');
      },
      mark: function (o, x, y, d) { o.push('<circle cx="' + n(x) + '" cy="' + n(y) + '" r="' + n(d * 0.75) + '" fill="#c99a2e"/>'); }
    },

    ink: {
      label: "Oq-qora", swatch: ["#ffffff", "#222222", "#222222"],
      font: SERIF, bg: "#ffffff", base: "#ffffff",
      kicker: "#333333", title: "#111111", sub: "#555555", ink: "#111111", muted: "#555555", rule: "#999999", accent: "#222222",
      line: "#444444", lineW: 1.8, knotBg: "#ffffff", rx: 10,
      card: { fill: "#ffffff", stroke: "#222222", name: "#111111", year: "#555555", sw: 1.3 },
      cardF: { fill: "#ffffff", stroke: "#222222", name: "#111111", year: "#555555", sw: 1.3, dash: "5 3" },
      root: { fill: "#222222", stroke: "#222222", name: "#ffffff", year: "#dddddd", sw: 1.3 },
      frame: function (o, W, H) {
        rect(o, 22, 22, W - 44, H - 44, 'fill="none" stroke="#111" stroke-width="2"');
        rect(o, 30, 30, W - 60, H - 60, 'fill="none" stroke="#111" stroke-width="0.7"');
      },
      mark: function (o, x, y, d) { diamond(o, x, y, d, "#222"); }
    }
  };
  var THEME_ORDER = ["classic", "emerald", "samarkand", "modern", "ink"];

  // Paper sheets in millimetres (portrait); the orientation follows the tree.
  var PAPERS = {
    auto: { label: "Moslashuvchan", hint: "Daraxt o'lchamida — ekranda ko'rish va Telegram'da ulashish uchun." },
    a4: { label: "A4", mm: [210, 297], hint: "A4 (21×30 sm), 300 DPI — oddiy printerda chop etish uchun." },
    a3: { label: "A3", mm: [297, 420], hint: "A3 (30×42 sm), 300 DPI — ramkaga solib devorga ilish uchun." },
    a2: { label: "A2", mm: [420, 594], hint: "A2 (42×59 sm), 300 DPI — katta oila uchun, matbaada chop etiladi." }
  };

  // ------------------------------------------------------------- choice --
  var STORE = "eshajara_export_style";
  var choice = { theme: "classic", paper: "auto" };
  try {
    var saved = JSON.parse(localStorage.getItem(STORE) || "null");
    if (saved && THEMES[saved.theme]) choice.theme = saved.theme;
    if (saved && PAPERS[saved.paper]) choice.paper = saved.paper;
  } catch (e) { /* defaults */ }
  function remember() { try { localStorage.setItem(STORE, JSON.stringify(choice)); } catch (e) { /* ignore */ } }

  // ------------------------------------------------------------- layout --
  function bbox(cards) {
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    cards.forEach(function (c) {
      minX = Math.min(minX, c.x); minY = Math.min(minY, c.y);
      maxX = Math.max(maxX, c.x + c.w); maxY = Math.max(maxY, c.y + c.h);
    });
    if (!cards.length) { minX = minY = 0; maxX = maxY = 200; }
    return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
  }

  // Title band and footer grow with a wide sheet so they stay in proportion.
  function bands(W, T, titleLen) {
    var k = Math.min(3, Math.max(1, W / 1500));
    var ins = (T.inset || 0) * k;
    var titleSize = Math.max(22 * k, Math.min(46 * k, (W - 240 * k - 2 * ins) / Math.max(8, titleLen * 0.56)));
    var rule = ins + 138 * k + titleSize;
    return { k: k, ins: ins, titleSize: titleSize, top: ins, rule: rule, head: rule + 50 * k, foot: 176 * k + ins };
  }

  function layout(box, T, paper, titleLen) {
    var PAD = 70;
    var W = Math.max(Math.round(box.w + PAD * 2), 1000), g, i;
    for (i = 0; i < 4; i++) { g = bands(W, T, titleLen); W = Math.max(W, Math.round(box.w + 2 * PAD + 2 * g.ins)); }
    function need(g) { return g.head + box.h + PAD * 1.4 + g.foot; }
    var H, mm = null, ts = 1;
    if (!paper.mm) {
      g = bands(W, T, titleLen);
      H = Math.round(need(g));
    } else {
      var landscape = W > need(g);
      var ratio = landscape ? paper.mm[0] / paper.mm[1] : paper.mm[1] / paper.mm[0];   // height / width
      for (i = 0; i < 10; i++) {
        g = bands(W, T, titleLen);
        var h = need(g);
        if (h <= W * ratio + 0.5) break;
        W = h / ratio;
      }
      g = bands(W, T, titleLen);
      W = Math.round(W); H = Math.round(W * ratio);
      mm = landscape ? [paper.mm[1], paper.mm[0]] : paper.mm;
      // A small family would sit lost in the middle of the sheet; let it fill it.
      var availW = W - 2 * PAD - 2 * g.ins, availH = H - g.head - g.foot - PAD * 1.4;
      ts = Math.min(2.4, availW / Math.max(1, box.w), availH / Math.max(1, box.h));
    }
    var tw = box.w * ts, th = box.h * ts;
    var areaTop = g.head + PAD * 0.4, areaH = H - g.foot - PAD - areaTop;
    return {
      W: W, H: H, g: g, mm: mm, ts: ts,
      tx: (W - tw) / 2 - box.x * ts, ty: areaTop + (areaH - th) / 2 - box.y * ts
    };
  }

  // ---------------------------------------------------------- drawing --
  function years(card) {
    var b = (card.year || "").replace(/^~/, "taxm. ");
    var d = (card.death || "").replace(/^~/, "taxm. ");
    if (b && d) return b + " – " + d;
    if (b) return b;
    if (d) return "v. " + d;
    return "";
  }

  function buildSvg(snap, meta, opts) {
    opts = opts || choice;
    var T = THEMES[opts.theme] || THEMES.classic;
    var paper = PAPERS[opts.paper] || PAPERS.auto;
    var cards = snap.cards;
    var L = layout(bbox(cards), T, paper, meta.title.length);
    var W = L.W, H = L.H, g = L.g, k = g.k, cx = W / 2, F = T.font;

    var o = [];
    o.push('<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + " " + H + '">');
    o.push("<title>" + esc(meta.title) + "</title>");
    o.push("<defs>" + (T.defs ? T.defs(W, H, k) : "") +
      (T.shadow ? '<filter id="cs" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="' + T.shadow + '"/></filter>' : "") +
      "</defs>");
    o.push('<rect width="' + W + '" height="' + H + '" fill="' + T.bg + '"/>');
    T.frame(o, W, H, k);

    // title band
    var top = g.top;
    o.push('<text x="' + cx + '" y="' + n(top + 78 * k) + '" text-anchor="middle" font-family="' + F + '" font-size="' + n(15 * k) +
      '" font-weight="700" letter-spacing="' + n(3 * k) + '" fill="' + T.kicker + '">' + esc(meta.kind) + "</text>");
    o.push('<text x="' + cx + '" y="' + n(top + 86 * k + g.titleSize) + '" text-anchor="middle" font-family="' + F + '" font-size="' +
      n(g.titleSize) + '" font-weight="700" fill="' + T.title + '">' + esc(meta.title) + "</text>");
    var sub = meta.subtitle || meta.people + " shaxs · " + meta.generations + " avlod";
    o.push('<text x="' + cx + '" y="' + n(top + 118 * k + g.titleSize) + '" text-anchor="middle" font-family="' + F + '" font-size="' + n(17 * k) +
      '"' + (F === SERIF ? ' font-style="italic"' : "") + ' fill="' + T.sub + '">' + esc(sub) + "</text>");
    var r = 120 * k, d = 6 * k, oy2 = g.rule;
    o.push('<path d="M' + n(cx - r) + " " + n(oy2) + " H" + n(cx - 2.4 * d) + " M" + n(cx + 2.4 * d) + " " + n(oy2) + " H" + n(cx + r) +
      '" stroke="' + T.accent + '" stroke-width="' + n(1.2 * k) + '"/>');
    T.mark(o, cx, oy2, d);

    // connectors, restyled for paper
    o.push('<g transform="translate(' + L.tx.toFixed(1) + " " + L.ty.toFixed(1) + ")" + (L.ts !== 1 ? " scale(" + L.ts.toFixed(4) + ")" : "") + '">');
    var doc = new DOMParser().parseFromString('<svg xmlns="http://www.w3.org/2000/svg">' + snap.lines + "</svg>", "image/svg+xml");
    var root = doc.documentElement;
    Array.prototype.forEach.call(root.querySelectorAll(".branch-line"), function (p) {
      o.push('<path d="' + esc(p.getAttribute("d")) + '" fill="none" stroke="' + T.line + '" stroke-width="' + T.lineW + '" stroke-linecap="round"/>');
    });
    Array.prototype.forEach.call(root.querySelectorAll(".branch-tip"), function (c) {
      o.push('<circle cx="' + c.getAttribute("cx") + '" cy="' + c.getAttribute("cy") + '" r="2.6" fill="' + T.line + '"/>');
    });
    Array.prototype.forEach.call(root.querySelectorAll(".marriage-link"), function (l) {
      o.push('<line x1="' + l.getAttribute("x1") + '" y1="' + l.getAttribute("y1") + '" x2="' + l.getAttribute("x2") + '" y2="' + l.getAttribute("y2") +
        '" stroke="' + T.line + '" stroke-width="' + T.lineW + '" stroke-linecap="round"/>');
    });
    Array.prototype.forEach.call(root.querySelectorAll(".marriage-knot"), function (gk) {
      Array.prototype.forEach.call(gk.querySelectorAll("circle"), function (c) {
        var bg = (c.getAttribute("class") || "").indexOf("knot-bg") !== -1;
        o.push('<circle cx="' + c.getAttribute("cx") + '" cy="' + c.getAttribute("cy") + '" r="' + c.getAttribute("r") + '" ' +
          (bg ? 'fill="' + T.knotBg + '"' : 'fill="none" stroke="' + T.line + '" stroke-width="1.6"') + "/>");
      });
    });

    // cards
    cards.forEach(function (c) {
      var s = c.root ? T.root : c.gender === "ayol" ? T.cardF : T.card;
      var y = years(c);
      o.push('<rect x="' + n(c.x) + '" y="' + n(c.y) + '" width="' + n(c.w) + '" height="' + n(c.h) + '" rx="' + T.rx + '" fill="' + s.fill +
        '" stroke="' + s.stroke + '" stroke-width="' + s.sw + '"' + (s.dash ? ' stroke-dasharray="' + s.dash + '"' : "") +
        (T.shadow ? ' filter="url(#cs)"' : "") + "/>");
      if (s.inner) {
        o.push('<rect x="' + n(c.x + 4) + '" y="' + n(c.y + 4) + '" width="' + n(c.w - 8) + '" height="' + n(c.h - 8) + '" rx="' + Math.max(2, T.rx - 4) +
          '" fill="none" stroke="' + s.inner + '" stroke-width="0.8"/>');
      }
      var mid = c.x + c.w / 2, midY = c.y + c.h / 2;
      var size = c.root ? 17 : 14.5;
      o.push('<text x="' + n(mid) + '" y="' + n(midY + (y ? -1 : 5)) + '" text-anchor="middle" font-family="' + F +
        '" font-size="' + size + '" font-weight="700" fill="' + s.name + '">' + esc(c.name) + "</text>");
      if (y) {
        o.push('<text x="' + n(mid) + '" y="' + n(midY + 14) + '" text-anchor="middle" font-family="' + F +
          '" font-size="10.5" fill="' + s.year + '">' + esc(y) + "</text>");
      }
    });
    o.push("</g>");

    // footer: who, when, and the check mark
    var fy = H - g.foot + 10 * k;
    var left = 70 * k + g.ins, right = W - 70 * k - g.ins, qrSize = 96 * k;
    o.push('<line x1="' + n(left) + '" y1="' + n(fy) + '" x2="' + n(right) + '" y2="' + n(fy) + '" stroke="' + T.rule + '" stroke-width="' + n(k) + '"/>');
    function footText(x, y, size, anchor, color, body, bold) {
      o.push('<text x="' + n(x) + '" y="' + n(y) + '"' + (anchor ? ' text-anchor="' + anchor + '"' : "") + ' font-family="' + F +
        '" font-size="' + n(size * k) + '"' + (bold ? ' font-weight="700"' : "") + ' fill="' + color + '">' + body + "</text>");
    }
    footText(left, fy + 40 * k, 15, "", T.ink, '<tspan font-weight="700">Tuzuvchi:</tspan> ' + esc(meta.compiler));
    footText(left, fy + 64 * k, 14, "", T.muted, esc(meta.date) + " · " + meta.people + " shaxs · " + meta.generations + " avlod");
    footText(left, fy + 88 * k, 13, "", T.muted, "e-Shajara · e-shajara.uz");
    var qx = right - qrSize, qy = fy + 18 * k, pad = 6 * k;
    footText(qx - 16 * k - pad, fy + 48 * k, 15, "end", T.ink, "Tekshirish kodi: " + esc(meta.code), true);
    footText(qx - 16 * k - pad, fy + 72 * k, 12.5, "end", T.muted, esc(meta.verifyUrl));
    // a white plate keeps the QR readable on every background
    rect(o, qx - pad, qy - pad, qrSize + 2 * pad, qrSize + 2 * pad, 'rx="' + n(6 * k) + '" fill="#ffffff" stroke="' + T.rule + '" stroke-width="' + n(k) + '"');
    if (meta.qr) {
      o.push('<g transform="translate(' + n(qx) + " " + n(qy) + ") scale(" + (qrSize / 120).toFixed(4) + ')">' + meta.qr + "</g>");
    } else {
      // preview: a QR-like placeholder
      var u = qrSize / 7;
      [[0, 0], [4, 0], [0, 4]].forEach(function (p) {
        rect(o, qx + p[0] * u, qy + p[1] * u, 3 * u, 3 * u, 'fill="none" stroke="#222" stroke-width="' + n(u * 0.6) + '"');
      });
      rect(o, qx + 4.5 * u, qy + 4.5 * u, 2 * u, 2 * u, 'fill="#222"');
    }
    o.push("</svg>");
    var markup = o.join("");
    return {
      markup: markup, width: W, height: H, mm: L.mm, base: T.base,
      // a sheet carries its real size, so print dialogs place it 1:1
      printMarkup: L.mm ? markup.replace('width="' + W + '" height="' + H + '"', 'width="' + L.mm[0] + 'mm" height="' + L.mm[1] + 'mm"') : markup
    };
  }

  function loadImage(markup) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(new Blob([markup], { type: "image/svg+xml;charset=utf-8" }));
      var img = new Image();
      img.onload = function () { resolve({ img: img, url: url }); };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error("Rasmni chizib bo'lmadi.")); };
      img.src = url;
    });
  }

  function canvasBlob(canvas) {
    return new Promise(function (resolve, reject) {
      canvas.toBlob(function (b) { b ? resolve(b) : reject(new Error("Rasm juda katta.")); }, "image/png");
    });
  }

  function rasterScale(poster) {
    var w = poster.width, h = poster.height;
    // Phones cap canvases around 16 megapixels; desktops go much further.
    var budget = (navigator.maxTouchPoints || 0) > 0 ? 16e6 : 90e6;
    var cap = Math.min(Math.sqrt(budget / (w * h)), 16000 / w, 16000 / h);
    var want = poster.mm ? (poster.mm[0] / 25.4 * DPI) / w : 3;   // a sheet aims at 300 DPI
    return Math.max(0.5, Math.min(want, cap));
  }

  /* Write the print resolution into the PNG (pHYs chunk), so a print shop's
     software opens an A3 sheet as 30×42 cm and not as a 1-metre poster. */
  var CRC = null;
  function crc32(bytes) {
    if (!CRC) {
      CRC = [];
      for (var i = 0; i < 256; i++) {
        var c = i;
        for (var j = 0; j < 8; j++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        CRC[i] = c >>> 0;
      }
    }
    var crc = 0xffffffff;
    for (var b = 0; b < bytes.length; b++) crc = CRC[(crc ^ bytes[b]) & 0xff] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  }
  function withDpi(blob, dpi) {
    return blob.arrayBuffer().then(function (buf) {
      var src = new Uint8Array(buf);
      var ppm = Math.round(dpi / 0.0254);
      var chunk = new Uint8Array(21), dv = new DataView(chunk.buffer);
      dv.setUint32(0, 9);
      chunk.set([0x70, 0x48, 0x59, 0x73], 4);           // "pHYs"
      dv.setUint32(8, ppm); dv.setUint32(12, ppm); chunk[16] = 1;
      dv.setUint32(17, crc32(chunk.subarray(4, 17)));
      var at = 33;                                       // signature (8) + IHDR (25)
      var out = new Uint8Array(src.length + 21);
      out.set(src.subarray(0, at), 0);
      out.set(chunk, at);
      out.set(src.subarray(at), at + 21);
      return new Blob([out], { type: "image/png" });
    }).catch(function () { return blob; });
  }

  function download(blob, name) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
  }

  function post(url, body, isJson) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: Object.assign({ "X-CSRFToken": shell.dataset.csrf || "" }, isJson ? { "Content-Type": "application/json" } : {}),
      body: body
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.error || "Server javob bermadi.");
        return d;
      });
    });
  }

  function sharePreview(loaded, poster) {
    var url = shell.dataset.previewUrl;
    if (!url) return Promise.resolve();
    var W = 1200, H = 630;
    var canvas = document.createElement("canvas");
    canvas.width = W; canvas.height = H;
    var ctx = canvas.getContext("2d");
    ctx.fillStyle = poster.base;
    ctx.fillRect(0, 0, W, H);
    var k = Math.min(W / poster.width, H / poster.height);
    var dw = poster.width * k, dh = poster.height * k;
    ctx.drawImage(loaded.img, (W - dw) / 2, (H - dh) / 2, dw, dh);
    return canvasBlob(canvas).then(function (blob) {
      var form = new FormData();
      form.append("image", blob, "preview.png");
      return post(url, form, false);
    }).catch(function () { /* the download matters more than the preview */ });
  }

  function run(kind) {
    if (busy) return;
    busy = true;
    menu.classList.add("is-busy");
    setStatus(kind === "png" ? "Yuqori sifatli rasm tayyorlanmoqda…" : "Vektor rasm tayyorlanmoqda…");
    var name = shell.dataset.treeName || "Shajara";
    var opts = { theme: choice.theme, paper: choice.paper };
    post(shell.dataset.recordUrl, JSON.stringify({ kind: kind, style: opts.theme, paper: opts.paper }), true)
      .then(function (rec) {
        var snap = window.ShajaraBoard.snapshot();
        var poster = buildSvg(snap, {
          title: name, kind: rec.kind_label, subtitle: rec.subtitle, compiler: rec.compiler, date: rec.date,
          people: rec.people, generations: rec.generations, code: rec.code, verifyUrl: rec.verify_url, qr: rec.qr_svg
        }, opts);
        var file = slug(name) + "-shajara" + (poster.mm ? "-" + opts.paper : "");
        return loadImage(poster.markup).then(function (loaded) {
          var job;
          if (kind === "svg") {
            download(new Blob([poster.printMarkup], { type: "image/svg+xml;charset=utf-8" }), file + ".svg");
            job = Promise.resolve();
          } else {
            var s = rasterScale(poster);
            var canvas = document.createElement("canvas");
            canvas.width = Math.round(poster.width * s);
            canvas.height = Math.round(poster.height * s);
            var ctx = canvas.getContext("2d");
            ctx.fillStyle = poster.base;
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.scale(s, s);
            ctx.drawImage(loaded.img, 0, 0, poster.width, poster.height);
            job = canvasBlob(canvas)
              .then(function (blob) { return poster.mm ? withDpi(blob, canvas.width / (poster.mm[0] / 25.4)) : blob; })
              .then(function (blob) { download(blob, file + ".png"); });
          }
          return job.then(function () { return sharePreview(loaded, poster); })
            .then(function () {
              URL.revokeObjectURL(loaded.url);
              setStatus("Tayyor. Tekshirish kodi: " + rec.code);
            });
        });
      })
      .catch(function (err) { setStatus(err.message || "Xatolik yuz berdi.", true); })
      .then(function () {
        busy = false;
        menu.classList.remove("is-busy");
      });
  }

  // -------------------------------------------------- preview & picker --
  var previewUrl = null;
  function renderPreview() {
    if (!previewImg) return;
    var snap = window.ShajaraBoard.snapshot();
    var rows = {};
    snap.cards.forEach(function (c) { rows[Math.round(c.y / 20)] = 1; });
    var poster = buildSvg(snap, {
      title: shell.dataset.treeName || "Shajara", kind: shell.dataset.kindLabel || "OILAVIY SHAJARA", subtitle: "",
      compiler: shell.dataset.compiler || "", date: "", people: snap.cards.length, generations: Object.keys(rows).length,
      code: "XXXX-XXXX", verifyUrl: "e-shajara.uz/tekshirish/…", qr: ""
    }, choice);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(new Blob([poster.markup], { type: "image/svg+xml;charset=utf-8" }));
    previewImg.src = previewUrl;
    previewImg.classList.toggle("is-sheet", !!poster.mm);
  }

  function radio(box, value) {
    Array.prototype.forEach.call(box.querySelectorAll("[role=radio]"), function (b) {
      var on = b.dataset.value === value;
      b.setAttribute("aria-checked", String(on));
      b.tabIndex = on ? 0 : -1;
    });
  }

  // The book is made on the server in the same style; its little cover follows the choice.
  var BOOK_COVERS = {
    classic: ["#7a2f26", "#4e1b15", "#f3dfae", "#d6b25e"], emerald: ["#1d5640", "#0b2219", "#f3e3b5", "#d6b25e"],
    samarkand: ["#2a4fa6", "#1f3c88", "#f8f4ea", "#3aa7a3"], modern: ["#1f8a51", "#14653a", "#ffffff", "#c99a2e"],
    ink: ["#3a3a3a", "#151515", "#ffffff", "#bbbbbb"]
  };
  function syncBook() {
    var link = document.getElementById("export-book");
    if (!link) return;
    link.href = link.getAttribute("data-base") + (choice.theme === "classic" ? "" : "?uslub=" + choice.theme);
    var cv = BOOK_COVERS[choice.theme] || BOOK_COVERS.classic, cover = link.querySelector(".export-book-cover");
    if (cover) {
      cover.style.background = "linear-gradient(160deg," + cv[0] + "," + cv[1] + ")";
      cover.style.color = cv[2];
      cover.style.setProperty("--cover-accent", cv[3]);
    }
  }

  function buildPicker() {
    if (themeBox) {
      THEME_ORDER.forEach(function (id) {
        var T = THEMES[id], b = document.createElement("button");
        b.type = "button"; b.className = "export-theme"; b.dataset.value = id;
        b.setAttribute("role", "radio");
        b.innerHTML = '<span class="export-sw" style="background:linear-gradient(135deg,' + T.swatch[0] + " 0 48%," + T.swatch[1] + " 48% 70%," +
          T.swatch[2] + ' 70%)"></span><span>' + esc(T.label) + "</span>";
        b.addEventListener("click", function () { choice.theme = id; remember(); radio(themeBox, id); syncBook(); renderPreview(); });
        themeBox.appendChild(b);
      });
      radio(themeBox, choice.theme);
      syncBook();
    }
    if (paperBox) {
      Object.keys(PAPERS).forEach(function (id) {
        var b = document.createElement("button");
        b.type = "button"; b.dataset.value = id;
        b.setAttribute("role", "radio");
        b.textContent = PAPERS[id].label;
        b.addEventListener("click", function () {
          choice.paper = id; remember(); radio(paperBox, id);
          if (paperHint) paperHint.textContent = PAPERS[id].hint;
          renderPreview();
        });
        paperBox.appendChild(b);
      });
      radio(paperBox, choice.paper);
      if (paperHint) paperHint.textContent = PAPERS[choice.paper].hint;
    }
    // arrow keys move inside each radio group
    [themeBox, paperBox].forEach(function (box) {
      if (!box) return;
      box.addEventListener("keydown", function (e) {
        if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].indexOf(e.key) < 0) return;
        var items = Array.prototype.slice.call(box.querySelectorAll("[role=radio]"));
        var i = items.indexOf(document.activeElement);
        if (i < 0) return;
        e.preventDefault();
        var nx = items[(i + (e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1) + items.length) % items.length];
        nx.focus(); nx.click();
      });
    });
  }

  // ------------------------------------------------------------- menu --
  function openMenu(open) {
    menu.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
    if (open) { setStatus(""); renderPreview(); }
  }
  btn.addEventListener("click", function (e) {
    e.stopPropagation();
    openMenu(menu.hidden);
  });
  ["pointerdown", "wheel", "click"].forEach(function (t) {
    menu.addEventListener(t, function (e) { e.stopPropagation(); }, { passive: t !== "click" });
  });
  document.addEventListener("click", function (e) {
    if (!menu.hidden && !menu.contains(e.target) && e.target !== btn) openMenu(false);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !menu.hidden) openMenu(false);
  });

  buildPicker();

  // The book is made on the server and takes a few seconds; say so.
  var book = document.getElementById("export-book");
  if (book) book.addEventListener("click", function () {
    var label = book.querySelector(".export-book-label");
    var was = label.textContent;
    book.classList.add("is-busy");
    label.textContent = "Kitob tayyorlanmoqda…";
    setTimeout(function () { book.classList.remove("is-busy"); label.textContent = was; }, 8000);
  });

  menu.querySelectorAll("[data-export]").forEach(function (b) {
    b.addEventListener("click", function () { run(b.dataset.export); });
  });

  if (/[?&]eksport=/.test(location.search)) openMenu(true);

  window.ShajaraExport = { build: buildSvg, run: run, themes: THEME_ORDER, papers: Object.keys(PAPERS) };
})();
