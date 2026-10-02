/* ════════════════════════════════════════════════
   SMART STATION – КЖД  |  Auth Logic
   Handles modal open/close, tab switching,
   login and logout flow.
   ════════════════════════════════════════════════ */

function openModal() {
  document.getElementById('authModal').classList.add('active');
}

function closeModal() {
  document.getElementById('authModal').classList.remove('active');
}

function switchTab(name, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
}

function doLogin() {
  const email = document.getElementById('login-email').value.trim();
  const pass  = document.getElementById('login-pass').value;

  if (!email || !pass) {
    alert('Введите email и пароль');
    return;
  }

  /* Simple demo auth – replace with real API call */
  closeModal();
  document.getElementById('landing').style.display = 'none';
  document.getElementById('dashboard').classList.add('active');
  document.getElementById('userDisplay').textContent = email;
}

function doLogout() {
  document.getElementById('dashboard').classList.remove('active');
  document.getElementById('landing').style.display = '';
  /* Reset map back to country level */
  zoomToLevel(0);
}
