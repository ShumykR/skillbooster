(function () {
  "use strict";

  var DATA = window.SKILLBOOSTER;
  var STORE_KEY = "skillbooster.v1";
  var THEME_KEY = "skillbooster.theme";
  var view = document.getElementById("view");
  var nav = document.getElementById("nav");
  var sidebar = document.getElementById("sidebar");

  // ---------- сховище -------------------------------------------------------
  function emptyState() {
    return { tasks: {}, verified: {}, checks: {}, concepts: {}, capstone: {}, days: [], settings: { baseUrl: "", model: "" } };
  }
  var state = load();

  function load() {
    try {
      var raw = localStorage.getItem(STORE_KEY) || localStorage.getItem("skillboost.v1"); // старий ключ до перейменування
      if (!raw) return emptyState();
      var s = JSON.parse(raw);
      var e = emptyState();
      return {
        tasks: s.tasks || e.tasks,
        verified: s.verified || e.verified,
        checks: s.checks || e.checks,
        concepts: s.concepts || e.concepts,
        capstone: s.capstone || e.capstone,
        days: s.days || e.days,
        settings: Object.assign(e.settings, s.settings || {}),
      };
    } catch (err) {
      return emptyState();
    }
  }
  function save() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (err) { /* приватний режим */ }
  }
  function today() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function touch() {
    var t = today();
    if (state.days.indexOf(t) === -1) state.days.push(t);
    save();
  }
  function streak() {
    var set = {};
    state.days.forEach(function (d) { set[d] = true; });
    var d = new Date();
    var key = function (x) {
      return x.getFullYear() + "-" + String(x.getMonth() + 1).padStart(2, "0") + "-" + String(x.getDate()).padStart(2, "0");
    };
    if (!set[key(d)]) d.setDate(d.getDate() - 1);
    var n = 0;
    while (set[key(d)]) { n++; d.setDate(d.getDate() - 1); }
    return n;
  }

  // ---------- допоміжне -----------------------------------------------------
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  // `код` і «№NNN»: номер існуючого завдання стає чипом-посиланням (поза <code>); plain вимикає чипи
  function md(s, plain) {
    var h = esc(s).replace(/`([^`]+)`/g, "<code>$1</code>");
    if (plain) return h;
    return h.split(/(<code>[\s\S]*?<\/code>)/).map(function (part, i) {
      return i % 2 ? part : part.replace(/№(\d+)/g, function (m, n) { return TASKS["t" + n] ? taskChip("t" + n) : m; });
    }).join("");
  }
  function stageById(id) { return DATA.stages.filter(function (s) { return s.id === id; })[0]; }

  // треки: окремі шляхи (Backend + DevOps, AI Engineering) зі своєю нумерацією етапів
  var TRACKS = DATA.tracks || [{ id: "core", icon: "", title: "Етапи", intro: "", order: "" }];
  var TRACK_KEY = "skillbooster.track";
  function trackById(id) { return TRACKS.filter(function (t) { return t.id === id; })[0]; }
  function trackOf(st) { return st.track || TRACKS[0].id; }
  function stagesOf(tid) { return DATA.stages.filter(function (s) { return trackOf(s) === tid; }); }
  function stageNo(st) { return stagesOf(trackOf(st)).indexOf(st) + 1; }
  var curTrack = TRACKS[0].id;
  try { if (trackById(localStorage.getItem(TRACK_KEY))) curTrack = localStorage.getItem(TRACK_KEY); } catch (err) { /* приватний режим */ }
  function setTrack(id) {
    curTrack = id;
    try { localStorage.setItem(TRACK_KEY, id); } catch (err) { /* приватний режим */ }
  }
  function checkDone(id, i) { return !!(state.checks[id] && state.checks[id][i]); }
  function taskState(id) { return state.tasks[id] || "todo"; }
  function conceptDone(stageId, i) { return !!(state.concepts[stageId] && state.concepts[stageId][i]); }

  // завдання за id і зворотні зв'язки «завдання → поняття», що воно тренує
  var TASKS = {}, TASK_STAGE = {}, TASK_CONCEPTS = {};
  DATA.stages.forEach(function (st) {
    st.tasks.forEach(function (t) { TASKS[t.id] = t; TASK_STAGE[t.id] = st.id; });
    (st.practice || []).forEach(function (ids, i) {
      ids.forEach(function (id) { (TASK_CONCEPTS[id] = TASK_CONCEPTS[id] || []).push({ stage: st, i: i }); });
    });
  });
  function practiceOf(st, i) { return (st.practice && st.practice[i]) || []; }
  function conceptProven(st, i) {
    return practiceOf(st, i).some(function (id) { return taskState(id) === "done"; });
  }
  // «розумію» (галочка або тест) і «довів» (зроблене завдання) дають по половині;
  // поняття без практики зараховується галочкою повністю
  function conceptScore(st, i) {
    var u = conceptDone(st.id, i) ? 1 : 0;
    if (!practiceOf(st, i).length) return u;
    return u / 2 + (conceptProven(st, i) ? 0.5 : 0);
  }

  function stageStats(st) {
    var td = st.tasks.filter(function (t) { return taskState(t.id) === "done"; }).length;
    var cs = 0, cu = 0, cp = 0, cpt = 0;
    st.concepts.forEach(function (_, i) {
      cs += conceptScore(st, i);
      if (conceptDone(st.id, i)) cu++;
      if (practiceOf(st, i).length) { cpt++; if (conceptProven(st, i)) cp++; }
    });
    var total = st.tasks.length + st.concepts.length;
    return {
      tasksDone: td, tasksTotal: st.tasks.length,
      conceptsDone: cs, conceptsTotal: st.concepts.length,
      conceptsUnderstood: cu, conceptsProven: cp, conceptsPractice: cpt,
      pct: total ? Math.round(((td + cs) / total) * 100) : 0,
    };
  }
  function overall(tid) {
    var done = 0, total = 0, tasksDone = 0, tasksTotal = 0;
    (tid ? stagesOf(tid) : DATA.stages).forEach(function (st) {
      var s = stageStats(st);
      done += s.tasksDone + s.conceptsDone;
      total += s.tasksTotal + s.conceptsTotal;
      tasksDone += s.tasksDone;
      tasksTotal += s.tasksTotal;
    });
    return { pct: total ? Math.round((done / total) * 100) : 0, tasksDone: tasksDone, tasksTotal: tasksTotal };
  }
  var LVL = { 1: "База", 2: "Середній", 3: "Просунутий" };
  function lvlBadge(l) { return '<span class="badge lvl' + l + '">' + LVL[l] + "</span>"; }
  function freeBadge(f) {
    var cls = f === "Безкоштовно" ? "free" : "part";
    return '<span class="badge ' + cls + '">' + esc(f) + "</span>";
  }
  function toast(msg) {
    var el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 2200);
  }

  // ---------- навігація / верхня панель -------------------------------------
  function trackTabs(cls) {
    if (TRACKS.length < 2) return "";
    return '<div class="' + cls + '">' + TRACKS.map(function (t) {
      return '<a class="track-tab' + (t.id === curTrack ? " active" : "") + '" href="#/track/' + t.id + '"' +
        (t.id === curTrack ? ' aria-current="page"' : "") + ">" + t.icon + " " + esc(t.title) +
        ' <span class="np">' + overall(t.id).pct + "%</span></a>";
    }).join("") + "</div>";
  }
  function renderNav(activeId) {
    var html = trackTabs("track-tabs side") + stagesOf(curTrack).map(function (st, i) {
      var s = stageStats(st);
      var cls = "nav-item" + (st.id === activeId ? " active" : "") + (s.pct === 100 ? " complete" : "");
      return '<a class="' + cls + '" href="#/stage/' + st.id + '">' +
        '<span class="ico">' + st.icon + "</span>" +
        '<span class="nt">' + (i + 1) + ". " + esc(st.title) + "</span>" +
        '<span class="np">' + s.pct + "%</span></a>";
    }).join("");
    nav.innerHTML = html;
  }
  function renderTop() {
    var o = overall();
    document.getElementById("topBar").style.width = o.pct + "%";
    document.getElementById("topText").textContent = o.pct + "% · " + o.tasksDone + "/" + o.tasksTotal + " завдань";
  }

  // ---------- сторінки ------------------------------------------------------
  function nextTask() {
    var list = stagesOf(curTrack);
    for (var i = 0; i < list.length; i++) {
      var st = list[i];
      var doing = st.tasks.filter(function (t) { return taskState(t.id) === "doing"; })[0];
      if (doing) return { stage: st, task: doing, doing: true };
    }
    for (var j = 0; j < list.length; j++) {
      var s2 = list[j];
      var todo = s2.tasks.filter(function (t) { return taskState(t.id) === "todo"; })[0];
      if (todo) return { stage: s2, task: todo, doing: false };
    }
    return null;
  }

  function renderHome() {
    var tr = trackById(curTrack), list = stagesOf(curTrack);
    var o = overall(curTrack);
    var nt = nextTask();
    var html = "<h1>Шлях Python-бекендера: від FastAPI до DevOps та AI</h1>" +
      '<p class="lead">Тут зібрано етапи, безкоштовні ресурси та ' + overall().tasksTotal +
      " практичних завдань із реальних production-проєктів. Відмічай прогрес, він зберігається в твоєму браузері.</p>" +
      trackTabs("track-tabs big") +
      (tr.intro ? '<p class="note">' + esc(tr.intro) + "</p>" : "") +
      '<div class="stat-row">' +
      '<div class="stat"><b>' + o.pct + '%</b><span>загальний прогрес</span></div>' +
      '<div class="stat"><b>' + o.tasksDone + "/" + o.tasksTotal + '</b><span>завдань виконано</span></div>' +
      '<div class="stat"><b>' + streak() + '</b><span>днів поспіль</span></div>' +
      '<div class="stat"><b>' + list.length + '</b><span>етапів</span></div></div>';

    if (nt) {
      html += '<div class="card next-card"><div><small>' + (nt.doing ? "Продовжити" : "Наступне завдання") + " · " +
        nt.stage.icon + " " + esc(nt.stage.title) + "</small><strong>" + esc(nt.task.title) + "</strong></div>" +
        '<a class="btn" href="#/stage/' + nt.stage.id + '" data-focus="task-' + nt.task.id + '">Відкрити</a></div>';
    } else {
      html += '<div class="card next-card"><strong>🎉 Усі завдання цього треку виконано. Час робити портфоліо й шукати роботу!</strong></div>';
    }

    html += "<h2>Етапи</h2><div class=\"grid\">" + list.map(function (st, i) {
      var s = stageStats(st);
      return '<a class="card stage-card" href="#/stage/' + st.id + '">' +
        '<div class="head"><span class="ico">' + st.icon + "</span><span>" + (i + 1) + ". " + esc(st.title) + "</span></div>" +
        "<p>" + esc(st.why) + "</p>" +
        '<div class="bar"><span style="width:' + s.pct + '%"></span></div>' +
        '<div class="meta"><span>' + s.tasksDone + "/" + s.tasksTotal + " завдань</span><span>" + s.pct + "%</span></div></a>";
    }).join("") + "</div>";

    if (tr.order) html += "<h2>Рекомендований порядок</h2>" + '<p class="note">' + esc(tr.order) + "</p>";
    return html;
  }

  function renderStage(st) {
    var tr = trackById(trackOf(st));
    var s = stageStats(st);
    var html = '<div class="crumbs"><a href="#/track/' + tr.id + '">' + esc(tr.title) + "</a> / Етап " + stageNo(st) + "</div>" +
      '<div class="stage-head"><div class="big">' + st.icon + "</div><div><h1>" + esc(st.title) + "</h1>" +
      '<div class="bar" style="width:260px;max-width:100%"><span style="width:' + s.pct + '%"></span></div>' +
      '<small class="note">' + s.pct + "% · розумію " + s.conceptsUnderstood + "/" + s.conceptsTotal +
      " · довів практикою " + s.conceptsProven + "/" + s.conceptsPractice +
      " · завдання " + s.tasksDone + "/" + s.tasksTotal + "</small></div></div>" +
      '<div class="why"><strong>Навіщо це на роботі.</strong> ' + esc(st.why) + "</div>";

    html += "<h2>Що треба знати</h2>" +
      '<p class="note">Галочка означає «розумію» (її ставить і пройдений тест 🧠). ' +
      "«Довів» зараховується сам, коли зроблено хоча б одне завдання з чипів поруч.</p>" +
      '<ul class="checklist concepts">' + st.concepts.map(function (c, i) { return conceptHtml(st, i); }).join("") + "</ul>";

    html += "<h2>Вивчити (безкоштовні ресурси)</h2><div class=\"res-grid\">" + st.resources.map(function (r) {
      return '<a class="card res" href="' + esc(r.url) + '" target="_blank" rel="noopener noreferrer">' +
        '<span class="rt">' + esc(r.name) + " ↗</span>" +
        '<span class="rn">' + esc(r.note) + "</span>" +
        '<span class="rb"><span class="badge">' + esc(r.kind) + '</span><span class="badge">' + esc(r.level) + "</span>" +
        freeBadge(r.free) + "</span></a>";
    }).join("") + "</div>";

    html += "<h2>Довести практикою</h2>" +
      '<p class="note">Клік по кружку змінює статус: не розпочато → у процесі → зроблено. Завдання з позначкою 🤖 використовують LLM (див. «Налаштування»).</p>' +
      '<div class="filters" id="filters">' +
      '<button class="chip" aria-pressed="true" data-f="all">Усі</button>' +
      '<button class="chip" aria-pressed="false" data-f="1">База</button>' +
      '<button class="chip" aria-pressed="false" data-f="2">Середній</button>' +
      '<button class="chip" aria-pressed="false" data-f="3">Просунутий</button>' +
      '<button class="chip" aria-pressed="false" data-f="open">Лише незавершені</button>' +
      (st.tasks.some(function (t) { return t.cwe && t.cwe.length; })
        ? '<button class="chip" aria-pressed="false" data-f="cwe" title="Завдання, що тренують конкретні слабкості CWE">🛡 CWE</button>' : "") +
      "</div>" +
      '<div id="taskList">' + st.tasks.map(function (t, i) {
        var head = "";
        if (t.group && (i === 0 || st.tasks[i - 1].group !== t.group)) head = '<h3 class="grp">' + esc(t.group) + "</h3>";
        return head + taskHtml(t);
      }).join("") + "</div>";
    return html;
  }

  function taskChip(id) {
    var t = TASKS[id], s = taskState(id);
    var mark = state.verified[id] ? " ✅" : s === "done" ? " ✓" : s === "doing" ? " …" : "";
    return '<a class="tchip s-' + s + '" href="#/stage/' + TASK_STAGE[id] + '" data-focus="task-' + id + '" title="' +
      esc(t.title) + '">' + (t.n ? "№" + t.n : esc(t.title)) + mark + "</a>";
  }

  function conceptHtml(st, i) {
    var key = st.id + ":" + i, ids = practiceOf(st, i);
    var qs = (st.quiz && st.quiz[i]) || [];
    var meta = "";
    if (ids.length) {
      meta += conceptProven(st, i) ? '<span class="proof ok">✓ довів</span>' : '<span class="proof">практика:</span>';
      meta += ids.map(taskChip).join("");
    }
    if (qs.length) {
      meta += '<button class="qbtn" data-quiz="' + key + '" aria-expanded="false">🧠 Перевірити себе · ' + qs.length + "</button>";
    }
    return '<li id="c-' + st.id + "-" + i + '"><label><input type="checkbox" data-concept="' + key + '"' +
      (conceptDone(st.id, i) ? " checked" : "") + "><span>" + md(st.concepts[i]) + "</span></label>" +
      (meta ? '<div class="cmeta">' + meta + "</div>" : "") +
      (qs.length ? '<div class="quiz" id="quiz-' + st.id + "-" + i + '" hidden></div>' : "") + "</li>";
  }

  // ---------- самоперевірка -------------------------------------------------
  // варіанти перемішуються при кожному відкритті; правильний пам'ятаємо за текстом
  var quizRun = null;
  function shuffled(a) {
    var r = a.slice();
    for (var i = r.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var x = r[i]; r[i] = r[j]; r[j] = x; }
    return r;
  }
  function openQuiz(key) {
    var p = key.split(":"), st = stageById(p[0]), qs = st.quiz[p[1]];
    quizRun = { key: key, left: qs.length, wrong: 0 };
    var box = document.getElementById("quiz-" + p[0] + "-" + p[1]);
    box.innerHTML = qs.map(function (q, qi) {
      return '<div class="qq" data-qi="' + qi + '"><p><b>' + (qi + 1) + ".</b> " + md(q.q) + "</p>" +
        shuffled(q.options.map(function (o, oi) { return { o: o, ok: oi === q.answer }; })).map(function (x) {
          return '<button class="qopt" data-ok="' + (x.ok ? 1 : 0) + '">' + md(x.o, true) + "</button>";
        }).join("") + '<p class="why-q" hidden>' + md(q.why) + "</p></div>";
    }).join("") + '<div class="qres" aria-live="polite"></div>';
    box.hidden = false;
  }
  function answerQuiz(btn) {
    var qq = btn.closest(".qq"), box = btn.closest(".quiz");
    if (!quizRun || qq.classList.contains("answered")) return;
    var ok = btn.getAttribute("data-ok") === "1";
    qq.classList.add("answered");
    qq.querySelectorAll(".qopt").forEach(function (b) {
      b.disabled = true;
      if (b.getAttribute("data-ok") === "1") b.classList.add("right");
    });
    if (!ok) { btn.classList.add("wrong"); quizRun.wrong++; }
    qq.querySelector(".why-q").hidden = false;
    if (--quizRun.left > 0) return;
    var res = box.querySelector(".qres"), key = quizRun.key;
    if (quizRun.wrong === 0) {
      var p = key.split(":");
      state.concepts[p[0]] = state.concepts[p[0]] || {};
      state.concepts[p[0]][p[1]] = true;
      touch();
      var cb = document.querySelector('[data-concept="' + key + '"]');
      if (cb) cb.checked = true;
      res.innerHTML = "<b>Усе правильно.</b> Поняття позначено як «розумію».";
      refreshProgress(p[0]);
    } else {
      res.innerHTML = "Помилок: " + quizRun.wrong + '. Прочитай пояснення й <button class="btn ghost" data-quiz-retry="' +
        key + '">спробуй ще раз</button>';
    }
    quizRun = null;
  }
  function refreshProgress(stageId) {
    var st = stageById(stageId);
    if (st && location.hash.indexOf("#/stage/" + stageId) === 0) {
      var s = stageStats(st);
      var small = document.querySelector(".stage-head small");
      if (small) small.textContent = s.pct + "% · розумію " + s.conceptsUnderstood + "/" + s.conceptsTotal +
        " · довів практикою " + s.conceptsProven + "/" + s.conceptsPractice + " · завдання " + s.tasksDone + "/" + s.tasksTotal;
      var bar = document.querySelector(".stage-head .bar > span");
      if (bar) bar.style.width = s.pct + "%";
    }
    renderNav(stageId);
    renderTop();
  }

  var TAG_KIND = { "": "", "~": " part", "?": " plan", "@": " lab" };
  var TAG_HINT = {
    "": "завдання тренує цю слабкість",
    "~": "часткове покриття",
    "?": "згадано в описі, ще не реалізовано",
    "@": "лише зовнішня лабораторія"
  };

  function tagsHtml(t) {
    var out = "";
    (t.cwe || []).forEach(function (raw) {
      var kind = /^[~?@]/.test(raw) ? raw.charAt(0) : "";
      var num = raw.replace(/^[~?@]/, "");
      var name = (DATA.cwe && DATA.cwe[num]) || "";
      out += '<a class="tag cwe' + TAG_KIND[kind] + '" href="https://cwe.mitre.org/data/definitions/' + esc(num) +
        '.html" target="_blank" rel="noopener noreferrer" title="' + esc((name ? name + " · " : "") + TAG_HINT[kind]) +
        '">CWE-' + esc(num) + "</a>";
    });
    (t.pattern || []).forEach(function (p) {
      out += '<span class="tag pat" title="Патерн проєктування">' + esc(p) + "</span>";
    });
    return out ? '<div class="tags">' + out + "</div>" : "";
  }

  // завдання без автотесту: кроки і чекліст «Готово, коли»; усі пункти відмічені = завдання зроблене
  function manualHtml(t) {
    if (t.auto || !t.done) return "";
    var marked = t.done.filter(function (_, i) { return checkDone(t.id, i); }).length;
    var open = marked > 0 || taskState(t.id) === "doing";
    return '<details class="manual"' + (open ? " open" : "") + "><summary>" +
      (t.kind === "документ" ? "Що підготувати" : "Як виконати") + " · готово " + marked + "/" + t.done.length + "</summary>" +
      (t.steps ? '<ol class="steps">' + t.steps.map(function (x) { return "<li>" + md(x) + "</li>"; }).join("") + "</ol>" : "") +
      '<div class="chk"><b>Готово, коли:</b></div><ul class="checklist">' +
      t.done.map(function (x, i) {
        return '<li><label><input type="checkbox" data-check="' + t.id + ":" + i + '"' + (checkDone(t.id, i) ? " checked" : "") +
          "><span>" + md(x) + "</span></label></li>";
      }).join("") + "</ul></details>";
  }

  function rerenderTask(id) {
    var card = document.getElementById("task-" + id);
    var t = TASKS[id];
    if (!card || !t) return;
    var tmp = document.createElement("div");
    tmp.innerHTML = taskHtml(t);
    card.replaceWith(tmp.firstElementChild);
    applyFilter();
    // чипи й «довів» у понять цього етапу залежать від статусу завдання
    (TASK_CONCEPTS[id] || []).forEach(function (c) {
      var li = document.getElementById("c-" + c.stage.id + "-" + c.i);
      if (li) {
        var wrap = document.createElement("div");
        wrap.innerHTML = conceptHtml(c.stage, c.i);
        li.replaceWith(wrap.firstElementChild);
      }
    });
    refreshProgress(location.hash.replace(/^#\/stage\//, ""));
  }

  function taskHtml(t) {
    var s = taskState(t.id);
    var icon = s === "done" ? "✓" : s === "doing" ? "…" : "";
    var label = s === "done" ? "Зроблено" : s === "doing" ? "У процесі" : "Не розпочато";
    return '<div class="card task ' + (s === "done" ? "done" : "") + '" data-s="' + s + '" data-lvl="' + t.level +
      '" data-tag="' + ((t.cwe && t.cwe.length) ? "cwe" : "") + '" id="task-' + t.id + '">' +
      '<button class="st" data-task="' + t.id + '" aria-label="' + label + ': ' + esc(t.title) + '. Змінити статус">' + icon + "</button>" +
      '<button class="linkbtn" data-copylink="task/' + t.id + '" title="Скопіювати посилання на завдання" aria-label="Скопіювати посилання на завдання">🔗</button>' +
      "<div><h3>" + (t.n ? '<span class="num">№' + t.n + "</span>" : "") + esc(t.title) + " " + lvlBadge(t.level) +
      (t.ai ? ' <span class="badge ai">🤖 LLM</span>' : "") +
      (t.auto ? ' <span class="badge free">🧪 автоперевірка</span>' : "") +
      (!t.auto && t.kind === "автотест" ? ' <span class="badge part" title="Умова готова, автоперевірка ще пишеться: поки можна розв\'язувати й перевіряти себе за умовою">⏳ автотест готується</span>' : "") +
      (!t.auto && t.kind === "документ" ?' <span class="badge part" title="Документ або розрахунок: оцінюєш себе за чеклістом">📝 документ</span>' : "") +
      (!t.auto && t.kind !== "документ" && t.done ? ' <span class="badge part" title="Практика в реальному інструменті: перевіряєш себе за чеклістом">🛠 практика</span>' : "") +
      (state.verified[t.id] ? ' <span class="badge ok" title="Тести пройдено ' + esc(state.verified[t.id]) +
        '">✅ перевірено тестами</span>' : "") + "</h3>" +
      "<p>" + md(t.desc) + ".</p>" +
      (t.check ? '<div class="chk"><b>Перевірка:</b> ' + md(t.check) + "</div>" : "") +
      (TASK_CONCEPTS[t.id] ? '<div class="chk"><b>Тренує:</b> ' + TASK_CONCEPTS[t.id].map(function (c) {
        return '<a href="#/stage/' + c.stage.id + '" data-focus="c-' + c.stage.id + "-" + c.i + '">' +
          esc(c.stage.concepts[c.i].replace(/`/g, "")) + "</a>";
      }).join(" · ") + "</div>" : "") +
      tagsHtml(t) + manualHtml(t) +
      (t.auto ? '<div class="chk">Папка <code>tasks/' + esc(t.auto) + "</code> · запуск: <code>python check.py " +
        esc(t.auto.split("_")[0]) + '</code> <button class="linkbtn inline" data-copy="python check.py ' + esc(t.auto.split("_")[0]) +
        '" title="Скопіювати команду">📋 Копіювати</button>' +
        (DATA.repo ? ' · <a href="' + DATA.repo + "/tree/main/tasks/" + esc(t.auto) + '" target="_blank" rel="noopener">Код на GitHub</a>' +
          ' · <a href="' + DATA.repo.replace("github.com", "github.dev") + "/tree/main/tasks/" + esc(t.auto) +
          '" target="_blank" rel="noopener">Відкрити в github.dev</a>' : "") + "</div>" : "") + "</div></div>";
  }


  function capDone(id, i) { return !!(state.capstone[id] && state.capstone[id][i]); }
  function capStats() {
    var done = 0, total = 0;
    DATA.capstone.milestones.forEach(function (m) {
      m.items.forEach(function (_, i) { total++; if (capDone(m.id, i)) done++; });
    });
    return { done: done, total: total, pct: total ? Math.round((done / total) * 100) : 0 };
  }
  function renderCapstone() {
    var c = DATA.capstone, st = capStats();
    var html = "<h1>" + esc(c.title) + "</h1>" +
      '<p class="lead">' + esc(c.intro) + "</p>" +
      '<div class="bar" style="max-width:360px"><span style="width:' + st.pct + '%"></span></div>' +
      '<small class="note">' + st.done + "/" + st.total + " пунктів · " + st.pct + "%</small>";
    html += c.milestones.map(function (m) {
      var stage = stageById(m.stage);
      return '<h2>' + esc(m.id.toUpperCase()) + ". " + esc(m.title) + "</h2>" +
        '<p class="note">Етап: <a href="#/stage/' + stage.id + '">' + stage.icon + " " + esc(stage.title) + "</a></p>" +
        '<ul class="checklist">' + m.items.map(function (it, i) {
          return '<li><label><input type="checkbox" data-cap="' + m.id + ":" + i + '"' + (capDone(m.id, i) ? " checked" : "") +
            "><span>" + md(it) + "</span></label></li>";
        }).join("") + "</ul>";
    }).join("");
    return html;
  }

  function renderLegacy() {
    var names = { keep: "Лишається", replace: "Замінити", skip: "Можна пропустити", new: "Нове" };
    var rows = DATA.legacy.map(function (r) {
      return "<tr><td>" + esc(r[0]) + '</td><td class="v-' + r[1] + '"><b>' + names[r[1]] + "</b></td><td>" + esc(r[2]) + "</td></tr>";
    }).join("");
    return "<h1>Що змінилось відносно відео 2023 року</h1>" +
      '<p class="lead">Список із відео описував JS-стек (MERN). Ось як кожен пункт виглядає для Python-бекендера у 2026 році.</p>' +
      '<div class="card" style="overflow-x:auto"><table><thead><tr><th>Тема з відео</th><th>Статус</th><th>Що замість / що додати</th></tr></thead><tbody>' +
      rows + "</tbody></table></div>";
  }

  // ---------- синхронізація з check.py --------------------------------------
  function markVerified(ids) {
    var n = 0, d = today();
    ids.forEach(function (id) {
      if (!TASKS[id]) return;
      state.tasks[id] = "done";
      state.verified[id] = d;
      n++;
    });
    touch();
    return n;
  }
  function syncIds(h) {
    var seen = {};
    var raw = h.replace(/^#\/sync\/?/, "");
    try { raw = decodeURIComponent(raw); } catch (err) { /* лишаємо як є */ }
    return raw.split(",").map(function (id) { return id.trim(); }).filter(function (id) {
      if (!TASKS[id] || seen[id]) return false;
      seen[id] = true;
      return true;
    });
  }
  function renderSync(ids) {
    if (!ids.length) return "<h1>Синхронізація</h1><p class=\"lead\">У посиланні немає відомих завдань.</p>";
    var fresh = ids.filter(function (id) { return !state.verified[id]; });
    return "<h1>Результати check.py</h1>" +
      '<p class="lead">Тести пройдено для ' + ids.length + " завдань" +
      (fresh.length < ids.length ? " (нових: " + fresh.length + ")" : "") +
      ". Позначити їх як «зроблено · перевірено тестами»? Решта прогресу не зміниться.</p>" +
      '<div class="card"><ul class="sync-list">' + ids.map(function (id) {
        return "<li>" + taskChip(id) + " " + esc(TASKS[id].title) + "</li>";
      }).join("") + "</ul>" +
      '<div class="row" style="margin-top:14px"><button class="btn" id="syncOk" data-ids="' + esc(ids.join(",")) +
      '">Позначити</button><a class="btn ghost" href="#/">Скасувати</a></div></div>';
  }

  function envText() {
    var s = state.settings;
    return "LLM_BASE_URL=" + (s.baseUrl || "https://your-proxy.example/v1") + "\n" +
      "LLM_API_KEY=вставте-ключ-сюди\n" +
      "LLM_MODEL=" + (s.model || "your-model-name");
  }
  function renderSettings() {
    return "<h1>Налаштування</h1>" +
      "<h2>AI-проксі для завдань з LLM</h2>" +
      '<p class="note">Підійде будь-який провайдер з OpenAI-сумісним API. Ключ тут <b>не зберігається</b>: вставляй його лише у файл <code>.env</code> на своєму комп\'ютері й додавай у GitHub Secrets.</p>' +
      '<div class="card form">' +
      '<label>Base URL<input id="sBase" placeholder="https://your-proxy.example/v1" value="' + esc(state.settings.baseUrl) + '"></label>' +
      '<label>Модель<input id="sModel" placeholder="назва-моделі" value="' + esc(state.settings.model) + '"></label>' +
      '<pre class="env" id="envOut">' + esc(envText()) + "</pre>" +
      '<div class="row"><button class="btn" id="copyEnv">Копіювати .env</button></div></div>' +
      "<h2>Прогрес</h2>" +
      '<div class="card form"><p class="note" style="margin:0">Прогрес живе у браузері. Зроби експорт, щоб перенести на інший пристрій або мати резервну копію.</p>' +
      '<div class="row"><button class="btn ghost" id="exportBtn">Експорт JSON</button>' +
      '<button class="btn ghost" id="importBtn">Імпорт JSON</button>' +
      '<button class="btn danger" id="resetBtn">Скинути прогрес</button></div>' +
      '<input type="file" id="importFile" accept="application/json" hidden></div>';
  }

  // ---------- роутинг -------------------------------------------------------
  var pendingFocus = null;
  // глибокі посилання: #/task/t129 і #/concept/ai-rag/4 (індекс 0-based, як у id картки) відкривають етап і підсвічують картку
  function deepLink(h) {
    var tk = h.match(/^#\/task\/(t\d+)\/?$/);
    if (tk && TASK_STAGE[tk[1]]) return { stage: TASK_STAGE[tk[1]], focus: "task-" + tk[1] };
    var cn = h.match(/^#\/concept\/([\w-]+)\/(\d+)\/?$/);
    var st = cn && stageById(cn[1]);
    if (st && +cn[2] < st.concepts.length) return { stage: st.id, focus: "c-" + st.id + "-" + cn[2] };
    return null;
  }
  function route() {
    var h = location.hash || "#/";
    var dl = deepLink(h);
    if (dl) {  // показуємо етап під канонічною адресою, посилання лишається в буфері
      pendingFocus = dl.focus;
      history.replaceState(null, "", "#/stage/" + dl.stage);
      h = "#/stage/" + dl.stage;
    }
    var legacy = h.match(/^#\/stage\/([\w-]+)\/?$/);
    if (legacy && !stageById(legacy[1]) && trackById(legacy[1])) {  // старий етап «ai» став треком
      history.replaceState(null, "", "#/track/" + legacy[1]);
      h = "#/track/" + legacy[1];
    }
    var m = h.match(/^#\/stage\/([\w-]+)/);
    var activeId = null;
    var html;
    var title = "SkillBooster";
    var tm = h.match(/^#\/track\/([\w-]+)/);
    if (m && stageById(m[1])) {
      var st = stageById(m[1]);
      activeId = st.id;
      setTrack(trackOf(st));
      html = renderStage(st);
      title = st.title + " · SkillBooster";
    } else if (h.indexOf("#/sync") === 0) {
      html = renderSync(syncIds(h));
      title = "Синхронізація · SkillBooster";
    } else if (h.indexOf("#/capstone") === 0) {
      html = renderCapstone();
      title = "Наскрізний проєкт · SkillBooster";
    } else if (h.indexOf("#/legacy") === 0) {
      html = renderLegacy();
      title = "Що змінилось · SkillBooster";
    } else if (h.indexOf("#/settings") === 0) {
      html = renderSettings();
      title = "Налаштування · SkillBooster";
    } else {
      if (tm && trackById(tm[1])) setTrack(tm[1]);
      html = renderHome();
    }
    view.innerHTML = html;
    document.title = title;
    renderNav(activeId);
    renderTop();
    sidebar.classList.remove("open");
    window.scrollTo(0, 0);
    if (pendingFocus) {
      focusEl(pendingFocus);
      pendingFocus = null;
    }
  }
  function copyText(txt, okMsg) {
    function fallback() {
      try {
        var ta = document.createElement("textarea");
        ta.value = txt;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        var ok = document.execCommand("copy");
        document.body.removeChild(ta);
        toast(ok ? okMsg : "Не вдалося скопіювати");
      } catch (err) { toast("Не вдалося скопіювати"); }
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(txt).then(function () { toast(okMsg); }, fallback);
    } else { fallback(); }
  }
  function focusEl(id) {
    var el = document.getElementById(id);
    if (!el) return;
    if (el.style.display === "none") {  // сховане фільтром завдання: скидаємо фільтр
      var all = document.querySelector('#filters [data-f="all"]');
      if (all) all.click();
    }
    el.scrollIntoView({ block: "center" });
    el.classList.remove("flash");
    void el.offsetWidth;
    el.classList.add("flash");
  }

  // ---------- події ---------------------------------------------------------
  document.addEventListener("click", function (e) {
    var link = e.target.closest("[data-focus]");
    if (link) {
      // посилання на ту саму сторінку не викличе hashchange: прокручуємо самі
      if (link.getAttribute("href") === location.hash) {
        e.preventDefault();
        focusEl(link.getAttribute("data-focus"));
        return;
      }
      pendingFocus = link.getAttribute("data-focus");
    }

    var qb = e.target.closest("[data-quiz]");
    if (qb) {
      var qp = qb.getAttribute("data-quiz").split(":");
      var box = document.getElementById("quiz-" + qp[0] + "-" + qp[1]);
      var open = box.hidden;
      document.querySelectorAll(".quiz").forEach(function (b) { b.hidden = true; });
      document.querySelectorAll("[data-quiz]").forEach(function (b) { b.setAttribute("aria-expanded", "false"); });
      if (open) { openQuiz(qb.getAttribute("data-quiz")); qb.setAttribute("aria-expanded", "true"); }
      return;
    }
    var retry = e.target.closest("[data-quiz-retry]");
    if (retry) { openQuiz(retry.getAttribute("data-quiz-retry")); return; }
    var opt = e.target.closest(".qopt");
    if (opt) { answerQuiz(opt); return; }

    if (e.target.id === "syncOk") {
      var n = markVerified(e.target.getAttribute("data-ids").split(","));
      toast("Перевірено тестами: " + n);
      location.hash = "#/";
      return;
    }

    var btn = e.target.closest("[data-task]");
    if (btn) {
      var id = btn.getAttribute("data-task");
      var order = ["todo", "doing", "done"];
      var next = order[(order.indexOf(taskState(id)) + 1) % 3];
      if (next === "todo") delete state.tasks[id]; else state.tasks[id] = next;
      delete state.verified[id];  // ручна зміна статусу знімає позначку тестів
      touch();
      rerenderTask(id);
      return;
    }

    var chip = e.target.closest("[data-f]");
    if (chip) {
      document.querySelectorAll("#filters .chip").forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
      chip.setAttribute("aria-pressed", "true");
      applyFilter();
      return;
    }

    var cp = e.target.closest("[data-copy]");
    if (cp) {
      copyText(cp.getAttribute("data-copy"), "Команду скопійовано");
      return;
    }

    var cl = e.target.closest("[data-copylink]");
    if (cl) {
      copyText(location.href.split("#")[0] + "#/" + cl.getAttribute("data-copylink"), "Посилання скопійовано");
      return;
    }

    if (e.target.id === "copyEnv") {
      var txt = envText();
      if (navigator.clipboard) {
        navigator.clipboard.writeText(txt).then(function () { toast("Скопійовано"); }, function () { toast("Не вдалося скопіювати"); });
      } else { toast("Виділи текст і скопіюй вручну"); }
    } else if (e.target.id === "exportBtn") {
      var blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "skillbooster-progress.json";
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    } else if (e.target.id === "importBtn") {
      document.getElementById("importFile").click();
    } else if (e.target.id === "resetBtn") {
      if (confirm("Скинути весь прогрес? Це неможливо скасувати.")) {
        var keep = state.settings;
        state = emptyState();
        state.settings = keep;
        save();
        route();
        toast("Прогрес скинуто");
      }
    }
  });

  document.addEventListener("change", function (e) {
    var cb = e.target.closest("[data-concept]");
    if (cb) {
      var p = cb.getAttribute("data-concept").split(":");
      state.concepts[p[0]] = state.concepts[p[0]] || {};
      if (cb.checked) state.concepts[p[0]][p[1]] = true; else delete state.concepts[p[0]][p[1]];
      touch();
      refreshProgress(p[0]);
      return;
    }
    var chk = e.target.closest("[data-check]");
    if (chk) {
      var c = chk.getAttribute("data-check").split(":");
      var tk = TASKS[c[0]];
      state.checks[c[0]] = state.checks[c[0]] || {};
      if (chk.checked) state.checks[c[0]][c[1]] = true; else delete state.checks[c[0]][c[1]];
      var all = tk.done.every(function (_, i) { return checkDone(c[0], i); });
      var any = tk.done.some(function (_, i) { return checkDone(c[0], i); });
      if (all) { state.tasks[c[0]] = "done"; }
      else if (taskState(c[0]) === "done") { state.tasks[c[0]] = any ? "doing" : "todo"; if (!any) delete state.tasks[c[0]]; }
      else if (any && taskState(c[0]) === "todo") { state.tasks[c[0]] = "doing"; }
      touch();
      rerenderTask(c[0]);
      return;
    }
    var cap = e.target.closest("[data-cap]");
    if (cap) {
      var q = cap.getAttribute("data-cap").split(":");
      state.capstone[q[0]] = state.capstone[q[0]] || {};
      if (cap.checked) state.capstone[q[0]][q[1]] = true; else delete state.capstone[q[0]][q[1]];
      touch();
      return;
    }
    if (e.target.id === "importFile" && e.target.files[0]) {
      var reader = new FileReader();
      reader.onload = function () {
        try {
          var s = JSON.parse(reader.result);
          if (!s || typeof s !== "object" || !s.tasks) throw new Error("bad");
          if (s.mode === "merge") {
            var n = markVerified(Object.keys(s.tasks));
            route();
            toast("Перевірено тестами: " + n);
            return;
          }
          var e0 = emptyState();
          state = {
            tasks: s.tasks, verified: s.verified || {}, checks: s.checks || {}, concepts: s.concepts || {}, capstone: s.capstone || {}, days: s.days || [],
            settings: Object.assign(e0.settings, s.settings || {}),
          };
          save();
          route();
          toast("Прогрес імпортовано");
        } catch (err) { toast("Файл не схожий на експорт SkillBooster"); }
      };
      reader.readAsText(e.target.files[0]);
    }
  });

  document.addEventListener("input", function (e) {
    if (e.target.id === "sBase" || e.target.id === "sModel") {
      state.settings.baseUrl = document.getElementById("sBase").value.trim();
      state.settings.model = document.getElementById("sModel").value.trim();
      save();
      document.getElementById("envOut").textContent = envText();
    }
  });

  function applyFilter() {
    var active = document.querySelector("#filters .chip[aria-pressed='true']");
    if (!active) return;
    var f = active.getAttribute("data-f");
    document.querySelectorAll("#taskList .task").forEach(function (el) {
      var show = true;
      if (f === "open") show = el.getAttribute("data-s") !== "done";
      else if (f === "cwe") show = el.getAttribute("data-tag") === "cwe";
      else if (f !== "all") show = el.getAttribute("data-lvl") === f;
      el.style.display = show ? "" : "none";
    });
    // заголовок підрозділу ховаємо, якщо під ним не лишилось видимих завдань
    document.querySelectorAll("#taskList .grp").forEach(function (g) {
      var visible = false;
      for (var n = g.nextElementSibling; n && !n.classList.contains("grp"); n = n.nextElementSibling) {
        if (n.style.display !== "none") { visible = true; break; }
      }
      g.style.display = visible ? "" : "none";
    });
  }

  // ---------- тема / меню ---------------------------------------------------
  function applyTheme(t) {
    if (t) document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
  }
  try { applyTheme(localStorage.getItem(THEME_KEY)); } catch (err) { /* ігноруємо */ }
  document.getElementById("themeBtn").addEventListener("click", function () {
    var cur = document.documentElement.getAttribute("data-theme");
    var dark = cur ? cur === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    var next = dark ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem(THEME_KEY, next); } catch (err) { /* ігноруємо */ }
  });
  document.getElementById("menuBtn").addEventListener("click", function () {
    sidebar.classList.toggle("open");
  });

  window.addEventListener("hashchange", route);
  route();
})();
