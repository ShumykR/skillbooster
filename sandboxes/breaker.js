// Пісочниця «Circuit breaker»: стани closed/open/half-open, скільки запитів не дійшли до зламаної залежності і що з затримкою.
(function () {
  "use strict";
  var K = window.SB_KIT;
  var T = 120;                 // секунд симуляції (крок 1 с)
  var LAT_OK = 50, LAT_FAIL = 2000, LAT_FAST = 5;   // мс: успіх, таймаут зламаної залежності, швидка відмова breaker'а

  function simulate(p, seed, useBreaker) {
    var rnd = K.rng(seed);
    var state = "closed", openUntil = 0, consec = 0, probesLeft = 0, probesOk = 0;
    var states = [], calls = [], total = 0, reached = 0, wasted = 0, fast = 0, latSum = 0, slow = 0, recoveredAt = null;
    for (var t = 0; t < T; t++) {
      var outage = t >= p.start && t < p.start + p.dur;
      var perr = outage ? p.err : 0;
      if (useBreaker && state === "open" && t >= openUntil) { state = "half"; probesLeft = p.probes; probesOk = 0; }
      states.push(useBreaker ? state : "closed");
      var callsNow = 0;
      for (var i = 0; i < p.rps; i++) {
        total++;
        var allow = !useBreaker || state === "closed" || (state === "half" && probesLeft > 0);
        if (!allow) { fast++; latSum += LAT_FAST; continue; }
        if (state === "half") probesLeft--;
        callsNow++; reached++;
        var fail = rnd() < perr;
        if (fail) { wasted++; latSum += LAT_FAIL; slow++; } else latSum += LAT_OK;
        if (!useBreaker) continue;
        if (state === "closed") {
          consec = fail ? consec + 1 : 0;
          if (consec >= p.threshold) { state = "open"; openUntil = t + p.openFor; consec = 0; }
        } else if (state === "half") {
          if (fail) { state = "open"; openUntil = t + p.openFor; }
          else if (++probesOk >= p.probes) { state = "closed"; consec = 0; }
        }
      }
      calls.push({ n: callsNow, bad: outage });
      if (recoveredAt === null && t >= p.start + p.dur && states[t] === "closed") recoveredAt = t - (p.start + p.dur);
    }
    return { states: states, calls: calls, total: total, reached: reached, wasted: wasted, fast: fast, avg: total ? latSum / total : 0, slow: slow, recoveredAt: recoveredAt };
  }

  function mount(root) {
    var el = K.el;
    var st = { rps: 10, start: 20, dur: 40, err: 1, threshold: 5, openFor: 10, probes: 3, seed: 3 };
    var ctl = el("div", { class: "sb-controls" });
    var res = el("div", { class: "sb-result", "aria-live": "polite" });
    root.appendChild(el("div", { class: "sb-layout" }, [ctl, res]));
    var COLOR = { closed: "ok", open: "bad", half: "warn" };

    function redraw() {
      var a = simulate(st, st.seed, true), b = simulate(st, st.seed, false);
      res.textContent = "";
      res.appendChild(el("h4", { text: "Стан breaker'а за секундами" }));
      var strip = el("div", { class: "sb-states", role: "img", "aria-label": "Стан breaker за секундами" });
      a.states.forEach(function (s, t) {
        var inOut = t >= st.start && t < st.start + st.dur;
        strip.appendChild(el("span", { class: "sb-st " + COLOR[s] + (inOut ? " outage" : ""), title: "t=" + t + " с: " + s + (inOut ? " (залежність лежить)" : "") }));
      });
      res.appendChild(strip);
      res.appendChild(el("p", { class: "note", text: "Зелений: closed · червоний: open (швидка відмова) · жовтий: half-open (пробні запити). Підкреслено: залежність справді лежить." }));
      res.appendChild(el("h4", { text: "Запити, що дійшли до залежності, за секунду" }));
      K.columns(res, a.calls.map(function (c, t) { return { v: c.n, cls: c.bad ? "bad" : "ok", title: "t=" + t + " с: " + c.n }; }), { height: 70, label: "Запити до залежності" });

      var tbl = el("table", { class: "sb-map" });
      [["", "Без breaker", "З breaker"],
        ["Усього запитів", K.fmtNum(b.total), K.fmtNum(a.total)],
        ["Дійшло до зламаної залежності", K.fmtNum(b.wasted), K.fmtNum(a.wasted)],
        ["Швидка відмова без виклику", "0", K.fmtNum(a.fast)],
        ["Повільних запитів (таймаут " + LAT_FAIL + " мс)", K.fmtNum(b.slow), K.fmtNum(a.slow)],
        ["Середня затримка", K.fmtNum(b.avg) + " мс", K.fmtNum(a.avg) + " мс"],
        ["Відновлення після кінця аварії", "миттєво", a.recoveredAt == null ? "не встигло" : a.recoveredAt + " с"]].forEach(function (row, i) {
        tbl.appendChild(el("tr", {}, row.map(function (c) { return el(i === 0 ? "th" : "td", { text: c }); })));
      });
      res.appendChild(tbl);
      var saved = b.wasted ? Math.round((1 - a.wasted / b.wasted) * 100) : 0;
      res.appendChild(el("div", { class: "sb-verdict safe", text: "Breaker зекономив " + saved + "% викликів зламаної залежності та зменшив середню затримку з " + K.fmtNum(b.avg) + " до " + K.fmtNum(a.avg) +
        " мс. Ціна: breaker повертається в closed " + (a.recoveredAt == null ? "вже після кінця симуляції" : a.recoveredAt ? "лише через " + a.recoveredAt + " с після кінця аварії" : "одразу після кінця аварії") + "." }));
    }

    K.slider(ctl, { label: "Запитів на секунду", min: 1, max: 50, step: 1, value: st.rps, onInput: function (v) { st.rps = v; redraw(); } });
    K.slider(ctl, { label: "Аварія починається на секунді", min: 5, max: 60, step: 1, value: st.start, onInput: function (v) { st.start = v; redraw(); } });
    K.slider(ctl, { label: "Тривалість аварії (с)", min: 5, max: 60, step: 1, value: st.dur, onInput: function (v) { st.dur = v; redraw(); } });
    K.slider(ctl, { label: "Частка помилок під час аварії", min: 10, max: 100, step: 5, value: st.err * 100, fmt: function (v) { return v + "%"; }, onInput: function (v) { st.err = v / 100; redraw(); } });
    K.slider(ctl, { label: "Поріг: помилок підряд до відкриття", min: 1, max: 20, step: 1, value: st.threshold, onInput: function (v) { st.threshold = v; redraw(); } });
    K.slider(ctl, { label: "Скільки секунд open", min: 1, max: 30, step: 1, value: st.openFor, onInput: function (v) { st.openFor = v; redraw(); } });
    K.slider(ctl, { label: "Пробних запитів у half-open", min: 1, max: 10, step: 1, value: st.probes, onInput: function (v) { st.probes = v; redraw(); } });
    K.button(ctl, "🎲 Інший seed", function () { st.seed = (st.seed * 48271) % 2147483647; redraw(); });
    ctl.appendChild(el("p", { class: "note", text: "Затримки умовні: успіх 50 мс, таймаут зламаної залежності 2000 мс, швидка відмова 5 мс. Частка помилок у ході аварії задається seed'ом." }));
    redraw();
  }

  window.SB_SANDBOXES.breaker = {
    title: "Circuit breaker: стани й ціна захисту",
    analogy: "Автоматичний запобіжник у щитку: коли лінія коротить, він вимикається, щоб не спалити проводку, а потім обережно пробує ввімкнутись. Користувач швидко чує «зараз недоступно» замість того, щоб чекати таймаут.",
    formula: "closed: рахуємо помилки підряд; ≥ порогу → open. open: усі запити відхиляються одразу до закінчення таймера; потім half-open: пропускаємо N пробних, усі успішні → closed, будь-яка помилка → знову open.",
    mapping: [
      ["Стрічка станів", "Положення запобіжника", "Стан breaker'а в часі"],
      ["Швидка відмова", "Миттєва відповідь «не зараз»", "Запит не доходить до залежності й не чекає таймауту"],
      ["Поріг і таймер", "Чутливість та пауза", "failure_threshold, recovery_timeout"],
      ["Пробні запити", "Обережна спроба ввімкнути", "Half-open: невелика кількість запитів перевіряє відновлення"],
    ],
    mount: mount,
  };
})();
