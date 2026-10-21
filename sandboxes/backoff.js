// Пісочниця «Backoff і jitter»: усі клієнти повторюють запити після падіння сервера. Без jitter вони б'ють хвилями (thundering herd).
(function () {
  "use strict";
  var K = window.SB_KIT;
  var T = 120;  // тривалість симуляції, секунд (крок 1 с)
  var STRATS = ["Фіксований інтервал", "Експоненційний backoff", "Експоненційний + full jitter"];

  // повертає навантаження по секундах, час успіху кожного клієнта й підсумки; усе детерміновано seed'ом
  function simulate(strat, p, seed) {
    var rnd = K.rng(seed);
    var next = [], tries = [], done = [], load = [], i;
    for (i = 0; i < p.clients; i++) { next.push(0); tries.push(0); done.push(null); }
    var attempts = 0;
    for (var s = 0; s < T; s++) {
      var bucket = [];
      for (i = 0; i < p.clients; i++) if (done[i] === null && Math.floor(next[i]) === s) bucket.push(i);
      bucket.sort(function (a, b) { return next[a] - next[b] || a - b; });
      load.push(bucket.length);
      attempts += bucket.length;
      bucket.forEach(function (c, idx) {
        if (s >= p.recover && idx < p.capacity) { done[c] = next[c]; return; }
        var step = Math.min(p.cap, p.base * Math.pow(2, tries[c]));
        var delay = strat === 0 ? p.base : strat === 1 ? step : rnd() * step;
        tries[c]++;
        next[c] = Math.max(next[c] + delay, s + 1);   // не раніше наступного кроку симуляції
      });
    }
    var ok = done.filter(function (x) { return x !== null; });
    var last = ok.length === p.clients ? Math.max.apply(null, ok) : null;
    var avg = ok.length ? ok.reduce(function (a, b) { return a + b; }, 0) / ok.length : null;
    var peak = Math.max.apply(null, load.slice(Math.ceil(p.recover)).concat([0]));
    return { load: load, attempts: attempts, last: last, avg: avg, peak: peak, ok: ok.length };
  }

  function mount(root) {
    var el = K.el;
    var st = { clients: 200, recover: 20, capacity: 30, cap: 32, base: 1, strat: 0, seed: 7 };
    var ctl = el("div", { class: "sb-controls" });
    var res = el("div", { class: "sb-result", "aria-live": "polite" });
    root.appendChild(el("div", { class: "sb-layout" }, [ctl, res]));

    function redraw() {
      var r = simulate(st.strat, st, st.seed);
      res.textContent = "";
      res.appendChild(el("h4", { text: "Запитів до сервера за секунду (" + STRATS[st.strat] + ")" }));
      K.columns(res, r.load.map(function (v, s) { return { v: v, cls: s < st.recover ? "down" : v > st.capacity ? "bad" : "ok", title: "t=" + s + " c: " + v + " запитів" }; }),
        { line: st.capacity, lineLabel: "Місткість сервера", label: "Навантаження на сервер по секундах" });
      res.appendChild(el("p", { class: "note", text: "Сірі стовпчики: сервер лежить (до " + st.recover + " с). Пунктир: місткість " + st.capacity + " запитів/с; червоні стовпчики перевищують її й відхиляються." }));

      var tbl = el("table", { class: "sb-map" });
      var head = ["Стратегія", "Пік після відновлення", "Усі успішні за", "Середній час успіху", "Усього спроб"];
      tbl.appendChild(el("tr", {}, head.map(function (h) { return el("th", { text: h }); })));
      STRATS.forEach(function (name, i) {
        var x = simulate(i, st, st.seed);
        tbl.appendChild(el("tr", { class: i === st.strat ? "sel" : "" }, [name, K.fmtNum(x.peak) + "/с", x.last == null ? "понад " + T + " с" : K.fmtNum(x.last) + " с",
          x.avg == null ? "-" : K.fmtNum(x.avg, 1) + " с", K.fmtNum(x.attempts)].map(function (c, j) { return el(j ? "td" : "th", { text: c }); })));
      });
      res.appendChild(tbl);
      res.appendChild(el("div", { class: "sb-verdict " + (r.peak > st.capacity ? "leak" : "safe"),
        text: r.peak > st.capacity ? "Хвилі повторів перевищують місткість: сервер, що ледь піднявся, знову падає під шквалом запитів." : "Навантаження після відновлення вкладається в місткість сервера." }));
    }

    K.slider(ctl, { label: "Клієнтів, що повторюють запити", min: 10, max: 500, step: 10, value: st.clients, onInput: function (v) { st.clients = v; redraw(); } });
    K.slider(ctl, { label: "Сервер відновиться через (с)", min: 5, max: 60, step: 1, value: st.recover, onInput: function (v) { st.recover = v; redraw(); } });
    K.slider(ctl, { label: "Місткість сервера (запитів/с)", min: 5, max: 100, step: 5, value: st.capacity, onInput: function (v) { st.capacity = v; redraw(); } });
    K.slider(ctl, { label: "Стеля затримки cap (с)", min: 4, max: 64, step: 4, value: st.cap, onInput: function (v) { st.cap = v; redraw(); } });
    K.slider(ctl, { label: "Базова затримка (с)", min: 1, max: 4, step: 1, value: st.base, onInput: function (v) { st.base = v; redraw(); } });
    K.select(ctl, { label: "Стратегія", options: STRATS, value: st.strat, onInput: function (v) { st.strat = v; redraw(); } });
    K.button(ctl, "🎲 Інший seed", function () { st.seed = (st.seed * 48271) % 2147483647; redraw(); });
    ctl.appendChild(el("p", { class: "note", text: "Seed визначає «випадкові» затримки jitter: той самий seed дає той самий результат. Крок симуляції 1 с." }));
    redraw();
  }

  window.SB_SANDBOXES.backoff = {
    title: "Backoff і jitter: чому клієнти б'ють хвилями",
    analogy: "Ворота відчинили після ремонту, а всі, хто стояв під ними, кидаються одночасно: тиснява. Якщо кожен чекає свій випадковий час, до воріт підходять по одному.",
    formula: "Затримка після n-ї невдачі: фіксована = b; експоненційна = min(cap, b·2ⁿ); full jitter = випадкове з [0, min(cap, b·2ⁿ)]. Синхронні клієнти без jitter повторюють у ті самі секунди.",
    mapping: [
      ["Клієнти", "Натовп під воротами", "Багато екземплярів сервісу чи мобільних застосунків із однаковим кодом повторів"],
      ["Місткість і пунктир", "Скільки людей проходить за секунду", "Пропускна здатність відновленої залежності"],
      ["Стратегія", "Правило, коли йти знову", "Політика ретраїв у HTTP-клієнті чи LLM-шлюзі"],
      ["Seed", "Фіксований жереб", "Детермінізм для тестів: jitter передається як параметр"],
    ],
    mount: mount,
  };
})();
