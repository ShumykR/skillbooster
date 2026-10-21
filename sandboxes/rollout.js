// Пісочниця «Rollout»: rolling, blue-green і canary з однаковою зламаною версією. Скільки запитів зачепив баг до відкату.
(function () {
  "use strict";
  var K = window.SB_KIT;
  var TICK = 10;                                // секунд на один крок симуляції
  var STRATS = ["Rolling update", "Blue-green", "Canary (5% → 25% → 50% → 100%)"];
  var CANARY = [0.05, 0.25, 0.5, 1];

  function row(t, o, n, ns, share, p) {
    var req = p.rps * TICK;
    return { t: t, o: o, n: n, ns: ns, share: share, affected: req * share * p.err };
  }

  function simulate(strat, p) {
    var N = p.replicas, rows = [], detect = p.err >= p.thr, rolledBack = false, t;

    if (strat === 0) {                           // rolling: контролер керується maxSurge/maxUnavailable, відкат симетричний
      var surge = p.surge, unav = p.unav;
      if (!surge && !unav) surge = 1;            // Kubernetes забороняє обидва нулі
      var ready = { o: N, n: 0 }, start = { o: 0, n: 0 }, mode = "fwd";
      for (t = 0; t < 60; t++) {
        var tot = ready.o + ready.n, share = tot ? ready.n / tot : 0;
        rows.push(row(t, ready.o, ready.n, mode === "fwd" ? start.n : start.o, share, p));
        if (mode === "fwd" && share > 0 && detect) { mode = "back"; rolledBack = true; }
        var src = mode === "fwd" ? "o" : "n", dst = mode === "fwd" ? "n" : "o";
        if (ready[dst] === N && ready[src] === 0 && start[dst] === 0) break;
        ready[dst] += start[dst]; start[dst] = 0;
        var create = Math.max(0, Math.min(N + surge - (ready.o + ready.n), N - ready[dst]));
        start[dst] += create;
        var removable = Math.max(0, ready.o + ready.n - (N - unav));
        ready[src] -= Math.min(ready[src], removable);
      }
    } else if (strat === 1) {                    // blue-green: зелене піднімається повністю, перемикання миттєве
      rows.push(row(0, N, 0, N, 0, p));
      rows.push(row(1, N, N, 0, 1, p));
      if (detect) { rolledBack = true; rows.push(row(2, N, N, 0, 0, p)); }
      else rows.push(row(2, 0, N, 0, 1, p));
    } else {                                     // canary: частка трафіку росте етапами, кожен утримується hold кроків
      rows.push(row(0, N, 0, Math.ceil(N * CANARY[0]), 0, p));
      outer:
      for (var s = 0; s < CANARY.length; s++) {
        var pods = Math.ceil(N * CANARY[s]);
        for (var h = 0; h < p.hold; h++) {
          rows.push(row(rows.length, s === CANARY.length - 1 && h > 0 ? 0 : N, pods, 0, CANARY[s], p));
          if (detect) { rolledBack = true; rows.push(row(rows.length, N, 0, 0, 0, p)); break outer; }
        }
      }
    }
    var total = rows.reduce(function (a, r) { return a + r.affected; }, 0);
    var last = rows[rows.length - 1];
    return { rows: rows, affected: total, rolledBack: rolledBack, seconds: (rows.length - 1) * TICK,
      outcome: rolledBack ? "відкат" : last.n === N && last.o === 0 ? (p.err > 0 ? "баг не помічено, версія розгорнута" : "розгорнуто") : "не завершено" };
  }

  function mount(root) {
    var el = K.el;
    var st = { replicas: 10, strat: 0, surge: 2, unav: 1, hold: 2, err: 0.2, thr: 0.05, rps: 100 };
    var ctl = el("div", { class: "sb-controls" });
    var res = el("div", { class: "sb-result", "aria-live": "polite" });
    root.appendChild(el("div", { class: "sb-layout" }, [ctl, res]));

    function pods(r) {
      var box = el("span", { class: "sb-pods" });
      function add(n, cls, label) { for (var i = 0; i < n; i++) box.appendChild(el("i", { class: "sb-pod " + cls, title: label })); }
      add(r.o, "old", "стара версія");
      add(r.n, "new", "нова версія (готова)");
      add(r.ns, "start", "запускається");
      return box;
    }

    function redraw() {
      var r = simulate(st.strat, st);
      res.textContent = "";
      res.appendChild(el("h4", { text: STRATS[st.strat] + ": поди в часі (1 рядок = " + TICK + " с)" }));
      var grid = el("div", { class: "sb-rollout" });
      r.rows.forEach(function (x) {
        grid.appendChild(el("div", { class: "sb-rrow" }, [el("span", { class: "sb-rt", text: x.t * TICK + " с" }), pods(x),
          el("span", { class: "sb-rs", text: K.fmtNum(x.share * 100) + "% на нову" })]));
      });
      res.appendChild(grid);
      res.appendChild(el("p", { class: "note", text: "Синій: стара версія · помаранчевий: нова · пунктир: запускається (ще без трафіку)." }));

      var tbl = el("table", { class: "sb-map" });
      tbl.appendChild(el("tr", {}, ["Стратегія", "Зачеплено запитів", "Час", "Підсумок"].map(function (h) { return el("th", { text: h }); })));
      STRATS.forEach(function (name, i) {
        var x = simulate(i, st);
        tbl.appendChild(el("tr", { class: i === st.strat ? "sel" : "" }, [name.split(" (")[0], K.fmtNum(x.affected), x.seconds + " с", x.outcome].map(function (c, j) { return el(j ? "td" : "th", { text: c }); })));
      });
      res.appendChild(tbl);
      var msg = !st.err ? "Нова версія без багів: усі стратегії розгортають її без втрат." :
        r.rolledBack ? "Баг помічено (помилок " + K.fmtNum(st.err * 100) + "% ≥ порогу " + K.fmtNum(st.thr * 100) + "%): відкат після " + K.fmtNum(r.affected) + " зачеплених запитів." :
          "Помилок " + K.fmtNum(st.err * 100) + "% нижче порогу відкату " + K.fmtNum(st.thr * 100) + "%: система не бачить проблеми, і баг доїде до 100% користувачів (" + K.fmtNum(r.affected) + " запитів).";
      res.appendChild(el("div", { class: "sb-verdict " + (r.rolledBack || !st.err ? "safe" : "leak"), text: msg }));
    }

    K.select(ctl, { label: "Стратегія", options: STRATS, value: st.strat, onInput: function (v) { st.strat = v; redraw(); } });
    K.slider(ctl, { label: "Кількість подів", min: 4, max: 20, step: 1, value: st.replicas, onInput: function (v) { st.replicas = v; redraw(); } });
    K.slider(ctl, { label: "maxSurge (rolling): скільки зайвих подів одночасно", min: 0, max: 5, step: 1, value: st.surge, onInput: function (v) { st.surge = v; redraw(); } });
    K.slider(ctl, { label: "maxUnavailable (rolling): скільки може бути недоступно", min: 0, max: 5, step: 1, value: st.unav, onInput: function (v) { st.unav = v; redraw(); } });
    K.slider(ctl, { label: "Утримання етапу canary (кроків)", min: 1, max: 4, step: 1, value: st.hold, onInput: function (v) { st.hold = v; redraw(); } });
    K.slider(ctl, { label: "Частка помилок нової версії", min: 0, max: 50, step: 1, value: st.err * 100, fmt: function (v) { return v + "%"; }, onInput: function (v) { st.err = v / 100; redraw(); } });
    K.slider(ctl, { label: "Поріг авто-відкату (частка помилок)", min: 1, max: 30, step: 1, value: st.thr * 100, fmt: function (v) { return v + "%"; }, onInput: function (v) { st.thr = v / 100; redraw(); } });
    K.slider(ctl, { label: "Трафік (запитів/с)", min: 10, max: 500, step: 10, value: st.rps, onInput: function (v) { st.rps = v; redraw(); } });
    ctl.appendChild(el("p", { class: "note", text: "Метрики оцінюються після кожного кроку; відкат застосовується на наступному. Якщо maxSurge і maxUnavailable обидва 0, симуляція бере maxSurge = 1 (так вимагає Kubernetes)." }));
    redraw();
  }

  window.SB_SANDBOXES.rollout = {
    title: "Rollout: rolling, blue-green, canary і ціна багу",
    analogy: "Міняєш мотор літака на льоту. Rolling міняє по одному двигуну, blue-green тримає запасний літак на землі й пересаджує всіх пасажирів одразу, canary спершу бере на нове кількох сміливців. Якщо новий мотор зламаний, питання лише в тому, скільки пасажирів встигне це відчути.",
    formula: "Rolling: нових подів ≤ replicas + maxSurge, доступних ≥ replicas − maxUnavailable. Зачеплено запитів = Σ (трафік × частка на нову версію × частка помилок) до завершення відкату. Відкат спрацьовує, якщо частка помилок ≥ порогу.",
    mapping: [
      ["Рядки з подами", "Склад парку літаків у часі", "Поди старої й нової версії під час rollout"],
      ["% на нову", "Скільки пасажирів на новому", "Частка трафіку, що потрапляє на нову версію"],
      ["Зачеплено запитів", "Постраждалі пасажири", "Скільки запитів побачили баг до відкату"],
      ["Поріг відкату", "Чутливість датчика", "Метрика й поріг, за яким автоматика повертає стару версію"],
    ],
    mount: mount,
  };
})();
