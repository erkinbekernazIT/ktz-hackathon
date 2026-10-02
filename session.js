/* ════════════════════════════════════════════════
   SMART STATION — единый вход по ролям
   Один логин (auth.html) → запись sessionStorage['ss_user']
   → переход на страницу своей роли.
   ПРОТОТИП: вход демонстрационный, пароли в коде.
   ════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* Демо-аккаунты */
  var ACCOUNTS = [
    { email: 'admin@smartstation.local',      pass: 'admin123', role: 'admin',      name: 'Администратор системы' },
    { email: 'dispatcher@smartstation.local', pass: 'pass123',  role: 'dispatcher', name: 'Петров А.А.' },
    { email: 'manager@smartstation.local',    pass: 'pass123',  role: 'manager',    name: 'Иванов К.Р.' },
    { email: 'duty@station.kz',               pass: 'duty123',  role: 'duty',       name: 'Ахметов Д.С.' },
    { email: 'tech@station.kz',               pass: 'tech123',  role: 'tech',       name: 'Бекова А.Т.' },
    { email: 'security@station.kz',           pass: 'sec123',   role: 'security',   name: 'Джаксыбеков Е.Н.' }
  ];

  /* Роль → должность и страница */
  var ROLES = {
    admin:      { position: 'Администратор системы',          page: 'admin.html' },
    dispatcher: { position: 'Диспетчер станции',              page: 'dispatcher.html' },
    manager:    { position: 'Руководитель станции',           page: 'manager.html' },
    duty:       { position: 'Дежурный по станции',            page: 'station.html' },
    tech:       { position: 'Сотрудник технической службы',   page: 'station.html' },
    security:   { position: 'Сотрудник службы безопасности',  page: 'station.html' }
  };

  /* Названия ролей из админки / регистрации → код роли */
  var LABEL_TO_ROLE = {
    'Администратор системы': 'admin',
    'Диспетчер станции': 'dispatcher', 'Диспетчер': 'dispatcher',
    'Руководитель станции': 'manager', 'Начальник станции': 'manager', 'Руководитель': 'manager',
    'Дежурный по станции': 'duty', 'Дежурный': 'duty',
    'Сотрудник технической службы': 'tech', 'Инженер': 'tech', 'Техник': 'tech', 'Инженер-технолог': 'tech',
    'Сотрудник службы безопасности': 'security', 'Работник службы безопасности': 'security',
    'Специалист службы безопасности': 'security'
  };

  function norm(r) { return ROLES[r] ? r : (LABEL_TO_ROLE[r] || null); }
  function readLS(k) { try { return JSON.parse(localStorage.getItem(k) || '[]'); } catch (e) { return []; } }

  /* Найти пользователя: демо → созданные админом → зарегистрированные */
  function find(email, pass) {
    email = String(email || '').trim().toLowerCase();
    var a = ACCOUNTS.filter(function (x) { return x.email === email && x.pass === pass; })[0];
    if (a) return { name: a.name, role: a.role, email: a.email, position: ROLES[a.role].position };

    var emp = readLS('ss_employees').filter(function (x) {
      return String(x.email || '').toLowerCase() === email && x.password === pass;
    })[0];
    if (emp) {
      if (emp.status === 'Заблокирован') return { blocked: true };
      var r = norm(emp.role);
      if (r) return { name: emp.fio || emp.name, role: r, email: email, position: emp.position || ROLES[r].position };
    }

    var reg = readLS('ss_registered').filter(function (x) { return x.email === email && x.pass === pass; })[0];
    if (reg && norm(reg.role)) {
      var rr = norm(reg.role);
      return { name: reg.name, role: rr, email: email, position: reg.position || ROLES[rr].position };
    }
    return null;
  }

  function emailTaken(email) {
    email = String(email || '').trim().toLowerCase();
    return ACCOUNTS.some(function (x) { return x.email === email; }) ||
      readLS('ss_employees').some(function (x) { return String(x.email || '').toLowerCase() === email; }) ||
      readLS('ss_registered').some(function (x) { return x.email === email; });
  }

  function register(u) {
    var list = readLS('ss_registered');
    list.push({ name: u.name, email: String(u.email).trim().toLowerCase(), pass: u.pass, role: u.role, position: ROLES[u.role].position });
    localStorage.setItem('ss_registered', JSON.stringify(list));
  }

  function start(u) {
    sessionStorage.setItem('ss_user', JSON.stringify({ name: u.name, role: u.role, email: u.email, position: u.position }));
    return ROLES[u.role].page;
  }

  function current() {
    try {
      var u = JSON.parse(sessionStorage.getItem('ss_user') || 'null');
      if (!u) return null;
      u.role = norm(u.role) || u.role;
      if (!u.position && ROLES[u.role]) u.position = ROLES[u.role].position;
      return u;
    } catch (e) { return null; }
  }

  /* Защита страницы: пускает только указанные роли (admin — везде) */
  function guard(roles) {
    var u = current();
    if (!u || (roles.indexOf(u.role) === -1 && u.role !== 'admin')) {
      location.replace('auth.html');
      return null;
    }
    return u;
  }

  function logout() {
    sessionStorage.removeItem('ss_user');
    location.href = 'auth.html';
  }

  function initials(name) {
    return String(name || '').split(/\s+/).map(function (w) { return w[0] || ''; }).slice(0, 2).join('').toUpperCase();
  }


  /* Страница открыта как файл (C:/...) — сервер недоступен, диспетчер и симулятор не работают */
  if (location.protocol === 'file:') {
    var showFileWarn = function () {
      if (document.getElementById('ssFileWarn')) return;
      var d = document.createElement('div');
      d.id = 'ssFileWarn';
      d.style.cssText = 'position:fixed;inset:0;z-index:2147483600;background:rgba(6,14,32,.92);display:flex;align-items:center;justify-content:center;padding:20px;font-family:Segoe UI,Arial,sans-serif';
      d.innerHTML = '<div style="max-width:560px;background:#fff;border-radius:18px;padding:28px 30px;box-shadow:0 30px 80px rgba(0,0,0,.5);color:#0c1d3d">' +
        '<div style="font-size:20px;font-weight:800;margin-bottom:10px">⚠ Сайт открыт как файл</div>' +
        '<div style="font-size:14px;line-height:1.6;color:#354f7a">Так не работают сервер, симулятор станции и диспетчер.<br><br>' +
        '<b>1.</b> Запустите <b>start.bat</b> (двойной клик) и не закрывайте чёрное окно.<br>' +
        '<b>2.</b> Откройте сайт по адресу ниже.</div>' +
        '<a href="http://localhost:8000/" style="display:block;margin-top:18px;text-align:center;padding:13px;border-radius:12px;background:#2563eb;color:#fff;font-weight:800;text-decoration:none;font-size:15px">Открыть http://localhost:8000</a></div>';
      document.body.appendChild(d);
    };
    if (document.body) showFileWarn(); else document.addEventListener('DOMContentLoaded', showFileWarn);
  }

  window.SS = {
    ACCOUNTS: ACCOUNTS, ROLES: ROLES, find: find, register: register, emailTaken: emailTaken,
    start: start, current: current, guard: guard, logout: logout, initials: initials, normRole: norm
  };
})();
