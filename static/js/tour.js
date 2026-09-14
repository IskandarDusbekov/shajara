/* First-run guide.

   A new account gets it once: every important button is lit up in turn with
   a short note on what it does, and at the key moments the guide waits for
   the person to press the real button themselves — create a family tree,
   open their own card, add the first relative. The walk crosses pages, so
   progress lives in localStorage; the server is told when it is finished or
   dismissed, and «Yordam» in the menu replays it at any time.

   Step fields
     page     url name the step belongs to
     el       CSS selector of the thing to light up (none → centred card)
     title, body
     action   "click": wait until the person presses the lit element
              (clickIn narrows which part of it counts)
     require  selector of an input that must be filled before «Keyingi»
     primary  label of the main button (default «Keyingi»)
*/
(function () {
  "use strict";

  var CFG = window.SHAJARA_TOUR;
  if (!CFG) return;

  var STEPS = [
    // ------------------------------------------------------------ start page
    { page: "my_trees", title: "e-Shajara'ga xush kelibsiz!", primary: "Boshlash",
      body: "Bir-ikki daqiqada asosiy tugmalar nima qilishini ko'rsataman, keyin birinchi oilaviy shajarangizni birga tuzamiz. Qadamlarni o'zingiz bosib bajarasiz." },
    { page: "my_trees", el: '[data-tour="nav-trees"]', title: "Shajaralarim",
      body: "Siz tuzgan va qarindoshlaringiz sizga ulashgan barcha shajaralar shu yerda turadi." },
    { page: "my_trees", el: '[data-tour="nav-library"]', title: "Kutubxona",
      body: "Hamma uchun ochiq shajaralar: tarixiy shaxslar, sulolalar. O'rganish, darsda ko'rsatish va o'zingizni sinash uchun." },
    { page: "my_trees", el: '[data-tour="nav-maps"]', title: "Tarixiy xaritalar",
      body: "Eski xaritalar ustida joylar, yillar va yurish yo'nalishlari. O'zingiz ham xarita yuklab belgilashingiz mumkin." },
    { page: "my_trees", el: '[data-tour="nav-requests"]', title: "So'rovlar",
      body: "Boshqa foydalanuvchilar shajaralarni bog'lash uchun yuborgan so'rovlar. Yangisi kelsa, shu yerda raqam chiqadi." },
    { page: "my_trees", el: '[data-tour="new-tree"]', title: "Yangi shajara",
      body: "Istalgan sahifadan yangi shajara boshlash tugmasi." },
    { page: "my_trees", el: "#theme-toggle", title: "Yorug' yoki qorong'i",
      body: "Ko'zingizga qulay rejimni tanlang — tanlov eslab qolinadi." },
    { page: "my_trees", el: "#header-menu-btn", title: "Menyu",
      body: "Profil, odam qidirish, PDF kitob va sozlamalar shu yerda. «Yordam» bandi shu qo'llanmani qayta ochadi." },
    { page: "my_trees", el: ".pf-start-tile.is-fam", action: "click", title: "Qani, boshladik!",
      body: "«Oilaviy shajara» tugmasini bosing — o'z oilangiz shajarasini tuzamiz." },

    // ----------------------------------------------------------- create form
    { page: "tree_create", el: ".pf-choices", title: "Shajara turi",
      body: "«Oilaviy» — o'z oilangiz uchun. «Ta'limiy» — tarixiy shaxs yoki sulola uchun. Hozir oilaviy tanlangan." },
    { page: "tree_create", el: '[data-tour="tree-name"]', require: "#id_tree_name", title: "Shajara nomi",
      body: "Nom yozing, masalan «Karimovlar oilasi». Yozganingizdan keyin «Keyingi» ochiladi." },
    { page: "tree_create", el: '[data-tour="root-person"]', require: "#id_first_name", title: "Kimdan boshlaymiz?",
      body: "Odatda o'zingizdan: ismingizni yozing va jinsingizni tanlang. Ota-ona, farzandlarni keyin qo'shasiz." },
    { page: "tree_create", el: '[data-tour="visibility"]', title: "Kim ko'radi",
      body: "«Shaxsiy» — faqat siz va taklif qilgan qarindoshlaringiz. «Ommaviy» — Kutubxonada hamma ko'radi. Keyin sozlamalardan o'zgartirsa bo'ladi." },
    { page: "tree_create", el: '[data-tour="create-submit"]', action: "click", title: "Yaratamiz",
      body: "«Shajarani yaratish» tugmasini bosing." },

    // -------------------------------------------------------------- tree map
    { page: "index", el: ".leaf-node-root", title: "Bu — siz",
      body: "Tojli karta — shajaraning bosh shaxsi. Butun oila shu kartadan tarqaladi: ota-ona tepada, farzandlar pastda." },
    { page: "index", el: ".map-hud", title: "Xarita tugmalari",
      body: "Kattalashtirish, kichiklashtirish, hammasini ko'rsatish, yuklab olish va bosh shaxsga qaytish. Xaritaning o'zini sichqoncha yoki barmoq bilan surasiz." },
    { page: "index", el: "#map-export-btn", title: "Yuklab olish",
      body: "Shajarani chiroyli PDF kitob yoki tiniq rasm sifatida saqlaysiz — chop etish va Telegram'da ulashish uchun." },
    { page: "index", el: '[data-tour="nav-about"]', title: "Shajara haqida",
      body: "Nechta avlod, nechta odam, kimlar qo'shgan — umumiy ma'lumotlar." },
    { page: "index", el: '[data-tour="nav-members"]', title: "A'zolar",
      body: "Qarindoshlaringizga taklif havolasini yuborasiz — ular ham o'z shoxini qo'shadi va shajara birga to'ladi." },
    { page: "index", el: '[data-tour="nav-quiz"]', title: "Test",
      body: "Oilangiz bo'yicha qiziqarli savollar: kim kimning otasi, qachon tug'ilgan." },
    { page: "index", el: ".leaf-node-root", action: "click", title: "Kartangizni bosing",
      body: "Endi birinchi qarindoshni qo'shamiz. Tojli kartangizni bosing." },
    { page: "index", el: "#pp-add", action: "click", title: "Qarindosh qo'shish",
      body: "Ochilgan oynada «Qarindosh qo'shish» (+) tugmasini bosing." },
    { page: "index", el: "#pp-relations", action: "click", clickIn: "a[data-relation]", title: "Kimni qo'shasiz?",
      body: "Birini tanlang — masalan «Otasi»." },

    // ------------------------------------------------------ add a relative
    { page: "add_relative", el: '[data-tour="person-name"]', require: "#id_first_name", title: "Ismini yozing",
      body: "Faqat ism majburiy. Familiya va otasining ismini bilsangiz, ular ham yordam beradi." },
    { page: "add_relative", el: '[data-tour="years"]', title: "Yillari",
      body: "Tug'ilgan yilini 4 raqam bilan yozing. Aniq bilmasangiz «taxminan»ni belgilang, umuman bilmasangiz bo'sh qoldiring." },
    { page: "add_relative", el: '[data-tour="birth-place"]', title: "Tug'ilgan joyi",
      body: "Ixtiyoriy. Viloyat va tumanni qidirib tanlaysiz — boshqa shajaralardagi qarindoshlarni topishga yordam beradi." },
    { page: "add_relative", el: '[data-tour="save"]', action: "click", title: "Saqlang",
      body: "«Saqlash» tugmasini bosing." },

    // ---------------------------------------------------------- person page
    { page: "person_detail", el: ".relation-section", title: "Qarindosh qo'shildi!",
      body: "Bu shaxs sahifasi. Ota-ona, aka-uka, turmush o'rtog'i va farzandlarni shu yerdagi «qo'shish» tugmalari bilan ham qo'shasiz." },
    { page: "person_detail", el: ".story-compose", title: "Hikoyalar",
      body: "Bu inson haqida xotira yoki voqea yozing — u PDF kitobda ham chiqadi." },
    { page: "person_detail", el: ".back-link", title: "Tayyor!", primary: "Tugatish",
      body: "Shajarangiz boshlandi. Chapdagi havola orqali xaritaga qaytasiz. Qo'llanmani istalgan payt menyudagi «Yordam» orqali qayta ochishingiz mumkin." }
  ];

  var STORE = "eshajara_tour_" + CFG.user;
  var STALE_MS = 6 * 60 * 60 * 1000;

  function load() {
    try {
      var s = JSON.parse(localStorage.getItem(STORE) || "null");
      if (s && Date.now() - s.t < STALE_MS) return s;
    } catch (e) {}
    return null;
  }
  function save(i, from) {
    try { localStorage.setItem(STORE, JSON.stringify({ i: i, from: from, t: Date.now() })); } catch (e) {}
  }
  function clear() { try { localStorage.removeItem(STORE); } catch (e) {} }

  function markDone() {
    CFG.pending = false;
    clear();
    try {
      fetch(CFG.doneUrl, { method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": CFG.csrf } });
    } catch (e) {}
  }

  function visible(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    var cs = getComputedStyle(el);
    return cs.visibility !== "hidden" && cs.display !== "none";
  }
  function find(step) { return step.el ? document.querySelector(step.el) : null; }

  // ------------------------------------------------------------------ view
  var ui = null, index = -1, target = null, raf = 0, lastKey = "";

  function build() {
    ui = document.createElement("div");
    ui.className = "tour-layer";
    ui.innerHTML =
      '<div class="tour-shade" data-s="t"></div><div class="tour-shade" data-s="l"></div>' +
      '<div class="tour-shade" data-s="r"></div><div class="tour-shade" data-s="b"></div>' +
      '<div class="tour-block"></div><div class="tour-ring"></div>' +
      '<div class="tour-pop" role="dialog" aria-modal="false" aria-labelledby="tour-title">' +
      '  <div class="tour-top"><span class="tour-count"></span>' +
      '    <button type="button" class="tour-x" aria-label="Qo\'llanmani yopish" title="Qo\'llanmani yopish">' +
      '      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>' +
      '  <div class="tour-bar"><i></i></div>' +
      '  <h2 class="tour-title" id="tour-title"></h2><p class="tour-body"></p>' +
      '  <p class="tour-wait"><span class="tour-tap"></span><span class="tour-wait-text"></span></p>' +
      '  <div class="tour-nav"><button type="button" class="tour-skip">O\'tkazib yuborish</button><span class="tour-gap"></span>' +
      '    <button type="button" class="tour-back">Orqaga</button><button type="button" class="tour-next">Keyingi</button></div>' +
      "</div>";
    document.body.appendChild(ui);
    ui.querySelector(".tour-x").addEventListener("click", dismiss);
    ui.querySelector(".tour-skip").addEventListener("click", dismiss);
    ui.querySelector(".tour-back").addEventListener("click", back);
    ui.querySelector(".tour-next").addEventListener("click", next);
    document.addEventListener("click", onClick, true);
    document.addEventListener("input", onInput, true);
    document.addEventListener("keydown", onKey, true);
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
  }

  function destroy() {
    if (!ui) return;
    cancelAnimationFrame(raf);
    document.removeEventListener("click", onClick, true);
    document.removeEventListener("input", onInput, true);
    document.removeEventListener("keydown", onKey, true);
    window.removeEventListener("scroll", measure, true);
    window.removeEventListener("resize", measure);
    ui.remove();
    ui = null;
    index = -1;
    document.documentElement.classList.remove("tour-on");
  }

  function pageSteps() {
    var out = [];
    STEPS.forEach(function (s, i) { if (s.page === CFG.page) out.push(i); });
    return out;
  }

  // First usable step at or after i on this page (targets can be missing:
  // a viewer has no «add» button, a phone hides some links).
  function usable(i, dir) {
    dir = dir || 1;
    while (i >= 0 && i < STEPS.length && STEPS[i].page === CFG.page) {
      var s = STEPS[i];
      if (!s.el || visible(find(s))) return i;
      i += dir;
    }
    return -1;
  }

  function show(i) {
    var at = usable(i, 1);
    if (at < 0) {
      // Nothing left to light up on this page. If a skipped step was one the
      // person had to press (say, a viewer has no «add» button) the walk
      // cannot go on, so it ends; otherwise it waits for the next page.
      var j = i, skippedAction = false;
      while (j < STEPS.length && STEPS[j].page === CFG.page) { skippedAction = skippedAction || STEPS[j].action === "click"; j++; }
      if (j < STEPS.length && !skippedAction) { save(j, j); destroy(); return; }
      finish();
      return;
    }
    if (!ui) build();
    document.documentElement.classList.add("tour-on");
    index = at;
    save(index, index);
    var step = STEPS[index];
    target = find(step);
    if (target && !isFixed(target)) {
      if (window.innerWidth < 640) {
        var header = document.querySelector(".app-header");
        var headerBottom = header && isFixed(header) ? header.getBoundingClientRect().bottom : 0;
        target.style.scrollMarginTop = Math.round(Math.max(0, headerBottom) + 20) + "px";
        target.scrollIntoView({ block: "start", inline: "nearest", behavior: "smooth" });
      } else {
        target.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
      }
    }

    var ids = pageSteps();
    var pos = ids.indexOf(index);
    ui.querySelector(".tour-count").textContent = "Qadam " + (index + 1) + " / " + STEPS.length;
    ui.querySelector(".tour-bar i").style.width = Math.round((index + 1) / STEPS.length * 100) + "%";
    ui.querySelector(".tour-title").textContent = step.title;
    ui.querySelector(".tour-body").textContent = step.body;

    var wait = ui.querySelector(".tour-wait");
    var nextBtn = ui.querySelector(".tour-next");
    wait.hidden = step.action !== "click";
    ui.querySelector(".tour-wait-text").textContent = step.action === "click" ? "Belgilangan joyni bosing" : "";
    nextBtn.hidden = step.action === "click";
    nextBtn.textContent = step.primary || (isLast() ? "Tugatish" : "Keyingi");
    var prev = usable(index - 1, -1);
    ui.querySelector(".tour-back").hidden = pos <= 0 || prev < 0;
    ui.querySelector(".tour-skip").hidden = index !== 0 && !(!step.el && pos === 0);
    ui.classList.toggle("is-centre", !step.el);
    ui.classList.toggle("is-action", step.action === "click" || !!step.require);
    syncRequire();

    lastKey = "";
    cancelAnimationFrame(raf);
    loop();
    setTimeout(measure, 400);   // after a smooth scroll settles, even where frames are throttled
    setTimeout(function () {
      var focusEl = step.require ? document.querySelector(step.require) : nextBtn.hidden ? null : nextBtn;
      if (focusEl && ui) { try { focusEl.focus({ preventScroll: true }); } catch (e) {} }
    }, 350);
  }

  function isLast() { return index === STEPS.length - 1; }
  function isFixed(el) {
    for (var n = el; n && n !== document.body; n = n.parentElement) {
      var p = getComputedStyle(n).position;
      if (p === "fixed" || p === "sticky") return true;
    }
    return false;
  }

  function syncRequire() {
    var step = STEPS[index];
    var nextBtn = ui.querySelector(".tour-next");
    if (!step.require) { nextBtn.disabled = false; return; }
    var input = document.querySelector(step.require);
    nextBtn.disabled = !(input && input.value.trim());
  }

  // Keep the spotlight glued to its target while the page scrolls, animates or resizes.
  function loop() {
    measure();
    if (ui) raf = requestAnimationFrame(loop);
  }

  function measure() {
    if (!ui) return;
    var step = STEPS[index];
    var vw = window.innerWidth, vh = window.innerHeight;
    var r = null;
    if (step.el) {
      target = find(step) || target;
      if (target && visible(target)) r = target.getBoundingClientRect();
    }
    var key = r ? [r.left, r.top, r.width, r.height, vw, vh].map(Math.round).join(",") : "c" + vw + "x" + vh;
    if (key !== lastKey) {
      lastKey = key;
      place(r, vw, vh);
    }
  }

  function place(r, vw, vh) {
    var pad = 8;
    var shades = ui.querySelectorAll(".tour-shade");
    var ring = ui.querySelector(".tour-ring");
    var block = ui.querySelector(".tour-block");
    var pop = ui.querySelector(".tour-pop");
    var step = STEPS[index];

    if (!r) {
      set(shades[0], 0, 0, vw, vh);
      [shades[1], shades[2], shades[3]].forEach(function (s) { set(s, 0, 0, 0, 0); });
      ring.style.display = "none";
      block.style.display = "none";
      pop.style.left = Math.max(12, (vw - pop.offsetWidth) / 2) + "px";
      pop.style.top = Math.max(12, (vh - pop.offsetHeight) / 2) + "px";
      return;
    }
    var x = Math.max(0, r.left - pad), y = Math.max(0, r.top - pad);
    var x2 = Math.min(vw, r.right + pad), y2 = Math.min(vh, r.bottom + pad);
    set(shades[0], 0, 0, vw, y);
    set(shades[1], 0, y, x, y2 - y);
    set(shades[2], x2, y, vw - x2, y2 - y);
    set(shades[3], 0, y2, vw, vh - y2);
    ring.style.display = "block";
    set(ring, x, y, x2 - x, y2 - y);
    // Info steps look but don't touch; action and typing steps let the hole through.
    var passThrough = step.action === "click" || !!step.require;
    block.style.display = passThrough ? "none" : "block";
    set(block, x, y, x2 - x, y2 - y);

    var pw = pop.offsetWidth, ph = pop.offsetHeight, gap = 14;
    var left, top;
    if (vw < 640) {
      // Phones: the card docks to the bottom edge, or to the top when the
      // lit element itself sits low (the map buttons, a save bar).
      left = 12;
      var coverIfBottom = Math.max(0, y2 - (vh - ph - 12)), coverIfTop = Math.max(0, 12 + ph - y);
      top = coverIfTop < coverIfBottom ? 12 : vh - ph - 12;
    } else {
      left = Math.min(Math.max(12, r.left + r.width / 2 - pw / 2), vw - pw - 12);
      if (y2 + gap + ph <= vh - 12) top = y2 + gap;
      else if (y - gap - ph >= 12) top = y - gap - ph;
      else {
        top = Math.min(Math.max(12, r.top + r.height / 2 - ph / 2), vh - ph - 12);
        left = (x2 + gap + pw <= vw - 12) ? x2 + gap : Math.max(12, x - gap - pw);
      }
    }
    pop.style.left = left + "px";
    pop.style.top = top + "px";
  }

  function set(el, x, y, w, h) {
    el.style.left = x + "px"; el.style.top = y + "px";
    el.style.width = Math.max(0, w) + "px"; el.style.height = Math.max(0, h) + "px";
  }

  // -------------------------------------------------------------- actions
  function next() {
    var step = STEPS[index];
    if (step.require) {
      var input = document.querySelector(step.require);
      if (!input || !input.value.trim()) { if (input) input.focus(); return; }
    }
    if (isLast()) { finish(); return; }
    show(index + 1);
  }
  function back() {
    var prev = usable(index - 1, -1);
    if (prev >= 0) show(prev);
  }

  function onInput(e) {
    if (!ui) return;
    var step = STEPS[index];
    if (step.require && e.target.matches && e.target.matches(step.require)) syncRequire();
  }

  function onKey(e) {
    if (!ui) return;
    if (e.key === "Escape") { e.stopPropagation(); dismiss(); }
    else if (e.key === "Enter" && STEPS[index].require && document.activeElement && document.activeElement.matches(STEPS[index].require)) {
      e.preventDefault();
      next();
    }
  }

  function onClick(e) {
    if (!ui || ui.contains(e.target)) return;
    var step = STEPS[index];
    if (step.action !== "click" || !target) return;
    var hit = step.clickIn ? e.target.closest(step.clickIn) : e.target;
    if (!hit || !target.contains(hit)) return;
    var from = index;
    var following = index + 1;
    save(following, from);
    // A link navigates away and the next page picks the walk up; a button
    // that opens something here moves on once the page has reacted.
    setTimeout(function () {
      if (!ui || index !== from) return;
      if (following < STEPS.length && STEPS[following].page === CFG.page) {
        waitFor(following, 0);
      } else {
        destroy();
      }
    }, 120);
  }

  function waitFor(i, tries) {
    if (!ui) return;
    if (visible(find(STEPS[i])) || tries > 25) { show(i); return; }
    setTimeout(function () { waitFor(i, tries + 1); }, 80);
  }

  function dismiss() {
    destroy();
    markDone();
  }

  function finish() {
    destroy();
    markDone();
  }

  // ----------------------------------------------------------------- start
  function startHere() {
    var ids = pageSteps();
    if (!ids.length) {
      save(0, 0);
      window.location.href = CFG.startUrl;
      return;
    }
    destroy();
    show(ids[0]);
  }

  window.startShajaraTour = startHere;

  function boot() {
    var replay = document.getElementById("tour-replay");
    if (replay) replay.addEventListener("click", function (e) {
      e.preventDefault();
      var menuBtn = document.getElementById("header-menu-btn");
      if (menuBtn && menuBtn.getAttribute("aria-expanded") === "true") menuBtn.click();
      startHere();
    });

    var state = load();
    if (state && STEPS[state.i]) {
      if (STEPS[state.i].page === CFG.page) { setTimeout(function () { show(state.i); }, 250); return; }
      if (STEPS[state.from] && STEPS[state.from].page === CFG.page) { setTimeout(function () { show(state.from); }, 250); return; }
      return;   // paused on another page; resume when the person gets there
    }
    if (CFG.pending) {
      var ids = pageSteps();
      if (ids.length) setTimeout(function () { show(ids[0]); }, 400);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
