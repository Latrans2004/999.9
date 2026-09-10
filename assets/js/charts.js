/* 999.9 — chart primitives.
 *
 * No dependencies, no CDN. Three forms only, because the site asks three
 * questions: how has concentration moved (line), who holds the share today
 * (bars), and what is the shape at a glance (sparkline).
 *
 * Every value drawn here is also present in a table view rendered alongside,
 * so the hover layer enhances and never gates. Country names arrive from
 * upstream APIs and are inserted with textContent, never innerHTML.
 */
(function (global) {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";
  var INK = { data: "#CBD5E2", dim: "#7C8697", grid: "#222835", faint: "#4A5264", text: "#A7B0C0", strong: "#EAEEF4", surface: "#0D1017" };

  function el(name, attrs) {
    var node = document.createElementNS(NS, name);
    for (var key in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, key) && attrs[key] != null) {
        node.setAttribute(key, String(attrs[key]));
      }
    }
    return node;
  }

  function text(node, value) { node.textContent = String(value); return node; }

  function fmt(value, digits) {
    if (value == null || isNaN(value)) return "—";
    return Number(value).toLocaleString("en-US", {
      minimumFractionDigits: digits || 0,
      maximumFractionDigits: digits || 0
    });
  }

  function niceCeil(value) {
    if (value <= 0) return 1000;
    var magnitude = Math.pow(10, Math.floor(Math.log10(value)));
    var steps = [1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10];
    for (var i = 0; i < steps.length; i++) {
      if (steps[i] * magnitude >= value) return steps[i] * magnitude;
    }
    return 10 * magnitude;
  }

  function tooltipFor(container) {
    var tip = container.querySelector(".tooltip");
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "tooltip";
      tip.setAttribute("role", "status");
      container.appendChild(tip);
    }
    return tip;
  }

  function place(tip, container, x, y) {
    var width = container.clientWidth;
    var tw = tip.offsetWidth;
    var left = x + 14;
    if (left + tw > width - 4) left = x - tw - 14;
    if (left < 4) left = 4;
    tip.style.left = left + "px";
    tip.style.top = Math.max(4, y - tip.offsetHeight - 10) + "px";
  }

  /* ------------------------------------------------------------------ line */

  function line(container, options) {
    var points = (options.series || []).filter(function (p) { return p && p.hhi != null; });
    container.innerHTML = "";
    if (points.length === 0) return;

    var width = Math.max(280, container.clientWidth || 640);
    var height = options.height || (width < 480 ? 220 : 280);
    var pad = { top: 18, right: width < 480 ? 18 : 58, bottom: 30, left: 46 };
    var plotW = width - pad.left - pad.right;
    var plotH = height - pad.top - pad.bottom;

    var maxValue = points.reduce(function (m, p) { return Math.max(m, p.hhi); }, 0);
    var yMax = niceCeil(Math.max(maxValue * 1.06, 1200));
    var years = points.map(function (p) { return p.year; });
    var xMin = Math.min.apply(null, years);
    var xMax = Math.max.apply(null, years);

    function sx(year) {
      if (xMax === xMin) return pad.left + plotW / 2;
      return pad.left + ((year - xMin) / (xMax - xMin)) * plotW;
    }
    function sy(value) { return pad.top + plotH - (value / yMax) * plotH; }

    var svg = el("svg", {
      viewBox: "0 0 " + width + " " + height,
      width: width, height: height,
      role: "img",
      "aria-label": options.ariaLabel || "Concentration index over time"
    });

    /* gridlines: solid hairlines, one step off surface */
    var ticks = [];
    var step = yMax / 4;
    for (var t = 0; t <= 4; t++) ticks.push(Math.round(step * t));
    ticks.forEach(function (value) {
      svg.appendChild(el("line", {
        x1: pad.left, x2: pad.left + plotW, y1: sy(value), y2: sy(value),
        stroke: INK.grid, "stroke-width": 1, "shape-rendering": "crispEdges"
      }));
      svg.appendChild(text(el("text", {
        x: pad.left - 10, y: sy(value) + 4, "text-anchor": "end",
        fill: INK.faint, "font-size": 10.5, "font-variant-numeric": "tabular-nums"
      }), fmt(value)));
    });

    /* the two DOJ band boundaries, when they fall inside the plot */
    (options.thresholds || []).forEach(function (threshold) {
      if (threshold.value > yMax) return;
      svg.appendChild(el("line", {
        x1: pad.left, x2: pad.left + plotW, y1: sy(threshold.value), y2: sy(threshold.value),
        stroke: INK.dim, "stroke-width": 1, opacity: 0.55, "shape-rendering": "crispEdges"
      }));
      if (width >= 480) {
        svg.appendChild(text(el("text", {
          x: pad.left + plotW + 8, y: sy(threshold.value) + 3.5,
          fill: INK.dim, "font-size": 9.5, "letter-spacing": "0.06em"
        }), threshold.label));
      }
    });

    /* area wash then the 2px line */
    var path = points.map(function (p, i) { return (i ? "L" : "M") + sx(p.year) + " " + sy(p.hhi); }).join(" ");
    svg.appendChild(el("path", {
      d: path + " L" + sx(points[points.length - 1].year) + " " + sy(0) + " L" + sx(points[0].year) + " " + sy(0) + " Z",
      fill: INK.data, opacity: 0.10, stroke: "none"
    }));
    svg.appendChild(el("path", {
      d: path, fill: "none", stroke: INK.data, "stroke-width": 2,
      "stroke-linejoin": "round", "stroke-linecap": "round"
    }));

    /* end marker with a surface ring, and one direct label */
    var last = points[points.length - 1];
    svg.appendChild(el("circle", {
      cx: sx(last.year), cy: sy(last.hhi), r: 4.5,
      fill: INK.data, stroke: INK.surface, "stroke-width": 2
    }));
    if (width >= 480) {
      svg.appendChild(text(el("text", {
        x: sx(last.year) + 10, y: sy(last.hhi) + 4,
        fill: INK.strong, "font-size": 12, "font-weight": 500
      }), fmt(last.hhi)));
    }

    /* x axis */
    var labelCount = width < 420 ? 2 : (width < 640 ? 4 : 6);
    var stride = Math.max(1, Math.ceil(points.length / labelCount));
    points.forEach(function (p, i) {
      if (i % stride !== 0 && i !== points.length - 1) return;
      svg.appendChild(text(el("text", {
        x: sx(p.year), y: height - 10, "text-anchor": i === points.length - 1 ? "end" : (i === 0 ? "start" : "middle"),
        fill: INK.faint, "font-size": 10.5, "font-variant-numeric": "tabular-nums"
      }), p.year));
    });

    /* crosshair layer */
    var hairline = el("line", { y1: pad.top, y2: pad.top + plotH, stroke: INK.dim, "stroke-width": 1, opacity: 0 });
    var focus = el("circle", { r: 4.5, fill: INK.strong, stroke: INK.surface, "stroke-width": 2, opacity: 0 });
    svg.appendChild(hairline);
    svg.appendChild(focus);

    container.appendChild(svg);
    var tip = tooltipFor(container);

    function nearest(clientX) {
      var box = svg.getBoundingClientRect();
      var x = (clientX - box.left) * (width / box.width);
      var best = points[0], bestDistance = Infinity;
      points.forEach(function (p) {
        var distance = Math.abs(sx(p.year) - x);
        if (distance < bestDistance) { bestDistance = distance; best = p; }
      });
      return best;
    }

    function show(point) {
      hairline.setAttribute("x1", sx(point.year));
      hairline.setAttribute("x2", sx(point.year));
      hairline.setAttribute("opacity", 0.5);
      focus.setAttribute("cx", sx(point.year));
      focus.setAttribute("cy", sy(point.hhi));
      focus.setAttribute("opacity", 1);

      tip.innerHTML = "";
      var row = document.createElement("div");
      row.className = "tooltip__row";
      var key = document.createElement("i");
      key.className = "tooltip__key";
      var value = document.createElement("strong");
      value.className = "tooltip__value";
      value.textContent = fmt(point.hhi) + " HHI";
      row.appendChild(key); row.appendChild(value);
      tip.appendChild(row);

      var label = document.createElement("span");
      label.className = "tooltip__label";
      var parts = [String(point.year)];
      if (point.cr3 != null) parts.push("top three " + fmt(point.cr3, 1) + "%");
      if (point.reporters != null) parts.push(point.reporters + " reporting");
      label.textContent = parts.join(" · ");
      tip.appendChild(label);

      tip.setAttribute("data-show", "true");
      var box = svg.getBoundingClientRect();
      place(tip, container, sx(point.year) * (box.width / width), sy(point.hhi) * (box.height / height));
    }

    function hide() {
      tip.setAttribute("data-show", "false");
      hairline.setAttribute("opacity", 0);
      focus.setAttribute("opacity", 0);
    }

    svg.addEventListener("pointermove", function (event) { show(nearest(event.clientX)); });
    svg.addEventListener("pointerleave", hide);

    /* keyboard parity with hover */
    svg.setAttribute("tabindex", "0");
    var cursor = points.length - 1;
    svg.addEventListener("focus", function () { show(points[cursor]); });
    svg.addEventListener("blur", hide);
    svg.addEventListener("keydown", function (event) {
      if (event.key === "ArrowLeft") { cursor = Math.max(0, cursor - 1); show(points[cursor]); event.preventDefault(); }
      if (event.key === "ArrowRight") { cursor = Math.min(points.length - 1, cursor + 1); show(points[cursor]); event.preventDefault(); }
    });
  }

  /* ------------------------------------------------------------------ bars */

  function bars(container, options) {
    var rows = (options.rows || []).slice(0, options.limit || 10);
    container.innerHTML = "";
    if (rows.length === 0) return;

    /* Bars are scaled against 100%, not against the largest row: the track is
       the whole market, so a 48% bar looks like 48% of it. Scaling to the
       leader would make every mineral's leader look the same size. */
    var list = document.createElement("ol");
    list.className = "shares";

    rows.forEach(function (row, index) {
      var item = document.createElement("li");
      item.className = "shares__row";
      item.tabIndex = 0;

      var rank = document.createElement("span");
      rank.className = "shares__rank";
      rank.textContent = String(index + 1);

      var name = document.createElement("span");
      name.className = "shares__name";
      name.textContent = row.name;
      if (row.code) name.title = row.name + " (" + row.code + ")";

      var track = document.createElement("span");
      track.className = "shares__track";
      var fill = document.createElement("span");
      fill.className = "shares__fill";
      fill.style.width = Math.max(1.5, row.share) + "%";
      track.appendChild(fill);

      var value = document.createElement("span");
      value.className = "shares__value";
      value.textContent = fmt(row.share, 1) + "%";

      item.appendChild(rank);
      item.appendChild(name);
      item.appendChild(track);
      item.appendChild(value);
      list.appendChild(item);

      var detail = row.detail;
      if (detail) {
        var tip = tooltipFor(container);
        function reveal() {
          tip.innerHTML = "";
          var strong = document.createElement("strong");
          strong.className = "tooltip__value";
          strong.textContent = fmt(row.share, 2) + "%";
          var label = document.createElement("span");
          label.className = "tooltip__label";
          label.textContent = row.name + " · " + detail;
          tip.appendChild(strong); tip.appendChild(label);
          tip.setAttribute("data-show", "true");
          var itemBox = item.getBoundingClientRect();
          var containerBox = container.getBoundingClientRect();
          place(tip, container, itemBox.left - containerBox.left + itemBox.width * 0.55,
                itemBox.top - containerBox.top + itemBox.height);
        }
        item.addEventListener("pointerenter", reveal);
        item.addEventListener("focus", reveal);
        item.addEventListener("pointerleave", function () { tip.setAttribute("data-show", "false"); });
        item.addEventListener("blur", function () { tip.setAttribute("data-show", "false"); });
      }
    });

    container.appendChild(list);
  }

  /* ------------------------------------------------------------- sparkline */

  function spark(container, values, options) {
    container.innerHTML = "";
    var series = (values || []).filter(function (v) { return v != null; });
    if (series.length < 2) return;

    var opts = options || {};
    var width = opts.width || 96;
    var height = opts.height || 34;
    var padding = 5;
    var min = Math.min.apply(null, series);
    var max = Math.max.apply(null, series);
    var span = (max - min) || 1;

    function sx(i) { return padding + (i / (series.length - 1)) * (width - padding * 2); }
    function sy(v) { return height - padding - ((v - min) / span) * (height - padding * 2); }

    var svg = el("svg", { viewBox: "0 0 " + width + " " + height, width: width, height: height, "aria-hidden": "true", focusable: "false" });
    var path = series.map(function (v, i) { return (i ? "L" : "M") + sx(i).toFixed(1) + " " + sy(v).toFixed(1); }).join(" ");
    svg.appendChild(el("path", { d: path, fill: "none", stroke: INK.dim, "stroke-width": 1.5, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    svg.appendChild(el("circle", { cx: sx(series.length - 1), cy: sy(series[series.length - 1]), r: 2.5, fill: INK.data }));
    container.appendChild(svg);
  }

  /* --------------------------------------------------------------- resize */

  var registry = [];

  function register(container, draw) {
    registry.push({ container: container, draw: draw });
    draw();
  }

  var pending;
  global.addEventListener("resize", function () {
    clearTimeout(pending);
    pending = setTimeout(function () {
      registry.forEach(function (entry) {
        if (entry.container.isConnected) entry.draw();
      });
    }, 140);
  });

  global.Chart = { line: line, bars: bars, spark: spark, register: register, fmt: fmt };
})(window);
