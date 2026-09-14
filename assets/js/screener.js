/* Petralysis — screener search, filter and sort.
 *
 * Progressive enhancement over a table that is already complete in the HTML.
 * Without this file the table reads in catalog order; with it, the controls
 * are revealed, rows are filtered by name or symbol and by category, and
 * column headers sort. Sort keys are the data-k-* attributes render.py wrote
 * on each row, so nothing is parsed back out of the cells and a blank key
 * (a pending mineral, a withheld figure) always sorts last.
 */
(function (global) {
  "use strict";

  var root = document.querySelector("[data-screener]");
  if (!root) return;

  var controls = root.querySelector("[data-screener-controls]");
  var search = root.querySelector("[data-screener-search]");
  var category = root.querySelector("[data-screener-category]");
  var count = root.querySelector("[data-screener-count]");
  var empty = root.querySelector("[data-screener-empty]");
  var table = root.querySelector("[data-screener-table]");
  var body = table.tBodies[0];
  var rows = Array.prototype.slice.call(body.rows);
  var headers = Array.prototype.slice.call(table.querySelectorAll("th[aria-sort]"));
  var total = rows.length;

  function t(key, fallback) {
    return (global.I18N && global.I18N.t) ? global.I18N.t(key, fallback) : fallback;
  }

  /* ------------------------------------------------------------- filter */

  function normalise(value) { return (value || "").toLowerCase().trim(); }

  function filter() {
    var needle = normalise(search && search.value);
    var chosen = category ? category.value : "";
    var shown = 0;
    rows.forEach(function (row) {
      var hit = true;
      if (needle && (row.getAttribute("data-search") || "").indexOf(needle) === -1) hit = false;
      if (chosen && row.getAttribute("data-category") !== chosen) hit = false;
      row.classList.toggle("is-hidden", !hit);
      if (hit) shown += 1;
    });
    if (count) {
      count.textContent = t("screener.showing", "Showing {shown} of {total}")
        .replace("{shown}", String(shown)).replace("{total}", String(total));
    }
    if (empty) empty.hidden = shown !== 0;
  }

  /* --------------------------------------------------------------- sort */

  function keyOf(row, name) {
    var raw = row.getAttribute("data-k-" + name);
    if (raw === null || raw === "") return null;
    var number = Number(raw);
    return isNaN(number) ? raw : number;
  }

  function sortBy(name, direction) {
    var sign = direction === "descending" ? -1 : 1;
    var ordered = rows.slice().sort(function (a, b) {
      var ka = keyOf(a, name), kb = keyOf(b, name);
      if (ka === null && kb === null) return rows.indexOf(a) - rows.indexOf(b);
      if (ka === null) return 1;   /* blanks last, whichever way the column runs */
      if (kb === null) return -1;
      if (ka < kb) return -1 * sign;
      if (ka > kb) return 1 * sign;
      return rows.indexOf(a) - rows.indexOf(b);
    });
    ordered.forEach(function (row) { body.appendChild(row); });
    headers.forEach(function (th) {
      var button = th.querySelector("[data-sort]");
      var mine = button && button.getAttribute("data-sort") === name;
      th.setAttribute("aria-sort", mine ? direction : "none");
    });
  }

  table.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("[data-sort]") : null;
    if (!button) return;
    var th = button.closest("th");
    var name = button.getAttribute("data-sort");
    var current = th.getAttribute("aria-sort");
    /* Numeric columns open descending because the largest figure is the one
       a reader is looking for; text columns open A to Z. */
    var numeric = th.classList.contains("num");
    var next;
    if (current === "none") next = numeric ? "descending" : "ascending";
    else next = current === "ascending" ? "descending" : "ascending";
    sortBy(name, next);
  });

  /* --------------------------------------------------------------- wire */

  function placeholders() {
    if (search) search.placeholder = t("screener.placeholder", "Name or symbol");
  }

  if (search) search.addEventListener("input", filter);
  if (category) category.addEventListener("change", filter);
  document.addEventListener("i18n:change", function () { placeholders(); filter(); });

  table.classList.add("is-sortable");
  if (controls) controls.hidden = false;
  placeholders();
  filter();
})(window);
