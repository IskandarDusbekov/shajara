/* The admin's map of Uzbekistan: real region borders coloured by a chosen
   figure, lines for tree networks and marriages that cross regions, and a
   live ring for people online right now.

   AdmRegionMap.mount(element, data) → controller
     data.rows      {regionName: {...figures}}  (from region_insights.build)
     data.links     [{a, b, n}]  trees of two regions in one family network
     data.marriages [{a, b, n}]  spouses born in two different regions
     data.metric    initial figure to colour by
   The element carries data-geo (GeoJSON url). Leaflet must be loaded. */
(function () {
  "use strict";

  var UZ_BOUNDS = [[37.1, 55.9], [45.65, 73.2]];
  // Where a label sits when the region's own centre would collide with a neighbour.
  var LABEL_AT = {
    "Toshkent shahri": [41.62, 68.95],
    "Toshkent viloyati": [41.95, 70.55],
    "Sirdaryo viloyati": [40.25, 68.45],
    "Jizzax viloyati": [40.6, 67.35],
    "Andijon viloyati": [40.9, 72.85],
    "Farg'ona viloyati": [40.12, 71.35],
    "Namangan viloyati": [41.38, 71.1]
  };

  function cssVar(name, fallback) {
    var host = document.querySelector(".adm-page") || document.body;
    var v = getComputedStyle(host).getPropertyValue(name).trim();
    return v || fallback;
  }

  // OpenStreetMap's free tiles; the stylesheet mutes them to grey (and
  // inverts them in dark mode) so the coloured regions stay the focus.
  var TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

  function bins(values) {
    var top = Math.max.apply(null, values.concat([0]));
    if (top <= 0) return [];
    var steps = Math.min(5, top);
    var width = Math.ceil(top / steps);
    var out = [];
    for (var i = 1; i <= steps; i++) out.push(width * i);
    return out;
  }
  function stepOf(value, bounds) {
    if (!value) return 0;
    for (var i = 0; i < bounds.length; i++) if (value <= bounds[i]) return i + 1;
    return bounds.length;
  }

  // A gentle arc between two points, so opposite-direction lines don't overlap.
  function arc(a, b) {
    var mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
    var dx = b[1] - a[1], dy = b[0] - a[0];
    var len = Math.sqrt(dx * dx + dy * dy) || 1;
    var bend = Math.min(0.9, len * 0.18);
    var cx = mx + (dx / len) * bend, cy = my - (dy / len) * bend;
    var pts = [];
    for (var t = 0; t <= 1.0001; t += 0.08) {
      var u = 1 - t;
      pts.push([u * u * a[0] + 2 * u * t * cx + t * t * b[0], u * u * a[1] + 2 * u * t * cy + t * t * b[1]]);
    }
    return pts;
  }

  function mount(el, data, opts) {
    opts = opts || {};
    var compact = !!data.compact;
    var metric = data.metric || "users";
    var metricLabel = {};
    (data.metrics || []).forEach(function (m) { metricLabel[m.key] = m.label; });
    var selected = null;
    var layers = {};      // region name → GeoJSON layer
    var labels = {};      // region name → tooltip marker
    var centres = {};
    var live = {};
    Object.keys(data.rows).forEach(function (n) { live[n] = data.rows[n].online || 0; });

    var map = L.map(el, {
      zoomControl: !compact, attributionControl: false, scrollWheelZoom: !compact, dragging: true,
      zoomSnap: 0.25, minZoom: 4.5, maxZoom: 10, maxBounds: [[33.5, 50], [49, 79]], maxBoundsViscosity: 0.8
    });
    map.setView([41.4, 64.6], 5);
    // OSM asks for a Referer; the site default ("same-origin") would withhold it.
    L.tileLayer(TILE_URL, { maxZoom: 19, referrerPolicy: "strict-origin-when-cross-origin" }).addTo(map);

    var linkLayer = L.layerGroup().addTo(map);
    var kinLayer = L.layerGroup().addTo(map);
    var liveLayer = L.layerGroup().addTo(map);

    function value(name) {
      var r = data.rows[name];
      if (!r) return 0;
      return metric === "online" ? (live[name] || 0) : (r[metric] || 0);
    }
    function palette() {
      return [cssVar("--m0", "#eee"), cssVar("--m1"), cssVar("--m2"), cssVar("--m3"), cssVar("--m4"), cssVar("--m5")];
    }
    var currentBins = [];

    function styleFor(name) {
      var pal = palette();
      var step = stepOf(value(name), currentBins);
      var isSel = name === selected;
      return {
        fillColor: pal[step], fillOpacity: step ? 0.82 : 0.55,
        color: isSel ? cssVar("--a-strong", "#111") : cssVar("--m-edge", "#fff"),
        weight: isSel ? 2.6 : 1.1, opacity: 1
      };
    }

    function labelHtml(name) {
      var r = data.rows[name];
      return (r ? r.short : name) + "<b>" + value(name) + "</b>";
    }

    function restyle() {
      currentBins = bins(Object.keys(layers).map(value));
      Object.keys(layers).forEach(function (name) {
        layers[name].setStyle(styleFor(name));
        if (labels[name]) labels[name].setTooltipContent(labelHtml(name));
      });
      if (selected && layers[selected]) layers[selected].bringToFront();
      drawLegend();
    }

    function drawLegend() {
      var box = opts.legend;
      if (!box) return;
      var pal = palette();
      box.textContent = "";
      var head = document.createElement("span");
      head.textContent = (metricLabel[metric] || "") + ":";
      box.appendChild(head);
      var zero = document.createElement("span");
      zero.innerHTML = '<i style="background:' + pal[0] + '"></i>0';
      box.appendChild(zero);
      var low = 1;
      currentBins.forEach(function (bound, i) {
        var s = document.createElement("span");
        s.innerHTML = '<i style="background:' + pal[i + 1] + '"></i>' + (bound > low ? low + "–" + bound : bound);
        box.appendChild(s);
        low = bound + 1;
      });
    }

    function tipHtml(name) {
      var r = data.rows[name];
      if (!r) return name;
      return "<b>" + name + "</b>" +
        "<span>Ro'yxatdan o'tgan:</span> " + r.users + (r.users_guess ? " <span>(+" + r.users_guess + " taxminiy)</span>" : "") + "<br>" +
        "<span>Hozir onlayn:</span> " + (live[name] || 0) + "<br>" +
        "<span>Shajaralar:</span> " + r.trees + " <span>· bog'langan " + r.trees_connected + "</span><br>" +
        "<span>Shaxslar:</span> " + r.people;
    }

    function drawLines() {
      linkLayer.clearLayers();
      kinLayer.clearLayers();
      var linkColor = cssVar("--m-link", "#1d4ed8"), kinColor = cssVar("--m-kin", "#b45309");
      (data.links || []).forEach(function (l) {
        if (!centres[l.a] || !centres[l.b]) return;
        L.polyline(arc(centres[l.a], centres[l.b]), {
          color: linkColor, weight: Math.min(7, 1.8 + l.n), opacity: 0.85, interactive: true
        }).bindTooltip(l.a + " ⇄ " + l.b + ": " + l.n + " ta umumiy oila tarmog'i", { sticky: true, className: "rmap-tip" }).addTo(linkLayer);
      });
      (data.marriages || []).forEach(function (l) {
        if (!centres[l.a] || !centres[l.b]) return;
        L.polyline(arc(centres[l.b], centres[l.a]), {
          color: kinColor, weight: Math.min(6, 1.4 + l.n * 0.8), opacity: 0.9, dashArray: "5 6", interactive: true
        }).bindTooltip(l.a + " — " + l.b + ": " + l.n + " ta nikoh (qudachilik)", { sticky: true, className: "rmap-tip" }).addTo(kinLayer);
      });
    }

    function drawLive() {
      liveLayer.clearLayers();
      Object.keys(live).forEach(function (name) {
        var n = live[name];
        if (!n || !centres[name]) return;
        var at = [centres[name][0] - (compact ? 0.35 : 0.3), centres[name][1]];
        var size = Math.round(16 + Math.min(22, Math.sqrt(n) * 6));
        L.marker(at, {
          icon: L.divIcon({ className: "rmap-live", html: '<span class="rmap-live-ring">' + n + "</span>", iconSize: [size, size] }),
          keyboard: false
        }).bindTooltip(name + ": " + n + " kishi hozir onlayn", { className: "rmap-tip", direction: "top" }).addTo(liveLayer);
      });
    }

    function select(name, silent) {
      if (!layers[name]) return;
      selected = name;
      restyle();
      if (!silent && opts.onSelect) opts.onSelect(name);
    }

    fetch(el.getAttribute("data-geo"))
      .then(function (r) { return r.json(); })
      .then(function (geo) {
        L.geoJSON(geo, {
          style: function (f) { return styleFor(f.properties.name); },
          onEachFeature: function (f, layer) {
            var name = f.properties.name;
            layers[name] = layer;
            centres[name] = f.properties.center;
            layer.bindTooltip(function () { return tipHtml(name); }, { sticky: true, className: "rmap-tip", direction: "top", offset: [0, -8] });
            layer.on("mouseover", function () { layer.setStyle({ weight: 2.4, color: cssVar("--a-strong", "#111") }); layer.bringToFront(); });
            layer.on("mouseout", function () { layer.setStyle(styleFor(name)); if (selected && layers[selected]) layers[selected].bringToFront(); });
            layer.on("click", function () { if (compact && opts.onSelect) { opts.onSelect(name); } else { select(name); } });
          }
        }).addTo(map);

        Object.keys(layers).forEach(function (name) {
          var at = LABEL_AT[name] || centres[name];
          labels[name] = L.marker(at, { opacity: 0, interactive: false, keyboard: false, icon: L.divIcon({ className: "", iconSize: [0, 0] }) })
            .bindTooltip(labelHtml(name), { permanent: true, direction: "center", className: "rmap-label" })
            .addTo(map);
        });
        restyle();
        drawLines();
        drawLive();
        linkLayer.eachLayer(function (l) { l.bringToFront(); });
        if (opts.initial) select(opts.initial, false);
      });

    document.addEventListener("adm:theme", function () {
      setTimeout(function () { restyle(); drawLines(); }, 30);
    });
    // The panel may still be settling into its grid when the map is created;
    // re-measure and re-frame the country whenever the box changes size.
    var framed = false;
    function refit() {
      map.invalidateSize();
      if (!el.clientWidth) return;
      if (!framed || !opts.keepView) map.fitBounds(UZ_BOUNDS, { padding: [8, 8], animate: false });
      framed = true;
    }
    if (window.ResizeObserver) new ResizeObserver(refit).observe(el);
    else window.addEventListener("resize", refit);
    setTimeout(refit, 60);

    return window.AdmRegionMap.current = {
      map: map,
      setMetric: function (key) { metric = key; restyle(); },
      select: function (name) { select(name, true); },
      toggle: function (which, on) {
        var layer = { links: linkLayer, kin: kinLayer, live: liveLayer }[which];
        if (!layer) return;
        if (on) map.addLayer(layer); else map.removeLayer(layer);
      },
      setLive: function (counts) {
        Object.keys(live).forEach(function (n) { live[n] = counts[n] || 0; });
        drawLive();
        if (metric === "online") restyle();
      },
      live: live
    };
  }

  // Poll who is online and hand the counts to every listener on the page.
  function pollLive(url, onData, every) {
    function tick() {
      if (document.hidden) return;
      fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (!d) return;
          document.querySelectorAll("[data-live-total]").forEach(function (n) { n.textContent = d.total; });
          document.querySelectorAll("[data-live-at]").forEach(function (n) { n.textContent = d.at; });
          onData(d);
        })
        .catch(function () {});
    }
    setInterval(tick, (every || 20) * 1000);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) tick(); });
    return tick;
  }

  window.AdmRegionMap = { mount: mount, pollLive: pollLive };
})();
