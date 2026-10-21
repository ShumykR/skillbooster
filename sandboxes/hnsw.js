// Пісочниця «HNSW»: багатошаровий граф на площині. Жадібний пошук зверху вниз, recall і кількість обчислених відстаней проти brute force.
(function () {
  "use strict";
  var K = window.SB_KIT;
  var NS = "http://www.w3.org/2000/svg";
  var LAYER_COLORS = ["#8a93a6", "#4f46e5", "#2fa87a", "#d9822b", "#c2477f"];

  function dist(a, b) { var dx = a[0] - b[0], dy = a[1] - b[1]; return Math.sqrt(dx * dx + dy * dy); }

  // жадібний пошук на одному шарі: кандидати за зростанням відстані, найкращі ef; рахуємо кожну обчислену відстань
  function searchLayer(q, eps, ef, adj, pts, counter, visitedOut) {
    var seen = {}, cand = [], best = [];
    eps.forEach(function (e) { seen[e] = true; var d = dist(q, pts[e]); counter.n++; cand.push({ id: e, d: d }); best.push({ id: e, d: d }); });
    var byD = function (a, b) { return a.d - b.d || a.id - b.id; };
    while (cand.length) {
      cand.sort(byD);
      var c = cand.shift();
      best.sort(byD);
      if (best.length >= ef && c.d > best[best.length - 1].d) break;
      if (visitedOut) visitedOut.push(c.id);
      (adj[c.id] || []).forEach(function (nb) {
        if (seen[nb]) return;
        seen[nb] = true;
        var d = dist(q, pts[nb]); counter.n++;
        best.sort(byD);
        if (best.length < ef || d < best[best.length - 1].d) {
          cand.push({ id: nb, d: d }); best.push({ id: nb, d: d });
          best.sort(byD);
          if (best.length > ef) best.pop();
        }
      });
    }
    best.sort(byD);
    return best;
  }

  function build(pts, M, rnd) {
    var mL = 1 / Math.log(Math.max(M, 2)), efC = Math.max(2 * M, 20), adj = [], levels = [], entry = -1, top = -1, c = { n: 0 };
    pts.forEach(function (p, i) {
      var lvl = Math.floor(-Math.log(1 - rnd()) * mL);
      levels[i] = lvl;
      for (var l = 0; l <= lvl; l++) { adj[l] = adj[l] || {}; adj[l][i] = []; }
      if (entry < 0) { entry = i; top = lvl; return; }
      var ep = [entry], lc;
      for (lc = top; lc > lvl; lc--) ep = [searchLayer(p, ep, 1, adj[lc], pts, c)[0].id];
      for (lc = Math.min(lvl, top); lc >= 0; lc--) {
        var W = searchLayer(p, ep, efC, adj[lc], pts, c), cap = lc === 0 ? 2 * M : M;
        adj[lc][i] = W.slice(0, M).map(function (x) { return x.id; });
        adj[lc][i].forEach(function (e) {
          adj[lc][e].push(i);
          if (adj[lc][e].length > cap) {      // лишаємо cap найближчих сусідів, порядок детермінований
            adj[lc][e].sort(function (a, b) { return dist(pts[e], pts[a]) - dist(pts[e], pts[b]) || a - b; });
            adj[lc][e].length = cap;
          }
        });
        ep = W.map(function (x) { return x.id; });
      }
      if (lvl > top) { top = lvl; entry = i; }
    });
    return { adj: adj, levels: levels, entry: entry, top: top };
  }

  function search(ix, pts, q, k, ef) {
    var c = { n: 0 }, ep = [ix.entry], paths = [], l;
    for (l = ix.top; l >= 1; l--) { var vis = []; var r = searchLayer(q, ep, 1, ix.adj[l], pts, c, vis); paths[l] = vis; ep = [r[0].id]; }
    var vis0 = [], res = searchLayer(q, ep, Math.max(ef, k), ix.adj[0], pts, c, vis0);
    paths[0] = vis0;
    return { found: res.slice(0, k).map(function (x) { return x.id; }), dists: c.n, paths: paths };
  }

  function truth(pts, q, k) {
    return pts.map(function (p, i) { return { id: i, d: dist(q, p) }; }).sort(function (a, b) { return a.d - b.d || a.id - b.id; }).slice(0, k).map(function (x) { return x.id; });
  }

  function svgEl(tag, attrs) {
    var n = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }

  function mount(root) {
    var el = K.el;
    var st = { n: 200, M: 4, ef: 10, k: 5, layer: 0, seed: 5, qx: 0.62, qy: 0.4 };
    var ctl = el("div", { class: "sb-controls" });
    var res = el("div", { class: "sb-result", "aria-live": "polite" });
    root.appendChild(el("div", { class: "sb-layout" }, [ctl, res]));
    var pts, ix;

    function rebuild() {
      var rnd = K.rng(st.seed);
      pts = []; for (var i = 0; i < st.n; i++) pts.push([rnd(), rnd()]);
      ix = build(pts, st.M, K.rng(st.seed + 1));
    }

    function redraw() {
      var q = [st.qx, st.qy], r = search(ix, pts, q, st.k, st.ef), tr = truth(pts, q, st.k);
      var hit = r.found.filter(function (x) { return tr.indexOf(x) !== -1; }).length;
      var L = Math.min(st.layer, ix.top);
      res.textContent = "";
      var svg = svgEl("svg", { viewBox: "0 0 1 1", class: "sb-svg", role: "img", "aria-label": "Граф HNSW на площині, шар " + L });
      var adj = ix.adj[L] || {};
      Object.keys(adj).forEach(function (a) { adj[a].forEach(function (b) { if (+a < b) svg.appendChild(svgEl("line", { x1: pts[a][0], y1: pts[a][1], x2: pts[b][0], y2: pts[b][1], stroke: "currentColor", "stroke-opacity": 0.18, "stroke-width": 0.002 })); }); });
      for (var l = ix.top; l >= 1; l--) {          // шлях жадібного спуску верхніми шарами
        var path = r.paths[l] || [];
        if (path.length > 1) svg.appendChild(svgEl("polyline", { points: path.map(function (id) { return pts[id].join(","); }).join(" "), fill: "none", stroke: LAYER_COLORS[l % 5], "stroke-width": 0.006 }));
      }
      (r.paths[0] || []).forEach(function (id) { svg.appendChild(svgEl("circle", { cx: pts[id][0], cy: pts[id][1], r: 0.011, fill: "#d9822b", "fill-opacity": 0.35 })); });
      pts.forEach(function (p, i) {
        var inL = ix.levels[i] >= L;
        svg.appendChild(svgEl("circle", { cx: p[0], cy: p[1], r: inL ? 0.008 : 0.005, fill: LAYER_COLORS[Math.min(ix.levels[i], 4)], "fill-opacity": inL ? 1 : 0.35 }));
      });
      tr.forEach(function (id) { svg.appendChild(svgEl("circle", { cx: pts[id][0], cy: pts[id][1], r: 0.02, fill: "none", stroke: r.found.indexOf(id) !== -1 ? "#2fa87a" : "#d6453a", "stroke-width": 0.005, "stroke-dasharray": "0.012 0.008" })); });
      r.found.forEach(function (id) { svg.appendChild(svgEl("circle", { cx: pts[id][0], cy: pts[id][1], r: 0.014, fill: "none", stroke: "#2fa87a", "stroke-width": 0.004 })); });
      svg.appendChild(svgEl("path", { d: "M" + (q[0] - 0.018) + " " + q[1] + "H" + (q[0] + 0.018) + "M" + q[0] + " " + (q[1] - 0.018) + "V" + (q[1] + 0.018), stroke: "#d6453a", "stroke-width": 0.007 }));
      svg.addEventListener("click", function (e) {
        var b = svg.getBoundingClientRect();
        st.qx = Math.min(1, Math.max(0, (e.clientX - b.left) / b.width)); st.qy = Math.min(1, Math.max(0, (e.clientY - b.top) / b.height));
        redraw();
      });
      res.appendChild(svg);
      res.appendChild(el("p", { class: "note", text: "Клік по площині ставить запит (хрестик). Колір точки = найвищий шар вузла. Помаранчеві кола: вузли, які пошук розглянув на шарі 0; лінії: шлях спуску верхніми шарами. Зелене коло: знайдено; червоний пунктир: справжній сусід, якого пропущено." }));

      var counts = []; for (var j = 0; j <= ix.top; j++) counts.push("шар " + j + ": " + Object.keys(ix.adj[j]).length);
      res.appendChild(el("div", { class: "sb-verdict " + (hit === st.k ? "safe" : "warn"),
        text: "Recall@" + st.k + " = " + hit + "/" + st.k + " (" + K.fmtNum(hit / st.k * 100) + "%). Обчислено відстаней: " + r.dists + " проти " + st.n + " у brute force (" + K.fmtNum(st.n / r.dists, 1) + "× менше). Вузлів по шарах: " + counts.join(", ") + "." }));

      // залежність від ef на 30 випадкових запитах
      var rq = K.rng(99), qs = []; for (var i = 0; i < 30; i++) qs.push([rq(), rq()]);
      var tbl = el("table", { class: "sb-map" });
      tbl.appendChild(el("tr", {}, ["ef_search", "середній recall", "відстаней на запит"].map(function (h) { return el("th", { text: h }); })));
      [1, 5, 10, 20, 50, 100].forEach(function (ef) {
        var rec = 0, ds = 0;
        qs.forEach(function (qq) { var s = search(ix, pts, qq, st.k, ef), t = truth(pts, qq, st.k); rec += s.found.filter(function (x) { return t.indexOf(x) !== -1; }).length / st.k; ds += s.dists; });
        tbl.appendChild(el("tr", { class: ef === st.ef ? "sel" : "" }, [String(ef), K.fmtNum(rec / qs.length * 100) + "%", K.fmtNum(ds / qs.length)].map(function (c, jj) { return el(jj ? "td" : "th", { text: c }); })));
      });
      res.appendChild(el("h4", { text: "Компроміс «якість / вартість» (30 випадкових запитів)" }));
      res.appendChild(tbl);
    }

    function both() { rebuild(); redraw(); }
    K.slider(ctl, { label: "Кількість точок", min: 50, max: 400, step: 10, value: st.n, onInput: function (v) { st.n = v; both(); } });
    K.slider(ctl, { label: "M (сусідів на вузол)", min: 2, max: 16, step: 1, value: st.M, onInput: function (v) { st.M = v; both(); } });
    K.slider(ctl, { label: "ef_search (ширина пошуку на шарі 0)", min: 1, max: 100, step: 1, value: st.ef, onInput: function (v) { st.ef = v; redraw(); } });
    K.slider(ctl, { label: "k (скільки сусідів шукаємо)", min: 1, max: 10, step: 1, value: st.k, onInput: function (v) { st.k = v; redraw(); } });
    K.slider(ctl, { label: "Який шар малювати", min: 0, max: 4, step: 1, value: st.layer, onInput: function (v) { st.layer = v; redraw(); } });
    K.slider(ctl, { label: "Запит X (клавіатурою)", min: 0, max: 100, step: 1, value: st.qx * 100, fmt: function (v) { return v + "%"; }, onInput: function (v) { st.qx = v / 100; redraw(); } });
    K.slider(ctl, { label: "Запит Y (клавіатурою)", min: 0, max: 100, step: 1, value: st.qy * 100, fmt: function (v) { return v + "%"; }, onInput: function (v) { st.qy = v / 100; redraw(); } });
    K.button(ctl, "🎲 Інші точки (seed)", function () { st.seed = (st.seed * 48271) % 2147483647; both(); });
    ctl.appendChild(el("p", { class: "note", text: "Індекс будується заново при зміні кількості точок, M або seed. Рівні вузлів визначає seeded RNG, тому картинка відтворювана." }));
    both();
  }

  window.SB_SANDBOXES.hnsw = {
    title: "HNSW: пошук у графі «малого світу»",
    analogy: "Шукаєш адресу в чужому місті: спершу летиш літаком між великими містами (верхні шари: рідкі, довгі стрибки), потім їдеш електричкою між районами, а на шарі 0 ходиш пішки по вулицях і шукаєш найближчий будинок. Не треба обійти всі вулиці.",
    formula: "Рівень вузла l = ⌊−ln(U)·mL⌋, mL = 1/ln M. Пошук: на шарах > 0 жадібно (ef = 1), на шарі 0 тримає ef найкращих кандидатів. Recall@k = |знайдені ∩ справжні| / k; вартість = кількість обчислених відстаней проти N у brute force.",
    mapping: [
      ["Шари графа", "Літак, електричка, піший хід", "Рідкі верхні шари з довгими ребрами й повний нижній"],
      ["ef_search", "Скільки варіантів тримаєш у голові", "Ширина пошуку: більше ef = вищий recall і більше обчислень"],
      ["M", "Скільки сусідніх вулиць пам'ятаєш", "Макс. число сусідів: пам'ять і якість проти часу побудови"],
      ["Червоний пунктир", "Пропущений найближчий будинок", "Помилка наближеного пошуку: втрата recall"],
    ],
    mount: mount,
  };
})();
