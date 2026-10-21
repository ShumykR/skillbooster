// Пісочниця «RRF»: злиття двох рейтингів (BM25 і вектор) за позиціями, а не за «сирими» оцінками.
(function () {
  "use strict";
  var K = window.SB_KIT;

  var DOCS = { A: "Інструкція зі встановлення", B: "FAQ: повернення коштів", C: "Код помилки E-4096", D: "Політика відпусток",
    E: "Як скасувати підписку", F: "Тарифи 2026", G: "Контакти підтримки", H: "Політика конфіденційності" };

  // RRF: score(d) = Σ w_i / (k + rank_i(d)); рівні бали розв'язуємо за найкращою позицією, потім за id (детермінованість)
  function fuse(lists, weights, k) {
    var score = {}, parts = {}, best = {};
    lists.forEach(function (list, li) {
      list.forEach(function (id, i) {
        var c = weights[li] / (k + i + 1);
        score[id] = (score[id] || 0) + c;
        (parts[id] = parts[id] || [0, 0])[li] = c;
        best[id] = Math.min(best[id] || 99, i + 1);
      });
    });
    return Object.keys(score).sort(function (a, b) {
      return score[b] - score[a] || best[a] - best[b] || (a < b ? -1 : 1);
    }).map(function (id) { return { id: id, score: score[id], parts: parts[id] }; });
  }

  function mount(root) {
    var el = K.el;
    var st = { k: 60, w: [1, 1], target: "E",
      lists: [["G", "B", "F", "A", "D", "E", "C", "H"], ["B", "E", "H", "G", "A", "F", "D", "C"]] };
    var names = ["BM25 (за словами)", "Вектор (за змістом)"];
    var ctl = el("div", { class: "sb-controls" });
    var res = el("div", { class: "sb-result", "aria-live": "polite" });
    root.appendChild(el("div", { class: "sb-layout" }, [ctl, res]));
    var listBox = el("div", { class: "sb-lists" });
    var focusReq = null;

    function rankIn(list, id) { return list.indexOf(id) + 1; }
    function metric(rank) { return "#" + rank + " · recall@5 " + (rank <= 5 ? "1" : "0") + " · RR " + K.fmtNum(1 / rank, 2); }

    function move(li, i, d) {
      var l = st.lists[li], j = i + d;
      if (j < 0 || j >= l.length) return;
      var t = l[i]; l[i] = l[j]; l[j] = t;
      focusReq = { li: li, id: t, d: d };
      redraw();
    }

    function drawLists() {
      listBox.textContent = "";
      st.lists.forEach(function (list, li) {
        var ol = el("ol", { class: "sb-rank" });
        list.forEach(function (id, i) {
          var up = el("button", { class: "sb-mv", type: "button", "aria-label": "Вище: " + DOCS[id], text: "▲" });
          var dn = el("button", { class: "sb-mv", type: "button", "aria-label": "Нижче: " + DOCS[id], text: "▼" });
          up.addEventListener("click", function () { move(li, i, -1); });
          dn.addEventListener("click", function () { move(li, i, 1); });
          up.setAttribute("data-k", li + id + "u"); dn.setAttribute("data-k", li + id + "d");
          ol.appendChild(el("li", { class: id === st.target ? "target" : "" }, [el("span", { text: DOCS[id] }), up, dn]));
        });
        listBox.appendChild(el("div", {}, [el("h4", { text: names[li] }), ol]));
      });
      if (focusReq) {
        var b = listBox.querySelector('[data-k="' + focusReq.li + focusReq.id + (focusReq.d < 0 ? "u" : "d") + '"]');
        if (b) b.focus();
        focusReq = null;
      }
    }

    function redraw() {
      drawLists();
      var fused = fuse(st.lists, st.w, st.k);
      var max = fused[0].score;
      res.textContent = "";
      res.appendChild(el("h4", { text: "Злитий рейтинг (RRF, k = " + st.k + ")" }));
      var ol = el("ol", { class: "sb-rank fused" });
      fused.forEach(function (x) {
        var seg = function (v, cls) { return el("span", { class: "sb-fill " + cls, style: "width:" + (max ? v / max * 100 : 0) + "%" }); };
        ol.appendChild(el("li", { class: x.id === st.target ? "target" : "" }, [
          el("span", { text: DOCS[x.id] }),
          el("span", { class: "sb-track sb-stack", title: "внесок BM25 (синій) і вектора (зелений)" }, [seg(x.parts[0], "c1"), seg(x.parts[1], "c2")]),
          el("span", { class: "sb-num", text: K.fmtNum(x.score * 1000, 2) }),
        ]));
      });
      res.appendChild(ol);
      var fr = fused.map(function (x) { return x.id; }).indexOf(st.target) + 1;
      var r0 = rankIn(st.lists[0], st.target), r1 = rankIn(st.lists[1], st.target);
      var tbl = el("table", { class: "sb-map" });
      [["«" + DOCS[st.target] + "»", "Позиція · recall@5 · RR"], ["BM25", metric(r0)], ["Вектор", metric(r1)], ["RRF", metric(fr)]].forEach(function (row, i) {
        tbl.appendChild(el("tr", {}, row.map(function (c) { return el(i === 0 ? "th" : "td", { text: c }); })));
      });
      res.appendChild(tbl);
      var better = fr < Math.min(r0, r1) ? "Злиття випередило обидва списки." : fr <= Math.max(r0, r1) ? "Злиття не гірше за слабший список." : "Злиття гірше за обидва: зазвичай так, коли документ у списках у протилежних кінцях.";
      res.appendChild(el("div", { class: "sb-verdict safe", text: better }));
    }

    ctl.appendChild(el("p", { class: "note", text: "Запит: «як відписатися від сервісу». Дві пошукові системи віддали свої рейтинги (внизу). Міняй позиції кнопками ▲▼ і дивись, як змінюється злитий список." }));
    K.select(ctl, { label: "Правильна відповідь", options: Object.keys(DOCS).map(function (id) { return DOCS[id]; }), value: Object.keys(DOCS).indexOf(st.target),
      onInput: function (i) { st.target = Object.keys(DOCS)[i]; redraw(); } });
    K.slider(ctl, { label: "k (згладжування: більше k = менш різкий внесок верхніх позицій)", min: 1, max: 100, step: 1, value: st.k, onInput: function (v) { st.k = v; redraw(); } });
    K.slider(ctl, { label: "Вага BM25", min: 0, max: 2, step: 0.1, value: 1, fmt: function (v) { return v.toFixed(1); }, onInput: function (v) { st.w[0] = v; redraw(); } });
    K.slider(ctl, { label: "Вага вектора", min: 0, max: 2, step: 0.1, value: 1, fmt: function (v) { return v.toFixed(1); }, onInput: function (v) { st.w[1] = v; redraw(); } });
    root.appendChild(listBox);
    redraw();
  }

  window.SB_SANDBOXES.rrf = {
    title: "RRF: злиття рейтингів BM25 і вектора",
    analogy: "Два експерти по-різному ранжують кандидатів. Ти не складаєш їхні «оцінки» (вони в різних одиницях), а даєш бали за місце: перше місце цінніше, але не безмежно. Хто високо в обох списках, виграє.",
    formula: "score(d) = Σ вага_i / (k + позиція_i(d)). Типове k = 60. recall@5 = чи є правильний документ у топ-5; RR = 1 / позиція (MRR це середнє RR за запитами).",
    mapping: [
      ["Два списки ▲▼", "Думка двох експертів", "Результати BM25 (за збігом слів) і векторного пошуку (за змістом)"],
      ["k", "Крутизна шкали місць", "Малий k: перші місця важать значно більше; великий: рейтинг вирівнюється"],
      ["Вага", "Довіра до експерта", "Налаштування гібридного пошуку під свої дані"],
      ["recall@5, RR", "Чи потрапила відповідь у видачу", "Метрики retrieval до і після злиття"],
    ],
    mount: mount,
  };
})();
