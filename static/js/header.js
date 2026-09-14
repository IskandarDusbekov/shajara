(function () {
  "use strict";

  // ---- the grouped menu panel ----
  var btn = document.getElementById("header-menu-btn");
  var nav = document.getElementById("header-nav");
  var backdrop = document.getElementById("header-menu-backdrop");

  if (btn && nav) {
    var setOpen = function (open) {
      nav.classList.toggle("open", open);
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      if (backdrop) backdrop.hidden = !open;
    };

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      setOpen(!nav.classList.contains("open"));
    });
    if (backdrop) backdrop.addEventListener("click", function () { setOpen(false); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && nav.classList.contains("open")) {
        setOpen(false);
        btn.focus();
      }
    });
  }

  // ---- theme toggle (light <-> dark) ----
  var toggle = document.getElementById("theme-toggle");
  if (toggle) {
    var isLight = function () { return document.documentElement.classList.contains("app-light"); };
    var syncLabel = function () {
      toggle.setAttribute("aria-pressed", isLight() ? "false" : "true");
      toggle.setAttribute("title", isLight() ? "Qorong'i rejim" : "Yorug' rejim");
    };
    syncLabel();
    toggle.addEventListener("click", function () {
      var light = document.documentElement.classList.toggle("app-light");
      try { localStorage.setItem("shajara_theme", light ? "light" : "dark"); } catch (e) { /* ignore */ }
      syncLabel();
    });
  }
})();
