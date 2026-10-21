// Пісочниця «Шум в evals»: на малому наборі випадкова різниця між версіями легко виглядає як покращення. Bootstrap показує межі шуму.
(function () {
  "use strict";
  var K = window.SB_KIT;
  var RHO = 0.6;   // кореляція «складності» питань для A і B: на тих самих питаннях помиляються схоже

  function phi(x) {
    var t = 1 / (1 + 0.2316419 * Math.abs(x));
    var d = 0.3989423 * Math.exp(-x * x / 2);
    var p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
    return x > 0 ? 1 - p : p;
  }
  function invPhi(p) {  // бісекція: достатньо для пісочниці
    var lo = -6, hi = 6;
    for (var i = 0; i < 40; i++) { var m = (lo + hi) / 2; if (phi(m) < p) lo = m; else hi = m; }
    return (lo + hi) / 2;
  }
  function normal(rnd) { return Math.sqrt(-2 * Math.log(1 - rnd())) * Math.cos(2 * Math.PI * rnd()); }

  // набір з n питань: 1 = модель відповіла правильно; частоти pA, pB точні в середньому, але поведінка питань спільна
  function dataset(n, pA, pB, rnd) {
    var zA = invPhi(pA), zB = invPhi(pB), a = new Uint8Array(n), b = new Uint8Array(n), s = Math.sqrt(1 - RHO * RHO);
    for (var i = 0; i < n; i++) {
      var z = normal(rnd);
      a[i] = (RHO * z + s * normal(rnd)) < zA ? 1 : 0;
      b[i] = (RHO * z + s * normal(rnd)) < zB ? 1 : 0;
    }
    return { a: a, b: b };
  }

  function analyse(p, seed) {
    var rnd = K.rng(seed), d = dataset(p.n, p.pA, p.pB, rnd), n = p.n, i, r;
    var sa = 0, sb = 0;
    for (i = 0; i < n; i++) { sa += d.a[i]; sb += d.b[i]; }
    var diffs = new Float64Array(p.boot);
    for (r = 0; r < p.boot; r++) {
      var x = 0, y = 0;
      for (i = 0; i < n; i++) {
        var j = Math.floor(rnd() * n);
        if (p.paired) { x += d.a[j]; y += d.b[j]; }                  // ті самі питання для обох
        else { x += d.a[j]; y += d.b[Math.floor(rnd() * n)]; }       // питання для A і B незалежні
      }
      diffs[r] = (y - x) / n;
    }
    var sorted = Array.prototype.slice.call(diffs).sort(function (u, v) { return u - v; });
    var lo = sorted[Math.floor(0.025 * (p.boot - 1))], hi = sorted[Math.ceil(0.975 * (p.boot - 1))];
    var verdict = lo > 0 ? "B" : hi < 0 ? "A" : "none";
    return { accA: sa / n, accB: sb / n, diff: (sb - sa) / n, lo: lo, hi: hi, verdict: verdict, sorted: sorted };
  }

  var VERDICT = { B: "B краще (CI > 0)", A: "A краще (CI < 0)", none: "Різниця не доведена (CI містить 0)" };

  function mount(root) {
    var el = K.el;
    var st = { pA: 0.7, pB: 0.73, n: 100, boot: 1000, paired: true, seed: 11 };
    var ctl = el("div", { class: "sb-controls" });
    var res = el("div", { class: "sb-result", "aria-live": "polite" });
    root.appendChild(el("div", { class: "sb-layout" }, [ctl, res]));
    var batch = null;
    var pct = function (x) { return K.fmtNum(x * 100, 1) + "%"; };
    var pp = function (x) { return (x >= 0 ? "+" : "") + K.fmtNum(x * 100, 1) + " п.п."; };

    function redraw() {
      var r = analyse(st, st.seed);
      res.textContent = "";
      res.appendChild(el("p", { text: "Виміряно: A " + pct(r.accA) + ", B " + pct(r.accB) + "; різниця B−A: " + pp(r.diff) + "; 95% bootstrap-інтервал: [" + pp(r.lo) + " … " + pp(r.hi) + "]" }));
      // гістограма різниць bootstrap: 25 бінів
      var min = r.sorted[0], max = r.sorted[r.sorted.length - 1], bins = 25, h = new Array(bins).fill(0);
      var span = max - min || 1;
      r.sorted.forEach(function (v) { h[Math.min(bins - 1, Math.floor((v - min) / span * bins))]++; });
      K.columns(res, h.map(function (c, i) {
        var center = min + (i + 0.5) * span / bins;
        return { v: c, cls: center > 0 ? "ok" : "bad", title: pp(center) + ": " + c };
      }), { height: 100, label: "Розподіл різниці B−A у bootstrap-ресемплах" });
      res.appendChild(el("p", { class: "note", text: "Розподіл різниці B−A за " + K.fmtNum(st.boot) + " ресемплів від " + pp(min) + " до " + pp(max) + ". Зелений: B краще, червоний: A краще." }));
      res.appendChild(el("div", { class: "sb-verdict " + (r.verdict === "B" ? "safe" : r.verdict === "A" ? "leak" : "warn"), text: "Гейт: " + VERDICT[r.verdict] + (r.verdict === "none" && st.pB > st.pA ? ". Справжня різниця є, але набір її не бачить." : "") }));

      if (batch) {
        res.appendChild(el("h4", { text: "20 незалежних запусків eval (інші seed, той самий набір параметрів)" }));
        var tbl = el("table", { class: "sb-map" });
        [["B краще", batch.B], ["Не доведено", batch.none], ["A краще", batch.A]].forEach(function (row) {
          tbl.appendChild(el("tr", {}, [el("th", { text: row[0] }), el("td", { text: row[1] + " з 20" })]));
        });
        res.appendChild(tbl);
        var wrong = st.pB > st.pA ? batch.none + batch.A : st.pB < st.pA ? batch.none + batch.B : batch.B + batch.A;
        res.appendChild(el("p", { class: "note", text: st.pA === st.pB ? "Версії однакові, а гейт «знайшов різницю» у " + wrong + " запусках із 20: це хибні спрацювання шуму." :
          "Правильний висновок («" + (st.pB > st.pA ? "B краще" : "A краще") + "») отримано в " + (20 - wrong) + " запусках із 20." }));
      }
      var dlt = Math.abs(st.pB - st.pA), pq = (st.pA + st.pB) / 2;
      res.appendChild(el("p", { class: "note", text: dlt ? "Орієнтир для незалежних вибірок: щоб надійно побачити різницю " + K.fmtNum(dlt * 100, 1) + " п.п., потрібно ≈ " + K.fmtNum(15.7 * pq * (1 - pq) / (dlt * dlt)) + " питань у кожній версії (парне порівняння потребує менше)." : "Різниці немає: будь-який «виграш» це шум." }));
    }

    function runBatch() {
      var c = { A: 0, B: 0, none: 0 };
      for (var i = 1; i <= 20; i++) c[analyse(st, st.seed + i * 101).verdict]++;
      batch = c;
      redraw();
    }

    K.slider(ctl, { label: "Справжня якість A", min: 0.1, max: 0.95, step: 0.01, value: st.pA, fmt: function (v) { return K.fmtNum(v * 100) + "%"; }, onInput: function (v) { st.pA = v; batch = null; redraw(); } });
    K.slider(ctl, { label: "Справжня якість B", min: 0.1, max: 0.95, step: 0.01, value: st.pB, fmt: function (v) { return K.fmtNum(v * 100) + "%"; }, onInput: function (v) { st.pB = v; batch = null; redraw(); } });
    K.slider(ctl, { label: "Розмір eval-набору (питань)", min: 20, max: 500, step: 10, value: st.n, onInput: function (v) { st.n = v; batch = null; redraw(); } });
    K.slider(ctl, { label: "Bootstrap-ресемплів", min: 100, max: 2000, step: 100, value: st.boot, onInput: function (v) { st.boot = v; batch = null; redraw(); } });
    K.check(ctl, { label: "Парне порівняння (ті самі питання для A і B)", value: st.paired, onInput: function (v) { st.paired = v; batch = null; redraw(); } });
    K.button(ctl, "🎲 Інший набір (seed)", function () { st.seed = (st.seed * 48271) % 2147483647; batch = null; redraw(); });
    K.button(ctl, "▶ Перезапустити 20 разів", runBatch);
    redraw();
  }

  window.SB_SANDBOXES["eval-noise"] = {
    title: "Шум в evals: коли різниця справжня",
    analogy: "Підкидаєш дві монети по 20 разів і дивишся, яка випала частіше: різниця майже завжди буде, але вона нічого не доводить. Що більше підкидань, то вужчий коридор випадковості.",
    formula: "Bootstrap: багато разів перевибираємо питання з поверненням, щоразу рахуємо різницю B−A; 2,5% і 97,5% цього розподілу дають 95% інтервал. Якщо весь інтервал вище 0, гейт пропускає B. Парне порівняння враховує, що питання складні для обох моделей однаково.",
    mapping: [
      ["Справжня якість A, B", "Монета з упередженням", "Невідома реальна якість моделі на всьому трафіку"],
      ["Розмір набору", "Кількість підкидань", "Кількість eval-питань"],
      ["Гістограма", "Коридор випадковості", "Розподіл різниці в bootstrap-ресемплах"],
      ["20 запусків", "Повтор експерименту", "Як часто шум дає хибне «поліпшення» або не бачить справжнього"],
    ],
    mount: mount,
  };
})();
