/* Petralysis — the globe page (critical-minerals/globe.html).
 *
 * One Globe instance for the life of the page; choosing a mineral or a
 * measure swaps its data, never the instance. The globe is an aid: the info
 * panel and the table beside and under it carry every figure it draws, and
 * the page stands on them alone when WebGL is missing or the globe fails.
 *
 * Data, all same-origin and static (the page makes no other request):
 *   data/globe/index.json     every catalog mineral, its status and layers
 *   data/globe/<id>.json      shares for one mineral, fetched on first use
 *   assets/geo/countries.geojson    Natural Earth borders, keyed ADM0_A3
 *   assets/js/vendor/globe.gl.min.js   loaded once the globe scrolls into
 *                                       view in a browser that has WebGL
 *
 * State lives in the URL as ?m=<mineral>&l=<layer>, rewritten with
 * history.replaceState on every change. An unknown or unpublished value
 * falls back to the defaults the index names.
 */
(function (global) {
  "use strict";

  var doc = global.document;
  var configNode = doc.getElementById("globe-config");
  if (!configNode) return;
  var config = JSON.parse(configNode.textContent);

  /* The fixed scale: the same colour means the same share for every mineral
     and measure, so two globes can be compared by eye. Greys are the site's
     neutral ramp; the top of the scale is the site's data blue, darkened so
     the ramp keeps contrast against white borders. */
  var SCALE_MAX = 0.85;
  var COLOR = {
    globe: "#E4E8EE",
    zero: "#CFD6E2",
    high: "#0B3F77",
    noData: "#F3F5F8",
    stroke: "rgba(255, 255, 255, 0.9)",
    side: "rgba(15, 98, 183, 0.22)",
    hoverInk: "#14181D"
  };
  var TABLE_COLLAPSED = 10;

  var reduceMotion = global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var els = {
    select: doc.getElementById("globe-mineral"),
    layers: doc.getElementById("globe-layers"),
    redirect: doc.getElementById("globe-redirect"),
    stage: doc.getElementById("globe-stage"),
    canvas: doc.getElementById("globe-canvas"),
    other: doc.getElementById("globe-other"),
    info: doc.getElementById("globe-info"),
    tableBody: doc.querySelector("#globe-table tbody"),
    tableSub: doc.getElementById("globe-table-sub"),
    more: doc.getElementById("globe-more")
  };

  var state = {
    index: null,
    features: [],
    names: {},          // ADM0_A3 -> English name
    cache: {},          // mineral id -> promise of its file
    mineral: null,      // index entry
    file: null,         // the mineral's file
    layer: null,        // the layer being shown
    redirected: null,   // { entry } when the URL asked for an unpublished mineral
    expanded: false,
    hover: null,
    globe: null,
    globeFailed: false
  };

  /* ------------------------------------------------------------ language */

  function lang() { return (global.I18N && global.I18N.lang) || "en"; }
  function t(key, english) {
    return (global.I18N && global.I18N.t) ? global.I18N.t(key, english) : english;
  }
  function fill(template, values) {
    return template.replace(/\{(\w+)\}/g, function (_, k) { return values[k] != null ? values[k] : ""; });
  }
  function pick(en, ja) { return lang() === "ja" && ja ? ja : en; }
  function mineralName(entry) { return pick(entry.name_en, entry.name_ja); }
  function layerName(layer) { return pick(layer.label, layer.label_ja); }
  function countryName(code) { return state.names[code] || code; }

  /* Fixed-point text that rounds exactly as the mineral pages do. Those are
     formatted in Python, which rounds an exact tie to even (4960.5 -> 4960);
     toFixed would round it up, and the two pages would disagree by one. */
  function fixed(x, digits) {
    var scale = Math.pow(10, digits), scaled = x * scale;
    if (Math.abs(scaled % 1) === 0.5) {
      var down = Math.floor(scaled);
      return ((down % 2 === 0 ? down : down + 1) / scale).toFixed(digits);
    }
    return x.toFixed(digits);
  }
  function pct(fraction, digits) { return fixed(fraction * 100, digits) + "%"; }
  function pctOf(percent, digits) { return fixed(Number(percent), digits) + "%"; }
  function grouped(n) { return fixed(n, 0).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }

  var BAND = {
    unconcentrated: "Unconcentrated",
    moderate: "Moderately concentrated",
    high: "Highly concentrated"
  };

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function node(tag, attrs, children) {
    var el = doc.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (!Object.prototype.hasOwnProperty.call(attrs, k)) continue;
        if (k === "text") el.textContent = attrs[k];
        else if (k === "className") el.className = attrs[k];
        else el.setAttribute(k, attrs[k]);
      }
    }
    (children || []).forEach(function (c) {
      if (c == null) return;
      el.appendChild(typeof c === "string" ? doc.createTextNode(c) : c);
    });
    return el;
  }

  /* -------------------------------------------------------------- colour */

  function hexToRgb(hex) {
    var n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function mix(a, b, f) {
    var x = hexToRgb(a), y = hexToRgb(b);
    return "#" + [0, 1, 2].map(function (i) {
      var v = Math.round(x[i] + (y[i] - x[i]) * f);
      return (v < 16 ? "0" : "") + v.toString(16);
    }).join("");
  }
  function shareColor(share) {
    return mix(COLOR.zero, COLOR.high, Math.sqrt(Math.min(share, SCALE_MAX) / SCALE_MAX));
  }

  /* One country's state in the current layer. */
  function cell(code) {
    var layer = state.layer;
    if (!layer) return { kind: "none" };
    if (Object.prototype.hasOwnProperty.call(layer.values, code)) return { kind: "share", share: layer.values[code] };
    if (layer.no_data.indexOf(code) !== -1) return { kind: "nodata" };
    return { kind: "unlisted" };
  }
  function capColor(feature) {
    var c = cell(feature.properties.ADM0_A3);
    var base = c.kind === "share" ? shareColor(c.share) : c.kind === "nodata" ? COLOR.noData : COLOR.zero;
    return feature === state.hover ? mix(base, COLOR.hoverInk, 0.3) : base;
  }
  function altitude(feature) {
    var c = cell(feature.properties.ADM0_A3);
    var base = c.kind === "share" ? 0.006 + c.share * 0.16 : c.kind === "nodata" ? 0.004 : 0.006;
    return feature === state.hover ? base + 0.02 : base;
  }
  function tooltip(feature) {
    var code = feature.properties.ADM0_A3;
    var c = cell(code);
    var line;
    if (c.kind === "share") line = t("globe.share", "Share") + " " + pct(c.share, 1);
    else if (c.kind === "nodata") line = t("globe.withheld", "No data (not disclosed)");
    else line = t("globe.not_listed", "Not listed by the source");
    return '<div class="globe-tip"><strong>' + escapeHtml(countryName(code)) + "</strong><br>" + escapeHtml(line) + "</div>";
  }

  /* ------------------------------------------------------------- loading */

  function getJSON(url) {
    return global.fetch(url, { credentials: "same-origin" }).then(function (r) {
      if (!r.ok) throw new Error(url + " " + r.status);
      return r.json();
    });
  }
  function mineralFile(id) {
    if (!state.cache[id]) state.cache[id] = getJSON(config.data + encodeURIComponent(id) + ".json");
    return state.cache[id];
  }
  function findMineral(id) {
    var list = state.index.minerals;
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  }

  /* --------------------------------------------------------------- state */

  function readUrl() {
    var params = new global.URLSearchParams(global.location.search);
    return { m: params.get("m"), l: params.get("l") };
  }
  function writeUrl() {
    if (!global.history || !global.history.replaceState) return;
    var params = new global.URLSearchParams(global.location.search);
    params.set("m", state.mineral.id);
    params.set("l", state.layer.id);
    global.history.replaceState(null, "", global.location.pathname + "?" + params.toString() + global.location.hash);
  }

  /* Resolve a requested mineral and layer to ones that can be shown. */
  function choose(requestedMineral, requestedLayer) {
    var entry = requestedMineral ? findMineral(requestedMineral) : null;
    state.redirected = entry && !entry.selectable ? entry : null;
    if (!entry || !entry.selectable) {
      entry = findMineral(state.index.default.mineral);
      requestedLayer = requestedMineral && entry && requestedMineral === entry.id ? requestedLayer : null;
    }
    if (!entry) return Promise.reject(new Error("no published mineral"));
    return mineralFile(entry.id).then(function (file) {
      var layer = null;
      for (var i = 0; i < file.layers.length; i++) {
        if (file.layers[i].id === requestedLayer) layer = file.layers[i];
      }
      if (!layer && state.layer) {
        // Switching mineral keeps the same measure when the new one has it.
        for (var j = 0; j < file.layers.length; j++) {
          if (file.layers[j].id === state.layer.id) layer = file.layers[j];
        }
      }
      state.mineral = entry;
      state.file = file;
      state.layer = layer || file.layers[0];
      state.expanded = false;
      els.select.value = entry.id;
      writeUrl();
      renderAll(true);
    });
  }

  /* -------------------------------------------------------------- render */

  function renderAll(moved) {
    renderRedirect();
    renderLayers();
    renderInfo();
    renderTable();
    renderLegend();
    renderAria();
    drawGlobe(moved);
  }

  function renderRedirect() {
    var entry = state.redirected;
    els.redirect.hidden = !entry;
    if (!entry) return;
    var status = entry.status === "under_review" ? t("screener.under_review", "Under review") : t("screener.pending", "Pending");
    els.redirect.textContent = fill(
      t("globe.redirect", "{name} is {status}, so it cannot be shown on the globe. Showing {fallback} instead."),
      { name: mineralName(entry), status: lang() === "ja" ? status : status.toLowerCase(), fallback: mineralName(state.mineral) }
    );
  }

  function renderLayers() {
    els.layers.textContent = "";
    state.file.layers.forEach(function (layer) {
      var button = node("button", {
        type: "button",
        className: "sides__side",
        "aria-pressed": layer === state.layer ? "true" : "false",
        "data-layer": layer.id,
        text: layerName(layer)
      });
      els.layers.appendChild(button);
    });
  }

  function statRow(label, value, note, extraClass) {
    return node("div", { className: "globe-info__row" + (extraClass ? " " + extraClass : "") }, [
      node("dt", { text: label }),
      node("dd", null, [
        node("span", { className: "globe-info__value", text: value }),
        note ? node("span", { className: "globe-info__note", text: note }) : null
      ])
    ]);
  }

  function renderInfo() {
    var layer = state.layer;
    var s = layer.summary;
    var ja = lang() === "ja";
    var rows = [];

    var yearNote = layer.provisional ? t("globe.provisional", "Provisional") : null;
    rows.push(statRow(t("globe.year", "Year"), String(layer.year), yearNote));
    rows.push(statRow(t("globe.source", "Source"), layer.source, pick(layer.measure, layer.measure_ja)));
    rows.push(statRow(
      t("globe.leader", "Leading country"),
      countryName(s.leader),
      ja ? "報告合計の" + pctOf(s.leader_share, 1) : pctOf(s.leader_share, 1) + " of the reported total"
    ));
    rows.push(statRow(
      t("globe.cr3", "Top three"),
      pctOf(s.cr3, 0),
      ja ? "上位3カ国のシェアの合計" : "Combined share of the three largest"
    ));
    if (typeof s.hhi === "number") {
      var hhiRow = statRow("HHI", grouped(s.hhi), null);
      if (s.band) {
        var band = node("span", {
          className: "band band--" + s.band,
          text: t("band." + s.band, BAND[s.band] || s.band)
        });
        hhiRow.querySelector("dd").appendChild(band);
      }
      rows.push(hhiRow);
    }
    if (typeof layer.world_coverage === "number") {
      rows.push(statRow(t("globe.coverage", "Coverage"), pct(layer.world_coverage, 1),
        t("globe.coverage_world", "of the published world total, held by the countries with a figure")));
    } else {
      rows.push(statRow(t("globe.coverage", "Coverage"), pct(layer.coverage, 1),
        t("globe.coverage_named", "of the reported total, held by the countries with a figure")));
    }
    if (typeof layer.report_completeness === "number") {
      rows.push(statRow(t("globe.report_completeness", "Report completeness"), pctOf(layer.report_completeness, 1), null));
    }
    if (layer.no_data.length) {
      rows.push(statRow(t("globe.no_data_list", "No data"), layer.no_data.map(countryName).join(", "), null));
    }

    var head = node("div", { className: "globe-info__head" }, [
      node("h2", { text: mineralName(state.mineral) }),
      node("p", { className: "globe-info__layer", text: layerName(layer) })
    ]);
    var note = node("p", { className: "globe-info__text", text: pick(layer.note_en, layer.note_ja) });
    var link = node("a", {
      href: config.pages + state.mineral.page_url,
      text: t("globe.page_link", "Open the mineral page →")
    });

    els.info.textContent = "";
    els.info.appendChild(head);
    els.info.appendChild(node("dl", { className: "globe-info__list" }, rows));
    els.info.appendChild(note);
    els.info.appendChild(node("p", { className: "globe-info__link" }, [link]));
  }

  function tableRows() {
    var layer = state.layer;
    var list = Object.keys(layer.values).map(function (code) { return [code, layer.values[code]]; });
    list.sort(function (a, b) { return b[1] - a[1] || (a[0] < b[0] ? -1 : 1); });
    return list;
  }

  function renderTable() {
    var list = tableRows();
    var layer = state.layer;
    var shown = state.expanded ? list : list.slice(0, TABLE_COLLAPSED);
    var cumulative = 0;
    els.tableBody.textContent = "";
    shown.forEach(function (row, i) {
      cumulative += row[1];
      els.tableBody.appendChild(node("tr", null, [
        node("td", { className: "num", text: String(i + 1) }),
        node("td", { className: "name", text: countryName(row[0]) }),
        node("td", { className: "num", text: pct(row[1], 2) }),
        node("td", { className: "num", text: pct(Math.min(cumulative, 1), 1) })
      ]));
    });
    if (state.expanded || list.length <= TABLE_COLLAPSED) {
      layer.no_data.forEach(function (code) {
        els.tableBody.appendChild(node("tr", { className: "is-nodata" }, [
          node("td", { className: "num", text: "—" }),
          node("td", { className: "name", text: countryName(code) }),
          node("td", { className: "num", text: t("globe.no_data", "No data") }),
          node("td", { className: "num", text: "—" })
        ]));
      });
    }
    els.tableSub.textContent = fill(t("globe.table_sub", "{mineral} · {layer} · {year}"), {
      mineral: mineralName(state.mineral), layer: layerName(layer), year: layer.year
    });
    els.more.hidden = list.length <= TABLE_COLLAPSED;
    els.more.setAttribute("aria-expanded", state.expanded ? "true" : "false");
    els.more.textContent = state.expanded
      ? t("globe.show_fewer", "Show the top ten only")
      : fill(t("globe.show_all", "Show all {n} countries"), { n: list.length + layer.no_data.length });
  }

  function renderLegend() {
    var other = state.layer.other_share || 0;
    els.other.hidden = !(other > 0);
    if (other > 0) {
      els.other.textContent = fill(t("globe.other", "Other (not attributed to a country) {pct}"), { pct: pct(other, 1) });
    }
  }

  function renderAria() {
    els.canvas.setAttribute("aria-label", fill(
      t("globe.aria", "Globe of country shares: {mineral}, {layer}, {year}. The table below lists the same figures."),
      { mineral: mineralName(state.mineral), layer: layerName(state.layer), year: state.layer.year }
    ));
  }

  function renderOptgroups() {
    var groups = els.select.querySelectorAll("optgroup");
    for (var i = 0; i < groups.length; i++) {
      var g = groups[i];
      g.label = pick(g.getAttribute("data-label-en"), g.getAttribute("data-label-ja"));
    }
  }

  /* --------------------------------------------------------------- globe */

  function hasWebGL() {
    try {
      var canvas = doc.createElement("canvas");
      return !!(global.WebGLRenderingContext &&
        (canvas.getContext("webgl2") || canvas.getContext("webgl") || canvas.getContext("experimental-webgl")));
    } catch (e) {
      return false;
    }
  }

  function hideGlobe() {
    state.globeFailed = true;
    els.stage.hidden = true;
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      if (global.Globe) { resolve(); return; }
      var script = doc.createElement("script");
      script.src = src;
      script.async = true;
      script.onload = function () { resolve(); };
      script.onerror = function () { reject(new Error("could not load " + src)); };
      doc.head.appendChild(script);
    });
  }

  /* A point inside the country's largest polygon, for aiming the camera. */
  function anchor(code) {
    var feature = null;
    for (var i = 0; i < state.features.length; i++) {
      if (state.features[i].properties.ADM0_A3 === code) { feature = state.features[i]; break; }
    }
    if (!feature) return null;
    var g = feature.geometry;
    var polygons = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
    var best = null, bestArea = -1;
    polygons.forEach(function (polygon) {
      var ring = polygon[0], minX = 180, maxX = -180, minY = 90, maxY = -90;
      ring.forEach(function (p) {
        if (p[0] < minX) minX = p[0]; if (p[0] > maxX) maxX = p[0];
        if (p[1] < minY) minY = p[1]; if (p[1] > maxY) maxY = p[1];
      });
      var area = (maxX - minX) * (maxY - minY);
      if (area > bestArea) { bestArea = area; best = { lng: (minX + maxX) / 2, lat: (minY + maxY) / 2 }; }
    });
    return best;
  }

  function size() {
    var width = els.canvas.clientWidth || els.stage.clientWidth || 600;
    var height = Math.round(Math.min(width, 560, Math.max(300, global.innerHeight * 0.62)));
    return { width: width, height: height };
  }

  function createGlobe() {
    var dims = size();
    var world = new global.Globe(els.canvas, { animateIn: !reduceMotion })
      .width(dims.width)
      .height(dims.height)
      .backgroundColor("rgba(0,0,0,0)")
      .showAtmosphere(false)
      .showGraticules(false)
      .polygonsData(state.features)
      .polygonCapColor(capColor)
      .polygonSideColor(function () { return COLOR.side; })
      .polygonStrokeColor(function () { return COLOR.stroke; })
      .polygonAltitude(altitude)
      .polygonLabel(tooltip)
      .polygonsTransitionDuration(reduceMotion ? 0 : 400)
      .onPolygonHover(function (feature) {
        state.hover = feature || null;
        els.canvas.style.cursor = feature ? "pointer" : "";
        controls.autoRotate = !reduceMotion && !feature;
        world.polygonCapColor(capColor).polygonAltitude(altitude);
      });

    // The sphere's Phong material reads darker than the flat caps under the
    // same light; a matching emissive term brings it back to the page's grey.
    var sphere = world.globeMaterial();
    sphere.color.set(COLOR.globe);
    if (sphere.emissive) { sphere.emissive.set(COLOR.globe); sphere.emissiveIntensity = 0.5; }
    if ("shininess" in sphere) sphere.shininess = 0;
    // Nearly flat light, so a colour on the globe reads as the same colour in
    // the legend: mostly ambient, with a little directional light for depth.
    world.lights().forEach(function (light) {
      if (light.isAmbientLight) light.intensity = Math.PI * 0.82;
      else if (light.isDirectionalLight) light.intensity = Math.PI * 0.22;
    });

    var controls = world.controls();
    controls.autoRotate = !reduceMotion;
    controls.autoRotateSpeed = 0.4;
    // Zooming would take the mouse wheel and the pinch from the page.
    controls.enableZoom = false;
    controls.enablePan = false;

    // Vertical swipes scroll the page; horizontal ones turn the globe.
    var surface = world.renderer().domElement;
    surface.style.touchAction = "pan-y";
    els.canvas.style.touchAction = "pan-y";
    var wrapper = surface.parentElement;
    if (wrapper && wrapper !== els.canvas) wrapper.style.touchAction = "pan-y";

    if (global.ResizeObserver) {
      new global.ResizeObserver(function () {
        var d = size();
        if (d.width !== world.width() || d.height !== world.height()) world.width(d.width).height(d.height);
      }).observe(els.stage);
    }
    return world;
  }

  function drawGlobe(moved) {
    var world = state.globe;
    if (!world || !state.layer) return;
    state.hover = null;
    world.polygonCapColor(capColor).polygonAltitude(altitude).polygonLabel(tooltip);
    if (moved) {
      var target = anchor(state.layer.summary.leader);
      if (target) world.pointOfView({ lat: Math.max(-50, Math.min(55, target.lat)), lng: target.lng, altitude: 1.8 }, reduceMotion ? 0 : 900);
    }
  }

  function startGlobe() {
    if (state.globe || state.globeFailed) return;
    if (!hasWebGL()) { hideGlobe(); return; }
    loadScript(els.canvas.getAttribute("data-vendor-src")).then(function () {
      try {
        state.globe = createGlobe();
      } catch (e) {
        hideGlobe();
        return;
      }
      drawGlobe(true);
    }, hideGlobe);
  }

  function watchGlobe() {
    if (!hasWebGL()) { hideGlobe(); return; }
    if (!global.IntersectionObserver) { startGlobe(); return; }
    var observer = new global.IntersectionObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].isIntersecting) {
          observer.disconnect();
          startGlobe();
          return;
        }
      }
    }, { rootMargin: "120px 0px" });
    observer.observe(els.stage);
  }

  /* -------------------------------------------------------------- events */

  els.select.addEventListener("change", function () {
    state.redirected = null;
    choose(els.select.value, state.layer ? state.layer.id : null).catch(failed);
  });

  els.layers.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("[data-layer]") : null;
    if (!button) return;
    var id = button.getAttribute("data-layer");
    for (var i = 0; i < state.file.layers.length; i++) {
      if (state.file.layers[i].id === id) state.layer = state.file.layers[i];
    }
    state.expanded = false;
    writeUrl();
    renderAll(true);
  });

  els.more.addEventListener("click", function () {
    state.expanded = !state.expanded;
    renderTable();
  });

  doc.addEventListener("i18n:change", function () {
    renderOptgroups();
    if (state.layer) renderAll(false);
  });

  function failed() {
    els.info.textContent = "";
    els.info.appendChild(node("p", { className: "muted", text: t("globe.load_failed", "The globe data could not be loaded. Every figure is on the mineral pages.") }));
    hideGlobe();
  }

  /* ---------------------------------------------------------------- boot */

  renderOptgroups();
  Promise.all([getJSON(config.index), getJSON(config.borders)]).then(function (loaded) {
    state.index = loaded[0];
    state.features = loaded[1].features;
    state.features.forEach(function (f) { state.names[f.properties.ADM0_A3] = f.properties.ADMIN; });
    var wanted = readUrl();
    return choose(wanted.m, wanted.l).then(watchGlobe);
  }).catch(failed);
})(window);
