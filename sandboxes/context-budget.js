// Пісочниця «Бюджет контексту»: що лишається у вікні, коли спрацьовує компактизація, і де ховається «lost in the middle».
(function () {
  "use strict";
  var K = window.SB_KIT;

  var RESERVE = 1500;        // токенів лишаємо під відповідь моделі
  var TURN = 350;            // токенів на один хід розмови (питання + відповідь)
  var KEEP_TURNS = 4;        // скільки останніх ходів компактизація лишає дослівно
  var SUMMARY_RATIO = 0.15;  // у скільки разів стискається решта історії

  // чиста функція: з параметрів у розподіл вікна
  function plan(p) {
    var hist = p.turns * TURN, docsAll = p.docs * p.docTok;
    var demand = p.instr + p.memory + docsAll + hist;
    var cap = p.window - RESERVE;
    var threshold = p.window * p.threshold;
    var compacted = false, histKept = hist;
    if (demand > threshold && p.turns > KEEP_TURNS) {
      compacted = true;
      var old = (p.turns - KEEP_TURNS) * TURN;
      histKept = Math.round(old * SUMMARY_RATIO) + KEEP_TURNS * TURN;
    }
    var docsKept = p.docs;
    var used = p.instr + p.memory + p.docs * p.docTok + histKept;
    // якщо й після компактизації не влізло, спершу відкидаємо хвіст документів (найнижчий пріоритет), потім історію
    while (used > cap && docsKept > 0) { docsKept--; used -= p.docTok; }
    var histFinal = histKept;
    if (used > cap) { histFinal = Math.max(0, histKept - (used - cap)); used = used - histKept + histFinal; }
    var turnAt = null;                                  // на якому ході спрацює компактизація
    var fixed = p.instr + p.memory + docsAll;
    if (fixed < threshold) turnAt = Math.floor((threshold - fixed) / TURN) + 1;
    return { hist: hist, docsAll: docsAll, demand: demand, cap: cap, threshold: threshold, compacted: compacted,
      docsKept: docsKept, histFinal: histFinal, used: used, turnAt: turnAt, histKept: histKept };
  }

  // ілюстративна U-подібна «увага» до позиції документа: краї ~100%, середина ~55%
  function attention(pos, n) {
    if (n <= 1) return 1;
    var x = (pos - 1) / (n - 1);
    return 0.55 + 0.45 * Math.pow(Math.abs(2 * x - 1), 1.5);
  }

  function mount(root) {
    var el = K.el;
    var st = { window: 32000, instr: 1500, memory: 800, docs: 8, docTok: 1200, turns: 30, threshold: 0.8, key: 4 };
    var ctl = el("div", { class: "sb-controls" });
    var res = el("div", { class: "sb-result", "aria-live": "polite" });
    root.appendChild(el("div", { class: "sb-layout" }, [ctl, res]));
    var keySlider;

    function redraw() {
      var r = plan(st);
      var W = st.window;
      res.textContent = "";
      var seg = function (v, cls, title) { return el("span", { class: "sb-fill " + cls, style: "width:" + Math.min(100, v / W * 100) + "%", title: title }); };
      res.appendChild(el("h4", { text: "Вікно " + K.fmtNum(W) + " токенів" }));
      res.appendChild(el("div", { class: "sb-track sb-stack tall", role: "img", "aria-label": "Заповнення вікна по секціях" }, [
        seg(st.instr, "c1", "Інструкції"), seg(st.memory, "c2", "Пам'ять"), seg(r.docsKept * st.docTok, "c3", "Документи"), seg(r.histFinal, "c4", "Історія"),
      ]));
      res.appendChild(el("p", { class: "note", text: "Синій: інструкції · зелений: пам'ять · помаранчевий: документи · рожевий: історія. Зайнято " +
        K.fmtNum(r.used) + " з " + K.fmtNum(r.cap) + " (решта " + K.fmtNum(RESERVE) + " під відповідь). Поріг компактизації: " + K.fmtNum(r.threshold) + "." }));

      var tbl = el("table", { class: "sb-map" });
      [["Секція", "Потрібно", "У вікні"],
        ["Інструкції", st.instr, st.instr], ["Пам'ять", st.memory, st.memory],
        ["Документи (" + st.docs + "×" + st.docTok + ")", r.docsAll, r.docsKept * st.docTok],
        ["Історія (" + st.turns + " ходів)", r.hist, r.histFinal]].forEach(function (row, i) {
        tbl.appendChild(el("tr", {}, row.map(function (c, j) { return el(i === 0 ? "th" : "td", { text: i && j ? K.fmtNum(c) : c }); })));
      });
      res.appendChild(tbl);

      var msgs = [];
      if (r.compacted) msgs.push("Компактизація спрацювала: старі ходи стиснуто до підсумку, лишено " + KEEP_TURNS + " останніх дослівно (історія " + K.fmtNum(r.hist) + " → " + K.fmtNum(r.histKept) + ").");
      else msgs.push(r.turnAt ? "Компактизація спрацює приблизно на ході " + r.turnAt + "." : "Інструкції, пам'ять і документи самі вже перевищують поріг: компактизація історії не допоможе.");
      if (r.docsKept < st.docs) msgs.push("Не вмістилось: відкинуто " + (st.docs - r.docsKept) + " документів з кінця списку.");
      if (r.histFinal < r.histKept) msgs.push("Навіть історію довелось обрізати: збільш вікно або скоротіть документи.");
      res.appendChild(el("div", { class: "sb-verdict " + (r.docsKept < st.docs ? "leak" : "safe"), text: msgs.join(" ") }));

      // документи: смуга «уваги» за позицією (ілюстративна модель)
      if (st.docs > 0) {
        res.appendChild(el("h4", { text: "Lost in the middle: увага до документів за позицією" }));
        var strip = el("div", { class: "sb-strip", role: "img", "aria-label": "Увага до документів за позицією" });
        for (var i = 1; i <= st.docs; i++) {
          var cut = i > r.docsKept, a = attention(i, st.docs);
          strip.appendChild(el("span", { class: "sb-cell" + (i === st.key ? " key" : "") + (cut ? " cut" : ""), title: "Документ " + i + (cut ? ": обрізано" : ": увага ≈ " + Math.round(a * 100) + "%"),
            style: "opacity:" + (cut ? 0.25 : 0.35 + a * 0.65), text: String(i) }));
        }
        res.appendChild(strip);
        var k = Math.min(st.key, st.docs), kc = k > r.docsKept;
        res.appendChild(el("p", { class: "note", text: kc ? "Ключовий документ №" + k + " обрізано, модель його не побачить." :
          "Ключовий документ №" + k + ": ілюстративна ймовірність, що модель його використає ≈ " + Math.round(attention(k, st.docs) * 100) + "%. Постав найважливіше на початок або в кінець." }));
      }
    }

    K.slider(ctl, { label: "Розмір контекстного вікна", min: 4000, max: 200000, step: 1000, value: st.window, fmt: K.fmtNum, onInput: function (v) { st.window = v; redraw(); } });
    K.slider(ctl, { label: "Системні інструкції (токенів)", min: 200, max: 6000, step: 100, value: st.instr, fmt: K.fmtNum, onInput: function (v) { st.instr = v; redraw(); } });
    K.slider(ctl, { label: "Пам'ять про користувача (токенів)", min: 0, max: 4000, step: 100, value: st.memory, fmt: K.fmtNum, onInput: function (v) { st.memory = v; redraw(); } });
    K.slider(ctl, { label: "Знайдені документи (кількість)", min: 0, max: 20, step: 1, value: st.docs, onInput: function (v) { st.docs = v; keySlider.max = Math.max(1, v); redraw(); } });
    K.slider(ctl, { label: "Токенів на документ", min: 200, max: 4000, step: 100, value: st.docTok, fmt: K.fmtNum, onInput: function (v) { st.docTok = v; redraw(); } });
    K.slider(ctl, { label: "Довжина розмови (ходів)", min: 0, max: 150, step: 1, value: st.turns, onInput: function (v) { st.turns = v; redraw(); } });
    K.slider(ctl, { label: "Поріг компактизації (частка вікна)", min: 50, max: 95, step: 5, value: st.threshold * 100, fmt: function (v) { return v + "%"; }, onInput: function (v) { st.threshold = v / 100; redraw(); } });
    K.slider(ctl, { label: "Позиція ключового документа", min: 1, max: 20, step: 1, value: st.key, onInput: function (v) { st.key = v; redraw(); } });
    keySlider = ctl.querySelectorAll("input[type=range]")[7];
    redraw();
  }

  window.SB_SANDBOXES["context-budget"] = {
    title: "Бюджет контексту: що влізе у вікно",
    analogy: "Вікно моделі це робочий стіл фіксованого розміру. Інструкції та пам'ять лежать завжди, документи й історія змагаються за місце. Коли стіл повний, старі папери стискають у конспект, а найнижчі за пріоритетом викидають.",
    formula: "Потрібно = інструкції + пам'ять + документи + історія. Компактизація спрацьовує, коли потрібно > поріг × вікно; якщо й тоді > вікно − резерв, відкидаємо хвіст документів, потім історію. «Увага» за позицією: ілюстрація U-кривої, не вимір конкретної моделі.",
    mapping: [
      ["Смуга вікна", "Стіл з фіксованою площею", "Контекстне вікно моделі в токенах"],
      ["Поріг і підсумок", "Конспект старих паперів", "Компактизація (summarization) історії розмови"],
      ["Відкинуті документи", "Що не влізло на стіл", "Обрізання чанків RAG за пріоритетом"],
      ["Смуга позицій", "Що видно на краях стола", "Lost in the middle: середина контексту використовується гірше"],
    ],
    mount: mount,
  };
})();
