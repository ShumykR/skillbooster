// Спільні дрібниці для пісочниць: DOM-помічник, повзунок із підписом, смуга, seeded RNG, форматування.
(function () {
  "use strict";
  window.SB_SANDBOXES = window.SB_SANDBOXES || {};

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") n.textContent = attrs[k];
      else if (k === "class") n.className = attrs[k];
      else n.setAttribute(k, attrs[k]);
    });
    [].concat(children || []).forEach(function (c) {
      if (c == null) return;
      n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return n;
  }

  var uid = 0;
  // повзунок з <label>, поточним значенням і доступний з клавіатури (нативний input[type=range])
  function slider(parent, o) {
    var id = "sbk" + (++uid);
    var inp = el("input", { type: "range", id: id, min: o.min, max: o.max, step: o.step || 1, value: o.value });
    var out = el("output", { for: id, class: "sb-val" });
    var fmt = o.fmt || function (v) { return String(v); };
    function sync() { out.textContent = fmt(+inp.value); }
    inp.addEventListener("input", function () { sync(); o.onInput(+inp.value); });
    sync();
    parent.appendChild(el("div", { class: "sb-ctl" }, [el("label", { for: id, text: o.label }), inp, out]));
    return { get: function () { return +inp.value; }, set: function (v) { inp.value = v; sync(); } };
  }

  function check(parent, o) {
    var id = "sbk" + (++uid);
    var inp = el("input", { type: "checkbox", id: id });
    inp.checked = !!o.value;
    inp.addEventListener("change", function () { o.onInput(inp.checked); });
    parent.appendChild(el("div", { class: "sb-ctl sb-check" }, [inp, el("label", { for: id, text: o.label })]));
    return { get: function () { return inp.checked; } };
  }

  // числове поле з підписом (для редагованих цін тощо)
  function num(parent, o) {
    var id = "sbk" + (++uid);
    var inp = el("input", { type: "number", id: id, min: o.min == null ? 0 : o.min, step: o.step || "any", value: o.value });
    inp.addEventListener("input", function () { var v = parseFloat(inp.value); o.onInput(isNaN(v) ? 0 : v); });
    parent.appendChild(el("div", { class: "sb-ctl" }, [el("label", { for: id, text: o.label }), inp]));
    return { get: function () { var v = parseFloat(inp.value); return isNaN(v) ? 0 : v; }, set: function (v) { inp.value = v; } };
  }

  function select(parent, o) {
    var id = "sbk" + (++uid);
    var sel = el("select", { id: id }, o.options.map(function (x, i) { return el("option", { value: i, text: x }); }));
    sel.value = o.value || 0;
    sel.addEventListener("change", function () { o.onInput(+sel.value); });
    parent.appendChild(el("div", { class: "sb-ctl" }, [el("label", { for: id, text: o.label }), sel]));
    return { get: function () { return +sel.value; } };
  }

  // горизонтальна смуга: сегменти [{label, value, cls}] у пропорції до max (або до суми)
  function bars(parent, rows, max) {
    var top = max || Math.max.apply(null, rows.map(function (r) { return r.value; }).concat([1e-9]));
    var box = el("div", { class: "sb-bars" });
    rows.forEach(function (r) {
      var w = Math.max(0, Math.min(100, (r.value / top) * 100));
      box.appendChild(el("div", { class: "sb-row" }, [
        el("span", { class: "sb-lab", text: r.label }),
        el("span", { class: "sb-track" }, [el("span", { class: "sb-fill " + (r.cls || ""), style: "width:" + w + "%" })]),
        el("span", { class: "sb-num", text: r.text != null ? r.text : String(r.value) }),
      ]));
    });
    parent.appendChild(box);
    return box;
  }

  // mulberry32: випадковість лише через seed, щоб результат відтворювався
  function rng(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function fmtNum(n, d) {
    return Number(n).toLocaleString("uk-UA", { maximumFractionDigits: d == null ? 0 : d, minimumFractionDigits: 0 });
  }
  function fmtUsd(n) {
    var d = Math.abs(n) >= 100 ? 0 : 2;
    return "$" + Number(n).toLocaleString("uk-UA", { maximumFractionDigits: d, minimumFractionDigits: d });
  }

  window.SB_KIT = { el: el, slider: slider, check: check, num: num, select: select, bars: bars, rng: rng, fmtNum: fmtNum, fmtUsd: fmtUsd };
})();
