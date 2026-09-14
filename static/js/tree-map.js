/* Pan/zoom surface for the tree canvas — the Google-Maps gestures:
   one finger drags, two fingers pinch to zoom, double tap zooms in, the
   wheel zooms under the cursor, and a flick keeps gliding.

   Usage:  var map = TreeMap.create(viewportEl, canvasEl, opts);
     opts.onChange(scale, fitScale)   — called on every view change
     opts.focus()                     — element the opening view centres on
     opts.dragTarget(event)           — return an element to move instead of
                                        panning the map (null = pan as usual)
     opts.onDragMove(el, dx, dy)      — deltas already divided by the zoom, so
                                        they arrive in the canvas's own units
     opts.onDragEnd(el, moved)
     opts.onDragArm(el)               — a finger has held a card long enough
                                        to pick it up (touch only)

   With a mouse a card moves as soon as it is dragged. With a finger that
   would make the map almost impossible to move — every swipe lands on some
   card — so on touch screens a swipe always pans, and a card is picked up
   only after it is pressed and held for a moment.
     opts.bounds()                    — the drawn area in canvas units,
                                        {x, y, w, h}; cards dragged outside the
                                        canvas box still count for fitting and
                                        for how far the map may be panned

   The canvas must be absolutely positioned with transform-origin: 0 0 and a
   width that does not depend on the viewport, so its children can be measured
   once and the geometry stays valid at every zoom level. */
(function (global) {
  "use strict";

  var MAX_SCALE = 3;
  var ABS_MIN_SCALE = 0.08;
  var READABLE_MIN = 0.5;    // a whole-tree fit below this is too small to read
  var TAP_SLOP = 9;          // px of movement still counted as a tap
  var DOUBLE_TAP_MS = 320;
  var HOLD_MS = 420;         // press-and-hold before a finger picks up a card
  var HOLD_SLOP = 8;         // how far the finger may wander while holding
  var EDGE_KEEP = 90;        // px of content that must stay inside the viewport
  var MAX_GLIDE = 1.2;       // px per ms; a full flick coasts about 240px

  function clamp(v, lo, hi) {
    return v < lo ? lo : (v > hi ? hi : v);
  }

  function create(viewport, canvas, options) {
    var opts = options || {};
    var tx = 0, ty = 0, scale = 1;
    var maxScale = opts.maxScale || MAX_SCALE;
    var fitScale = 1, minScale = ABS_MIN_SCALE;

    var ready = false;         // has the view been framed at least once?
    var userAdjusted = false;  // has the reader moved the view themselves?
    var prevView = { w: 0, h: 0 };

    var pointers = {};         // pointerId -> {x, y}
    var pointerCount = 0;
    var pinch = null;          // {dist, mx, my}
    var last = null;           // last position of the single panning pointer
    var downPos = null, dragged = false, suppressClick = false;
    var lastTap = 0, lastTapPos = null;
    var vx = 0, vy = 0, lastMoveAt = 0, glide = null;
    var drag = null;           // {el, moved} while a card is being carried
    var hold = null;           // {el, timer, pointerId} while a finger rests on a card
    var idleTimer = null;

    // ------------------------------------------------------------ geometry --

    function viewSize() {
      var r = viewport.getBoundingClientRect();
      return { w: r.width, h: r.height };
    }

    function bounds() {
      var b = opts.bounds ? opts.bounds() : null;
      if (b && b.w > 0 && b.h > 0) return b;
      return { x: 0, y: 0, w: canvas.offsetWidth, h: canvas.offsetHeight };
    }

    function measurable(v, b) {
      return !!(v.w && v.h && b.w && b.h);
    }

    function clampPan() {
      var v = viewSize(), b = bounds();
      var w = b.w * scale, h = b.h * scale;
      var keepX = Math.min(EDGE_KEEP, w * 0.5, v.w * 0.5);
      var keepY = Math.min(EDGE_KEEP, h * 0.5, v.h * 0.5);
      // The limits apply to the drawn area's on-screen edges, not the origin.
      tx = clamp(tx, -(w - keepX) - b.x * scale, v.w - keepX - b.x * scale);
      ty = clamp(ty, -(h - keepY) - b.y * scale, v.h - keepY - b.y * scale);
    }

    /* A permanently promoted compositor layer is rasterised once at 1:1 and
       then stretched as a bitmap, which turns text to mush past 100% zoom on a
       big screen. Promote it only while a gesture is running, then let the
       browser re-rasterise it sharply at rest. */
    function markInteracting() {
      canvas.classList.add("is-interacting");
      clearTimeout(idleTimer);
      idleTimer = setTimeout(function () {
        canvas.classList.remove("is-interacting");
      }, 220);
    }

    function apply() {
      clampPan();
      canvas.style.transform =
        "translate(" + tx.toFixed(2) + "px," + ty.toFixed(2) + "px) scale(" + scale.toFixed(4) + ")";
      if (opts.onChange) opts.onChange(scale, fitScale);
    }

    /** Zoom towards a point given in viewport-local pixels. */
    function zoomAt(px, py, next) {
      next = clamp(next, minScale, maxScale);
      if (next === scale) return;
      var wx = (px - tx) / scale;
      var wy = (py - ty) / scale;
      scale = next;
      tx = px - wx * scale;
      ty = py - wy * scale;
      apply();
    }

    function zoomBy(factor) {
      var v = viewSize();
      stopGlide();
      userAdjusted = true;
      zoomAt(v.w / 2, v.h / 2, scale * factor);
    }

    /** World (unscaled canvas) coordinates of an element's centre. */
    function worldCentre(el) {
      var vr = viewport.getBoundingClientRect();
      var er = el.getBoundingClientRect();
      return {
        x: (er.left + er.width / 2 - vr.left - tx) / scale,
        y: (er.top + er.height / 2 - vr.top - ty) / scale
      };
    }

    /* offsetX shifts the target point right of centre — used when a side
       panel covers the left part of the viewport. */
    function putWorldAtCentre(w, targetScale, offsetX) {
      var v = viewSize();
      if (targetScale != null) scale = clamp(targetScale, minScale, maxScale);
      tx = v.w / 2 + (offsetX || 0) - w.x * scale;
      ty = v.h / 2 - w.y * scale;
      apply();
    }

    function centreOn(el, targetScale, offsetX) {
      if (!el) return;
      stopGlide();
      userAdjusted = true;
      putWorldAtCentre(worldCentre(el), targetScale, offsetX);   // measure before scaling
    }

    function panBy(dx, dy, framing) {
      stopGlide();
      if (!framing) userAdjusted = true;
      tx += dx;
      ty += dy;
      apply();
    }

    /** The scale at which the whole tree is on screen at once. */
    function computeFitScale(v, b) {
      var pad = v.w < 560 ? 14 : 30;
      var s = Math.min((v.w - pad * 2) / b.w, (v.h - pad * 2) / b.h);
      fitScale = clamp(s, ABS_MIN_SCALE, 1);        // never blow a small tree up
      // Zooming out past the fit is allowed, so a huge tree can still be
      // surveyed whole even when it opens closer in.
      minScale = Math.max(ABS_MIN_SCALE, Math.min(fitScale, READABLE_MIN) * 0.7);
    }

    /** Frame the entire tree. Returns false while the element is unmeasurable
        (a hidden tab, a phone mid address-bar animation) so the caller can
        try again later. */
    function fit() {
      stopGlide();
      var v = viewSize(), b = bounds();
      if (!measurable(v, b)) return false;
      computeFitScale(v, b);
      scale = fitScale;
      tx = (v.w - b.w * scale) / 2 - b.x * scale;
      ty = (v.h - b.h * scale) / 2 - b.y * scale;
      ready = true;
      userAdjusted = false;
      prevView = v;
      apply();
      return true;
    }

    /* The opening view. A tree that fits legibly is simply framed whole; a big
       one would shrink to an unreadable smudge on a phone, so it opens at a
       readable zoom centred on the root person instead — the reader pans out
       from there, or taps ⛶ for the whole thing. */
    function initialView() {
      stopGlide();
      var v = viewSize(), b = bounds();
      if (!measurable(v, b)) return false;
      computeFitScale(v, b);

      var focus = opts.focus ? opts.focus() : null;
      var open = clamp(fitScale, Math.min(READABLE_MIN, 1), 1);
      if (!focus || open <= fitScale + 0.001) return fit();

      var w = worldCentre(focus);                   // measure before scaling
      scale = open;
      ready = true;
      userAdjusted = false;
      prevView = v;
      putWorldAtCentre(w);
      return true;
    }

    /* The viewport gets resized by all sorts of things: rotation, the mobile
       address bar, the header menu opening, or simply becoming measurable for
       the first time. Until the reader has moved the view themselves we keep
       re-framing it; afterwards we just hold their centre point steady. */
    function handleResize() {
      var v = viewSize();
      if (!v.w || !v.h) return;
      if (!ready || !userAdjusted) { initialView(); return; }
      if (prevView.w && prevView.h) {
        var wx = (prevView.w / 2 - tx) / scale;
        var wy = (prevView.h / 2 - ty) / scale;
        tx = v.w / 2 - wx * scale;
        ty = v.h / 2 - wy * scale;
      }
      prevView = v;
      apply();
    }

    // -------------------------------------------------------------- inertia --

    function stopGlide() {
      if (glide) { cancelAnimationFrame(glide); glide = null; }
      vx = vy = 0;
    }

    function startGlide() {
      if (Math.abs(vx) < 0.05 && Math.abs(vy) < 0.05) return;
      var step = function () {
        markInteracting();
        tx += vx * 16;
        ty += vy * 16;
        vx *= 0.92;
        vy *= 0.92;
        apply();
        if (Math.abs(vx) > 0.02 || Math.abs(vy) > 0.02) {
          glide = requestAnimationFrame(step);
        } else {
          glide = null;
        }
      };
      glide = requestAnimationFrame(step);
    }

    // ------------------------------------------------------------- pointers --

    function localPoint(e) {
      var r = viewport.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    }

    function twoPointers() {
      var ids = Object.keys(pointers);
      if (ids.length < 2) return null;
      var a = pointers[ids[0]], b = pointers[ids[1]];
      var dx = b.x - a.x, dy = b.y - a.y;
      var r = viewport.getBoundingClientRect();
      return {
        dist: Math.max(1, Math.sqrt(dx * dx + dy * dy)),
        mx: (a.x + b.x) / 2 - r.left,
        my: (a.y + b.y) / 2 - r.top
      };
    }

    function dist(ax, ay, bx, by) {
      return Math.sqrt((ax - bx) * (ax - bx) + (ay - by) * (ay - by));
    }

    function onPointerDown(e) {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      stopGlide();
      userAdjusted = true;
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
      pointerCount = Object.keys(pointers).length;

      if (pointerCount === 1) {
        last = { x: e.clientX, y: e.clientY };
        downPos = { x: e.clientX, y: e.clientY };
        dragged = false;
        suppressClick = false;
        lastMoveAt = Date.now();
        var target = opts.dragTarget ? opts.dragTarget(e) : null;
        cancelHold();
        drag = null;
        if (target && e.pointerType === "mouse") {
          drag = { el: target, moved: false };
        } else if (target) {
          startHold(target, e.pointerId);
        }
        viewport.classList.add(drag ? "is-carrying" : "is-panning");
      } else if (pointerCount === 2) {
        cancelHold();
        if (drag) {                 // a second finger turns a card drag into a pinch
          if (opts.onDragEnd) opts.onDragEnd(drag.el, drag.moved);
          drag = null;
          viewport.classList.remove("is-carrying");
        }
        pinch = twoPointers();
        dragged = true;             // a pinch is never a tap
        suppressClick = true;
        Object.keys(pointers).forEach(function (id) { capture(+id); });
      }
    }

    function startHold(el, pointerId) {
      hold = {
        el: el,
        pointerId: pointerId,
        timer: setTimeout(function () {
          if (!hold || dragged || pointerCount !== 1) { cancelHold(); return; }
          drag = { el: hold.el, moved: false, lifted: true };
          hold = null;
          suppressClick = true;     // lifting a card is not a tap on it
          viewport.classList.remove("is-panning");
          viewport.classList.add("is-carrying");
          capture(pointerId);
          try { if (navigator.vibrate) navigator.vibrate(12); } catch (err) { /* ignore */ }
          if (opts.onDragArm) opts.onDragArm(drag.el);
        }, HOLD_MS)
      };
    }

    function cancelHold() {
      if (hold) clearTimeout(hold.timer);
      hold = null;
    }

    /* Pointer capture is taken only once a gesture has really begun. Taking it
       on pointerdown retargets the whole press to the viewport, so a plain
       click never reaches the card under the cursor — no selection, no sheet,
       no highlighted branches. */
    function capture(pointerId) {
      try { viewport.setPointerCapture(pointerId); } catch (err) { /* ignore */ }
    }

    function onPointerMove(e) {
      if (!pointers[e.pointerId]) return;
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
      pointerCount = Object.keys(pointers).length;

      if (pointerCount >= 2) {
        markInteracting();
        var now = twoPointers();
        if (pinch && now) {
          zoomAt(now.mx, now.my, scale * (now.dist / pinch.dist));
          tx += now.mx - pinch.mx;   // two-finger drag, on top of the pinch
          ty += now.my - pinch.my;
          apply();
        }
        pinch = now;
        return;
      }

      if (!last) return;
      var dx = e.clientX - last.x, dy = e.clientY - last.y;
      last = { x: e.clientX, y: e.clientY };
      // A finger that moves off before the hold completes wanted to pan.
      if (hold && downPos && dist(e.clientX, e.clientY, downPos.x, downPos.y) > HOLD_SLOP) cancelHold();
      // A card already lifted follows the finger from the first pixel.
      var slop = drag && drag.lifted ? 0 : TAP_SLOP;
      if (!dragged && downPos && dist(e.clientX, e.clientY, downPos.x, downPos.y) > slop) {
        dragged = true;
        suppressClick = true;
        capture(e.pointerId);
      }
      if (!dragged) return;

      var t = Date.now();
      var dt = Math.max(1, t - lastMoveAt);
      lastMoveAt = t;
      markInteracting();

      if (drag) {
        // The card follows the finger, so the on-screen delta is converted
        // back into the canvas's own unscaled units.
        drag.moved = true;
        if (opts.onDragMove) opts.onDragMove(drag.el, dx / scale, dy / scale);
        return;
      }

      // A coarse or stalled move would otherwise read as a violent flick and
      // throw the tree off-screen, so the glide speed is bounded.
      vx = clamp(dx / dt, -MAX_GLIDE, MAX_GLIDE);
      vy = clamp(dy / dt, -MAX_GLIDE, MAX_GLIDE);
      tx += dx;
      ty += dy;
      apply();
    }

    function onPointerUp(e) {
      if (!pointers[e.pointerId]) return;
      delete pointers[e.pointerId];
      pointerCount = Object.keys(pointers).length;
      cancelHold();
      if (viewport.hasPointerCapture && viewport.hasPointerCapture(e.pointerId)) {
        try { viewport.releasePointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      }

      if (pointerCount === 1) {
        // Lifting one finger of a pinch: re-anchor so the view doesn't jump.
        var id = Object.keys(pointers)[0];
        last = { x: pointers[id].x, y: pointers[id].y };
        pinch = null;
        return;
      }
      if (pointerCount > 1) { pinch = twoPointers(); return; }

      viewport.classList.remove("is-panning", "is-carrying");
      pinch = null;
      last = null;

      if (drag) {
        var wasLifted = drag.lifted;
        if (opts.onDragEnd) opts.onDragEnd(drag.el, drag.moved);
        drag = null;
        if (dragged || wasLifted) return;   // a real move or a hold, so not a tap
      } else if (dragged) {
        if (Date.now() - lastMoveAt < 90) startGlide();
        return;
      }

      // A clean tap: check for a double tap before letting the click through.
      var p = localPoint(e);
      var now = Date.now();
      if (now - lastTap < DOUBLE_TAP_MS && lastTapPos && dist(p.x, p.y, lastTapPos.x, lastTapPos.y) < 40) {
        suppressClick = true;
        lastTap = 0;
        zoomAt(p.x, p.y, scale * 1.8);
        return;
      }
      lastTap = now;
      lastTapPos = p;
    }

    function onPointerCancel(e) {
      cancelHold();
      delete pointers[e.pointerId];
      pointerCount = Object.keys(pointers).length;
      if (pointerCount === 0) {
        viewport.classList.remove("is-panning", "is-carrying");
        if (drag && opts.onDragEnd) opts.onDragEnd(drag.el, drag.moved);
        drag = null;
        last = null;
        pinch = null;
      }
    }

    function onWheel(e) {
      e.preventDefault();
      stopGlide();
      markInteracting();
      userAdjusted = true;
      var p = localPoint(e);
      var delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      // ctrlKey means a trackpad pinch, which sends much smaller deltas.
      var k = e.ctrlKey ? 0.99 : 0.9985;
      zoomAt(p.x, p.y, scale * Math.pow(k, delta));
    }

    function onClickCapture(e) {
      if (!suppressClick) return;
      suppressClick = false;
      e.preventDefault();
      e.stopPropagation();
    }

    function onKeyDown(e) {
      var step = 60;
      if (e.key === "+" || e.key === "=") { zoomBy(1.25); }
      else if (e.key === "-" || e.key === "_") { zoomBy(1 / 1.25); }
      else if (e.key === "0") { fit(); }
      else if (e.key === "ArrowLeft") { userAdjusted = true; tx += step; apply(); }
      else if (e.key === "ArrowRight") { userAdjusted = true; tx -= step; apply(); }
      else if (e.key === "ArrowUp") { userAdjusted = true; ty += step; apply(); }
      else if (e.key === "ArrowDown") { userAdjusted = true; ty -= step; apply(); }
      else { return; }
      e.preventDefault();
    }

    if (typeof ResizeObserver === "function") {
      new ResizeObserver(handleResize).observe(viewport);
    } else {
      global.addEventListener("resize", handleResize);
    }

    viewport.addEventListener("pointerdown", onPointerDown);
    // The long press that lifts a card must not open the phone's context menu.
    viewport.addEventListener("contextmenu", function (e) {
      if (e.target.closest && opts.dragTarget && opts.dragTarget(e)) e.preventDefault();
    });
    viewport.addEventListener("pointermove", onPointerMove);
    viewport.addEventListener("pointerup", onPointerUp);
    viewport.addEventListener("pointercancel", onPointerCancel);
    // Uncaptured presses can end outside the board; the handlers ignore
    // pointers they are not tracking, so the second delivery is harmless.
    global.addEventListener("pointerup", onPointerUp);
    global.addEventListener("pointercancel", onPointerCancel);
    viewport.addEventListener("wheel", onWheel, { passive: false });
    viewport.addEventListener("click", onClickCapture, true);
    viewport.addEventListener("keydown", onKeyDown);
    // Safari fires its own pinch gestures on top of pointer events.
    ["gesturestart", "gesturechange", "gestureend"].forEach(function (name) {
      viewport.addEventListener(name, function (e) { e.preventDefault(); });
    });

    return {
      fit: fit,
      initialView: initialView,
      centreOn: centreOn,
      panBy: panBy,
      zoomBy: zoomBy,
      zoomIn: function () { zoomBy(1.3); },
      zoomOut: function () { zoomBy(1 / 1.3); },
      getScale: function () { return scale; },
      getFitScale: function () { return fitScale; },
      isReady: function () { return ready; },
      refresh: apply,
      /** Viewport pixel (e.g. a click) -> unscaled canvas coordinates. */
      toWorld: function (clientX, clientY) {
        var r = viewport.getBoundingClientRect();
        return { x: (clientX - r.left - tx) / scale, y: (clientY - r.top - ty) / scale };
      },
      /** Bring a canvas point to the middle of the viewport. */
      centreOnPoint: function (x, y, targetScale, offsetX) {
        stopGlide();
        userAdjusted = true;
        putWorldAtCentre({ x: x, y: y }, targetScale, offsetX);
      }
    };
  }

  global.TreeMap = { create: create };
})(window);
