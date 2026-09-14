/* Download the tree as a picture.

   The picture is redrawn from the live board (window.ShajaraBoard), so it
   shows the arrangement the reader made. It is a poster: a title band, the
   tree, and a footer with the compiler, the date and a QR check code the
   server issues for every copy.

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

  var SERIF = "'Palatino Linotype', 'Book Antiqua', Palatino, Georgia, 'Times New Roman', serif";
  var C = { paper: "#fbf7ec", ink: "#2b2118", muted: "#7a6a55", gold: "#a47b32", goldSoft: "#d9c49a",
            wine: "#6b2a22", card: "#fffdf8", rose: "#b56f7c" };
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

  // ------------------------------------------------------------- menu --
  function openMenu(open) {
    menu.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
    if (open) setStatus("");
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

  // ---------------------------------------------------------- drawing --
  function years(card) {
    var b = (card.year || "").replace(/^~/, "taxm. ");
    var d = (card.death || "").replace(/^~/, "taxm. ");
    if (b && d) return b + " – " + d;
    if (b) return b;
    if (d) return "v. " + d;
    return "";
  }

  function buildSvg(snap, meta) {
    var cards = snap.cards;
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    cards.forEach(function (c) {
      minX = Math.min(minX, c.x); minY = Math.min(minY, c.y);
      maxX = Math.max(maxX, c.x + c.w); maxY = Math.max(maxY, c.y + c.h);
    });
    if (!cards.length) { minX = minY = 0; maxX = maxY = 200; }
    var treeW = maxX - minX, treeH = maxY - minY;
    var PAD = 70;
    var W = Math.max(Math.round(treeW + PAD * 2), 1000);
    // Title and footer grow with a wide tree so they stay in proportion.
    var k = Math.min(3, Math.max(1, W / 1500));
    var FOOT = Math.round(150 * k);
    var cx = W / 2;
    var titleSize = Math.max(22 * k, Math.min(46 * k, (W - 240) / Math.max(8, meta.title.length * 0.56)));
    var oy2 = 138 * k + titleSize;
    var HEAD = Math.round(oy2 + 50 * k);
    var H = Math.round(HEAD + treeH + PAD * 1.4 + FOOT);
    var ox = (W - treeW) / 2 - minX, oy = HEAD + PAD * 0.4 - minY;

    var out = [];
    out.push('<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + " " + H + '">');
    out.push("<title>" + esc(meta.title) + "</title>");
    out.push('<rect width="100%" height="100%" fill="' + C.paper + '"/>');
    out.push('<rect x="22" y="22" width="' + (W - 44) + '" height="' + (H - 44) + '" fill="none" stroke="' + C.gold + '" stroke-width="2.4"/>');
    out.push('<rect x="31" y="31" width="' + (W - 62) + '" height="' + (H - 62) + '" fill="none" stroke="' + C.gold + '" stroke-width="0.9"/>');
    [[22, 22], [W - 22, 22], [22, H - 22], [W - 22, H - 22]].forEach(function (p) {
      out.push('<path d="M' + p[0] + " " + (p[1] - 9) + " l9 9 l-9 9 l-9 -9z\" fill=\"" + C.gold + '"/>');
    });

    // title band
    out.push('<text x="' + cx + '" y="' + (78 * k) + '" text-anchor="middle" font-family="' + SERIF + '" font-size="' + (15 * k) + '" font-weight="700" letter-spacing="' + (3 * k) + '" fill="' + C.gold + '">' + esc(meta.kind) + "</text>");
    out.push('<text x="' + cx + '" y="' + (86 * k + titleSize) + '" text-anchor="middle" font-family="' + SERIF + '" font-size="' + titleSize.toFixed(1) + '" font-weight="700" fill="' + C.wine + '">' + esc(meta.title) + "</text>");
    var sub = meta.subtitle || meta.people + " shaxs · " + meta.generations + " avlod";
    out.push('<text x="' + cx + '" y="' + (118 * k + titleSize) + '" text-anchor="middle" font-family="' + SERIF + '" font-size="' + (17 * k) + '" font-style="italic" fill="' + C.muted + '">' + esc(sub) + "</text>");
    var r = 120 * k, d = 6 * k;
    out.push('<path d="M' + (cx - r) + " " + oy2 + " H" + (cx - 2 * d) + " M" + (cx + 2 * d) + " " + oy2 + " H" + (cx + r) + '" stroke="' + C.gold + '" stroke-width="' + (1.2 * k) + '"/>');
    out.push('<path d="M' + cx + " " + (oy2 - d) + " l" + d + " " + d + " l" + (-d) + " " + d + " l" + (-d) + " " + (-d) + 'z" fill="' + C.gold + '"/>');

    // connectors, restyled for paper
    out.push('<g transform="translate(' + ox.toFixed(1) + " " + oy.toFixed(1) + ')">');
    var doc = new DOMParser().parseFromString('<svg xmlns="http://www.w3.org/2000/svg">' + snap.lines + "</svg>", "image/svg+xml");
    var root = doc.documentElement;
    Array.prototype.forEach.call(root.querySelectorAll(".branch-line"), function (p) {
      out.push('<path d="' + esc(p.getAttribute("d")) + '" fill="none" stroke="' + C.gold + '" stroke-width="2.2" stroke-linecap="round"/>');
    });
    Array.prototype.forEach.call(root.querySelectorAll(".branch-tip"), function (c) {
      out.push('<circle cx="' + c.getAttribute("cx") + '" cy="' + c.getAttribute("cy") + '" r="2.6" fill="' + C.gold + '"/>');
    });
    Array.prototype.forEach.call(root.querySelectorAll(".marriage-link"), function (l) {
      out.push('<line x1="' + l.getAttribute("x1") + '" y1="' + l.getAttribute("y1") + '" x2="' + l.getAttribute("x2") + '" y2="' + l.getAttribute("y2") + '" stroke="' + C.gold + '" stroke-width="2.2" stroke-linecap="round"/>');
    });
    Array.prototype.forEach.call(root.querySelectorAll(".marriage-knot"), function (g) {
      Array.prototype.forEach.call(g.querySelectorAll("circle"), function (c) {
        var bg = c.getAttribute("class").indexOf("knot-bg") !== -1;
        out.push('<circle cx="' + c.getAttribute("cx") + '" cy="' + c.getAttribute("cy") + '" r="' + c.getAttribute("r") + '" ' +
          (bg ? 'fill="' + C.paper + '"' : 'fill="none" stroke="' + C.gold + '" stroke-width="1.6"') + "/>");
      });
    });

    // cards
    cards.forEach(function (c) {
      var fill = c.root ? C.wine : C.card;
      var stroke = c.root ? C.gold : c.gender === "ayol" ? C.rose : C.gold;
      var nameColor = c.root ? "#fbf1dc" : C.ink;
      var yearColor = c.root ? "#e7d2a8" : C.muted;
      var y = years(c);
      out.push('<rect x="' + c.x.toFixed(1) + '" y="' + c.y.toFixed(1) + '" width="' + c.w.toFixed(1) + '" height="' + c.h.toFixed(1) +
        '" rx="12" fill="' + fill + '" stroke="' + stroke + '" stroke-width="' + (c.root ? 2.4 : 1.6) + '"/>');
      var mid = c.x + c.w / 2, midY = c.y + c.h / 2;
      var size = c.root ? 17 : 14.5;
      out.push('<text x="' + mid.toFixed(1) + '" y="' + (midY + (y ? -1 : 5)).toFixed(1) + '" text-anchor="middle" font-family="' + SERIF +
        '" font-size="' + size + '" font-weight="700" fill="' + nameColor + '">' + esc(c.name) + "</text>");
      if (y) {
        out.push('<text x="' + mid.toFixed(1) + '" y="' + (midY + 14).toFixed(1) + '" text-anchor="middle" font-family="' + SERIF +
          '" font-size="10.5" fill="' + yearColor + '">' + esc(y) + "</text>");
      }
    });
    out.push("</g>");

    // footer: who, when, and the check mark
    var fy = H - FOOT + 10 * k;
    out.push('<line x1="' + 70 * k + '" y1="' + fy + '" x2="' + (W - 70 * k) + '" y2="' + fy + '" stroke="' + C.goldSoft + '" stroke-width="' + k + '"/>');
    var left = 70 * k, qrSize = 96 * k;
    function footText(x, y, size, anchor, color, body, bold) {
      out.push('<text x="' + x + '" y="' + y + '"' + (anchor ? ' text-anchor="' + anchor + '"' : "") + ' font-family="' + SERIF +
        '" font-size="' + (size * k).toFixed(1) + '"' + (bold ? ' font-weight="700"' : "") + ' fill="' + color + '">' + body + "</text>");
    }
    footText(left, fy + 40 * k, 15, "", C.ink, '<tspan font-weight="700">Tuzuvchi:</tspan> ' + esc(meta.compiler));
    footText(left, fy + 64 * k, 14, "", C.muted, esc(meta.date) + " · " + meta.people + " shaxs · " + meta.generations + " avlod");
    footText(left, fy + 88 * k, 13, "", C.muted, "e-Shajara · e-shajara.uz");
    var qx = W - 70 * k - qrSize;
    footText(qx - 16 * k, fy + 48 * k, 15, "end", C.ink, "Tekshirish kodi: " + esc(meta.code), true);
    footText(qx - 16 * k, fy + 72 * k, 12.5, "end", C.muted, esc(meta.verifyUrl));
    if (meta.qr) {
      out.push('<g transform="translate(' + qx + " " + (fy + 18 * k) + ") scale(" + (qrSize / 120) + ')">' + meta.qr + "</g>");
    }
    out.push("</svg>");
    return { markup: out.join(""), width: W, height: H };
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

  function rasterScale(w, h) {
    // Phones cap canvases around 16 megapixels; desktops go much further.
    var budget = (navigator.maxTouchPoints || 0) > 0 ? 16e6 : 90e6;
    var s = Math.min(3, Math.sqrt(budget / (w * h)), 16000 / w, 16000 / h);
    return Math.max(0.5, s);
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
    ctx.fillStyle = C.paper;
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
    post(shell.dataset.recordUrl, JSON.stringify({ kind: kind }), true)
      .then(function (rec) {
        var snap = window.ShajaraBoard.snapshot();
        var poster = buildSvg(snap, {
          title: name, kind: rec.kind_label, subtitle: rec.subtitle, compiler: rec.compiler, date: rec.date,
          people: rec.people, generations: rec.generations, code: rec.code, verifyUrl: rec.verify_url, qr: rec.qr_svg
        });
        var file = slug(name) + "-shajara";
        return loadImage(poster.markup).then(function (loaded) {
          var job;
          if (kind === "svg") {
            download(new Blob([poster.markup], { type: "image/svg+xml;charset=utf-8" }), file + ".svg");
            job = Promise.resolve();
          } else {
            var s = rasterScale(poster.width, poster.height);
            var canvas = document.createElement("canvas");
            canvas.width = Math.round(poster.width * s);
            canvas.height = Math.round(poster.height * s);
            var ctx = canvas.getContext("2d");
            ctx.scale(s, s);
            ctx.drawImage(loaded.img, 0, 0, poster.width, poster.height);
            job = canvasBlob(canvas).then(function (blob) { download(blob, file + ".png"); });
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

  menu.querySelectorAll("[data-export]").forEach(function (b) {
    b.addEventListener("click", function () { run(b.dataset.export); });
  });

  if (/[?&]eksport=/.test(location.search)) openMenu(true);

  window.ShajaraExport = { build: buildSvg, run: run };
})();
