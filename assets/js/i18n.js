/* 999.9 — language toggle (English / Japanese).
 *
 * Every page is rendered once, in English, and carries its Japanese text
 * alongside. Nothing is translated at runtime: this file only chooses which
 * of the two prepared versions is visible. The conventions it understands:
 *
 *   data-i18n="key"           text from the shared dictionary embedded in
 *                             #i18n-data (pipeline/i18n.py, STRINGS_JA)
 *   data-i18n-text="…"        text given inline on the element itself, for
 *                             strings that carry numbers or are page-specific
 *   data-lang-only="en|ja"    a whole block that exists in one language only;
 *                             the other language's block is hidden
 *
 * English is always the element's own rendered content, cached on first use,
 * so switching back never needs a second dictionary. An empty or missing
 * translation leaves the English in place rather than blanking the element.
 *
 * The choice is remembered per browser. With no saved choice, a browser whose
 * preferred language is Japanese starts in Japanese.
 */
(function (global) {
  "use strict";

  var STORAGE_KEY = "999.9:lang";
  var LANGS = ["en", "ja"];
  var root = document.documentElement;

  var dict = {};
  var dictNode = document.getElementById("i18n-data");
  if (dictNode) {
    try { dict = JSON.parse(dictNode.textContent) || {}; } catch (e) { dict = {}; }
  }

  function saved() {
    try {
      var value = global.localStorage.getItem(STORAGE_KEY);
      if (LANGS.indexOf(value) !== -1) return value;
    } catch (e) { /* storage blocked: fall through */ }
    return null;
  }

  function initial() {
    var choice = saved();
    if (choice) return choice;
    var preferred = (global.navigator && (global.navigator.language || "")) || "";
    return /^ja\b/i.test(preferred) ? "ja" : "en";
  }

  var originals = new WeakMap();

  function original(node) {
    if (!originals.has(node)) originals.set(node, node.textContent);
    return originals.get(node);
  }

  function translate(node, lang) {
    var english = original(node);
    if (lang !== "ja") {
      if (node.textContent !== english) node.textContent = english;
      return;
    }
    var value = null;
    if (node.hasAttribute("data-i18n-text")) {
      value = node.getAttribute("data-i18n-text");
    } else if (node.hasAttribute("data-i18n")) {
      value = dict[node.getAttribute("data-i18n")];
    }
    node.textContent = value ? value : english;
  }

  function apply(lang) {
    root.setAttribute("lang", lang);

    var nodes = document.querySelectorAll("[data-i18n], [data-i18n-text]");
    for (var i = 0; i < nodes.length; i++) translate(nodes[i], lang);

    var blocks = document.querySelectorAll("[data-lang-only]");
    for (var j = 0; j < blocks.length; j++) {
      blocks[j].hidden = blocks[j].getAttribute("data-lang-only") !== lang;
    }

    var buttons = document.querySelectorAll("[data-set-lang]");
    for (var k = 0; k < buttons.length; k++) {
      var active = buttons[k].getAttribute("data-set-lang") === lang;
      buttons[k].setAttribute("aria-pressed", active ? "true" : "false");
    }

    root.classList.remove("i18n-pending");
  }

  var api = {
    lang: initial(),
    t: function (key, fallback) {
      if (api.lang === "ja" && dict[key]) return dict[key];
      return fallback;
    },
    set: function (lang) {
      if (LANGS.indexOf(lang) === -1 || lang === api.lang) return;
      api.lang = lang;
      try { global.localStorage.setItem(STORAGE_KEY, lang); } catch (e) { /* not fatal */ }
      apply(lang);
      if (global.Chart && typeof global.Chart.redraw === "function") global.Chart.redraw();
      var event;
      try {
        event = new CustomEvent("i18n:change", { detail: { lang: lang } });
      } catch (e) {
        event = document.createEvent("CustomEvent");
        event.initCustomEvent("i18n:change", false, false, { lang: lang });
      }
      document.dispatchEvent(event);
    }
  };

  global.I18N = api;

  document.addEventListener("click", function (event) {
    var target = event.target;
    var button = target && target.closest ? target.closest("[data-set-lang]") : null;
    if (!button) return;
    event.preventDefault();
    api.set(button.getAttribute("data-set-lang"));
  });

  /* This script sits at the end of <body>, so the DOM is already parsed:
     apply immediately, before charts.js draws anything. */
  apply(api.lang);
})(window);
