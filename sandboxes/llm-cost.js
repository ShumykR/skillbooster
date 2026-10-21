// Пісочниця «Калькулятор вартості LLM»: що саме складає місячний рахунок і яке важіль економить найбільше.
(function () {
  "use strict";
  var K = window.SB_KIT;

  // ціни УМОВНІ і редагуються: підстав свої з прайсу провайдера ($ за 1 млн токенів)
  var MODELS = [
    { name: "Мала модель (умовно)", inp: 0.25, cached: 0.025, out: 1.25 },
    { name: "Середня модель (умовно)", inp: 3, cached: 0.3, out: 15 },
    { name: "Велика модель (умовно)", inp: 15, cached: 1.5, out: 75 },
  ];
  var LANGS = [["Англійська (×1)", 1], ["Українська (×1,4)", 1.4]];
  var DAYS = 30;

  function compute(p) {
    var inTok = p.input * p.lang;                     // токенів входу на запит
    var cachedTok = inTok * p.cached;
    var freshTok = inTok - cachedTok;
    var outTok = p.output * p.lang;                   // видимий вивід
    var reasonTok = p.reasoning;                      // reasoning тарифікується як вивід
    var k = p.batch ? 0.5 : 1;                        // batch API: знижка на все
    var n = p.rpd * DAYS / 1e6;                       // мільйонів «запит·токен» на місяць
    var parts = [
      { label: "Вхід без кешу", usd: freshTok * n * p.price.inp * k, cls: "c1" },
      { label: "Вхід з кешу", usd: cachedTok * n * p.price.cached * k, cls: "c2" },
      { label: "Вивід", usd: outTok * n * p.price.out * k, cls: "c3" },
      { label: "Reasoning", usd: reasonTok * n * p.price.out * k, cls: "c4" },
    ];
    var total = parts.reduce(function (a, x) { return a + x.usd; }, 0);
    return { parts: parts, total: total, perReq: p.rpd ? total / (p.rpd * DAYS) : 0 };
  }

  function mount(root) {
    var el = K.el;
    var st = { rpd: 10000, input: 3000, output: 400, cached: 0.5, lang: 1, reasoning: 0, batch: false, model: 1,
      price: { inp: MODELS[1].inp, cached: MODELS[1].cached, out: MODELS[1].out } };

    var ctl = el("div", { class: "sb-controls" });
    var res = el("div", { class: "sb-result", "aria-live": "polite" });
    root.appendChild(el("div", { class: "sb-layout" }, [ctl, res]));

    function redraw() {
      var r = compute(st);
      res.textContent = "";
      res.appendChild(el("div", { class: "sb-big" }, [el("span", { text: K.fmtUsd(r.total) }), el("small", { text: " на місяць (" + DAYS + " днів)" })]));
      res.appendChild(el("p", { class: "note", text: "≈ " + K.fmtUsd(r.perReq * 1000) + " за 1000 запитів · " + K.fmtNum(r.perReq * 100, 3) + " ¢ за запит" }));
      K.bars(res, r.parts.map(function (x) {
        return { label: x.label, value: x.usd, cls: x.cls, text: K.fmtUsd(x.usd) + (r.total ? " · " + Math.round(x.usd / r.total * 100) + "%" : "") };
      }), r.total || 1);

      // що-якщо: економія від кожного важеля окремо, відсортована
      var levers = [];
      function lever(name, patch) {
        var alt = compute(Object.assign({}, st, patch));
        levers.push({ name: name, save: r.total - alt.total });
      }
      if (st.cached < 0.9) lever("Кеш префікса до 90% входу", { cached: 0.9 });
      if (!st.batch) lever("Batch API (−50%, для відкладених завдань)", { batch: true });
      if (st.reasoning > 0) lever("Без reasoning-токенів", { reasoning: 0 });
      lever("Вивід коротший на 30%", { output: st.output * 0.7 });
      lever("Вхід коротший на 30% (стиснення контексту)", { input: st.input * 0.7 });
      if (st.model > 0) lever("Модель на рівень менша (умовно)", { price: MODELS[st.model - 1] });
      levers.sort(function (a, b) { return b.save - a.save; });
      var list = el("ol", { class: "sb-levers" });
      levers.forEach(function (x, i) {
        list.appendChild(el("li", { class: i === 0 ? "top" : "" }, [x.name + ": ", el("b", { text: "−" + K.fmtUsd(Math.max(0, x.save)) })]));
      });
      res.appendChild(el("h4", { text: "Що економить найбільше (кожен важіль окремо)" }));
      res.appendChild(list);
    }

    var priceInputs = {};
    function setModel(i) {
      st.model = i;
      st.price = { inp: MODELS[i].inp, cached: MODELS[i].cached, out: MODELS[i].out };
      Object.keys(priceInputs).forEach(function (k) { priceInputs[k].set(st.price[k]); });
      redraw();
    }

    K.slider(ctl, { label: "Запитів на день", min: 100, max: 1000000, step: 100, value: st.rpd, fmt: K.fmtNum, onInput: function (v) { st.rpd = v; redraw(); } });
    K.slider(ctl, { label: "Токенів входу на запит (англ.)", min: 100, max: 100000, step: 100, value: st.input, fmt: K.fmtNum, onInput: function (v) { st.input = v; redraw(); } });
    K.slider(ctl, { label: "Токенів виводу на запит (англ.)", min: 10, max: 8000, step: 10, value: st.output, fmt: K.fmtNum, onInput: function (v) { st.output = v; redraw(); } });
    K.slider(ctl, { label: "Частка входу з кешу префікса", min: 0, max: 100, step: 5, value: st.cached * 100, fmt: function (v) { return v + "%"; }, onInput: function (v) { st.cached = v / 100; redraw(); } });
    K.slider(ctl, { label: "Reasoning-токенів на запит", min: 0, max: 20000, step: 100, value: st.reasoning, fmt: K.fmtNum, onInput: function (v) { st.reasoning = v; redraw(); } });
    K.select(ctl, { label: "Мова тексту", options: LANGS.map(function (x) { return x[0]; }), value: 0, onInput: function (i) { st.lang = LANGS[i][1]; redraw(); } });
    K.check(ctl, { label: "Batch API (відповідь не миттєво, −50%)", value: st.batch, onInput: function (v) { st.batch = v; redraw(); } });
    K.select(ctl, { label: "Модель (шаблон цін)", options: MODELS.map(function (m) { return m.name; }), value: st.model, onInput: setModel });
    ctl.appendChild(el("p", { class: "note", text: "Ціни умовні, $ за 1 млн токенів. Підстав свої з прайсу провайдера:" }));
    [["inp", "Ціна входу"], ["cached", "Ціна входу з кешу"], ["out", "Ціна виводу (і reasoning)"]].forEach(function (x) {
      priceInputs[x[0]] = K.num(ctl, { label: x[1], value: st.price[x[0]], step: 0.01, onInput: function (v) { st.price[x[0]] = v; redraw(); } });
    });
    redraw();
  }

  window.SB_SANDBOXES["llm-cost"] = {
    title: "Калькулятор вартості LLM",
    analogy: "Рахунок за LLM схожий на рахунок за таксі: платиш за кілометри входу, за кілометри виводу, а «думання» водія (reasoning) тарифікується як вивід. Знижка на попередню домовленість (кеш префікса) і на «неспішну» поїздку (batch) може важити більше, ніж дешевший автомобіль.",
    formula: "Вартість = запитів × (вхід_без_кешу × ціна_входу + вхід_з_кешу × ціна_кешу + (вивід + reasoning) × ціна_виводу) × (0,5 якщо batch). Токени ×1,4 для української: той самий зміст коштує більше.",
    mapping: [
      ["Повзунок «входу»", "Довжина промпту й контексту", "Системний промпт, історія, знайдені чанки RAG"],
      ["Частка кешу", "Знижка за повторюваний префікс", "Prompt caching: стабільний початок промпту читається дешевше"],
      ["Reasoning-токени", "Думання перед відповіддю", "Приховані токени «міркування», тарифікуються як вивід"],
      ["Batch API", "Відкладена поїздка", "Асинхронна обробка зі знижкою, коли відповідь не потрібна миттєво"],
    ],
    mount: mount,
  };
})();
