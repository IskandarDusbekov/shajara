/* A searchable picker that replaces a plain <select> or text input.

     <select data-combo data-combo-placeholder="Viloyatni tanlang">…</select>
     <input  data-combo data-combo-custom data-combo-source="birth_region">

   The original field stays in the form (hidden) and keeps the value, so the
   form posts exactly as before and works without JavaScript too.

     - typing filters the list; apostrophes and letter case are ignored, so
       "gijduvon" finds "G'ijduvon"
     - arrow keys move, Enter picks, Escape closes
     - data-combo-custom: a name that is not in the list can be kept as typed
     - data-combo-source="<select name>": the options come from
       window.UZ_DISTRICTS for whatever that select currently holds */
(function () {
  "use strict";

  function norm(s) {
    return String(s || "").toLowerCase().replace(/[ʻʼ‘’'`]/g, "").replace(/\s+/g, " ").trim();
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  var uid = 0;

  function Combo(field) {
    var self = this;
    var isSelect = field.tagName === "SELECT";
    var allowCustom = field.hasAttribute("data-combo-custom");
    var sourceName = field.getAttribute("data-combo-source");
    var source = sourceName && field.form ? field.form.querySelector('[name="' + sourceName + '"]') : null;
    var placeholder = field.getAttribute("data-combo-placeholder") || field.getAttribute("placeholder") || "Tanlang";
    var id = "combo-" + (++uid);

    var wrap = el("div", "combo");
    var button = el("button", "combo-field");
    button.type = "button";
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false");
    if (field.id) {
      var label = document.querySelector('label[for="' + field.id + '"]');
      if (label) { label.setAttribute("for", id + "-btn"); }
    }
    button.id = id + "-btn";
    var valueText = el("span", "combo-value");
    var clear = el("span", "combo-clear");
    clear.setAttribute("role", "button");
    clear.setAttribute("aria-label", "Tozalash");
    clear.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>';
    var caret = el("span", "combo-caret");
    caret.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>';
    button.appendChild(valueText);
    button.appendChild(clear);
    button.appendChild(caret);

    var pop = el("div", "combo-pop");
    pop.hidden = true;
    var search = el("input", "combo-search");
    search.type = "search";
    search.setAttribute("autocomplete", "off");
    search.setAttribute("aria-controls", id + "-list");
    search.placeholder = "Qidirish…";
    var list = el("ul", "combo-list");
    list.id = id + "-list";
    list.setAttribute("role", "listbox");
    var empty = el("p", "combo-empty");
    pop.appendChild(search);
    pop.appendChild(list);
    pop.appendChild(empty);

    field.parentNode.insertBefore(wrap, field);
    wrap.appendChild(button);
    wrap.appendChild(pop);
    wrap.appendChild(field);
    field.classList.add("combo-native");
    field.setAttribute("tabindex", "-1");
    field.setAttribute("aria-hidden", "true");

    var items = [];      // {value, label}
    var shown = [];
    var active = -1;

    function options() {
      if (isSelect) {
        return Array.prototype.map.call(field.options, function (o) { return { value: o.value, label: o.textContent.trim() }; })
          .filter(function (o) { return o.value !== ""; });
      }
      var names = (source && window.UZ_DISTRICTS && window.UZ_DISTRICTS[source.value]) || [];
      return names.map(function (n) { return { value: n, label: n }; });
    }

    function current() {
      if (isSelect) {
        var o = field.options[field.selectedIndex];
        return o && o.value ? o.textContent.trim() : "";
      }
      return field.value;
    }

    function paint() {
      var v = current();
      valueText.textContent = v || placeholder;
      button.classList.toggle("is-empty", !v);
      clear.hidden = !v;
      button.disabled = !isSelect && !!source && !source.value && !field.value;
      if (button.disabled) valueText.textContent = field.getAttribute("data-combo-wait") || placeholder;
    }

    function setValue(value) {
      field.value = value;
      field.dispatchEvent(new Event("change", { bubbles: true }));
      paint();
    }

    function render() {
      var q = norm(search.value);
      items = options();
      shown = q ? items.filter(function (o) { return norm(o.label).indexOf(q) !== -1; }) : items.slice();
      if (q) {
        // names that start with the query first
        shown.sort(function (a, b) { return (norm(a.label).indexOf(q) === 0 ? 0 : 1) - (norm(b.label).indexOf(q) === 0 ? 0 : 1); });
      }
      list.innerHTML = "";
      var selected = isSelect ? field.value : field.value;
      shown.forEach(function (o, i) {
        var li = el("li", "combo-option");
        li.id = id + "-opt-" + i;
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", String(o.value === selected));
        var label = o.label, at = q ? norm(label).indexOf(q) : -1;
        if (at !== -1 && norm(label) === label.toLowerCase()) {
          li.appendChild(document.createTextNode(label.slice(0, at)));
          li.appendChild(el("mark", "", label.slice(at, at + q.length)));
          li.appendChild(document.createTextNode(label.slice(at + q.length)));
        } else {
          li.textContent = label;
        }
        li.addEventListener("mousedown", function (e) { e.preventDefault(); });
        li.addEventListener("click", function () { pick(o.value); });
        list.appendChild(li);
      });
      if (allowCustom && q && !items.some(function (o) { return norm(o.label) === q; })) {
        var li = el("li", "combo-option combo-custom");
        li.id = id + "-opt-" + shown.length;
        li.setAttribute("role", "option");
        li.textContent = "«" + search.value.trim() + "» deb yozish";
        li.addEventListener("mousedown", function (e) { e.preventDefault(); });
        li.addEventListener("click", function () { pick(search.value.trim()); });
        list.appendChild(li);
        shown.push({ value: search.value.trim(), label: search.value.trim(), custom: true });
      }
      empty.hidden = shown.length > 0;
      empty.textContent = items.length ? "Hech narsa topilmadi" : "Ro'yxat bo'sh — o'zingiz yozing";
      move(shown.length ? 0 : -1);
    }

    function move(i) {
      var opts = list.children;
      if (active >= 0 && opts[active]) opts[active].classList.remove("is-active");
      active = Math.max(-1, Math.min(i, opts.length - 1));
      if (active >= 0) {
        opts[active].classList.add("is-active");
        opts[active].scrollIntoView({ block: "nearest" });
        search.setAttribute("aria-activedescendant", opts[active].id);
      }
    }

    function open() {
      if (button.disabled) return;
      pop.hidden = false;
      wrap.classList.add("is-open");
      button.setAttribute("aria-expanded", "true");
      search.value = "";
      render();
      var sel = shown.findIndex(function (o) { return o.value === field.value; });
      if (sel >= 0) move(sel);
      setTimeout(function () { search.focus(); }, 0);
    }

    function close(focusButton) {
      pop.hidden = true;
      wrap.classList.remove("is-open");
      button.setAttribute("aria-expanded", "false");
      if (focusButton) button.focus();
    }

    function pick(value) {
      setValue(value);
      close(true);
    }

    button.addEventListener("click", function (e) {
      if (e.target.closest(".combo-clear")) {
        setValue("");
        return;
      }
      pop.hidden ? open() : close(false);
    });
    button.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
    });
    search.addEventListener("input", render);
    search.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); move(active + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(active - 1); }
      else if (e.key === "Enter") {
        e.preventDefault();
        if (active >= 0 && shown[active]) pick(shown[active].value);
        else if (allowCustom && search.value.trim()) pick(search.value.trim());
      } else if (e.key === "Escape") { e.preventDefault(); close(true); }
      else if (e.key === "Tab") { close(false); }
    });
    document.addEventListener("mousedown", function (e) {
      if (!pop.hidden && !wrap.contains(e.target)) close(false);
    });

    if (source) {
      source.addEventListener("change", function () {
        // A district from another region no longer fits.
        var names = (window.UZ_DISTRICTS && window.UZ_DISTRICTS[source.value]) || [];
        if (field.value && names.indexOf(field.value) === -1 && !field.hasAttribute("data-combo-keep")) setValue("");
        paint();
      });
    }
    field.addEventListener("change", paint);
    paint();
    self.refresh = paint;
  }

  function init(root) {
    (root || document).querySelectorAll("[data-combo]:not(.combo-native)").forEach(function (f) { new Combo(f); });
  }

  window.ShajaraCombo = { init: init };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { init(); });
  else init();
})();
