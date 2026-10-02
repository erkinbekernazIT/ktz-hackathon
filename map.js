/* ════════════════════════════════════════════════
   SMART STATION – КЖД  |  Interactive Map Logic
   Levels: 0 = Country → 1 = City → 2 = Station
   ════════════════════════════════════════════════ */

/* ─── State ──────────────────────────────────────── */
let level         = 0;
let activeCity    = null;
let activeStation = null;

/* ─── DOM refs (assigned after DOMContentLoaded) ── */
let mapGroup, stationsL, depotsL, backBtn, badge, breadcrumb, mapInfo;

document.addEventListener('DOMContentLoaded', () => {
  mapGroup   = document.getElementById('map-group');
  stationsL  = document.getElementById('stations-layer');
  depotsL    = document.getElementById('depots-layer');
  backBtn    = document.getElementById('mapBackBtn');
  badge      = document.getElementById('levelBadge');
  breadcrumb = document.getElementById('breadcrumb');
  mapInfo    = document.getElementById('mapInfo');
});

/* ─── Transform helper ───────────────────────────── */
function applyTransform(scale, tx, ty) {
  mapGroup.style.transform = `scale(${scale}) translate(${tx}px,${ty}px)`;
}

/* ─── Breadcrumb ─────────────────────────────────── */
function updateBreadcrumb() {
  let html = `<span onclick="zoomToLevel(0)">Казахстан</span>`;

  if (activeCity) {
    html += `<span class="sep">›</span>`;
    if (level === 2) {
      html += `<span onclick="zoomToLevel(1)">${DATA[activeCity].label}</span>`;
      html += `<span class="sep">›</span>`;
      html += `<span>${activeStation ? activeStation.label : ''}</span>`;
    } else {
      html += `<span>${DATA[activeCity].label}</span>`;
    }
  }

  breadcrumb.innerHTML = html;
}

/* ─── Info panel ─────────────────────────────────── */
function showInfo(title, body) {
  document.getElementById('infoTitle').textContent = title;
  document.getElementById('infoBody').innerHTML    = body;
  mapInfo.classList.add('visible');
}

function hideInfo() {
  mapInfo.classList.remove('visible');
}

/* ─── Zoom levels ────────────────────────────────── */
function zoomToLevel(l) {
  if (l === 0) {
    level = 0;
    activeCity    = null;
    activeStation = null;

    applyTransform(1, 0, 0);
    document.getElementById('cities-layer').setAttribute('visibility', 'visible');
    stationsL.setAttribute('visibility', 'hidden');
    depotsL.setAttribute('visibility', 'hidden');
    stationsL.innerHTML = '';
    depotsL.innerHTML   = '';

    backBtn.classList.remove('visible');
    badge.textContent = '🇰🇿 Казахстан';
    hideInfo();
    updateBreadcrumb();
    return;
  }

  if (l === 1 && activeCity) {
    level         = 1;
    activeStation = null;

    const city            = DATA[activeCity];
    const { scale, tx, ty } = city.zoom;

    applyTransform(scale, tx, ty);
    document.getElementById('cities-layer').setAttribute('visibility', 'hidden');
    renderStations(activeCity);
    stationsL.setAttribute('visibility', 'visible');
    depotsL.setAttribute('visibility', 'hidden');
    depotsL.innerHTML = '';

    backBtn.classList.add('visible');
    badge.textContent = `📍 ${city.label}`;
    showInfo(city.label, `<b>${city.stations.length}</b> станций`);
    updateBreadcrumb();
  }
}

/* ─── City click ─────────────────────────────────── */
function selectCity(cityId) {
  if (level !== 0) return;
  activeCity = cityId;
  zoomToLevel(1);
}

/* ─── Station click ──────────────────────────────── */
function selectStation(stationId) {
  if (level !== 1) return;

  const city = DATA[activeCity];
  activeStation = city.stations.find(s => s.id === stationId);
  if (!activeStation) return;

  level = 2;

  /* Zoom deeper, centering the station (SVG viewBox 900×520 → center 450,260) */
  const { scale: baseScale } = city.zoom;
  const newScale = baseScale * 1.8;
  const newTx    = (450 / newScale) - activeStation.cx;
  const newTy    = (260 / newScale) - activeStation.cy;

  applyTransform(newScale, newTx, newTy);
  renderDepots(stationId, activeStation.cx, activeStation.cy);
  depotsL.setAttribute('visibility', 'visible');

  badge.textContent = `🏭 ${activeStation.label}`;
  const deps = DEPOTS[stationId] || [];
  showInfo(activeStation.label, `<b>${deps.length}</b> депо`);
  updateBreadcrumb();
}

/* ─── Render stations ────────────────────────────── */
function renderStations(cityId) {
  stationsL.innerHTML = '';
  const W = 80, H = 22, RX = 6;

  DATA[cityId].stations.forEach(st => {
    const g = svgEl('g');
    g.setAttribute('class', 'station-marker');
    g.setAttribute('onclick', `selectStation('${st.id}')`);

    const rect = svgEl('rect');
    rect.setAttribute('x',            st.cx - W / 2);
    rect.setAttribute('y',            st.cy - H / 2);
    rect.setAttribute('width',        W);
    rect.setAttribute('height',       H);
    rect.setAttribute('rx',           RX);
    rect.setAttribute('fill',         '#1a56db');
    rect.setAttribute('stroke',       '#fff');
    rect.setAttribute('stroke-width', '1.5');

    const txt = svgEl('text');
    txt.setAttribute('x',              st.cx);
    txt.setAttribute('y',              st.cy + 4);
    txt.setAttribute('text-anchor',    'middle');
    txt.setAttribute('fill',           '#fff');
    txt.setAttribute('font-size',      '9');
    txt.setAttribute('font-weight',    '700');
    txt.setAttribute('pointer-events', 'none');
    txt.textContent = st.label;

    g.addEventListener('mouseenter', () => rect.setAttribute('fill', '#f5a623'));
    g.addEventListener('mouseleave', () => rect.setAttribute('fill', '#1a56db'));

    g.appendChild(rect);
    g.appendChild(txt);
    stationsL.appendChild(g);
  });
}

/* ─── Render depots ──────────────────────────────── */
function renderDepots(stationId, sx, sy) {
  depotsL.innerHTML = '';
  const SIZE = 9;

  (DEPOTS[stationId] || []).forEach(dep => {
    const px = sx + dep.dx;
    const py = sy + dep.dy;
    const g  = svgEl('g');
    g.setAttribute('class', 'depot-marker');

    /* connector line */
    const line = svgEl('line');
    line.setAttribute('x1',              sx);
    line.setAttribute('y1',              sy);
    line.setAttribute('x2',              px);
    line.setAttribute('y2',              py);
    line.setAttribute('stroke',          '#059669');
    line.setAttribute('stroke-width',    '1');
    line.setAttribute('stroke-dasharray','3,2');
    line.setAttribute('opacity',         '0.7');

    /* diamond shape */
    const poly = svgEl('polygon');
    poly.setAttribute('points',
      `${px},${py - SIZE} ${px + SIZE},${py} ${px},${py + SIZE} ${px - SIZE},${py}`);
    poly.setAttribute('fill',         '#059669');
    poly.setAttribute('stroke',       '#fff');
    poly.setAttribute('stroke-width', '1.5');

    const txt = svgEl('text');
    txt.setAttribute('x',              px);
    txt.setAttribute('y',              py + SIZE + 11);
    txt.setAttribute('text-anchor',    'middle');
    txt.setAttribute('fill',           '#065f46');
    txt.setAttribute('font-size',      '8');
    txt.setAttribute('font-weight',    '700');
    txt.setAttribute('pointer-events', 'none');
    txt.textContent = dep.label;

    g.appendChild(line);
    g.appendChild(poly);
    g.appendChild(txt);
    depotsL.appendChild(g);
  });
}

/* ─── Back button ────────────────────────────────── */
function goBack() {
  if (level === 2) zoomToLevel(1);
  else if (level === 1) zoomToLevel(0);
}

/* ─── SVG element factory ────────────────────────── */
function svgEl(tag) {
  return document.createElementNS('http://www.w3.org/2000/svg', tag);
}
