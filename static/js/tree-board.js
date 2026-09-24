/* The tree board, shared by the Xarita and Sof ko'rinish pages. On top of
   the pan/zoom surface in tree-map.js this adds:
     - connector lines that meet each card exactly on its border,
     - a marriage knot instead of a plain dashed line between spouses,
     - tap a card to light up its branches and act on that person,
     - an automatic arrangement where every family hangs under its own
       parents, instead of one crowded row per generation,
     - drag a card to rearrange the tree (spouses always travel together) and
       save that arrangement: on the server for the owner, in this browser
       for everyone else.
   When the shell carries data-add-url the sheet also offers the owner the
   add-a-relative shortcuts. */
(function () {
  "use strict";

  var shell = document.querySelector(".map-shell");
  var viewport = document.getElementById("map-viewport");
  var canvas = document.getElementById("map-canvas");
  var content = document.getElementById("tree-content");
  var svg = document.getElementById("lines-svg");
  var dataEl = document.getElementById("families-data");
  if (!shell || !viewport || !canvas || !content || !svg || !dataEl) return;

  var families = JSON.parse(dataEl.textContent);
  var nodes = Array.prototype.slice.call(document.querySelectorAll(".preview-node"));
  var rootNode = document.querySelector(".leaf-node-root");
  var selectedId = null;
  var map = null;
  var boardBounds = null;
  var topLayer = 10;   // the last card moved is drawn above the rest
  var nodeById = {};
  nodes.forEach(function (el) { nodeById[el.dataset.person] = el; });

  // ------------------------------------------------------- couples & moves --

  /* Spouses form a unit: moving either one has to move the other, so each
     marriage merges the two into a single group (a man with two wives ends up
     as one three-person group, which is what you want on the board). */
  var parentOf = {};

  function findGroup(id) {
    id = String(id);
    if (parentOf[id] === undefined) parentOf[id] = id;
    while (parentOf[id] !== id) {
      parentOf[id] = parentOf[parentOf[id]];
      id = parentOf[id];
    }
    return id;
  }

  function union(a, b) {
    var ra = findGroup(a), rb = findGroup(b);
    if (ra !== rb) parentOf[ra] = rb;
  }

  families.forEach(function (f) {
    if (f.father_id && f.mother_id) union(f.father_id, f.mother_id);
  });

  var groupMembers = {};
  nodes.forEach(function (el) {
    var g = findGroup(el.dataset.person);
    (groupMembers[g] = groupMembers[g] || []).push(el);
  });

  function partners(el) {
    return groupMembers[findGroup(el.dataset.person)] || [el];
  }

  // ------------------------------------------------ the automatic layout --

  /* The server sends one row per generation. Laid out as flat rows, a big
     family turns into a wall of cards with lines criss-crossing the whole
     board, so the cards are placed here instead, as a family tree is drawn by
     hand: every couple is one block and the children of a block sit together
     right under it. Neighbouring branches are pushed apart only as far as
     their outlines, generation by generation, require (the Reingold–Tilford
     idea), so a small branch tucks in beside a big one instead of waiting
     until the big one's widest generation has ended. */
  var PAD_X = 48, PAD_Y = 34;      // margin around the drawing
  var COUPLE_GAP = 22;             // between spouses (room for the knot)
  var SIBLING_GAP = 26;            // between neighbouring blocks
  var TREE_GAP = 70;               // between unrelated trees on one board
  var ROW_GAP = 74;                // between generations

  var generation = {};
  Array.prototype.forEach.call(content.querySelectorAll(".row"), function (row, i) {
    row.querySelectorAll(".preview-node").forEach(function (el) { generation[el.dataset.person] = i; });
  });

  var nodeIndex = {};
  nodes.forEach(function (el, i) { nodeIndex[el.dataset.person] = i; });

  var autoPos = {};     // id -> {x, y}: the automatic arrangement
  var pos = {};         // id -> {x, y}: where each card is right now
  var unitOrder = [];   // blocks, parents before children
  var layoutParent = {};

  function unitOf(id) { return findGroup(id); }

  function computeAutoLayout() {
    content.classList.add("is-arranged");
    var size = {};
    nodes.forEach(function (el) {
      size[el.dataset.person] = { w: el.offsetWidth, h: el.offsetHeight };
    });

    // blocks and their generation
    var units = {};
    nodes.forEach(function (el) {
      var id = el.dataset.person, u = unitOf(id);
      var unit = units[u] || (units[u] = { key: u, members: [], gen: Infinity, first: Infinity, kids: [], width: 0 });
      unit.members.push(id);
      unit.gen = Math.min(unit.gen, generation[id] || 0);
      unit.first = Math.min(unit.first, nodeIndex[id]);
    });
    Object.keys(units).forEach(function (k) {
      var unit = units[k];
      unit.members.sort(function (a, b) { return nodeIndex[a] - nodeIndex[b]; });
      unit.own = unit.members.reduce(function (sum, id) { return sum + size[id].w; }, 0) +
        (unit.members.length - 1) * COUPLE_GAP;
    });

    // Each block hangs under one parent block: the first one met going down
    // the generations, so a couple whose both sides have parents on the board
    // is still drawn once.
    var sorted = Object.keys(units).map(function (k) { return units[k]; });
    sorted.sort(function (a, b) { return a.gen - b.gen || a.first - b.first; });
    layoutParent = {};
    sorted.forEach(function (unit) {
      families.forEach(function (f) {
        var parentHere = [f.father_id, f.mother_id].some(function (p) {
          return p && nodeById[p] && unitOf(p) === unit.key;
        });
        if (!parentHere) return;
        f.child_ids.forEach(function (cid) {
          if (!nodeById[cid]) return;
          var cu = unitOf(cid);
          if (cu === unit.key || layoutParent[cu] !== undefined || units[cu].gen <= unit.gen) return;
          layoutParent[cu] = unit.key;
          unit.kids.push(units[cu]);
        });
      });
    });
    sorted.forEach(function (unit) {
      unit.kids.sort(function (a, b) { return a.first - b.first; });
    });

    /* In-laws: parents who are on the board only because their child married
       in. Their child already hangs under the other side's parents, so on
       their own they would drift off to the far edge. Seat them right beside
       those other parents (the co-parents-in-law) instead. */
    var besideRoot = {};
    sorted.forEach(function (unit) {
      if (layoutParent[unit.key] !== undefined || unit.kids.length) return;
      var host;
      families.forEach(function (f) {
        if (host !== undefined) return;
        var parentHere = [f.father_id, f.mother_id].some(function (p) {
          return p && nodeById[p] && unitOf(p) === unit.key;
        });
        if (!parentHere) return;
        f.child_ids.forEach(function (cid) {
          if (host !== undefined || !nodeById[cid]) return;
          var cu = unitOf(cid);
          if (cu !== unit.key && layoutParent[cu] !== undefined) host = layoutParent[cu];
        });
      });
      if (host === undefined || host === unit.key) return;
      var above = layoutParent[host];
      if (above !== undefined && units[above].gen < unit.gen) {
        layoutParent[unit.key] = above;
        var list = units[above].kids;
        list.splice(list.indexOf(units[host]) + 1, 0, unit);
      } else if (above === undefined) {
        besideRoot[unit.key] = host;
      }
    });

    /* Lay the branches of a row of blocks side by side. Each branch comes as
       an outline — the leftmost and rightmost x it uses in every generation,
       in its own frame — and is shifted right just enough to clear every
       generation of what is already placed. */
    function packSideBySide(branches, gap) {
      var left = {}, right = {}, offsets = [];
      branches.forEach(function (b, i) {
        var shift = 0;
        if (i) {
          shift = -Infinity;
          Object.keys(b.left).forEach(function (g) {
            if (right[g] !== undefined) shift = Math.max(shift, right[g] + gap - b.left[g]);
          });
          // no generation in common: just keep them in order
          if (shift === -Infinity) shift = offsets[i - 1] + SIBLING_GAP;
        }
        offsets.push(shift);
        Object.keys(b.left).forEach(function (g) {
          var l = b.left[g] + shift, r = b.right[g] + shift;
          left[g] = left[g] === undefined ? l : Math.min(left[g], l);
          right[g] = right[g] === undefined ? r : Math.max(right[g], r);
        });
      });
      return { left: left, right: right, offsets: offsets };
    }

    /* A block's branch, in a frame where the block itself starts at x = 0. */
    function shapeOf(unit) {
      var left = {}, right = {};
      left[unit.gen] = 0;
      right[unit.gen] = unit.own;
      unit.kidX = [];
      if (!unit.kids.length) return { left: left, right: right };

      var kidShapes = unit.kids.map(shapeOf);
      var packed = packSideBySide(kidShapes, SIBLING_GAP);
      // centre the block over its first and last child block
      var first = packed.offsets[0] + unit.kids[0].own / 2;
      var lastKid = unit.kids.length - 1;
      var last = packed.offsets[lastKid] + unit.kids[lastKid].own / 2;
      var shift = unit.own / 2 - (first + last) / 2;
      unit.kidX = packed.offsets.map(function (o) { return o + shift; });
      Object.keys(packed.left).forEach(function (g) {
        var l = packed.left[g] + shift, r = packed.right[g] + shift;
        left[g] = left[g] === undefined ? l : Math.min(left[g], l);
        right[g] = right[g] === undefined ? r : Math.max(right[g], r);
      });
      return { left: left, right: right };
    }

    // row heights and tops
    var rowH = [];
    nodes.forEach(function (el) {
      var g = generation[el.dataset.person] || 0;
      rowH[g] = Math.max(rowH[g] || 0, size[el.dataset.person].h);
    });
    var rowTop = [], y = PAD_Y;
    for (var g = 0; g < rowH.length; g++) {
      rowTop[g] = y;
      y += (rowH[g] || 0) + ROW_GAP;
    }

    autoPos = {};
    unitOrder = [];
    function place(unit, x0) {
      unitOrder.push(unit.key);
      var x = x0;
      unit.members.forEach(function (id) {
        var g = generation[id] || 0;
        autoPos[id] = { x: x, y: rowTop[g] + (rowH[g] - size[id].h) / 2 };
        x += size[id].w + COUPLE_GAP;
      });
      unit.kids.forEach(function (kid, i) { place(kid, x0 + unit.kidX[i]); });
    }

    // Separate trees on one board (e.g. an in-law's family) sit side by side
    // with a wider gap, packed by outline like any branches.
    var roots = [];
    sorted.forEach(function (unit) {
      if (layoutParent[unit.key] === undefined && besideRoot[unit.key] === undefined) roots.push(unit);
    });
    sorted.forEach(function (unit) {
      var host = besideRoot[unit.key];
      if (host === undefined) return;
      var at = roots.indexOf(units[host]);
      roots.splice(at === -1 ? roots.length : at + 1, 0, unit);
    });
    var packedRoots = packSideBySide(roots.map(shapeOf), TREE_GAP);
    var minX = Infinity, maxX = -Infinity;
    Object.keys(packedRoots.left).forEach(function (g) {
      minX = Math.min(minX, packedRoots.left[g]);
      maxX = Math.max(maxX, packedRoots.right[g]);
    });
    roots.forEach(function (root, i) { place(root, PAD_X - minX + packedRoots.offsets[i]); });

    content.style.width = Math.max(maxX - minX + 2 * PAD_X, 200) + "px";
    content.style.height = Math.max(y - ROW_GAP + PAD_Y, 120) + "px";
  }

  // ---------------------------------------------- saving an arrangement --

  var STORE_KEY = "shajara_layout_v2_" + (shell.dataset.treeKey || "x");
  var layoutUrl = shell.dataset.layoutUrl || "";   // only the owner saves on the server
  var resetBtn = document.getElementById("map-reset-layout");
  var layoutBar = document.getElementById("layout-bar");
  var saveBtn = document.getElementById("layout-save");
  var cancelBtn = document.getElementById("layout-cancel");
  var savedPos = {};    // the arrangement last saved ({} = automatic)
  var dirty = false;    // cards moved since then

  function readSaved() {
    var raw = null;
    if (!layoutUrl) {
      try { raw = JSON.parse(localStorage.getItem(STORE_KEY) || "null"); } catch (e) { raw = null; }
    }
    if (!raw) {
      var el = document.getElementById("layout-data");
      try { raw = el ? JSON.parse(el.textContent) : null; } catch (e) { raw = null; }
    }
    var out = {};
    if (raw && typeof raw === "object") {
      Object.keys(raw).forEach(function (id) {
        var v = raw[id];
        if (Array.isArray(v) && v.length === 2 && isFinite(v[0]) && isFinite(v[1])) out[id] = { x: +v[0], y: +v[1] };
      });
    }
    return out;
  }

  /* Saved positions win. Someone added after the save has none, so they
     follow the block they hang from: it moves by as much as that block was
     moved, which keeps a new child under its (dragged) parents. */
  function positionsFrom(saved) {
    var out = {}, shift = {};
    unitOrder.forEach(function (u) {
      var members = (groupMembers[u] || []).map(function (el) { return el.dataset.person; });
      var d = null;
      members.forEach(function (id) {
        if (!d && saved[id] && autoPos[id]) d = { x: saved[id].x - autoPos[id].x, y: saved[id].y - autoPos[id].y };
      });
      if (!d) d = layoutParent[u] !== undefined ? shift[layoutParent[u]] : { x: 0, y: 0 };
      shift[u] = d;
      members.forEach(function (id) {
        if (!autoPos[id]) return;
        out[id] = saved[id] ? { x: saved[id].x, y: saved[id].y } : { x: autoPos[id].x + d.x, y: autoPos[id].y + d.y };
      });
    });
    return out;
  }

  function isAutomatic(p) {
    return Object.keys(autoPos).every(function (id) {
      return p[id] && Math.abs(p[id].x - autoPos[id].x) < 1 && Math.abs(p[id].y - autoPos[id].y) < 1;
    });
  }

  function placeNode(el) {
    var p = pos[el.dataset.person];
    el.style.transform = p ? "translate(" + p.x + "px," + p.y + "px)" : "";
  }

  function syncLayoutControls() {
    if (resetBtn) resetBtn.hidden = isAutomatic(pos);
    if (layoutBar) layoutBar.hidden = !dirty;
  }

  function setDirty(value) {
    dirty = value;
    syncLayoutControls();
  }

  function moveBy(el, dx, dy) {
    partners(el).forEach(function (member) {
      var id = member.dataset.person;
      var p = pos[id] || { x: 0, y: 0 };
      pos[id] = { x: Math.round((p.x + dx) * 10) / 10, y: Math.round((p.y + dy) * 10) / 10 };
      placeNode(member);
    });
  }

  /* Glide every card to a new arrangement, then redraw the lines once. */
  function applyPositions(next, animate) {
    pos = next;
    if (animate) {
      content.classList.add("is-rearranging");
      nodes.forEach(placeNode);
      setTimeout(function () {
        content.classList.remove("is-rearranging");
        renderLines();
      }, 420);
    } else {
      nodes.forEach(placeNode);
      renderLines();
    }
    syncLayoutControls();
  }

  function autoArrange() {
    applyPositions(positionsFrom({}), true);
    setDirty(!isAutomatic(positionsFrom(savedPos)));
  }

  function cancelChanges() {
    applyPositions(positionsFrom(savedPos), true);
    setDirty(false);
  }

  function showToast(text, ok) {
    var box = shell.querySelector(".map-toasts");
    if (!box) {
      box = document.createElement("div");
      box.className = "map-toasts";
      shell.appendChild(box);
    }
    var t = document.createElement("div");
    t.className = "toast-msg" + (ok ? " toast-success" : "");
    t.textContent = text;
    box.appendChild(t);
    setTimeout(function () { t.remove(); }, 3200);
  }

  function saveLayout() {
    var automatic = isAutomatic(pos);
    var payload = {};
    if (!automatic) {
      Object.keys(pos).forEach(function (id) { payload[id] = [pos[id].x, pos[id].y]; });
    }
    function done() {
      savedPos = automatic ? {} : readBack(payload);
      setDirty(false);
      showToast(automatic ? "Avtomatik tartib saqlandi" : "Tartib saqlandi", true);
    }
    if (!layoutUrl) {
      try {
        if (automatic) localStorage.removeItem(STORE_KEY);
        else localStorage.setItem(STORE_KEY, JSON.stringify(payload));
        done();
      } catch (e) {
        showToast("Bu brauzerda tartibni saqlab bo'lmadi", false);
      }
      return;
    }
    if (saveBtn) saveBtn.disabled = true;
    fetch(layoutUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": shell.dataset.csrf || "" },
      body: JSON.stringify({ positions: payload })
    }).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      done();
    }).catch(function () {
      showToast("Saqlanmadi — internetni tekshirib, qayta urinib ko'ring", false);
    }).then(function () {
      if (saveBtn) saveBtn.disabled = false;
    });
  }

  function readBack(payload) {
    var out = {};
    Object.keys(payload).forEach(function (id) { out[id] = { x: payload[id][0], y: payload[id][1] }; });
    return out;
  }

  if (saveBtn) saveBtn.addEventListener("click", saveLayout);
  if (cancelBtn) cancelBtn.addEventListener("click", cancelChanges);
  window.addEventListener("beforeunload", function (e) {
    if (!dirty) return;
    e.preventDefault();
    e.returnValue = "";
  });

  /* (Re)measure and place everything. Unsaved moves survive a re-run, e.g.
     when the web fonts finish loading. */
  function arrange() {
    var keep = dirty ? pos : null;
    computeAutoLayout();
    savedPos = readSaved();
    pos = keep || positionsFrom(savedPos);
    nodes.forEach(placeNode);
    syncLayoutControls();
  }

  // -------------------------------------------------------- the connectors --

  /* Measured through getBoundingClientRect, which reports pixels *after* the
     canvas transform; dividing by the live zoom puts them back into the
     unscaled coordinate system the SVG draws in. */
  function boxOf(el, origin, s) {
    var r = el.getBoundingClientRect();
    var left = (r.left - origin.x) / s, top = (r.top - origin.y) / s;
    var w = r.width / s, h = r.height / s;
    return { left: left, top: top, w: w, h: h, cx: left + w / 2, cy: top + h / 2 };
  }

  /* The point where the line from a box's centre towards (tx, ty) crosses the
     box's border — this is what makes every connector land exactly on a card's
     edge instead of disappearing under it or stopping short in mid-air. */
  function edgeToward(box, tx, ty) {
    var dx = tx - box.cx, dy = ty - box.cy;
    if (!dx && !dy) return { x: box.cx, y: box.cy };
    var t = Math.min(
      dx ? (box.w / 2) / Math.abs(dx) : Infinity,
      dy ? (box.h / 2) / Math.abs(dy) : Infinity
    );
    return { x: box.cx + dx * t, y: box.cy + dy * t };
  }

  function renderLines() {
    var cRect = content.getBoundingClientRect();
    var s = (map ? map.getScale() : 1) || 1;
    var origin = { x: cRect.left, y: cRect.top };
    var box = {};
    nodes.forEach(function (el) { box[el.dataset.person] = boxOf(el, origin, s); });

    // The drawn area: the canvas plus any card dragged beyond its edges, so
    // "show everything" and the pan limits still reach every person.
    var minX = 0, minY = 0, maxX = canvas.offsetWidth, maxY = canvas.offsetHeight;
    Object.keys(box).forEach(function (id) {
      var b = box[id];
      minX = Math.min(minX, b.left - 40);
      minY = Math.min(minY, b.top - 40);
      maxX = Math.max(maxX, b.left + b.w + 40);
      maxY = Math.max(maxY, b.top + b.h + 40);
    });
    boardBounds = { x: minX, y: minY, w: maxX - minX, h: maxY - minY };

    var branches = "";   // parent -> child curves, drawn underneath
    var knots = "";      // marriage knots, drawn on top

    families.forEach(function (f) {
      var father = f.father_id ? box[f.father_id] : null;
      var mother = f.mother_id ? box[f.mother_id] : null;
      var people = [f.father_id, f.mother_id].concat(f.child_ids).filter(Boolean).join(",");
      var hub;   // the point this family's children hang from

      if (father && mother) {
        var a = edgeToward(father, mother.cx, mother.cy);
        var b = edgeToward(mother, father.cx, father.cy);
        hub = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };

        var couple = f.father_id + "," + f.mother_id;
        knots +=
          '<line class="tree-line marriage-link" data-people="' + couple + '" ' +
          'x1="' + a.x + '" y1="' + a.y + '" x2="' + b.x + '" y2="' + b.y + '"/>' +
          '<g class="tree-line marriage-knot" data-people="' + couple + '">' +
          '<circle class="knot-bg" cx="' + hub.x + '" cy="' + hub.y + '" r="11"/>' +
          '<circle class="knot-ring" cx="' + (hub.x - 3) + '" cy="' + hub.y + '" r="4.6"/>' +
          '<circle class="knot-ring" cx="' + (hub.x + 3) + '" cy="' + hub.y + '" r="4.6"/>' +
          "</g>";
      } else if (father || mother) {
        var solo = father || mother;
        hub = { x: solo.cx, y: solo.cy };
      } else {
        return;
      }

      f.child_ids.forEach(function (cid) {
        var child = box[cid];
        if (!child) return;
        var from = (father && mother) ? hub : edgeToward(father || mother, child.cx, child.cy);
        var to = edgeToward(child, from.x, from.y);
        // A vertical S-curve. The pull flips sign on its own if the reader has
        // dragged a child above its parents.
        var pull = (to.y - from.y) * 0.45;
        if (Math.abs(pull) < 26) pull = pull < 0 ? -26 : 26;
        branches +=
          '<path class="tree-line branch-line" data-people="' + people + '" fill="none" d="' +
          "M " + from.x + " " + from.y +
          " C " + from.x + " " + (from.y + pull) + ", " + to.x + " " + (to.y - pull) +
          ", " + to.x + " " + to.y + '"/>' +
          '<circle class="tree-line branch-tip" data-people="' + people + '" cx="' + to.x +
          '" cy="' + to.y + '" r="2.8"/>';
      });
    });

    svg.innerHTML =
      '<defs><linearGradient id="branchGrad" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="#c9a227"/><stop offset="100%" stop-color="#8a6d1f"/>' +
      '</linearGradient></defs>' + branches + knots;
    if (selectedId) applyHighlight(selectedId);
  }

  // --------------------------------------------------------- the highlight --

  function forEachLine(fn) {
    svg.querySelectorAll("[data-people]").forEach(fn);
  }

  function clearHighlight() {
    forEachLine(function (el) { el.classList.remove("dim", "active"); });
    nodes.forEach(function (el) { el.classList.remove("selected", "related"); });
  }

  function applyHighlight(personId) {
    var id = String(personId);
    var related = {};
    forEachLine(function (el) {
      var people = (el.dataset.people || "").split(",");
      if (people.indexOf(id) !== -1) {
        el.classList.add("active");
        el.classList.remove("dim");
        people.forEach(function (p) { if (p) related[p] = true; });
      } else {
        el.classList.add("dim");
        el.classList.remove("active");
      }
    });
    nodes.forEach(function (el) {
      var pid = el.dataset.person;
      el.classList.toggle("selected", pid === id);
      el.classList.toggle("related", pid !== id && !!related[pid]);
    });
  }

  // ----------------------------------------------------- the person panel --

  var panel = document.getElementById("person-panel");
  var ppAvatar = document.getElementById("pp-avatar");
  var ppName = document.getElementById("pp-name");
  var ppChips = document.getElementById("pp-chips");
  var ppBody = document.getElementById("pp-body");
  var ppOpen = document.getElementById("pp-open");
  var ppClose = document.getElementById("pp-close");
  var addBtn = document.getElementById("pp-add");
  var relations = document.getElementById("pp-relations");
  var addUrl = shell.dataset.addUrl || "";
  var hint = document.getElementById("map-hint");

  function hideHint() {
    if (hint) hint.classList.add("is-gone");
  }

  function isWide() {
    return window.matchMedia("(min-width: 900px)").matches;
  }

  /* On a phone the panel is a bottom sheet and the round controls ride above
     it; on a wide screen it is a side card and nothing needs to move. */
  function syncPanelSpace() {
    var open = panel && !panel.hidden;
    var h = open && !isWide() ? panel.getBoundingClientRect().height : 0;
    shell.style.setProperty("--sheet-h", h + "px");
    shell.classList.toggle("has-sheet", h > 0);
    shell.classList.toggle("has-panel", !!open && isWide());
  }

  // --- family links, read straight from the family records ---

  function familyOf(personId) {
    var id = Number(personId);
    var parents = [], spouses = [], children = [], siblings = [];
    families.forEach(function (f) {
      if (f.child_ids.indexOf(id) !== -1) {
        if (f.father_id) parents.push(f.father_id);
        if (f.mother_id) parents.push(f.mother_id);
        f.child_ids.forEach(function (c) { if (c !== id) siblings.push(c); });
      }
      if (f.father_id === id || f.mother_id === id) {
        var other = f.father_id === id ? f.mother_id : f.father_id;
        if (other) spouses.push(other);
        f.child_ids.forEach(function (c) { children.push(c); });
      }
    });
    function known(list) {
      var seen = {};
      return list.filter(function (x) {
        if (seen[x] || !nodeById[x]) return false;
        seen[x] = true;
        return true;
      });
    }
    return { parents: known(parents), spouses: known(spouses),
             children: known(children), siblings: known(siblings) };
  }

  // --- small DOM helpers; every piece of user text goes in as textContent ---

  function h(tag, className, text) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (text != null) el.textContent = text;
    return el;
  }

  function avatarInto(target, el, small) {
    target.textContent = "";
    target.className = (small ? "pp-mini-avatar" : "pp-avatar") + " g-" + (el.dataset.gender || "erkak");
    if (el.dataset.photo) {
      var img = document.createElement("img");
      img.src = el.dataset.photo;
      img.alt = "";
      img.loading = "lazy";
      target.appendChild(img);
    } else {
      target.textContent = (el.dataset.name || "?").trim().charAt(0).toUpperCase();
    }
  }

  function levelOf(el) {
    // The root's own row is captioned with their name, which reads oddly for
    // the spouses standing beside them; they get their role instead.
    var level = el.dataset.level || "";
    if (rootNode && level === rootNode.dataset.name) return el === rootNode ? "" : "Turmush o'rtog'i";
    return level;
  }

  function personButton(id) {
    var el = nodeById[id];
    var b = h("button", "pp-person");
    b.type = "button";
    b.dataset.go = id;
    var av = h("span");
    avatarInto(av, el, true);
    b.appendChild(av);
    var txt = h("span", "pp-person-text");
    txt.appendChild(h("span", "pp-person-name", el.dataset.name));
    if (el.dataset.year) txt.appendChild(h("span", "pp-person-year", el.dataset.year));
    b.appendChild(txt);
    b.title = el.dataset.name + " — xaritada ko'rsatish";
    return b;
  }

  function relationGroup(label, ids) {
    var row = h("div", "pp-rel");
    var head = h("div", "pp-rel-head");
    head.appendChild(h("span", "pp-rel-label", label));
    if (ids.length) head.appendChild(h("span", "pp-rel-count", String(ids.length)));
    row.appendChild(head);
    if (!ids.length) {
      row.appendChild(h("span", "pp-rel-empty", "Kiritilmagan"));
    } else {
      var list = h("div", "pp-people");
      ids.forEach(function (id) { list.appendChild(personButton(id)); });
      row.appendChild(list);
    }
    return row;
  }

  function section(title) {
    var sec = h("section", "pp-section");
    sec.appendChild(h("h3", "pp-section-title", title));
    return sec;
  }

  function fillPanel(el) {
    avatarInto(ppAvatar, el, false);
    ppName.textContent = el.dataset.name;

    ppChips.textContent = "";
    ppChips.appendChild(h("span", "pp-chip pp-chip-" + (el.dataset.gender || "erkak"), el.dataset.role));
    var level = levelOf(el);
    if (level) ppChips.appendChild(h("span", "pp-chip", level));

    ppOpen.setAttribute("href", el.dataset.url);

    if (relations) {
      relations.hidden = true;
      if (addBtn) addBtn.setAttribute("aria-expanded", "false");
      relations.querySelectorAll("a[data-relation]").forEach(function (a) {
        a.setAttribute("href", addUrl + "?anchor=" + el.dataset.person + "&relation=" + a.dataset.relation);
      });
    }

    ppBody.textContent = "";

    // 1. Life facts — only the ones that were actually filled in.
    var facts = [
      ["Tug'ilgan yili", el.dataset.year],
      ["Vafot etgan yili", el.dataset.death],
      ["Otasining ismi", el.dataset.patronymic],
      ["Tug'ilgan joyi", el.dataset.place],
      ["Manba yozuvlar", el.dataset.merged ? el.dataset.merged + " ta yozuvdan birlashtirilgan" : ""],
      ["Kasbi", el.dataset.occupation],
      ["Yashash joyi", el.dataset.location]
    ].filter(function (f) { return f[1]; });
    if (facts.length) {
      var about = section("Ma'lumot");
      var dl = h("dl", "pp-facts");
      facts.forEach(function (f) {
        var item = h("div", "pp-fact");
        item.appendChild(h("dt", null, f[0]));
        item.appendChild(h("dd", null, f[1]));
        dl.appendChild(item);
      });
      about.appendChild(dl);
      ppBody.appendChild(about);
    }

    // 2. Family, in the order people ask about it.
    var fam = familyOf(el.dataset.person);
    var family = section("Oilasi");
    family.appendChild(relationGroup("Ota-onasi", fam.parents));
    family.appendChild(relationGroup(fam.spouses.length > 1 ? "Turmush o'rtoqlari" : "Turmush o'rtog'i", fam.spouses));
    family.appendChild(relationGroup("Farzandlari", fam.children));
    if (fam.siblings.length) family.appendChild(relationGroup("Aka-uka, opa-singillari", fam.siblings));
    ppBody.appendChild(family);

    // 3. A short note, if there is one.
    if (el.dataset.bio) {
      var bio = section("Qisqacha");
      bio.appendChild(h("p", "pp-bio", el.dataset.bio));
      ppBody.appendChild(bio);
    }
  }

  /* On a wide screen the panel covers the left of the board, so a selected
     card hiding underneath it is slid into the open part. */
  function keepClearOfPanel(el) {
    if (!isWide() || !panel || panel.hidden) return;
    var pr = panel.getBoundingClientRect();
    var er = el.getBoundingClientRect();
    var vr = viewport.getBoundingClientRect();
    var gap = 24;
    var dx = 0, dy = 0;
    if (er.left < pr.right + gap) dx = pr.right + gap - er.left;
    if (er.right + dx > vr.right - 80) dx = Math.min(dx, vr.right - 80 - er.right);
    if (er.top < vr.top + gap) dy = vr.top + gap - er.top;
    if (er.bottom > vr.bottom - gap) dy = vr.bottom - gap - er.bottom;
    if (dx || dy) map.panBy(dx, dy);
  }

  function select(el, focusOnMap) {
    var pid = el.dataset.person;
    if (selectedId === pid && !focusOnMap) { deselect(); return; }
    clearHighlight();
    applyHighlight(pid);
    selectedId = pid;
    if (!panel) return;
    fillPanel(el);
    var wasOpen = !panel.hidden;
    panel.hidden = false;
    panel.scrollTop = 0;
    hideHint();
    syncPanelSpace();
    if (!isWide()) {
      setSheet("peek", wasOpen);
      keepAboveSheet(el);
      return;
    }
    if (focusOnMap) {
      map.centreOn(el, null, panel.getBoundingClientRect().right / 2);
    } else {
      keepClearOfPanel(el);
    }
  }

  function deselect() {
    clearHighlight();
    selectedId = null;
    if (!panel) return;
    if (!isWide() && !panel.hidden) {
      // slide the sheet away before hiding it
      setSheet("closed", true);
      setTimeout(function () {
        if (!selectedId) { panel.hidden = true; syncPanelSpace(); }
      }, 260);
      return;
    }
    panel.hidden = true;
    syncPanelSpace();
  }

  // ------------------------------------------------ the phone bottom sheet --

  /* On a phone the panel is a bottom sheet with three resting places:
       peek   — name, tags and the buttons; the tree stays visible above
       full   — every detail, scrollable
       closed — swiped away
     It follows the finger while dragged and snaps on release, like the place
     sheet in a maps app. */
  var sheetState = "closed";
  var sheetY = 0;
  var grabBtn = document.getElementById("pp-grab");
  var moreBtn = document.getElementById("pp-more");

  function peekHeight() {
    var actions = panel.querySelector(".pp-actions");
    var top = panel.getBoundingClientRect().top;
    return Math.round(actions.getBoundingClientRect().bottom - top + 10);
  }

  function placeSheet(y, animate) {
    sheetY = Math.max(0, y);
    panel.classList.toggle("is-dragging", !animate);
    panel.style.transform = "translateY(" + sheetY + "px)";
  }

  function setSheet(state, animate) {
    if (isWide()) {
      panel.style.transform = "";
      panel.classList.remove("is-peek", "is-full", "is-dragging");
      return;
    }
    var height = panel.offsetHeight;
    if (!animate && state !== "closed") placeSheet(height, false);   // start below the edge
    if (!animate) panel.offsetHeight;                                 // commit that position
    sheetState = state;
    var y = state === "full" ? 0 : state === "peek" ? height - peekHeight() : height + 20;
    placeSheet(y, true);
    panel.classList.toggle("is-peek", state === "peek");
    panel.classList.toggle("is-full", state === "full");
    if (state !== "full") panel.scrollTop = 0;
    var hud = shell.querySelector(".map-hud");
    var room = viewport.getBoundingClientRect().height - peekHeight();
    var fits = !hud || room > hud.offsetHeight + 24;
    shell.style.setProperty("--sheet-h", peekHeight() + "px");
    shell.classList.toggle("sheet-peek", state === "peek" && fits);
    shell.classList.toggle("sheet-cover", state === "full" || (state === "peek" && !fits));
    var open = state === "full";
    [grabBtn, moreBtn].forEach(function (b) { if (b) b.setAttribute("aria-expanded", String(open)); });
    if (moreBtn) moreBtn.querySelector("span").textContent = open ? "Yig'ish" : "Batafsil";
  }

  /* Keep the tapped card in the strip of board above the compact sheet. */
  function keepAboveSheet(el) {
    var vr = viewport.getBoundingClientRect();
    var er = el.getBoundingClientRect();
    var sheetTop = vr.bottom - peekHeight();
    var dy = 0;
    if (er.bottom > sheetTop - 16) dy = sheetTop - 16 - er.bottom;
    if (er.top + dy < vr.top + 12) dy = vr.top + 12 - er.top;
    if (dy) map.panBy(0, dy);
  }

  if (panel) {
    if (grabBtn) grabBtn.addEventListener("click", function () {
      if (sheetDrag && sheetDrag.moved) return;
      setSheet(sheetState === "full" ? "peek" : "full", true);
    });
    if (moreBtn) moreBtn.addEventListener("click", function () {
      setSheet(sheetState === "full" ? "peek" : "full", true);
    });

    var sheetDrag = null;
    panel.addEventListener("pointerdown", function (e) {
      if (isWide() || panel.hidden) return;
      var onControl = e.target.closest("a, button:not(.pp-grab), select, input, textarea");
      var onHandle = e.target.closest(".pp-grab, .pp-head");
      // In the compact state the whole sheet is a handle; once open, only the
      // top is, so the details can still scroll.
      if (onControl || !(onHandle || sheetState === "peek")) {
        sheetDrag = null;
        return;
      }
      sheetDrag = { id: e.pointerId, y0: e.clientY, base: sheetY, t0: Date.now(), moved: false };
    });
    // Followed on the document: a quick swipe's first move already lands
    // outside the sheet, before pointer capture could be taken.
    document.addEventListener("pointermove", function (e) {
      if (!sheetDrag || e.pointerId !== sheetDrag.id) return;
      var dy = e.clientY - sheetDrag.y0;
      if (!sheetDrag.moved && Math.abs(dy) < 6) return;
      if (!sheetDrag.moved) {
        sheetDrag.moved = true;
        try { panel.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      }
      placeSheet(sheetDrag.base + dy, false);
    });
    var endDrag = function (e) {
      if (!sheetDrag || e.pointerId !== sheetDrag.id) return;
      var drag = sheetDrag;
      if (!drag.moved) { sheetDrag = null; return; }
      var height = panel.offsetHeight;
      var peekY = height - peekHeight();
      var velocity = (e.clientY - drag.y0) / Math.max(1, Date.now() - drag.t0);   // px per ms, + is down
      if (sheetY > peekY + 60 || (velocity > 0.8 && sheetY > peekY - 20)) {
        deselect();
      } else if (sheetY < peekY / 2 || velocity < -0.5) {
        setSheet("full", true);
      } else {
        setSheet("peek", true);
      }
      // let the click that follows a drag know it was a drag
      setTimeout(function () { sheetDrag = null; }, 0);
    };
    document.addEventListener("pointerup", endDrag);
    document.addEventListener("pointercancel", endDrag);
  }

  nodes.forEach(function (node) {
    node.addEventListener("click", function () { select(node, false); });
  });
  if (ppClose) ppClose.addEventListener("click", deselect);

  if (addBtn && relations) {
    addBtn.addEventListener("click", function () {
      var open = relations.hidden;
      relations.hidden = !open;
      addBtn.setAttribute("aria-expanded", String(open));
      if (open && !isWide()) setSheet("full", true);
      syncPanelSpace();
    });
  }

  /* The panel sits over the board: nothing it receives may reach the pan/zoom
     surface underneath. Relatives listed in it jump the map to that person. */
  if (panel) {
    ["pointerdown", "wheel"].forEach(function (type) {
      panel.addEventListener(type, function (e) { e.stopPropagation(); }, { passive: true });
    });
    panel.addEventListener("click", function (e) {
      e.stopPropagation();
      var go = e.target.closest && e.target.closest("[data-go]");
      if (go && nodeById[go.dataset.go]) {
        select(nodeById[go.dataset.go], true);
        return;
      }
      var link = e.target.closest && e.target.closest("a[href]");
      if (!link) return;
      var href = link.getAttribute("href");
      if (!href || href === "#") return;
      e.preventDefault();
      window.location.assign(href);
    });
  }
  viewport.addEventListener("click", function (e) {
    if (selectedId && !(e.target.closest && e.target.closest(".preview-node"))) deselect();
  });

  // ---------------------------------------------------------------- the map --

  var zoomLabel = document.getElementById("map-zoom-level");
  var linesPending = false;

  function queueLines() {
    if (linesPending) return;
    linesPending = true;
    requestAnimationFrame(function () {
      linesPending = false;
      renderLines();
    });
  }

  map = window.TreeMap.create(viewport, canvas, {
    onChange: function (scale) {
      if (zoomLabel) zoomLabel.textContent = Math.round(scale * 100) + "%";
    },
    focus: function () { return rootNode; },
    dragTarget: function (e) {
      return e.target.closest ? e.target.closest(".preview-node") : null;
    },
    bounds: function () { return boardBounds; },
    onDragArm: function (el) {
      partners(el).forEach(function (m) { m.classList.add("is-lifted"); });
    },
    onDragMove: function (el, dx, dy) {
      if (!el.classList.contains("is-carried")) {
        topLayer += 1;
        partners(el).forEach(function (m) {
          m.classList.add("is-carried");
          m.style.zIndex = String(topLayer);
        });
      }
      moveBy(el, dx, dy);
      queueLines();
    },
    onDragEnd: function (el, moved) {
      partners(el).forEach(function (m) { m.classList.remove("is-carried", "is-lifted"); });
      if (moved) {
        setDirty(true);
        renderLines();
      }
    }
  });

  /* What tree-export.js needs to redraw the board as a picture: every card
     where it stands now (in unscaled board units) and the connector shapes. */
  window.ShajaraBoard = {
    snapshot: function () {
      renderLines();
      var cRect = content.getBoundingClientRect();
      var s = map.getScale() || 1;
      var origin = { x: cRect.left, y: cRect.top };
      return {
        cards: nodes.map(function (el) {
          var b = boxOf(el, origin, s);
          return {
            id: el.dataset.person, name: el.dataset.name || "", year: el.dataset.year || "",
            death: el.dataset.death || "", gender: el.dataset.gender || "",
            root: el.classList.contains("leaf-node-root"),
            x: b.left, y: b.top, w: b.w, h: b.h
          };
        }),
        lines: svg.innerHTML
      };
    }
  };

  document.querySelectorAll("[data-map-action]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      var action = btn.dataset.mapAction;
      if (action === "zoom-in") map.zoomIn();
      else if (action === "zoom-out") map.zoomOut();
      else if (action === "fit") map.fit();
      else if (action === "root") map.centreOn(rootNode, Math.max(1, map.getFitScale()));
      else if (action === "reset-layout") autoArrange();
    });
  });

  var legend = document.getElementById("map-legend");
  var legendBtn = document.getElementById("map-legend-btn");
  if (legend && legendBtn) {
    legendBtn.addEventListener("click", function () {
      var open = legend.hidden;
      legend.hidden = !open;
      legendBtn.setAttribute("aria-expanded", String(open));
    });
  }

  // ------------------------------------------------------------- lifecycle --

  function layout() {
    arrange();
    renderLines();
    map.initialView();
    // A page may cover part of the board with its own card (e.g. analytics);
    // it names how many pixels on the right to keep clear.
    var clear = +(shell.dataset.clearRight || 0);
    if (clear && window.matchMedia("(min-width: 900px)").matches) map.panBy(-clear / 2, 0, true);
  }

  layout();
  window.addEventListener("load", layout);
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(layout);
  }

  /* The map keeps itself framed as the viewport changes (see tree-map.js).
     Only the node layout needs help here: the narrow-screen breakpoint
     resizes the cards, so the connectors have to be redrawn when the window
     actually crosses it. */
  var lastWidth = window.innerWidth;
  var resizeTimer = null;
  window.addEventListener("resize", function () {
    if (window.innerWidth === lastWidth) return;
    lastWidth = window.innerWidth;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      layout();
      syncPanelSpace();
      if (panel && !panel.hidden) setSheet(isWide() ? "full" : sheetState === "full" ? "full" : "peek", true);
    }, 180);
  });

  /* Enter opens whoever is selected — the quickest route on a desktop, and a
     keyboard-only way through the board. */
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && selectedId) { deselect(); return; }
    if (e.key !== "Enter" || !selectedId) return;
    var el = document.getElementById("node-" + selectedId);
    if (el) window.location.assign(el.dataset.url);
  });

  if (hint) {
    viewport.addEventListener("pointerdown", hideHint, { once: true });
    setTimeout(hideHint, 7000);
  }
})();


/* "Keyingi qadam" guide: can be minimised to a pill; comes back when the tree grows. */
(function () {
  "use strict";
  var card = document.getElementById("next-card"), pill = document.getElementById("nc-pill"), min = document.getElementById("nc-min");
  if (!card || !pill || !min) return;
  var key = "eshajara_nc_" + card.getAttribute("data-key"), people = card.getAttribute("data-people");
  function read() { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function write(v) { try { localStorage.setItem(key, v); } catch (e) { /* ignore */ } }
  function show(open) { card.hidden = !open; pill.hidden = open; }
  show(read() !== people);
  min.addEventListener("click", function () { write(people); show(false); });
  pill.addEventListener("click", function () { try { localStorage.removeItem(key); } catch (e) { /* ignore */ } show(true); });
})();