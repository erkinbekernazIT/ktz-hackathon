/* ════════════════════════════════════════════════
   SMART STATION – КЖД  |  Map Data
   Cities → Stations → Depots
   ════════════════════════════════════════════════ */

const DATA = {
  almaty: {
    label: 'Алматы',
    cx: 680, cy: 360,
    zoom: { scale: 2.8, tx: -1204, ty: -768 },
    stations: [
      { id: 'alm_1', label: 'Алматы-1',        cx: 670, cy: 335 },
      { id: 'alm_2', label: 'Алматы-2',        cx: 700, cy: 365 },
      { id: 'alm_3', label: 'Алматы Сортир.',  cx: 655, cy: 380 },
    ],
  },
  astana: {
    label: 'Астана',
    cx: 440, cy: 200,
    zoom: { scale: 2.8, tx: -782, ty: -360 },
    stations: [
      { id: 'ast_1', label: 'Астана-пасс.',    cx: 430, cy: 190 },
      { id: 'ast_2', label: 'Астана-груз.',    cx: 455, cy: 205 },
      { id: 'ast_3', label: 'Нур-Султан Зап.', cx: 420, cy: 215 },
    ],
  },
  shymkent: {
    label: 'Шымкент',
    cx: 530, cy: 400,
    zoom: { scale: 2.8, tx: -984, ty: -920 },
    stations: [
      { id: 'shm_1', label: 'Шымкент-пасс.',  cx: 520, cy: 390 },
      { id: 'shm_2', label: 'Шымкент-груз.',  cx: 545, cy: 408 },
    ],
  },
  aktobe: {
    label: 'Актобе',
    cx: 220, cy: 210,
    zoom: { scale: 2.8, tx: -366, ty: -388 },
    stations: [
      { id: 'akb_1', label: 'Актобе-1',       cx: 210, cy: 200 },
      { id: 'akb_2', label: 'Актобе-2',       cx: 235, cy: 215 },
    ],
  },
  karaganda: {
    label: 'Карагандa',
    cx: 500, cy: 270,
    zoom: { scale: 2.8, tx: -900, ty: -486 },
    stations: [
      { id: 'kar_1', label: 'Карагандa-пасс.', cx: 490, cy: 260 },
      { id: 'kar_2', label: 'Карагандa-груз.', cx: 515, cy: 278 },
      { id: 'kar_3', label: 'Шахтинск',        cx: 498, cy: 288 },
    ],
  },
  pavlodar: {
    label: 'Павлодар',
    cx: 580, cy: 160,
    zoom: { scale: 2.8, tx: -1074, ty: -258 },
    stations: [
      { id: 'pav_1', label: 'Павлодар-пасс.', cx: 572, cy: 150 },
      { id: 'pav_2', label: 'Павлодар-груз.', cx: 592, cy: 165 },
    ],
  },
  atyrau: {
    label: 'Атырау',
    cx: 150, cy: 290,
    zoom: { scale: 2.8, tx: -120, ty: -572 },
    stations: [
      { id: 'aty_1', label: 'Атырау-пасс.',   cx: 142, cy: 280 },
      { id: 'aty_2', label: 'Атырау-груз.',   cx: 162, cy: 296 },
    ],
  },
};

const DEPOTS = {
  alm_1: [{ label: 'Депо ТЧЭ-1',          dx: -25, dy: -18 },
          { label: 'Депо ТЧЭ-2',           dx:  22, dy: -18 }],
  alm_2: [{ label: 'Локомотивное депо',    dx:   0, dy: -20 }],
  alm_3: [{ label: 'Сортировочное депо',   dx:   0, dy: -20 }],
  ast_1: [{ label: 'Депо Астана-1',        dx: -22, dy: -18 },
          { label: 'Депо Астана-2',        dx:  24, dy: -18 }],
  ast_2: [{ label: 'Грузовое депо',        dx:   0, dy: -20 }],
  ast_3: [{ label: 'Депо Зап.',            dx:   0, dy: -20 }],
  shm_1: [{ label: 'Депо Шымкент',         dx: -18, dy: -18 },
          { label: 'Ремонтное депо',       dx:  22, dy: -18 }],
  shm_2: [{ label: 'Грузовое депо',        dx:   0, dy: -20 }],
  akb_1: [{ label: 'Депо Актобе',          dx:   0, dy: -20 }],
  akb_2: [{ label: 'Тяговое депо',         dx:   0, dy: -20 }],
  kar_1: [{ label: 'Депо КАР-1',           dx: -20, dy: -18 },
          { label: 'Депо КАР-2',           dx:  22, dy: -18 }],
  kar_2: [{ label: 'Грузовое депо',        dx:   0, dy: -20 }],
  kar_3: [{ label: 'Депо Шахтинск',        dx:   0, dy: -20 }],
  pav_1: [{ label: 'Депо Павлодар',        dx:   0, dy: -20 }],
  pav_2: [{ label: 'Грузовое депо',        dx:   0, dy: -20 }],
  aty_1: [{ label: 'Депо Атырау',          dx:   0, dy: -20 }],
  aty_2: [{ label: 'Грузовое депо',        dx:   0, dy: -20 }],
};
