// Пісочниця «Token bucket»: ємність дозволяє сплеск, швидкість поповнення задає середню межу, Retry-After каже, коли повторити.
(function () {
  "use strict";
  var K = window.SB_KIT;
  var T = 60, DT = 0.1;                         // 60 секунд, крок 0,1 с
  var PROFILES = ["Рівний потік", "Сплеск", "Атака (×10 на 15 с)"];

  // скільки запитів приходить у момент t (детерміновано: накопичувач дробової частини)
  function arrivals(profile, p, t, acc) {
    var rate = p.lambda;
    if (profile === 2 && t >= 20 && t < 35) rate *= 10;
    acc.v += rate * DT;
    var n = Math.floor(acc.v);
    acc.v -= n;
    if (profile === 1 && (Math.abs(t - 10) < DT / 2 || Math.abs(t - 35) < DT / 2)) n += p.burst;
    return n;
  }

  function simulate(profile, p) {
    var tokens = p.cap, acc = { v: 0 }, levels = [], rejPerSec = [], accepted = 0, rejected = 0, maxRetry = 0;
    var steps = Math.round(T / DT), perSec = Math.round(1 / DT), rejSec = 0;
    for (var i = 0; i < steps; i++) {
      var t = i * DT;
      tokens = Math.min(p.cap, tokens + p.refill * DT);
      var n = arrivals(profile, p, t, acc);
      for (var k = 0; k < n; k++) {
        if (tokens >= 1) { tokens -= 1; accepted++; }
        else { rejected++; rejSec++; maxRetry = Math.max(maxRetry, Math.ceil((1 - tokens) / p.refill)); }
      }
      if (i % 5 === 0) levels.push(tokens);          // стовпчик на кожні 0,5 с
      if ((i + 1) % perSec === 0) { rejPerSec.push(rejSec); rejSec = 0; }
    }
    return { levels: levels, rejPerSec: rejPerSec, accepted: accepted, rejected: rejected, maxRetry: maxRetry };
  }

  function mount(root) {
    var el = K.el;
    var st = { cap: 10, refill: 5, lambda: 4, burst: 40, profile: 1 };
    var ctl = el("div", { class: "sb-controls" });
    var res = el("div", { class: "sb-result", "aria-live": "polite" });
    root.appendChild(el("div", { class: "sb-layout" }, [ctl, res]));

    function redraw() {
      var r = simulate(st.profile, st);
      res.textContent = "";
      res.appendChild(el("h4", { text: "Рівень відра (токенів) за 60 с" }));
      K.columns(res, r.levels.map(function (v, i) { return { v: v, cls: v < 1 ? "bad" : "ok", title: "t=" + (i * 0.5) + " с: " + K.fmtNum(v, 1) + " токенів" }; }),
        { line: st.cap, lineLabel: "Ємність відра", height: 90, label: "Рівень відра в часі" });
      res.appendChild(el("h4", { text: "Відхилені запити за секунду (429)" }));
      K.columns(res, r.rejPerSec.map(function (v, s) { return { v: v, cls: "bad", title: "t=" + s + " с: " + v + " відхилено" }; }), { height: 70, label: "Відхилені запити" });
      var total = r.accepted + r.rejected;
      var tbl = el("table", { class: "sb-map" });
      [["Усього запитів", K.fmtNum(total)], ["Прийнято", K.fmtNum(r.accepted) + " (" + K.fmtNum(total ? r.accepted / total * 100 : 0) + "%)"],
        ["Відхилено", K.fmtNum(r.rejected)], ["Найбільший Retry-After", r.maxRetry ? r.maxRetry + " с" : "-"],
        ["Середня межа", K.fmtNum(st.refill) + " запитів/с (довгострокова)"]].forEach(function (row) {
        tbl.appendChild(el("tr", {}, [el("th", { text: row[0] }), el("td", { text: row[1] })]));
      });
      res.appendChild(tbl);
      var msg = r.rejected === 0 ? "Усе прийнято: потік вкладається в швидкість поповнення, а сплеск у ємність відра." :
        st.profile === 1 && st.lambda <= st.refill ? "Сплеск вищий за ємність: відхилено лише надлишок, далі відро поповнюється зі швидкістю " + st.refill + "/с." :
        "Потік перевищує швидкість поповнення: відро спорожніло, зайве отримує 429 з Retry-After.";
      res.appendChild(el("div", { class: "sb-verdict " + (r.rejected ? "leak" : "safe"), text: msg }));
    }

    K.slider(ctl, { label: "Ємність відра (макс. сплеск)", min: 1, max: 100, step: 1, value: st.cap, onInput: function (v) { st.cap = v; redraw(); } });
    K.slider(ctl, { label: "Поповнення (токенів/с)", min: 1, max: 50, step: 1, value: st.refill, onInput: function (v) { st.refill = v; redraw(); } });
    K.slider(ctl, { label: "Базовий потік (запитів/с)", min: 1, max: 50, step: 1, value: st.lambda, onInput: function (v) { st.lambda = v; redraw(); } });
    K.slider(ctl, { label: "Розмір сплеску (запитів одразу)", min: 5, max: 200, step: 5, value: st.burst, onInput: function (v) { st.burst = v; redraw(); } });
    K.select(ctl, { label: "Профіль трафіку", options: PROFILES, value: st.profile, onInput: function (v) { st.profile = v; redraw(); } });
    ctl.appendChild(el("p", { class: "note", text: "Сплеск відбувається на 10-й і 35-й секундах; атака це ×10 від базового потоку з 20-ї по 35-ту. Retry-After = час, поки відро набере 1 токен." }));
    redraw();
  }

  window.SB_SANDBOXES["token-bucket"] = {
    title: "Token bucket: сплеск, поповнення, Retry-After",
    analogy: "Відро з жетонами: кожен запит забирає один жетон, нові падають у відро з постійною швидкістю, але відро не вміщує більше за свою ємність. Повне відро дозволяє короткий сплеск, порожнє змушує чекати.",
    formula: "tokens = min(ємність, tokens + швидкість·Δt); запит приймається, якщо tokens ≥ 1, і забирає 1. Retry-After = ⌈(1 − tokens) / швидкість⌉ секунд. Довгострокова межа = швидкість, а максимальний сплеск = ємність.",
    mapping: [
      ["Ємність", "Розмір відра", "Максимальний сплеск, який дозволено одразу"],
      ["Поповнення", "Краплі в секунду", "Середня довгострокова межа запитів"],
      ["Червоні стовпчики", "Відра не вистачило", "Відповіді 429 Too Many Requests"],
      ["Retry-After", "Скільки чекати до наступного жетона", "Заголовок відповіді, який чесний клієнт поважає"],
    ],
    mount: mount,
  };
})();
