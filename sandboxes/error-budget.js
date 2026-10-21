// Пісочниця «Error budget»: SLO дає бюджет помилок; burn rate показує, як швидко він згоряє; multi-window алерти ловлять це вчасно.
(function () {
  "use strict";
  var K = window.SB_KIT;
  var SLOS = [99, 99.5, 99.9, 99.95, 99.99];
  // стандартні правила з Google SRE Workbook для 30-денного SLO: [назва, довге вікно, коротке вікно (хв), поріг burn rate, реакція]
  var RULES = [
    ["Page: швидке згоряння", 60, 5, 14.4, "page"],
    ["Page: помірне згоряння", 360, 30, 6, "page"],
    ["Ticket: повільне згоряння", 4320, 360, 1, "ticket"],
  ];

  // середня частка помилок у вікні W, що закінчується через m хвилин від початку інциденту тривалістю D зі часткою e
  function burn(W, m, D, e, budgetRate) {
    var overlap = Math.max(0, Math.min(m, D) - Math.max(0, m - W));
    return (overlap * e / W) / budgetRate;
  }

  function evaluate(p) {
    var budgetRate = 1 - p.slo / 100;                 // допустима частка помилок
    var budgetMin = budgetRate * p.days * 1440;       // бюджет у «хвилинах повної відмови»
    var spent = p.dur * p.share;                      // скільки з'їв інцидент (хвилин повної відмови)
    var rules = RULES.map(function (r) {
      var fire = null;
      for (var m = 1; m <= p.dur + r[1]; m++) {
        if (burn(r[1], m, p.dur, p.share, budgetRate) >= r[3] && burn(r[2], m, p.dur, p.share, budgetRate) >= r[3]) { fire = m; break; }
      }
      return { name: r[0], long: r[1], short: r[2], thr: r[3], kind: r[4], fire: fire, spentAtFire: fire == null ? null : Math.min(fire, p.dur) * p.share / budgetMin };
    });
    return { budgetRate: budgetRate, budgetMin: budgetMin, spent: spent, left: 1 - spent / budgetMin, burnNow: p.share / budgetRate, rules: rules,
      incidents: spent ? Math.floor(budgetMin / spent) : Infinity };
  }

  function human(min) { return min >= 120 ? K.fmtNum(min / 60, 1) + " год" : K.fmtNum(min, 0) + " хв"; }

  function mount(root) {
    var el = K.el;
    var st = { slo: 99.9, days: 30, dur: 30, share: 1 };
    var ctl = el("div", { class: "sb-controls" });
    var res = el("div", { class: "sb-result", "aria-live": "polite" });
    root.appendChild(el("div", { class: "sb-layout" }, [ctl, res]));

    function redraw() {
      var r = evaluate(st);
      res.textContent = "";
      res.appendChild(el("div", { class: "sb-big" }, [el("span", { text: K.fmtNum(r.left * 100, 1) + "%" }), el("small", { text: " бюджету лишилось" })]));
      K.bars(res, [{ label: "Бюджет", value: Math.max(0, r.left), cls: r.left < 0 ? "c4" : r.left < 0.25 ? "c3" : "c2", text: human(r.budgetMin) + " повної відмови на " + st.days + " днів" }], 1);
      res.appendChild(el("p", { text: "SLO " + st.slo + "% допускає " + K.fmtNum(r.budgetRate * 100, 3) + "% помилок. Інцидент з'їв " + K.fmtNum(r.spent, 1) + " хв із " + K.fmtNum(r.budgetMin, 1) +
        ". Burn rate під час інциденту: ×" + K.fmtNum(r.burnNow, 1) + " (1 = бюджет рівно вичерпується до кінця вікна). Такий інцидент можна дозволити собі ≈ " + (r.incidents === Infinity ? "безліч" : r.incidents) + " разів за вікно." }));

      var tbl = el("table", { class: "sb-map" });
      tbl.appendChild(el("tr", {}, ["Алерт", "Вікна", "Поріг", "Спрацює", "Бюджету вже з'їдено"].map(function (h) { return el("th", { text: h }); })));
      r.rules.forEach(function (x) {
        tbl.appendChild(el("tr", { class: x.fire != null ? "sel" : "" }, [x.name + " (" + x.kind + ")", human(x.long) + " і " + human(x.short), "×" + x.thr,
          x.fire == null ? "ні" : "через " + human(x.fire), x.spentAtFire == null ? "-" : K.fmtNum(x.spentAtFire * 100, 1) + "%"].map(function (c, j) { return el(j ? "td" : "th", { text: c }); })));
      });
      res.appendChild(tbl);
      var first = r.rules.filter(function (x) { return x.fire != null; }).sort(function (a, b) { return a.fire - b.fire; })[0];
      res.appendChild(el("div", { class: "sb-verdict " + (first ? "safe" : "leak"),
        text: first ? "Перший алерт: «" + first.name + "» через " + human(first.fire) + " (бюджету з'їдено " + K.fmtNum(first.spentAtFire * 100, 1) + "%)." :
          "Жоден алерт не спрацює, а бюджет " + (r.left < 0 ? "уже перевищено" : "підтоптано") + ": такий тихий інцидент помітить лише звіт." }));
    }

    K.select(ctl, { label: "SLO доступності", options: SLOS.map(function (x) { return x + "%"; }), value: 2, onInput: function (i) { st.slo = SLOS[i]; redraw(); } });
    K.slider(ctl, { label: "Вікно SLO (днів)", min: 7, max: 30, step: 1, value: st.days, onInput: function (v) { st.days = v; redraw(); } });
    K.slider(ctl, { label: "Тривалість інциденту (хв)", min: 1, max: 720, step: 1, value: st.dur, onInput: function (v) { st.dur = v; redraw(); } });
    K.slider(ctl, { label: "Частка запитів з помилкою під час інциденту", min: 1, max: 100, step: 1, value: st.share * 100, fmt: function (v) { return v + "%"; }, onInput: function (v) { st.share = v / 100; redraw(); } });
    ctl.appendChild(el("p", { class: "note", text: "Пороги алертів стандартні для 30-денного вікна (14,4 / 6 / 1). Кожен алерт вимагає і довге, і коротке вікно: так він не спрацьовує на давній сплеск і швидко затихає після виправлення." }));
    redraw();
  }

  window.SB_SANDBOXES["error-budget"] = {
    title: "Error budget і burn rate",
    analogy: "SLO це місячний ліміт на «погані» хвилини, як ліміт мобільного трафіку. Burn rate показує, наскільки швидко ти його палиш: ×1 вистачить рівно до кінця місяця, ×14 згорить за дві доби.",
    formula: "Бюджет = (1 − SLO) × вікно. Burn rate = частка помилок / (1 − SLO). Алерт спрацьовує, коли burn rate ≥ порогу і на довгому, і на короткому вікні.",
    mapping: [
      ["SLO і вікно", "Місячний ліміт", "Ціль доступності й період, за який її рахують"],
      ["Інцидент", "Різке перевитрачання", "Тривалість і частка помилкових запитів"],
      ["Burn rate", "Швидкість витрати", "Множник відносно «рівної» витрати бюджету"],
      ["Дві пари вікон", "Подвійне підтвердження", "Multi-window multi-burn-rate алерти зі SRE Workbook"],
    ],
    mount: mount,
  };
})();
