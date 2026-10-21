// Пісочниця «Агент як скінченний автомат»: стани дозволяють різні інструменти, незворотна дія чекає людину, мовчання ескалує.
(function () {
  "use strict";
  var K = window.SB_KIT;

  var TOOLS = { read_file: "read", write_report: "write", delete_file: "irreversible" };
  var KIND = { read: "читання", write: "оборотна зміна", irreversible: "незворотна дія" };
  // що дозволено де (як у таблиці завдання №184): kind → чи виконується без підтвердження
  var ALLOW = { planning: { read: true }, acting: { read: true, write: true }, waiting_approval: {}, done: {}, failed: {} };
  var NODES = ["planning", "acting", "waiting_approval", "done", "failed"];

  function newState() { return { s: "planning", denials: 0, clock: 0, pending: null, log: [] }; }

  function mount(root) {
    var el = K.el;
    var cfg = { timeout: 120, maxDenials: 3 };
    var m = newState();
    var flash = null;
    var ctl = el("div", { class: "sb-controls" });
    var res = el("div", { class: "sb-result", "aria-live": "polite" });
    root.appendChild(el("div", { class: "sb-layout" }, [ctl, res]));

    function log(text, cls) { m.log.unshift({ t: m.clock, text: text, cls: cls || "" }); if (m.log.length > 14) m.log.pop(); }
    function go(to, why) { log(m.s + " → " + to + " (" + why + ")", to === "failed" ? "stop" : "ok"); m.s = to; }
    function deny(code, tool) {
      flash = m.s;
      log("✗ " + tool + ": відмова «" + code + "»", "stop");
      if (code !== "terminal_state") {
        m.denials++;
        if (m.denials >= cfg.maxDenials && m.s !== "failed" && m.s !== "done") go("failed", "too_many_denials");
      }
    }

    function propose(tool) {
      flash = null;
      if (m.s === "done" || m.s === "failed") return deny("terminal_state", tool);
      if (m.s === "waiting_approval") return deny("waiting_approval", tool);
      var kind = TOOLS[tool];
      if (!kind) return deny("unknown_tool", tool);
      if (kind === "irreversible" && m.s === "acting") {
        m.pending = { tool: tool, at: m.clock };
        log("⏸ " + tool + ": потрібне підтвердження людини, виклик збережено", "wait");
        return go("waiting_approval", "irreversible_call");
      }
      if (!ALLOW[m.s][kind]) return deny("not_allowed_in_state", tool);
      log("✓ " + tool + " виконано (" + KIND[kind] + ")", "ok");
    }

    function human(ok) {
      flash = null;
      if (m.s !== "waiting_approval" || !m.pending) { log("Людині нічого підтверджувати", ""); return; }
      if (ok) { log("👤 схвалено: виконано збережений виклик " + m.pending.tool, "ok"); go("acting", "approved"); }
      else { log("👤 відхилено: " + m.pending.tool + " не виконано", "stop"); go("acting", "rejected"); }
      m.pending = null;
    }

    function wait(sec) {
      flash = null;
      m.clock += sec;
      if (m.s === "waiting_approval" && m.pending && m.clock - m.pending.at >= cfg.timeout) {
        log("⏰ людина мовчить " + cfg.timeout + " с: ескалація на оператора", "stop");
        go("failed", "approval_timeout");
        m.pending = null;
      } else log("минуло " + sec + " с", "");
    }

    function draw() {
      res.textContent = "";
      var flow = el("div", { class: "sb-fsm", role: "img", "aria-label": "Діаграма станів агента" });
      NODES.forEach(function (n, i) {
        flow.appendChild(el("span", { class: "sb-node" + (n === m.s ? " cur" : "") + (n === flash ? " flash" : "") + (n === "failed" ? " fail" : "") + (n === "done" ? " fin" : ""), text: n }));
        if (i < NODES.length - 1) flow.appendChild(el("span", { class: "sb-arrow", text: i === 2 ? "·" : "→" }));
      });
      res.appendChild(flow);
      var allowed = m.s === "acting" ? "read, write; irreversible тільки через підтвердження" : Object.keys(ALLOW[m.s]).filter(function (k) { return ALLOW[m.s][k]; }).join(", ") || "нічого";
      res.appendChild(el("p", { text: "Стан: " + m.s + ". Дозволено: " + allowed + "." }));
      var waiting = m.s === "waiting_approval" && m.pending ? " · очікування підтвердження " + (m.clock - m.pending.at) + " з " + cfg.timeout + " с" : "";
      res.appendChild(el("p", { class: "note", text: "Відмов: " + m.denials + " з " + cfg.maxDenials + " · годинник: " + m.clock + " с" + waiting }));
      var ol = el("ol", { class: "sb-flow" });
      if (!m.log.length) ol.appendChild(el("li", { class: "ok" }, [el("span", { text: "Журнал порожній: натисни дію зліва." })]));
      m.log.forEach(function (x) { ol.appendChild(el("li", { class: x.cls === "stop" ? "stop" : x.cls === "wait" ? "wait" : "ok" }, [el("b", { text: "t=" + x.t + " с" }), el("span", { text: x.text })])); });
      res.appendChild(el("h4", { text: "Журнал переходів і викликів" }));
      res.appendChild(ol);
    }

    function btn(label, fn) { return K.button(ctl, label, function () { fn(); draw(); }); }
    ctl.appendChild(el("p", { class: "note", text: "Що пропонує модель:" }));
    btn("read_file (читання)", function () { propose("read_file"); });
    btn("write_report (оборотна зміна)", function () { propose("write_report"); });
    btn("delete_file (незворотна)", function () { propose("delete_file"); });
    btn("format_disk (невідомий інструмент)", function () { propose("format_disk"); });
    ctl.appendChild(el("p", { class: "note", text: "Керування агентом:" }));
    btn("План готовий → acting", function () { if (m.s === "planning") go("acting", "plan_ready"); else log("Перехід можливий лише з planning", ""); });
    btn("Завершити задачу → done", function () { if (m.s === "acting") go("done", "task_complete"); else log("Завершити можна лише з acting", ""); });
    ctl.appendChild(el("p", { class: "note", text: "Людина:" }));
    btn("👍 Схвалити", function () { human(true); });
    btn("👎 Відхилити", function () { human(false); });
    btn("⏳ Мовчить: +30 с", function () { wait(30); });
    ctl.appendChild(el("p", { class: "note", text: "Налаштування:" }));
    K.slider(ctl, { label: "Тайм-аут підтвердження (с)", min: 30, max: 300, step: 30, value: cfg.timeout, onInput: function (v) { cfg.timeout = v; draw(); } });
    K.slider(ctl, { label: "Ліміт відмов до failed", min: 1, max: 6, step: 1, value: cfg.maxDenials, onInput: function (v) { cfg.maxDenials = v; draw(); } });
    K.button(ctl, "↺ Почати спочатку", function () { m = newState(); flash = null; draw(); });
    draw();
  }

  window.SB_SANDBOXES["agent-fsm"] = {
    title: "Агент як скінченний автомат",
    analogy: "Стажист у лабораторії: у «плануванні» він лише читає документи, в «роботі» змінює оборотні речі, а перед незворотною дією (злити розчин) кличе старшого. Якщо старший мовчить, стажист не вирішує сам, а зупиняється й сповіщає начальника.",
    formula: "Дозвіл = таблиця (стан, тип інструмента). Незворотний виклик у acting не виконується, а зберігається й переводить у waiting_approval; схвалення виконує саме збережений виклик. Відмови накопичуються: ліміт → failed. Тайм-аут очікування → failed з ескалацією.",
    mapping: [
      ["Діаграма станів", "Фази роботи", "Стан агента в харнесі: planning, acting, waiting_approval, done, failed"],
      ["Кнопки моделі", "Пропозиції стажиста", "Виклики інструментів, які пропонує модель"],
      ["Схвалити / мовчить", "Старший відповів або ні", "HITL-гейт зі збереженим викликом і тайм-аутом"],
      ["Лічильник відмов", "Скільки разів стажист ліз у заборонене", "Ознака скомпрометованої моделі: швидкий перехід у failed"],
    ],
    mount: mount,
  };
})();
