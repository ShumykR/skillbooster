// Пісочниця «Base rate»: рідкісна подія + «точний» класифікатор = море хибних тривог (теорема Байєса на 100 000 запитів).
(function () {
  "use strict";
  var K = window.SB_KIT;
  var N = 100000;

  // Φ(x): інтеграл стандартного нормального розподілу (наближення Абрамовіца-Стегана, похибка < 1e-7)
  function phi(x) {
    var t = 1 / (1 + 0.2316419 * Math.abs(x));
    var d = 0.3989423 * Math.exp(-x * x / 2);
    var p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
    return x > 0 ? 1 - p : p;
  }

  // оцінки: нормальні N(0,1) і атаки N(d,1); поріг t: блокуємо, якщо оцінка > t
  function compute(p, d, t) {
    var tpr = 1 - phi(t - d), fpr = 1 - phi(t);
    var attacks = N * p, benign = N - attacks;
    var tp = attacks * tpr, fn = attacks - tp, fp = benign * fpr, tn = benign - fp;
    return { tpr: tpr, fpr: fpr, tp: tp, fn: fn, fp: fp, tn: tn, precision: tp + fp ? tp / (tp + fp) : 0, perAttack: tp ? fp / tp : Infinity };
  }

  function mount(root) {
    var el = K.el;
    var st = { logp: -3, d: 3, t: 2.5 };
    var ctl = el("div", { class: "sb-controls" });
    var res = el("div", { class: "sb-result", "aria-live": "polite" });
    root.appendChild(el("div", { class: "sb-layout" }, [ctl, res]));
    var pct = function (x) { return K.fmtNum(x * 100, 2) + "%"; };

    function redraw() {
      var p = Math.pow(10, st.logp), r = compute(p, st.d, st.t);
      res.textContent = "";
      res.appendChild(el("p", { text: "Із " + K.fmtNum(N) + " запитів атак ≈ " + K.fmtNum(N * p, N * p < 10 ? 1 : 0) + " (" + pct(p) + "). Класифікатор ловить " + pct(r.tpr) + " атак і хибно блокує " + pct(r.fpr) + " звичайних запитів." }));
      var rows = [["", "Заблоковано", "Пропущено"], ["Справжні атаки", K.fmtNum(r.tp, 1), K.fmtNum(r.fn, 1)], ["Звичайні запити", K.fmtNum(r.fp, 0), K.fmtNum(r.tn, 0)]];
      var tbl = el("table", { class: "sb-map" });
      rows.forEach(function (row, i) {
        tbl.appendChild(el("tr", {}, row.map(function (c, j) { return el(i === 0 || j === 0 ? "th" : "td", { text: c, class: i === 2 && j === 1 ? "sb-cell-bad" : i === 1 && j === 1 ? "sb-cell-ok" : "" }); })));
      });
      res.appendChild(tbl);
      K.bars(res, [
        { label: "Precision", value: r.precision, cls: "c2", text: pct(r.precision) },
        { label: "Recall (TPR)", value: r.tpr, text: pct(r.tpr) },
        { label: "FPR", value: r.fpr, cls: "c4", text: pct(r.fpr) },
      ], 1);
      res.appendChild(el("div", { class: "sb-verdict " + (r.precision < 0.5 ? "leak" : "safe"),
        text: r.tp ? "Хибних блокувань на одну справжню атаку: " + K.fmtNum(r.perAttack, 1) + ". " + (r.precision < 0.5 ? "Блокування рідко буває правильним: precision лише " : "Блокування здебільшого правильне: precision ") + pct(r.precision) + "." : "Атаки не ловляться взагалі." }));
    }

    K.slider(ctl, { label: "Частка атак серед запитів (log-шкала)", min: -4, max: -1, step: 0.1, value: st.logp, fmt: function (v) { return pct(Math.pow(10, v)); }, onInput: function (v) { st.logp = v; redraw(); } });
    K.slider(ctl, { label: "Наскільки класи розділені (d′: чим більше, тим кращий класифікатор)", min: 0, max: 6, step: 0.1, value: st.d, fmt: function (v) { return v.toFixed(1); }, onInput: function (v) { st.d = v; redraw(); } });
    K.slider(ctl, { label: "Поріг блокування (вище = менше хибних, але більше пропущених)", min: -1, max: 6, step: 0.1, value: st.t, fmt: function (v) { return v.toFixed(1); }, onInput: function (v) { st.t = v; redraw(); } });
    ctl.appendChild(el("p", { class: "note", text: "Оцінки звичайних запитів ~ N(0,1), атак ~ N(d′,1). Спробуй: перетягни частку атак до 0,01% і подивись, що буде з precision." }));
    redraw();
  }

  window.SB_SANDBOXES["base-rate"] = {
    title: "Base rate: чому «99% точний» не означає «99% блокувань правильні»",
    analogy: "Металошукач на вході в бібліотеку: майже ніхто не носить зброю, тож майже кожен його спрацьований сигнал це ключі від квартири. Що рідша подія, то більше хибних тривог на одну справжню, навіть коли датчик «точний».",
    formula: "precision = TP / (TP + FP), де TP = N·p·TPR, FP = N·(1−p)·FPR. При p = 0,1%, TPR = 70%, FPR = 0,6% маємо TP ≈ 70, FP ≈ 600: правильним виявляється приблизно кожне десяте блокування.",
    mapping: [
      ["Частка атак", "Скільки носіїв «зброї»", "Базова частота (prior) атак у реальному трафіку"],
      ["d′ і поріг", "Чутливість датчика", "Якість класифікатора й обраний поріг, що міняє TPR на FPR"],
      ["Матриця помилок", "Хто спрацював, а хто ні", "TP/FP/FN/TN на 100 000 запитів"],
      ["Хибних на одну атаку", "Скільки «ключів» на одну «зброю»", "Ціна блокування для звичайних користувачів"],
    ],
    mount: mount,
  };
})();
