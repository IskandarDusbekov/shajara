/* Historical map: view and edit.

   The image, a routes layer (SVG) and a markers layer sit in one canvas that
   tree-map.js pans and zooms. Markers and route arrows are counter-scaled so
   they keep their on-screen size at every zoom.

   Timeline: dragging the year (or pressing play) shows only what had
   happened by then — places appear in their year and each route is drawn up
   to the last stop it had reached, so a campaign unrolls year by year.

   Editing (owner only):
     Ko'rish     tap a place for details; drag a place to move it
     Joy qo'shish tap the map where the place is, fill in name/year/type
     Yo'nalish   pick or start a route, then tap places in order */
(function () {
  "use strict";

  var dataEl = document.getElementById("hm-data");
  var shell = document.getElementById("hm-shell");
  if (!dataEl || !shell || !window.TreeMap) return;

  var DATA = JSON.parse(dataEl.textContent);
  var W = DATA.map.width, H = DATA.map.height;
  var canEdit = !!DATA.canEdit;
  var viewport = document.getElementById("hm-viewport");
  var canvas = document.getElementById("hm-canvas");
  var svg = document.getElementById("hm-routes");
  var markersEl = document.getElementById("hm-markers");
  var hint = document.getElementById("hm-hint");
  var detail = document.getElementById("hm-detail");
  var SVGNS = "http://www.w3.org/2000/svg";

  var KIND = {}; DATA.kinds.forEach(function (k) { KIND[k[0]] = k[1]; });
  var ROUTE_KIND = {}; DATA.routeKinds.forEach(function (k) { ROUTE_KIND[k[0]] = k[1]; });
  var COLORS = ["#b3261e", "#6b2a22", "#c26a1b", "#a47b32", "#2d7a4f", "#2f5ea8", "#3b5b8c", "#7a4fa0"];
  var ICON = {
    shahar: '<circle cx="12" cy="12" r="4.2"/>',
    poytaxt: '<path d="M4 17h16l-1.5-9-4 4L12 6l-2.5 6-4-4z"/>',
    jang: '<path d="M5 5l14 14M19 5 5 19M4 8l4-4M16 20l4-4M20 8l-4-4M8 20l-4-4"/>',
    voqea: '<path d="M6 21V4M6 4h11l-2 4 2 4H6"/>',
    qarorgoh: '<path d="M3 19 12 5l9 14zM12 5v14M9 19l3-5 3 5"/>',
    tugilgan: '<path d="M12 3l2.4 5 5.6.8-4 4 1 5.6L12 16l-5 2.4 1-5.6-4-4 5.6-.8z"/>',
    vafot: '<path d="M8 21h8M10 21V9a2 2 0 0 1 4 0v12M7 9h10"/>',
    yodgorlik: '<path d="M4 20h16M6 20v-7M18 20v-7M4 13h16M6 13c0-4 3-7 6-8 3 1 6 4 6 8"/>'
  };

  var places = {};
  DATA.places.forEach(function (p) { places[p.id] = p; });
  var routes = DATA.routes.slice();
  var hidden = {};
  var mode = "view";
  var selected = null;
  var focusRoute = null;
  var draftRoute = null;
  var draftPlace = null;
  var year = null;
  var inv = 1;
  var map;

  // ------------------------------------------------------------ helpers --
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function yearText(y) {
    return y == null || y === "" ? "" : (y < 0 ? "mil. av. " + (-y) : String(y));
  }
  function span(a, b) {
    if (a == null && b == null) return "";
    if (a != null && b != null && b !== a) return yearText(a) + "–" + yearText(b);
    return yearText(a != null ? a : b);
  }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function toast(text, bad) {
    var t = document.createElement("div");
    t.className = "hm-toast" + (bad ? " is-bad" : " is-good");
    t.textContent = text;
    shell.appendChild(t);
    setTimeout(function () { t.remove(); }, 3600);
  }
  function api(url, body) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": shell.dataset.csrf },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.error || "Saqlanmadi.");
        return d;
      });
    });
  }
  function stopYear(stop) {
    if (stop.year != null) return stop.year;
    var p = places[stop.place];
    return p ? p.year : null;
  }
  function placeVisible(p) {
    return year == null || p.year == null || p.year <= year;
  }
  function routeYears(r) {
    var ys = r.stops.map(stopYear).filter(function (y) { return y != null; });
    return { from: r.year_start != null ? r.year_start : (ys.length ? Math.min.apply(null, ys) : null),
             to: r.year_end != null ? r.year_end : (ys.length ? Math.max.apply(null, ys) : null) };
  }

  // ------------------------------------------------------------ markers --
  function renderMarkers() {
    var list = Object.keys(places).map(function (id) { return places[id]; });
    if (draftPlace) list.push(draftPlace);
    list.sort(function (a, b) { return (a.year == null ? -1e9 : a.year) - (b.year == null ? -1e9 : b.year); });
    var stopIndex = {};
    if (draftRoute) draftRoute.stops.forEach(function (s, i) { (stopIndex[s.place] = stopIndex[s.place] || []).push(i + 1); });
    var html = "";
    list.forEach(function (p) {
      var cls = "hm-marker kind-" + p.kind;
      if (p === draftPlace) cls += " is-draft";
      if (selected === p.id) cls += " is-selected";
      if (!placeVisible(p)) cls += " is-future";
      if (stopIndex[p.id]) cls += " is-stop";
      html += '<button type="button" class="' + cls + '" data-kind="' + p.kind + '" data-year="' + (p.year == null ? "" : p.year) + '" data-id="' + (p.id || "draft") + '" style="left:' +
        (p.x * W).toFixed(1) + "px;top:" + (p.y * H).toFixed(1) + 'px" aria-label="' + esc(p.name || "Yangi joy") + '">' +
        '<span class="hm-dot"><svg viewBox="0 0 24 24">' + (ICON[p.kind] || ICON.shahar) + "</svg></span>" +
        (stopIndex[p.id] ? '<span class="hm-stopno">' + stopIndex[p.id].join(",") + "</span>" : "") +
        '<span class="hm-label"><b>' + esc(p.name || "Yangi joy") + "</b>" +
        (p.year != null ? "<small>" + esc(span(p.year, p.year_end)) + "</small>" : "") + "</span></button>";
    });
    markersEl.innerHTML = html;
    declutter();
  }

  /* Where labels would overlap, keep the more important one (the selected
     place, capitals and battles first) and reduce the others to their dot;
     hovering a dot still shows its name. Re-run as the zoom changes. */
  var PRIORITY = { poytaxt: 0, jang: 1, tugilgan: 1, vafot: 1, voqea: 2, qarorgoh: 3, yodgorlik: 3, shahar: 3 };
  function declutter() {
    var ms = Array.prototype.slice.call(markersEl.querySelectorAll(".hm-marker:not(.is-future)"));
    ms.forEach(function (m) { m.classList.remove("is-crowded"); });
    ms.sort(function (a, b) {
      var sa = a.classList.contains("is-selected") || a.classList.contains("is-draft") ? -1 : (a.dataset.kind in PRIORITY ? PRIORITY[a.dataset.kind] : 3);
      var sb = b.classList.contains("is-selected") || b.classList.contains("is-draft") ? -1 : (b.dataset.kind in PRIORITY ? PRIORITY[b.dataset.kind] : 3);
      return sa - sb;
    });
    var boxes = ms.map(function (m) {
      return { m: m, label: m.querySelector(".hm-label").getBoundingClientRect(), dot: m.querySelector(".hm-dot").getBoundingClientRect() };
    });
    var taken = boxes.map(function (b) { return b.dot; });
    var kept = [];
    function hits(r, list) {
      return list.some(function (t) { return !(r.right <= t.left + 2 || r.left >= t.right - 2 || r.bottom <= t.top + 2 || r.top >= t.bottom - 2); });
    }
    boxes.forEach(function (b) {
      var others = taken.filter(function (t) { return t !== b.dot; });
      if (hits(b.label, kept) || hits(b.label, others)) b.m.classList.add("is-crowded");
      else kept.push(b.label);
    });
  }

  // ------------------------------------------------------------- routes --
  function controls(pts) {
    var segs = [];
    for (var i = 0; i < pts.length - 1; i++) {
      var p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
      // a gentle bow even for two points, so a route never looks ruled
      var c1 = { x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6 };
      var c2 = { x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6 };
      if (p0 === p1 && p3 === p2) {
        var dx = p2.x - p1.x, dy = p2.y - p1.y;
        c1 = { x: p1.x + dx / 3 - dy * 0.12, y: p1.y + dy / 3 + dx * 0.12 };
        c2 = { x: p1.x + dx * 2 / 3 - dy * 0.12, y: p1.y + dy * 2 / 3 + dx * 0.12 };
      }
      segs.push([p1, c1, c2, p2]);
    }
    return segs;
  }
  function bez(s, t) {
    var u = 1 - t;
    return {
      x: u * u * u * s[0].x + 3 * u * u * t * s[1].x + 3 * u * t * t * s[2].x + t * t * t * s[3].x,
      y: u * u * u * s[0].y + 3 * u * u * t * s[1].y + 3 * u * t * t * s[2].y + t * t * t * s[3].y
    };
  }
  function el(name, attrs) {
    var n = document.createElementNS(SVGNS, name);
    Object.keys(attrs).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }

  function renderRoutes() {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var list = routes.filter(function (r) { return !draftRoute || r.id !== draftRoute.id; });
    if (draftRoute) list = list.concat([draftRoute]);
    list.forEach(function (r) {
      if (hidden[r.id] && r !== draftRoute) return;
      var pts = [];
      for (var i = 0; i < r.stops.length; i++) {
        var s = r.stops[i], p = places[s.place];
        if (!p) continue;
        var y = stopYear(s);
        if (year != null && y != null && y > year && r !== draftRoute) break;
        pts.push({ x: p.x * W, y: p.y * H });
      }
      if (pts.length < 2) return;
      var segs = controls(pts);
      var d = "M" + pts[0].x.toFixed(1) + " " + pts[0].y.toFixed(1);
      segs.forEach(function (s) {
        d += " C" + s[1].x.toFixed(1) + " " + s[1].y.toFixed(1) + " " + s[2].x.toFixed(1) + " " + s[2].y.toFixed(1) +
          " " + s[3].x.toFixed(1) + " " + s[3].y.toFixed(1);
      });
      var dim = focusRoute != null && focusRoute !== r.id && r !== draftRoute;
      var g = el("g", { "class": "hm-route kind-" + r.kind + (dim ? " is-dim" : "") + (focusRoute === r.id ? " is-focus" : ""), "data-id": r.id || "draft" });
      var w = (focusRoute === r.id || r === draftRoute ? 6 : 4.2) * inv;
      var dash = { savdo: [12, 8], kochish: [2, 9], elchilik: [16, 6, 3, 6], sayohat: [6, 7] }[r.kind];
      g.appendChild(el("path", { d: d, fill: "none", stroke: "#fbf3df", "stroke-width": w + 5 * inv, "stroke-linecap": "round", opacity: 0.85 }));
      var main = el("path", { d: d, fill: "none", stroke: r.color, "stroke-width": w, "stroke-linecap": "round", "stroke-linejoin": "round" });
      if (dash) main.setAttribute("stroke-dasharray", dash.map(function (v) { return v * inv; }).join(" "));
      g.appendChild(main);
      if (r.kind === "harbiy") {
        g.appendChild(el("path", { d: d, fill: "none", stroke: "#fff6e2", "stroke-width": w * 0.35, "stroke-linecap": "round",
          "stroke-dasharray": (10 * inv) + " " + (22 * inv), "class": "hm-flow", style: "--dash:" + (32 * inv) + "px" }));
      }
      segs.forEach(function (s) {
        var a = bez(s, 0.52), b = bez(s, 0.56);
        var ang = Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI;
        var head = el("g", { transform: "translate(" + a.x.toFixed(1) + " " + a.y.toFixed(1) + ") rotate(" + ang.toFixed(1) + ") scale(" + inv + ")" });
        head.appendChild(el("path", { d: "M-9 -7 L9 0 L-9 7 L-5 0 Z", fill: r.color, stroke: "#fbf3df", "stroke-width": 1.5 }));
        g.appendChild(head);
      });
      svg.appendChild(g);
    });
  }

  var pending = false;
  function render() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(function () {
      pending = false;
      renderRoutes();
      renderMarkers();
      renderLists();
    });
  }

  // ----------------------------------------------------------- the map --
  var zoomLabel = document.getElementById("hm-zoom");
  map = window.TreeMap.create(viewport, canvas, {
    maxScale: 4,
    onChange: function (scale) {
      inv = 1 / scale;
      canvas.style.setProperty("--inv", inv.toFixed(4));
      if (zoomLabel) zoomLabel.textContent = Math.round(scale * 100) + "%";
      if (!pending) {
        pending = true;
        requestAnimationFrame(function () { pending = false; renderRoutes(); declutter(); });
      }
    },
    dragTarget: function (e) {
      if (!canEdit || mode === "route" || draftRoute) return null;
      var m = e.target.closest && e.target.closest(".hm-marker");
      return m && m.dataset.id !== "draft" ? m : null;
    },
    onDragMove: function (node, dx, dy) {
      var p = places[node.dataset.id];
      if (!p) return;
      p.x = clamp(p.x + dx / W, 0, 1);
      p.y = clamp(p.y + dy / H, 0, 1);
      node.style.left = (p.x * W).toFixed(1) + "px";
      node.style.top = (p.y * H).toFixed(1) + "px";
      node.classList.add("is-dragging");
      if (!pending) {
        pending = true;
        requestAnimationFrame(function () { pending = false; renderRoutes(); });
      }
    },
    onDragEnd: function (node, moved) {
      node.classList.remove("is-dragging");
      var p = places[node.dataset.id];
      if (!moved || !p) return;
      api(DATA.api.place, { id: p.id, x: p.x, y: p.y })
        .then(function () { toast("«" + p.name + "» ko'chirildi"); })
        .catch(function (err) { toast(err.message, true); });
    }
  });

  document.querySelectorAll("[data-hm]").forEach(function (b) {
    b.addEventListener("click", function () {
      var a = b.dataset.hm;
      if (a === "zoom-in") map.zoomIn();
      else if (a === "zoom-out") map.zoomOut();
      else if (a === "fit") map.fit();
    });
  });

  function panelOffset() {
    var panel = document.getElementById("hm-panel");
    return window.innerWidth >= 900 && !shell.classList.contains("panel-closed") ? -panel.offsetWidth / 2 : 0;
  }
  function centreOnPlace(p) {
    map.centreOnPoint(p.x * W, p.y * H, Math.max(map.getScale(), 0.7), panelOffset());
  }
  function focusOnRoute(r) {
    var pts = r.stops.map(function (s) { return places[s.place]; }).filter(Boolean);
    if (!pts.length) return;
    var xs = pts.map(function (p) { return p.x * W; }), ys = pts.map(function (p) { return p.y * H; });
    var minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
    var minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
    var vr = viewport.getBoundingClientRect();
    var room = vr.width - (window.innerWidth >= 900 && !shell.classList.contains("panel-closed") ? 380 : 0);
    var s = Math.min((room - 120) / Math.max(200, maxX - minX), (vr.height - 220) / Math.max(200, maxY - minY));
    map.centreOnPoint((minX + maxX) / 2, (minY + maxY) / 2, clamp(s, 0.15, 2), panelOffset());
  }

  // ------------------------------------------------------------ timeline --
  var slider = document.getElementById("hm-year");
  var allBox = document.getElementById("hm-all");
  var yearNow = document.getElementById("hm-year-now");
  var playBtn = document.getElementById("hm-play");
  var timer = null;
  var minYear = null, maxYear = null;

  function collectYears() {
    var ys = [];
    Object.keys(places).forEach(function (id) {
      var p = places[id];
      if (p.year != null) ys.push(p.year);
      if (p.year_end != null) ys.push(p.year_end);
    });
    routes.forEach(function (r) {
      r.stops.forEach(function (s) { if (s.year != null) ys.push(s.year); });
      if (r.year_start != null) ys.push(r.year_start);
      if (r.year_end != null) ys.push(r.year_end);
    });
    if (!ys.length) {
      document.getElementById("hm-timeline").hidden = true;
      return;
    }
    document.getElementById("hm-timeline").hidden = false;
    minYear = Math.min.apply(null, ys);
    maxYear = Math.max.apply(null, ys);
    if (minYear === maxYear) maxYear = minYear + 1;
    slider.min = minYear;
    slider.max = maxYear;
    document.getElementById("hm-year-min").textContent = yearText(minYear);
    document.getElementById("hm-year-max").textContent = yearText(maxYear);
    if (year == null) slider.value = maxYear;
  }

  function setYear(y) {
    year = y;
    allBox.checked = y == null;
    if (y != null) slider.value = y;
    yearNow.textContent = y == null ? "Barcha yillar" : yearText(y) + (y >= 0 ? "-yil" : "");
    render();
  }
  slider.addEventListener("input", function () { stop(); setYear(parseInt(slider.value, 10)); });
  allBox.addEventListener("change", function () { stop(); setYear(allBox.checked ? null : parseInt(slider.value, 10)); });

  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
    playBtn.classList.remove("is-playing");
    playBtn.setAttribute("aria-label", "Ijro etish");
  }
  playBtn.addEventListener("click", function () {
    if (timer) { stop(); return; }
    if (minYear == null) return;
    var y = year == null || year >= maxYear ? minYear : year;
    var step = Math.max(1, Math.round((maxYear - minYear) / 160));
    playBtn.classList.add("is-playing");
    playBtn.setAttribute("aria-label", "To'xtatish");
    setYear(y);
    timer = setInterval(function () {
      y = Math.min(maxYear, y + step);
      setYear(y);
      if (y >= maxYear) stop();
    }, 90);
  });

  // --------------------------------------------------------------- panel --
  var panelToggle = document.getElementById("hm-panel-toggle");
  if (window.innerWidth < 900) shell.classList.add("panel-closed");
  function syncPanelToggle() {
    panelToggle.setAttribute("aria-expanded", String(!shell.classList.contains("panel-closed")));
  }
  panelToggle.addEventListener("click", function () {
    shell.classList.toggle("panel-closed");
    syncPanelToggle();
  });
  syncPanelToggle();
  function openPanel() {
    shell.classList.remove("panel-closed");
    syncPanelToggle();
  }
  ["pointerdown", "wheel"].forEach(function (t) {
    document.getElementById("hm-panel").addEventListener(t, function (e) { e.stopPropagation(); }, { passive: true });
  });

  var currentTab = "places";
  function showPane(name) {
    document.querySelectorAll("#hm-panel-body [data-pane]").forEach(function (p) { p.hidden = p.dataset.pane !== name; });
    document.querySelectorAll(".hm-tab").forEach(function (t) { t.classList.toggle("is-on", t.dataset.tab === name); });
    if (name !== "detail") currentTab = name;
  }
  document.querySelectorAll(".hm-tab").forEach(function (t) {
    t.addEventListener("click", function () {
      if (draftRoute || draftPlace) return;
      selected = null;
      focusRoute = t.dataset.tab === "routes" ? focusRoute : null;
      showPane(t.dataset.tab);
      render();
    });
  });

  var filter = document.getElementById("hm-filter");
  filter.addEventListener("input", renderLists);

  function norm(s) { return String(s || "").toLowerCase().replace(/[ʻʼ‘’'`]/g, ""); }

  function renderLists() {
    var ps = Object.keys(places).map(function (id) { return places[id]; });
    document.getElementById("hm-count-places").textContent = ps.length;
    document.getElementById("hm-count-routes").textContent = routes.length;
    var q = norm(filter.value);
    ps.sort(function (a, b) {
      return (a.year == null ? 1e9 : a.year) - (b.year == null ? 1e9 : b.year) || a.name.localeCompare(b.name);
    });
    document.getElementById("hm-place-list").innerHTML = ps.filter(function (p) { return !q || norm(p.name).indexOf(q) !== -1; })
      .map(function (p) {
        return '<li><button type="button" class="hm-item' + (placeVisible(p) ? "" : " is-future") + (selected === p.id ? " is-on" : "") +
          '" data-place="' + p.id + '"><span class="hm-item-dot kind-' + p.kind + '"><svg viewBox="0 0 24 24">' + (ICON[p.kind] || "") +
          '</svg></span><span class="hm-item-main"><b>' + esc(p.name) + "</b><small>" + esc(KIND[p.kind] || "") + "</small></span>" +
          '<span class="hm-item-year">' + esc(span(p.year, p.year_end)) + "</span></button></li>";
      }).join("") || '<li class="hm-empty">' + (q ? "Topilmadi" : canEdit ? "Hali joy yo'q. «Joy qo'shish»ni bosing va xaritada nuqtani tanlang." : "Hali joy belgilanmagan.") + "</li>";

    document.getElementById("hm-route-list").innerHTML = routes.map(function (r) {
      var ys = routeYears(r);
      return '<li class="hm-route-row' + (focusRoute === r.id ? " is-on" : "") + '"><button type="button" class="hm-item" data-route="' + r.id + '">' +
        '<span class="hm-swatch kind-' + r.kind + '" style="--c:' + esc(r.color) + '"></span><span class="hm-item-main"><b>' + esc(r.name) +
        "</b><small>" + esc(ROUTE_KIND[r.kind] || "") + " · " + r.stops.length + " bekat</small></span>" +
        '<span class="hm-item-year">' + esc(span(ys.from, ys.to)) + "</span></button>" +
        '<button type="button" class="hm-eye' + (hidden[r.id] ? " is-off" : "") + '" data-eye="' + r.id + '" aria-label="Ko\'rsatish/yashirish">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>' +
        (hidden[r.id] ? '<path d="M4 4l16 16"/>' : "") + "</svg></button></li>";
    }).join("") || '<li class="hm-empty">' + (canEdit ? "Hali yo'nalish yo'q." : "Yo'nalishlar chizilmagan.") + "</li>";
  }

  document.getElementById("hm-place-list").addEventListener("click", function (e) {
    var b = e.target.closest("[data-place]");
    if (b) selectPlace(+b.dataset.place, true);
  });
  document.getElementById("hm-route-list").addEventListener("click", function (e) {
    var eye = e.target.closest("[data-eye]");
    if (eye) {
      hidden[eye.dataset.eye] = !hidden[eye.dataset.eye];
      render();
      return;
    }
    var b = e.target.closest("[data-route]");
    if (!b) return;
    var r = routes.filter(function (x) { return x.id === +b.dataset.route; })[0];
    if (!r) return;
    showRoute(r);
  });

  // ------------------------------------------------------------ details --
  function personLink(p) {
    if (!p.person || !shell.dataset.treeKey) return "";
    return '<a class="hm-person" href="/shajara/' + esc(shell.dataset.treeKey) + "/shaxs/" + p.person + '/">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/></svg>' +
      esc(p.person_name) + " — shajarada</a>";
  }

  function selectPlace(id, centre) {
    var p = places[id];
    if (!p) return;
    selected = id;
    focusRoute = null;
    var through = routes.filter(function (r) { return r.stops.some(function (s) { return s.place === id; }); });
    detail.innerHTML =
      '<button type="button" class="hm-back" data-act="back">← Ro\'yxat</button>' +
      '<p class="hm-detail-kind kind-' + p.kind + '"><span class="hm-item-dot kind-' + p.kind + '"><svg viewBox="0 0 24 24">' + (ICON[p.kind] || "") + "</svg></span>" + esc(KIND[p.kind] || "") + "</p>" +
      '<h2 class="hm-detail-name">' + esc(p.name) + "</h2>" +
      (p.year != null ? '<p class="hm-detail-year">' + esc(span(p.year, p.year_end)) + "</p>" : "") +
      (p.description ? '<p class="hm-detail-text">' + esc(p.description).replace(/\n/g, "<br>") + "</p>" : "") +
      personLink(p) +
      (through.length ? '<p class="pf-label" style="margin-top:14px;">Shu joydan o\'tgan yo\'nalishlar</p><ul class="hm-chips">' +
        through.map(function (r) { return '<li><button type="button" data-route-go="' + r.id + '"><i style="background:' + esc(r.color) + '"></i>' + esc(r.name) + "</button></li>"; }).join("") + "</ul>" : "") +
      (canEdit ? '<div class="pf-actions"><button type="button" class="pf-btn pf-btn-sm" data-act="edit">Tahrirlash</button>' +
        '<button type="button" class="pf-btn pf-btn-sm pf-btn-danger" data-act="delete">O\'chirish</button></div>' +
        '<p class="pf-help">Joyni ko\'chirish uchun belgini xaritada torting (telefonda — bosib turib).</p>' : "");
    showPane("detail");
    openPanel();
    if (centre) centreOnPlace(p);
    render();
  }

  detail.addEventListener("click", function (e) {
    var go = e.target.closest("[data-route-go]");
    if (go) {
      var r = routes.filter(function (x) { return x.id === +go.dataset.routeGo; })[0];
      if (r) showRoute(r);
      return;
    }
    var act = e.target.closest("[data-act]");
    if (!act) return;
    var a = act.dataset.act;
    if (a === "back") { closeDetail(); }
    else if (a === "edit") { placeForm(places[selected]); }
    else if (a === "delete") { deletePlace(places[selected]); }
  });

  function closeDetail() {
    selected = null;
    focusRoute = null;
    draftPlace = null;
    draftRoute = null;
    showPane(currentTab);
    render();
  }

  function showRoute(r) {
    focusRoute = r.id;
    selected = null;
    hidden[r.id] = false;
    var ys = routeYears(r);
    var stopsHtml = r.stops.map(function (s, i) {
      var p = places[s.place];
      return p ? '<li><span class="hm-stop-no" style="background:' + esc(r.color) + '">' + (i + 1) + '</span><button type="button" data-place-go="' + p.id + '">' + esc(p.name) +
        "</button><small>" + esc(yearText(stopYear(s))) + "</small></li>" : "";
    }).join("");
    detail.innerHTML =
      '<button type="button" class="hm-back" data-act="back">← Ro\'yxat</button>' +
      '<p class="hm-detail-kind"><span class="hm-swatch kind-' + r.kind + '" style="--c:' + esc(r.color) + '"></span>' + esc(ROUTE_KIND[r.kind] || "") + "</p>" +
      '<h2 class="hm-detail-name">' + esc(r.name) + "</h2>" +
      (ys.from != null ? '<p class="hm-detail-year">' + esc(span(ys.from, ys.to)) + "</p>" : "") +
      (r.description ? '<p class="hm-detail-text">' + esc(r.description) + "</p>" : "") +
      '<ol class="hm-stops">' + stopsHtml + "</ol>" +
      '<div class="pf-actions"><button type="button" class="pf-btn pf-btn-sm pf-btn-edu" data-act="replay">▶ Yurishni ko\'rsatish</button>' +
      (canEdit ? '<button type="button" class="pf-btn pf-btn-sm" data-act="edit-route">Tahrirlash</button>' : "") + "</div>";
    showPane("detail");
    openPanel();
    focusOnRoute(r);
    render();
  }

  detail.addEventListener("click", function (e) {
    var pg = e.target.closest("[data-place-go]");
    if (pg) { selectPlace(+pg.dataset.placeGo, true); return; }
    var act = e.target.closest("[data-act]");
    if (!act) return;
    var r = routes.filter(function (x) { return x.id === focusRoute; })[0];
    if (act.dataset.act === "replay" && r) {
      var ys = routeYears(r);
      if (ys.from == null) return;
      stop();
      var y = ys.from;
      setYear(y);
      playBtn.classList.add("is-playing");
      timer = setInterval(function () {
        y += 1;
        setYear(y);
        if (y >= ys.to) stop();
      }, Math.max(120, 2400 / Math.max(1, ys.to - ys.from)));
    } else if (act.dataset.act === "edit-route" && r) {
      routeForm(r);
    }
  });

  // -------------------------------------------------------- place form --
  function kindOptions(current) {
    return DATA.kinds.map(function (k) { return '<option value="' + k[0] + '"' + (k[0] === current ? " selected" : "") + ">" + esc(k[1]) + "</option>"; }).join("");
  }

  function placeForm(p) {
    var isNew = !p.id;
    var people = DATA.people || [];
    detail.innerHTML =
      '<button type="button" class="hm-back" data-form="cancel">← Bekor qilish</button>' +
      '<h2 class="hm-detail-name">' + (isNew ? "Yangi joy" : "Joyni tahrirlash") + "</h2>" +
      '<form class="hm-form" id="hm-place-form" novalidate>' +
      '<label class="pf-label">Nomi<span class="pf-req">*</span></label><input class="pf-input" name="name" maxlength="120" value="' + esc(p.name || "") + '" placeholder="Masalan: Anqara jangi" required>' +
      '<label class="pf-label">Turi</label><select class="pf-input" name="kind">' + kindOptions(p.kind || "shahar") + "</select>" +
      '<div class="pf-row"><div><label class="pf-label">Yil</label><input class="pf-input" name="year" inputmode="numeric" value="' + (p.year == null ? "" : p.year) + '" placeholder="1402"></div>' +
      '<div><label class="pf-label">Tugagan yil</label><input class="pf-input" name="year_end" inputmode="numeric" value="' + (p.year_end == null ? "" : p.year_end) + '" placeholder="ixtiyoriy"></div></div>' +
      '<p class="pf-help">Miloddan avvalgi yilni minus bilan yozing: −329 → <b>-329</b>.</p>' +
      '<label class="pf-label">Nima bo\'lgan</label><textarea class="pf-input" name="description" rows="4" placeholder="Voqea, uning ahamiyati, qatnashganlar…">' + esc(p.description || "") + "</textarea>" +
      (people.length ? '<label class="pf-label">Shajaradagi shaxs <small>ixtiyoriy</small></label><select class="pf-input" name="person"><option value="">— bog\'lanmagan —</option>' +
        people.map(function (x) { return '<option value="' + x.id + '"' + (x.id === p.person ? " selected" : "") + ">" + esc(x.name) + (x.years ? " (" + esc(x.years) + ")" : "") + "</option>"; }).join("") + "</select>" : "") +
      '<p class="pf-error" data-form-error hidden></p>' +
      '<div class="pf-actions"><button type="submit" class="pf-btn pf-btn-primary">Saqlash</button><button type="button" class="pf-btn" data-form="cancel">Bekor qilish</button></div>' +
      "</form>";
    showPane("detail");
    openPanel();
    var form = document.getElementById("hm-place-form");
    setTimeout(function () { form.name.focus(); }, 50);
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var body = {
        name: form.name.value, kind: form.kind.value, x: p.x, y: p.y,
        year: form.year.value.trim().replace("−", "-"), year_end: form.year_end.value.trim().replace("−", "-"),
        description: form.description.value
      };
      if (form.person) body.person = form.person.value || null;
      if (!isNew) body.id = p.id;
      var err = form.querySelector("[data-form-error]");
      api(DATA.api.place, body).then(function (d) {
        draftPlace = null;
        places[d.place.id] = d.place;
        collectYears();
        toast(isNew ? "Joy qo'shildi" : "Saqlandi");
        if (isNew && mode === "add") { /* stay in add mode for the next one */ }
        selectPlace(d.place.id, false);
      }).catch(function (ex) {
        err.textContent = ex.message;
        err.hidden = false;
      });
    });
    form.parentNode.querySelectorAll("[data-form=cancel]").forEach(function (b) {
      b.addEventListener("click", function () {
        if (isNew) { draftPlace = null; closeDetail(); } else { selectPlace(p.id, false); }
      });
    });
    render();
  }

  function deletePlace(p) {
    if (!p || !confirm("«" + p.name + "» o'chirilsinmi? U orqali o'tgan yo'nalishlardan ham olib tashlanadi.")) return;
    api(DATA.api.place, { id: p.id, delete: true }).then(function (d) {
      delete places[p.id];
      if (d.routes) routes = d.routes;
      collectYears();
      closeDetail();
      toast("O'chirildi");
    }).catch(function (ex) { toast(ex.message, true); });
  }

  // -------------------------------------------------------- route form --
  function routeForm(r) {
    draftRoute = JSON.parse(JSON.stringify(r || { name: "", kind: "harbiy", color: COLORS[routes.length % COLORS.length],
      year_start: null, year_end: null, description: "", stops: [] }));
    setMode("route", true);
    selected = null;
    focusRoute = null;
    drawRouteForm();
  }

  function drawRouteForm() {
    var r = draftRoute;
    var isNew = !r.id;
    detail.innerHTML =
      '<button type="button" class="hm-back" data-rform="cancel">← Bekor qilish</button>' +
      '<h2 class="hm-detail-name">' + (isNew ? "Yangi yo'nalish" : "Yo'nalishni tahrirlash") + "</h2>" +
      '<form class="hm-form" id="hm-route-form" novalidate>' +
      '<label class="pf-label">Nomi<span class="pf-req">*</span></label><input class="pf-input" name="name" maxlength="150" value="' + esc(r.name) + '" placeholder="Masalan: Hindiston yurishi (1398–1399)">' +
      '<div class="pf-row"><div><label class="pf-label">Turi</label><select class="pf-input" name="kind">' +
      DATA.routeKinds.map(function (k) { return '<option value="' + k[0] + '"' + (k[0] === r.kind ? " selected" : "") + ">" + esc(k[1]) + "</option>"; }).join("") +
      '</select></div><div><label class="pf-label">Rangi</label><div class="hm-colors">' +
      COLORS.map(function (c) { return '<button type="button" class="hm-color' + (c === r.color ? " is-on" : "") + '" data-color="' + c + '" style="background:' + c + '" aria-label="' + c + '"></button>'; }).join("") +
      "</div></div></div>" +
      '<div class="pf-row"><div><label class="pf-label">Boshlangan yil</label><input class="pf-input" name="year_start" inputmode="numeric" value="' + (r.year_start == null ? "" : r.year_start) + '"></div>' +
      '<div><label class="pf-label">Tugagan yil</label><input class="pf-input" name="year_end" inputmode="numeric" value="' + (r.year_end == null ? "" : r.year_end) + '"></div></div>' +
      '<label class="pf-label">Tavsif</label><textarea class="pf-input" name="description" rows="2">' + esc(r.description) + "</textarea>" +
      '<p class="pf-label">Bekatlar <small>' + r.stops.length + "</small></p>" +
      '<p class="hm-callout">Xaritadagi joylarni <b>ketma-ket bosing</b> — har biri bekat bo\'lib qo\'shiladi. Kerakli joy yo\'q bo\'lsa, avval uni «Joy qo\'shish» bilan belgilang.</p>' +
      '<ol class="hm-stops hm-stops-edit">' + r.stops.map(function (s, i) {
        var p = places[s.place];
        return '<li><span class="hm-stop-no" style="background:' + esc(r.color) + '">' + (i + 1) + "</span><span class=\"hm-stop-name\">" + esc(p ? p.name : "?") + "</span>" +
          '<input class="pf-input hm-stop-year" data-stop-year="' + i + '" inputmode="numeric" placeholder="' + esc(p && p.year != null ? p.year : "yil") + '" value="' + (s.year == null ? "" : s.year) + '" aria-label="Bekat yili">' +
          '<button type="button" data-stop-up="' + i + '" aria-label="Yuqoriga">↑</button><button type="button" data-stop-del="' + i + '" aria-label="Olib tashlash">×</button></li>';
      }).join("") + "</ol>" +
      '<p class="pf-error" data-form-error hidden></p>' +
      '<div class="pf-actions"><button type="submit" class="pf-btn pf-btn-primary">Saqlash</button>' +
      (isNew ? "" : '<button type="button" class="pf-btn pf-btn-danger" data-rform="delete">O\'chirish</button>') + "</div></form>";
    showPane("detail");
    openPanel();
    var form = document.getElementById("hm-route-form");
    function pull() {
      draftRoute.name = form.name.value;
      draftRoute.kind = form.kind.value;
      draftRoute.year_start = form.year_start.value.trim() === "" ? null : parseInt(form.year_start.value.replace("−", "-"), 10);
      draftRoute.year_end = form.year_end.value.trim() === "" ? null : parseInt(form.year_end.value.replace("−", "-"), 10);
      draftRoute.description = form.description.value;
      form.querySelectorAll("[data-stop-year]").forEach(function (inp) {
        var v = inp.value.trim().replace("−", "-");
        draftRoute.stops[+inp.dataset.stopYear].year = v === "" ? null : parseInt(v, 10);
      });
    }
    form.addEventListener("input", function () { pull(); render(); });
    form.addEventListener("click", function (e) {
      var c = e.target.closest("[data-color]");
      if (c) { pull(); draftRoute.color = c.dataset.color; drawRouteForm(); return; }
      var up = e.target.closest("[data-stop-up]");
      if (up) {
        pull();
        var i = +up.dataset.stopUp;
        if (i > 0) { var t = draftRoute.stops[i - 1]; draftRoute.stops[i - 1] = draftRoute.stops[i]; draftRoute.stops[i] = t; }
        drawRouteForm();
        return;
      }
      var del = e.target.closest("[data-stop-del]");
      if (del) { pull(); draftRoute.stops.splice(+del.dataset.stopDel, 1); drawRouteForm(); }
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      pull();
      var body = JSON.parse(JSON.stringify(draftRoute));
      var err = form.querySelector("[data-form-error]");
      if (body.stops.length < 2) {
        err.textContent = "Kamida 2 ta bekat tanlang: xaritadagi joylarni ketma-ket bosing.";
        err.hidden = false;
        return;
      }
      api(DATA.api.route, body).then(function (d) {
        var saved = d.route;
        var found = false;
        routes = routes.map(function (x) { if (x.id === saved.id) { found = true; return saved; } return x; });
        if (!found) routes.push(saved);
        draftRoute = null;
        collectYears();
        setMode("view", true);
        toast("Yo'nalish saqlandi");
        showRoute(saved);
      }).catch(function (ex) { err.textContent = ex.message; err.hidden = false; });
    });
    detail.querySelectorAll("[data-rform=cancel]").forEach(function (b) {
      b.addEventListener("click", function () { draftRoute = null; setMode("view", true); closeDetail(); showPane("routes"); });
    });
    var delBtn = detail.querySelector("[data-rform=delete]");
    if (delBtn) delBtn.addEventListener("click", function () {
      if (!confirm("«" + draftRoute.name + "» yo'nalishi o'chirilsinmi?")) return;
      api(DATA.api.route, { id: draftRoute.id, delete: true }).then(function () {
        var id = draftRoute.id;
        routes = routes.filter(function (x) { return x.id !== id; });
        draftRoute = null;
        setMode("view", true);
        collectYears();
        closeDetail();
        showPane("routes");
        toast("O'chirildi");
      }).catch(function (ex) { toast(ex.message, true); });
    });
    render();
  }

  var newRouteBtn = document.getElementById("hm-new-route");
  if (newRouteBtn) newRouteBtn.addEventListener("click", function () { routeForm(null); });

  // ---------------------------------------------------------------- modes --
  var HINTS = {
    add: "Joy belgilamoqchi bo'lgan nuqtani xaritada bosing",
    route: "Joylarni ketma-ket bosing — bekat bo'lib qo'shiladi"
  };
  function setMode(m, quiet) {
    mode = m;
    document.querySelectorAll(".hm-tool[data-mode]").forEach(function (b) { b.classList.toggle("is-on", b.dataset.mode === m); });
    shell.classList.toggle("mode-add", m === "add");
    shell.classList.toggle("mode-route", m === "route");
    hint.textContent = HINTS[m] || "";
    hint.hidden = !HINTS[m];
    if (quiet) return;
    if (m === "route" && !draftRoute) {
      showPane("routes");
      openPanel();
      if (!routes.length) routeForm(null);
    }
    if (m !== "route" && draftRoute) { draftRoute = null; closeDetail(); }
    if (m !== "add" && draftPlace) { draftPlace = null; closeDetail(); }
  }
  document.querySelectorAll(".hm-tool[data-mode]").forEach(function (b) {
    b.addEventListener("click", function () { setMode(b.dataset.mode); });
  });

  // -------------------------------------------------------------- clicks --
  markersEl.addEventListener("click", function (e) {
    var m = e.target.closest(".hm-marker");
    if (!m || m.dataset.id === "draft") return;
    e.stopPropagation();
    var id = +m.dataset.id;
    if (draftRoute) {
      var last = draftRoute.stops[draftRoute.stops.length - 1];
      if (last && last.place === id) return;
      draftRoute.stops.push({ place: id, year: null });
      drawRouteForm();
      return;
    }
    selectPlace(id, false);
  });

  viewport.addEventListener("click", function (e) {
    if (e.target.closest(".hm-marker")) return;
    if (canEdit && mode === "add") {
      var w = map.toWorld(e.clientX, e.clientY);
      if (w.x < 0 || w.y < 0 || w.x > W || w.y > H) return;
      draftPlace = { id: null, name: "", kind: "shahar", x: w.x / W, y: w.y / H, year: year, year_end: null, description: "", person: null };
      selected = null;
      placeForm(draftPlace);
      return;
    }
    if (mode === "route") return;
    if (selected != null || focusRoute != null) closeDetail();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (draftPlace || draftRoute) { draftPlace = null; draftRoute = null; setMode("view", true); closeDetail(); }
    else if (selected != null || focusRoute != null) closeDetail();
    else if (mode !== "view") setMode("view");
  });

  // --------------------------------------------------------------- start --
  collectYears();
  setYear(null);
  function frame() { map.fit(); }
  var img = document.getElementById("hm-image");
  if (img.complete) frame(); else img.addEventListener("load", frame);
  frame();
})();
