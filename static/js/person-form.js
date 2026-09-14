/* The add/edit person form: easy year entry and a photo preview.
   (Region and district pickers are combobox.js.)

   - Year fields take digits only (the phone shows its number pad), show the
     age they imply, and a "taxminan" tick marks a guess.
   - "Aniq sanasini bilaman" reveals the date picker; a picked date fills the
     year so the two never disagree.
   - Death year appears only once "Vafot etgan" is ticked. */
(function () {
  "use strict";


  var form = document.getElementById("person-form");
  if (!form) return;
  var thisYear = new Date().getFullYear();

  // ----------------------------------------------------------------- years --
  function ageText(year, approx, deathYear) {
    if (!year) return "";
    var end = deathYear || thisYear;
    var age = end - year;
    if (age < 0 || age > 130) return deathYear ? "" : "";
    var word = deathYear ? "yoshida vafot etgan" : "yoshda";
    return (approx ? "taxminan " : "") + age + " " + word;
  }

  function digits(input) {
    var clean = input.value.replace(/\D/g, "").slice(0, 4);
    if (clean !== input.value) input.value = clean;
    return clean.length >= 3 ? parseInt(clean, 10) : null;
  }

  function wireYear(name) {
    var input = form.querySelector('[name="' + name + '"]');
    if (!input) return null;
    var approx = form.querySelector('[name="' + name + '_approx"]');
    var note = form.querySelector('[data-note-for="' + name + '"]');
    var error = form.querySelector('[data-error-for="' + name + '"]');
    function check() {
      var y = digits(input);
      var bad = y && (y > thisYear || y < 100);
      if (error) {
        error.hidden = !bad;
        error.textContent = y > thisYear ? "Kelajakdagi yil bo'lmaydi." : "Yilni to'liq yozing, masalan: 1956";
      }
      return bad ? null : y;
    }
    input.addEventListener("input", refresh);
    if (approx) approx.addEventListener("change", refresh);
    return { input: input, approx: approx, note: note, value: check };
  }

  var birth = wireYear("birth_year");
  var death = wireYear("death_year");
  var dateBox = form.querySelector("[data-date-box]");
  var dateToggle = form.querySelector("[data-date-toggle]");
  var dateInput = form.querySelector('[name="birth_date"]');
  var deceased = form.querySelector("[data-deceased]");
  var deathBox = form.querySelector("[data-death-box]");

  function refresh() {
    var by = birth ? birth.value() : null;
    var dy = death && (!deceased || deceased.checked) ? death.value() : null;
    if (birth && birth.note) birth.note.textContent = dy ? "" : ageText(by, birth.approx && birth.approx.checked);
    if (death && death.note) death.note.textContent = by && dy ? ageText(by, (birth.approx && birth.approx.checked) || (death.approx && death.approx.checked), dy) : "";
    var err = form.querySelector('[data-error-for="death_order"]');
    if (err) err.hidden = !(by && dy && dy < by);
  }

  if (dateToggle && dateBox) {
    dateToggle.addEventListener("click", function () {
      dateBox.hidden = !dateBox.hidden;
      dateToggle.setAttribute("aria-expanded", String(!dateBox.hidden));
      if (!dateBox.hidden && dateInput) dateInput.focus();
    });
  }
  if (dateInput && birth) {
    dateInput.addEventListener("change", function () {
      if (!dateInput.value) return;
      birth.input.value = dateInput.value.slice(0, 4);
      if (birth.approx) birth.approx.checked = false;
      refresh();
    });
  }
  if (deceased && deathBox) {
    deceased.addEventListener("change", function () {
      deathBox.hidden = !deceased.checked;
      if (!deceased.checked && death) {
        death.input.value = "";
        if (death.approx) death.approx.checked = false;
      } else if (death) {
        death.input.focus();
      }
      refresh();
    });
  }
  refresh();

  // ---------------------------------------------------------- photo --
  var photo = form.querySelector('[name="photo"]');
  var thumb = document.getElementById("photo-thumb");
  if (photo && thumb) {
    photo.addEventListener("change", function () {
      var f = photo.files && photo.files[0];
      if (!f || !/^image\//.test(f.type)) return;
      var img = document.createElement("img");
      img.alt = "";
      img.src = URL.createObjectURL(f);
      thumb.innerHTML = "";
      thumb.appendChild(img);
    });
  }
})();
