/* ════════════════════════════════════════════════
   SMART STATION — панель модуля Глеба (Railway Station Manager)
   Сервер Глеба встроен в общий сервер по адресу /gleb/...
   Панель: граф станции, поиск маршрутов, бронирование путей.
   Открыть: GlebPanel.open()
   ════════════════════════════════════════════════ */
(function () {
  'use strict';
  var API = '/gleb';
  var NODE_RU = {
    'N-ENTRY-N': 'Въезд Север', 'N-ENTRY-S': 'Въезд Юг',
    'N-SW-1': 'Стрелка №1', 'N-SW-2': 'Стрелка №2', 'N-JCT-1': 'Узел №1',
    'N-PLT-1': 'Платформа №1', 'N-PLT-2': 'Платформа №2', 'N-PLT-3': 'Платформа №3',
    'N-EXIT-E': 'Выезд Восток'
  };
  var TYPE_RU = { Passenger: 'Пассажирский', Freight: 'Грузовой', HighSpeed: 'Скоростной', Service: 'Служебный' };
  var topo = null, state = null, cands = [], selected = -1, timer = null, trainNo = 101;

  function nn(id) { if (NODE_RU[id]) return NODE_RU[id]; if (topo) { for (var i = 0; i < topo.nodes.length; i++) if (topo.nodes[i].id === id) return topo.nodes[i].name || id; } return id; }
  function el(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function api(path, body) {
    return fetch(API + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {})
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || r.status); return j; }); });
  }

  var CSS = '' +
    '#glebOv{position:fixed;inset:0;z-index:8500;background:rgba(3,8,20,.72);backdrop-filter:blur(6px);display:none;align-items:center;justify-content:center;padding:18px;font-family:Inter,"Segoe UI",system-ui,sans-serif}' +
    '#glebOv.show{display:flex}' +
    '#glebBox{width:min(1180px,100%);max-height:100%;overflow:auto;background:#0b1528;color:#dbe7ff;border:1px solid #1e3a66;border-radius:18px;box-shadow:0 30px 80px rgba(0,0,0,.6)}' +
    '.gb-head{display:flex;align-items:center;gap:14px;padding:16px 22px;border-bottom:1px solid #1a2f55;background:linear-gradient(90deg,#0e1f3d,#0b1528)}' +
    '.gb-head h3{font-size:15px;font-weight:800;letter-spacing:.3px;color:#fff;margin:0}' +
    '.gb-head small{display:block;font-size:11px;color:#6f8fc4;margin-top:2px;font-weight:500}' +
    '.gb-x{margin-left:auto;width:34px;height:34px;border-radius:10px;border:1px solid #27406b;background:none;color:#9bb4dd;font-size:16px;cursor:pointer}' +
    '.gb-x:hover{background:#3b1220;color:#fca5a5;border-color:#7f1d1d}' +
    '.gb-chips{display:flex;flex-wrap:wrap;gap:8px;padding:12px 22px;border-bottom:1px solid #1a2f55}' +
    '.gb-chip{font-size:11px;padding:5px 11px;border-radius:999px;background:#10213f;border:1px solid #1f3b69;color:#9fb8e2}' +
    '.gb-chip b{color:#fff;font-weight:700}.gb-chip.ok b{color:#4ade80}.gb-chip.bad b{color:#f87171}' +
    '.gb-grid{display:grid;grid-template-columns:1.55fr 1fr;gap:18px;padding:18px 22px 22px}' +
    '@media(max-width:900px){.gb-grid{grid-template-columns:1fr}}' +
    '.gb-card{background:#0e1b33;border:1px solid #1c355f;border-radius:14px;overflow:hidden}' +
    '.gb-card h4{margin:0;padding:11px 15px;font-size:11px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase;color:#7fa6e6;border-bottom:1px solid #1c355f;background:#0f2040}' +
    '.gb-svg{width:100%;height:auto;display:block;background:radial-gradient(ellipse at 50% 40%,#10264a,#0b1528)}' +
    '.gb-legend{display:flex;gap:14px;flex-wrap:wrap;padding:9px 15px;font-size:11px;color:#8aa6d6;border-top:1px solid #1c355f}' +
    '.gb-legend i{display:inline-block;width:18px;height:4px;border-radius:3px;margin-right:6px;vertical-align:middle}' +
    '.gb-form{padding:14px 15px;display:grid;grid-template-columns:1fr 1fr;gap:10px}' +
    '.gb-form label{font-size:10px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:#7fa6e6;display:block;margin-bottom:5px}' +
    '.gb-form select,.gb-form input{width:100%;height:36px;padding:0 10px;border-radius:10px;border:1px solid #27406b;background:#0b1528;color:#e6efff;font:inherit;font-size:12px;outline:none}' +
    '.gb-form select:focus,.gb-form input:focus{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.25)}' +
    '.gb-btn{height:38px;border:none;border-radius:10px;background:linear-gradient(90deg,#2563eb,#3b82f6);color:#fff;font:inherit;font-size:12px;font-weight:800;letter-spacing:.4px;cursor:pointer;box-shadow:0 6px 18px rgba(37,99,235,.35)}' +
    '.gb-btn:hover{filter:brightness(1.1)}.gb-btn:disabled{opacity:.5;cursor:default}' +
    '.gb-btn.sm{height:28px;padding:0 11px;font-size:11px;box-shadow:none}' +
    '.gb-btn.ghost{background:#13284a;border:1px solid #27406b;color:#bcd0f2}' +
    '.gb-btn.red{background:#3a1220;border:1px solid #7f1d1d;color:#fca5a5}' +
    '.gb-list{padding:6px 0;max-height:260px;overflow:auto}' +
    '.gb-item{padding:10px 15px;border-bottom:1px solid #16294a;cursor:pointer;transition:background .15s}' +
    '.gb-item:last-child{border-bottom:none}.gb-item:hover{background:#12264a}' +
    '.gb-item.sel{background:rgba(59,130,246,.18);box-shadow:inset 3px 0 0 #3b82f6}' +
    '.gb-item .t{font-size:12px;font-weight:700;color:#fff}.gb-item .m{font-size:11px;color:#86a3d3;margin-top:3px}' +
    '.gb-item .row{display:flex;align-items:center;gap:8px;justify-content:space-between}' +
    '.gb-empty{padding:16px 15px;font-size:12px;color:#6f8fc4}' +
    '.gb-msg{margin:0 15px 12px;font-size:12px;padding:8px 11px;border-radius:10px;display:none}' +
    '.gb-msg.ok{display:block;background:rgba(22,163,74,.14);color:#86efac;border:1px solid #166534}' +
    '.gb-msg.err{display:block;background:rgba(220,38,38,.14);color:#fca5a5;border:1px solid #7f1d1d}' +
    '.gb-off{padding:40px 22px;text-align:center;color:#9fb8e2;font-size:13px;line-height:1.6}';

  function build() {
    if (el('glebOv')) return;
    var st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
    var ov = document.createElement('div'); ov.id = 'glebOv';
    ov.innerHTML =
      '<div id="glebBox">' +
      '<div class="gb-head"><div><h3>🧭 Маршруты и пути — модуль Railway Station Manager</h3>' +
      '<small>Построение маршрутов по графу станции с учётом занятости путей и ограничений поезда</small></div>' +
      '<button class="gb-x" onclick="GlebPanel.close()" title="Закрыть">✕</button></div>' +
      '<div class="gb-chips" id="gbChips"><span class="gb-chip">Загрузка...</span></div>' +
      '<div id="gbBody">' +
      '<div class="gb-grid">' +
      '<div class="gb-card"><h4>Граф станции</h4><svg class="gb-svg" id="gbSvg" viewBox="0 0 760 360"></svg>' +
      '<div class="gb-legend"><span><i style="background:#3b5b8f"></i>Свободен</span><span><i style="background:#ef4444"></i>Занят</span>' +
      '<span><i style="background:#22d3ee"></i>Выбранный маршрут</span></div></div>' +
      '<div style="display:flex;flex-direction:column;gap:18px">' +
      '<div class="gb-card"><h4>Новый маршрут</h4><div class="gb-form">' +
      '<div><label>Поезд №</label><input id="gbTrain"></div>' +
      '<div><label>Тип поезда</label><select id="gbType"></select></div>' +
      '<div><label>Откуда</label><select id="gbFrom"></select></div>' +
      '<div><label>Куда</label><select id="gbTo"></select></div>' +
      '<div><label>Длина состава (м)</label><input id="gbLen" type="number" value="400"></div>' +
      '<div><label>Вес (т)</label><input id="gbW" type="number" value="1200"></div>' +
      '<button class="gb-btn" style="grid-column:1/-1" id="gbFind" onclick="GlebPanel.find()">Найти маршруты</button>' +
      '</div><div class="gb-msg" id="gbMsg"></div>' +
      '<div class="gb-list" id="gbCands"><div class="gb-empty">Выберите откуда и куда, затем нажмите «Найти маршруты».</div></div></div>' +
      '<div class="gb-card"><h4>Активные маршруты</h4><div class="gb-list" id="gbActive"><div class="gb-empty">Нет активных маршрутов</div></div></div>' +
      '</div></div></div></div>';
    ov.addEventListener('click', function (e) { if (e.target === ov) close(); });
    document.body.appendChild(ov);
    var ty = el('gbType');
    Object.keys(TYPE_RU).forEach(function (k) { var o = document.createElement('option'); o.value = k; o.textContent = TYPE_RU[k]; ty.appendChild(o); });
  }

  function chips(s) {
    var c = el('gbChips');
    if (!s) { c.innerHTML = '<span class="gb-chip bad">Модуль: <b>не подключён</b></span>'; return; }
    var llm = s.components && s.components.llm_client === 'GroqLLMClient' ? 'Groq AI' : 'Детерминированный';
    var occ = state ? state.tracks.filter(function (t) { return t.occupied; }).length : s.occupancy.occupied_tracks;
    c.innerHTML =
      '<span class="gb-chip ok">Модуль: <b>подключён</b></span>' +
      '<span class="gb-chip">Станция: <b>' + esc(s.station.name) + '</b></span>' +
      '<span class="gb-chip">Узлов: <b>' + s.station.nodes + '</b></span>' +
      '<span class="gb-chip">Путей: <b>' + s.station.tracks + '</b></span>' +
      '<span class="gb-chip">Занято: <b>' + occ + '</b></span>' +
      '<span class="gb-chip">Планировщик: <b>' + llm + '</b></span>';
  }

  function fillSelects() {
    var f = el('gbFrom'), t = el('gbTo');
    if (f.options.length) return;
    topo.nodes.forEach(function (n) {
      if (n.type === 'Entry') f.add(new Option(nn(n.id), n.id));
      if (n.type === 'Platform' || n.type === 'Junction' || n.type === 'Exit') t.add(new Option(nn(n.id), n.id));
    });
    el('gbTrain').value = String(trainNo) + 'А';
  }

  function draw() {
    if (!topo) return;
    var svg = el('gbSvg'), W = 760, H = 360, P = 50;
    var xs = topo.nodes.map(function (n) { return n.position ? n.position.x : 0; });
    var ys = topo.nodes.map(function (n) { return n.position ? n.position.y : 0; });
    var minx = Math.min.apply(0, xs), maxx = Math.max.apply(0, xs), miny = Math.min.apply(0, ys), maxy = Math.max.apply(0, ys);
    function X(n) { return P + ((n.position ? n.position.x : 0) - minx) / ((maxx - minx) || 1) * (W - 2 * P); }
    function Y(n) { return H - P - ((n.position ? n.position.y : 0) - miny) / ((maxy - miny) || 1) * (H - 2 * P); }
    var byId = {}; topo.nodes.forEach(function (n) { byId[n.id] = n; });
    var occ = {}; (state ? state.tracks : []).forEach(function (t) { occ[t.id] = t; });
    var sel = {}; if (cands[selected]) cands[selected].path.forEach(function (p) { sel[p] = 1; });
    var h = '<defs><filter id="gbGlow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>';
    topo.tracks.forEach(function (t) {
      var a = byId[t.from], b = byId[t.to]; if (!a || !b) return;
      var o = occ[t.id] && occ[t.id].occupied, s = sel[t.id];
      var col = s ? '#22d3ee' : o ? '#ef4444' : '#3b5b8f';
      h += '<line x1="' + X(a) + '" y1="' + Y(a) + '" x2="' + X(b) + '" y2="' + Y(b) + '" stroke="' + col + '" stroke-width="' + (s || o ? 6 : 4) + '" stroke-linecap="round"' + (s || o ? ' filter="url(#gbGlow)"' : '') + '><title>' + t.id + ' · ' + t.length_m + ' м</title></line>';
      var mx = (X(a) + X(b)) / 2, my = (Y(a) + Y(b)) / 2;
      h += '<text x="' + mx + '" y="' + (my - 7) + '" fill="' + (s ? '#a5f3fc' : o ? '#fca5a5' : '#5d7cb0') + '" font-size="9" text-anchor="middle" font-family="monospace">' + t.id + (o && occ[t.id].train_id ? ' · ' + esc(occ[t.id].train_id) : '') + '</text>';
    });
    var COL = { Entry: '#22c55e', Exit: '#f59e0b', Platform: '#3b82f6', Switch: '#a78bfa', Junction: '#e879f9' };
    topo.nodes.forEach(function (n) {
      var c = COL[n.type] || '#94a3b8', x = X(n), y = Y(n);
      h += '<circle cx="' + x + '" cy="' + y + '" r="' + (n.type === 'Platform' ? 10 : 8) + '" fill="#0b1528" stroke="' + c + '" stroke-width="3"/>';
      h += '<text x="' + x + '" y="' + (y + 24) + '" fill="#dbe7ff" font-size="11" font-weight="700" text-anchor="middle" font-family="Inter,Segoe UI,sans-serif">' + esc(nn(n.id)) + '</text>';
    });
    svg.innerHTML = h;
  }

  function msg(t, bad) { var m = el('gbMsg'); m.textContent = t; m.className = 'gb-msg ' + (bad ? 'err' : 'ok'); }

  function renderCands() {
    var box = el('gbCands');
    if (!cands.length) { box.innerHTML = '<div class="gb-empty">Свободных маршрутов нет — все варианты проходят через занятые пути.</div>'; return; }
    box.innerHTML = cands.map(function (c, i) {
      return '<div class="gb-item' + (i === selected ? ' sel' : '') + '" onclick="GlebPanel.pick(' + i + ')">' +
        '<div class="row"><div class="t">Вариант ' + (i + 1) + ' · ' + Math.round(c.length_m) + ' м · ' + c.path.length + ' пути</div>' +
        '<button class="gb-btn sm" onclick="event.stopPropagation();GlebPanel.reserve(' + i + ')">Забронировать</button></div>' +
        '<div class="m">' + c.path.join(' → ') + '</div></div>';
    }).join('');
  }

  function renderActive() {
    var box = el('gbActive'), list = state ? state.active_routes : [];
    if (!list.length) { box.innerHTML = '<div class="gb-empty">Нет активных маршрутов</div>'; return; }
    box.innerHTML = list.map(function (r) {
      return '<div class="gb-item"><div class="row"><div class="t">Поезд ' + esc(r.train_id) + ' · ' + Math.round(r.length_m) + ' м</div>' +
        '<button class="gb-btn sm red" onclick="GlebPanel.release(\'' + r.id + '\')">Освободить</button></div>' +
        '<div class="m">' + r.path.join(' → ') + '</div></div>';
    }).join('');
  }

  function refresh() {
    return Promise.all([api('/status'), api('/station/state')]).then(function (r) {
      state = r[1]; chips(r[0]); draw(); renderActive();
    }).catch(function () { offline(); });
  }

  function offline() {
    el('gbBody').innerHTML = '<div class="gb-off">Модуль Railway Station Manager сейчас недоступен.<br>' +
      'Проверьте, что папка <b>backend-gleb</b> лежит рядом с папкой <b>app</b>, и перезапустите start.bat.</div>';
    chips(null);
  }

  function open() {
    build();
    el('glebOv').classList.add('show');
    if (!topo) {
      api('/station/topology').then(function (t) { topo = t; fillSelects(); return refresh(); }).catch(offline);
    } else refresh();
    clearInterval(timer); timer = setInterval(refresh, 3000);
  }
  function close() { var o = el('glebOv'); if (o) o.classList.remove('show'); clearInterval(timer); }

  function find() {
    var b = el('gbFind'); b.disabled = true;
    api('/routes/candidates', {
      train_id: el('gbTrain').value.trim() || 'T-001', from_node: el('gbFrom').value, to_node: el('gbTo').value,
      train_type: el('gbType').value, length_m: +el('gbLen').value || 400, weight_t: +el('gbW').value || 1200
    }).then(function (r) {
      cands = r.candidates; selected = cands.length ? 0 : -1;
      renderCands(); draw();
      msg('Найдено вариантов: ' + r.count, false);
    }).catch(function (e) { msg('Ошибка: ' + e.message, true); })
      .then(function () { b.disabled = false; });
  }
  function pick(i) { selected = i; renderCands(); draw(); }
  function reserve(i) {
    var c = cands[i];
    api('/routes/reserve', { train_id: c.train_id, path: c.path }).then(function () {
      msg('Маршрут забронирован, пути заняты', false);
      cands = []; selected = -1; renderCands();
      trainNo++; el('gbTrain').value = String(trainNo) + 'А';
      return refresh();
    }).catch(function (e) { msg('Ошибка: ' + e.message, true); });
  }
  function release(id) {
    api('/routes/' + id + '/release', {}).then(function () { msg('Маршрут освобождён', false); return refresh(); })
      .catch(function (e) { msg('Ошибка: ' + e.message, true); });
  }
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });

  window.GlebPanel = { open: open, close: close, find: find, pick: pick, reserve: reserve, release: release };
})();
