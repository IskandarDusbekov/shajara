/* Share boxes ([data-share]): copy the link, and use the phone's own share
   sheet where the browser has one. Boxes added later (the quiz result) call
   window.ShajaraShare.bind(box). */
(function () {
  "use strict";

  function bind(box) {
    if (!box || box.dataset.shareBound) return;
    box.dataset.shareBound = "1";
    var copy = box.querySelector("[data-share-copy]");
    var native = box.querySelector("[data-share-native]");

    if (copy) copy.addEventListener("click", function () {
      var label = copy.querySelector("span") || copy;
      var old = label.textContent;
      function done(ok) {
        label.textContent = ok ? "Nusxalandi!" : "Nusxalab bo'lmadi";
        setTimeout(function () { label.textContent = old; }, 1800);
      }
      var text = box.dataset.url;
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
      } else {
        var area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        var ok = false;
        try { ok = document.execCommand("copy"); } catch (e) {}
        area.remove();
        done(ok);
      }
    });

    if (native && navigator.share) {
      native.hidden = false;
      native.addEventListener("click", function () {
        navigator.share({ title: "e-Shajara", text: box.dataset.text, url: box.dataset.url }).catch(function () {});
      });
    }
  }

  window.ShajaraShare = { bind: bind };
  document.querySelectorAll("[data-share]").forEach(bind);
})();
