/* N8 Crosslink – Dashboard & Adminportal */
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const NET = { frn: { label: 'FRN', icon: '📻' }, dmr: { label: 'DMR', icon: '📡' }, zello: { label: 'Zello', icon: '💬' } };
const ORDER = ['frn', 'dmr', 'zello'];
let S = { state: null, me: null, lh: [], lhLimit: 25, cfg: null, range: 'today', adminSec: 'general' };

/* ---------- Helfer ---------- */
function fmtDur(s) {
  s = Math.round(s || 0);
  if (s < 60) return s + ' s';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`;
}
function fmtTime(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const t = d.toLocaleTimeString(N8Kit.locale(), { hour: '2-digit', minute: '2-digit' });
  return d.toDateString() === now.toDateString() ? t : d.toLocaleDateString(N8Kit.locale(), { day: '2-digit', month: '2-digit' }) + ' ' + t;
}
function ago(ts) {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return 'gerade eben'; if (s < 3600) return Math.floor(s / 60) + ' min';
  if (s < 86400) return Math.floor(s / 3600) + ' h'; return Math.floor(s / 86400) + ' d';
}
function initials(name) {
  const p = String(name || '?').trim().split(/\s+/);
  return (p[0] || '?').slice(0, 2).toUpperCase();
}
function splitName(t) {               // "DL1ABC Hans" -> ["DL1ABC", "Hans"]
  const n = String(t?.name || '').trim(); const cs = t?.callsign || '';
  if (cs && n.toUpperCase().startsWith(cs.toUpperCase())) return [cs, n.slice(cs.length).trim()];
  return [n || cs || '?', cs && cs !== n ? cs : ''];
}
const AVV = Math.floor(Date.now() / 86400000);   // Avatare max. 1 Tag im Browser-Cache
function avatarKey(src, o) { return src === 'dmr' ? (o.dmr_id || '') : (src === 'zello' ? (o.name || o.callsign || '') : (o.callsign || o.name || '')); }
function avatar(src, key, label, cls = 'avatar', style = '') {
  const img = key ? `<img src="/api/avatar/${src}/${encodeURIComponent(key)}?v=${AVV}" alt="" loading="lazy" onerror="this.remove()">` : '';
  return `<span class="${cls} ${src}" ${style}><span class="av-fb">${esc(initials(label))}</span>${img}</span>`;
}
const badge = (k, extra = '') => `<span class="badge ${k} ${extra}">${esc(NET[k]?.label || k)}</span>`;
/* Status-Popup: statusPopup('busy'|'ok'|'err', Titel, Text) */
function statusPopup(state, title, text = '') {
  const box = $('#statusBox');
  box.classList.remove('ok', 'err'); if (state !== 'busy') box.classList.add(state);
  $('#spIcon').innerHTML = state === 'busy' ? '<span class="spinner"></span>' : state === 'ok' ? '✅' : '⚠️';
  $('#spTitle').textContent = title; $('#spText').textContent = text;
  $('#spOk').hidden = state === 'busy';
  $('#statusModal').classList.add('open');
}
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2800); }
async function api(path, opts = {}) {
  const o = { headers: { 'Content-Type': 'application/json', 'X-N8': '1' }, credentials: 'same-origin', ...opts };
  if (o.body && typeof o.body !== 'string') o.body = JSON.stringify(o.body);
  const r = await fetch(path, o);
  let data = null; try { data = await r.json(); } catch { /* leer */ }
  if (!r.ok) throw new Error(data?.detail || r.statusText);
  return data;
}

/* ---------- Tabs & Abschnitte ---------- */
function showTab(name) {
  $$('#mainTabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $$('.tab-pane').forEach(p => p.classList.toggle('hidden', p.id !== 'tab-' + name));
  if (name === 'stats') loadStats();
  if (name === 'nets') renderNetDetails();
  if (name === 'admin') loadAdmin();
  history.replaceState(null, '', '#' + name);
}
$$('#mainTabs button').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
$$('.collapsible').forEach(h => {
  const key = 'n8x_c_' + h.dataset.section, body = $(`[data-body="${h.dataset.section}"]`);
  const set = (c) => { h.classList.toggle('collapsed', c); body.classList.toggle('hidden', c); };
  set(localStorageGet(key) === '1');
  h.addEventListener('click', () => { const c = !h.classList.contains('collapsed'); set(c); localStorageSet(key, c ? '1' : '0'); });
});
function localStorageGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function localStorageSet(k, v) { try { localStorage.setItem(k, v); } catch { /* egal */ } }
$('#linksBtn').addEventListener('click', (e) => { e.stopPropagation(); $('#linksMenu').classList.toggle('open'); });
document.addEventListener('click', () => $('#linksMenu').classList.remove('open'));

/* ---------- WebSocket ---------- */
let ws, wsRetry = 1000;
function connectWS() {
  ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
  ws.onopen = () => { wsRetry = 1000; $('#ssLive').className = 'ss on'; loadLastHeard(); loadToday(); loadEvents(); };
  ws.onclose = () => { $('#ssLive').className = 'ss'; setTimeout(connectWS, wsRetry); wsRetry = Math.min(wsRetry * 2, 15000); };
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === 'state') { S.state = m; renderState(); }
    if (m.type === 'meter') { onMeter(m); return; }
    else if (m.type === 'talk_start' || m.type === 'talk_end') { loadLastHeard(); if (m.type === 'talk_end') loadToday(); }
    else if (m.type === 'event') addEvent(m);
  };
}
$('#ssLive').addEventListener('click', () => location.reload());

/* ---------- Live-Status ---------- */
function renderState() {
  const st = S.state; if (!st) return;
  const ports = st.ports || {};
  const online = ORDER.filter(k => ports[k]?.enabled && ports[k]?.online).length;
  const enabled = ORDER.filter(k => ports[k]?.enabled).length;
  $('#stNets').textContent = `${online}/${enabled}`;
  // Statusleiste
  for (const k of ORDER) {
    const p = ports[k] || {}; const el = $('#ss' + k[0].toUpperCase() + k.slice(1));
    let cls = 'ss'; if (!p.enabled) cls += ' warn'; else if (p.online) cls += ' on';
    if (p.tx) cls = 'ss tx'; else if (p.rx) cls = 'ss rx';
    el.className = cls;
    $('#ss' + k[0].toUpperCase() + k.slice(1) + 'Lbl').innerHTML = '&nbsp;' + esc(!p.enabled ? 'aus' : p.tx ? 'sendet' : p.rx ? 'empfängt' : p.online ? 'online' : p.state || 'offline');
  }
  const v = st.vocoder;
  $('#ssVoc').className = 'ss ' + (v ? (v.online ? 'on' : '') : 'warn');
  $('#ssVocLbl').innerHTML = '&nbsp;' + esc(v ? (v.mode === 'n8vocoder' ? 'N8schicht' : v.mode === 'usb' ? 'USB-Stick' : v.mode) + (v.online ? '' : ' offline') : 'aus');
  const act = st.active;
  $('#ssTalk').classList.toggle('live', !!act);
  $('#ssTalker').innerHTML = act ? `🎙 ${esc(act.talker.name || act.talker.callsign || '')} <span style="color:var(--text-dim);font-weight:400">· ${esc(NET[act.source]?.label || act.source)}</span>` : 'Ruhe';
  // Rückfall, falls (noch) keine Spektrum-Meldungen kommen: Pegel aus dem Status
  if (act && performance.now() - MTR.t > 500) { MTR.tl = st.ports[act.source]?.rx_level ?? -90; MTR.src = act.source; MTR.tf = performance.now(); }
  renderOnAir(); renderNetCards(); renderRoom();
  const up = st.update;
  if (!S.me?.user) $('#updateBanner').hidden = true;
  else if (JSON.stringify(up || {}) !== S.updSig) {
    S.updSig = JSON.stringify(up || {});
    N8Kit.update.banner($('#updateBanner'), kitUpdate(up), { app: 'n8x', onInstall: () => startUpdate(),
      onDetails: () => { S.adminSec = 'sys-update'; showTab('admin'); } });
  }
  if ($('#tab-nets') && !$('#tab-nets').classList.contains('hidden')) renderNetDetails();
}

/* ---------- On Air: Display wie ein Funkgerät, mit Pegel, Audio-Spektrum, Vocoder und Tagesstatistik ---------- */
const OA = { talk: 0, peak: -90, sum: 0, n: 0, voc0: null, src: '' };
(function buildVu() {
  const m = $('#oaVu'); if (!m) return;
  m.innerHTML = Array.from({ length: 30 }, (_, i) => { const db = -60 + (i + 1) * 2; return `<i class="${db > -6 ? 'r' : db > -18 ? 'y' : 'g'}"></i>`; }).join('');
})();
const VU = { n: -1, pk: -1, segs: null };
function setVu(lvl, peak) {
  const segs = VU.segs || (VU.segs = $$('#oaVu i')); if (!segs.length) return;
  const n = Math.max(0, Math.min(30, Math.round((lvl + 60) / 2))), pk = peak > -60 ? Math.max(0, Math.min(30, Math.round((peak + 60) / 2))) - 1 : -1;
  if (n === VU.n && pk === VU.pk) return;          // nur ändern, was sich ändert
  VU.n = n; VU.pk = pk;
  segs.forEach((el, i) => { el.classList.toggle('lit', i < n); el.classList.toggle('peak', i === pk); });
}
function cssVar(name, fb) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fb; }

/* Live-Anzeige: der Server schickt während einer Durchsage 25× je Sekunde Pegel, Spitze und 32 Spektrum-Bänder
 * (Meldung "meter"). Die Seite zeichnet mit der Bildwiederholrate des Bildschirms und glättet dazwischen:
 * schneller Anstieg, ruhiger Abfall, Spitzenwerte mit Haltezeit – so laufen Pegel und Spektrum flüssig. */
const MTR = { n: 32, f0: 120, f1: 3900, t: 0, tf: 0, src: '', tl: -90, l: -90, vp: -90, vpT: 0,
  tb: new Float32Array(32), b: new Float32Array(32), pk: new Float32Array(32), pkT: new Float64Array(32), last: 0, idle: false };
function onMeter(m) {
  const now = performance.now(), b = m.b || [];
  MTR.t = MTR.tf = now; MTR.src = m.src; MTR.tl = m.l;
  for (let i = 0; i < MTR.n; i++) MTR.tb[i] = b[i] || 0;
  if (m.l > -60) { OA.peak = Math.max(OA.peak, m.l); OA.sum += m.l; OA.n++; }
  MTR.idle = false;
}
function meterFrame(now) {
  requestAnimationFrame(meterFrame);
  const dt = Math.min(0.1, (now - (MTR.last || now)) / 1000); MTR.last = now;
  const live = !!S.state?.active;
  // Daten veraltet (Pause zwischen zwei Paketen, Ende der Durchsage): Ziel sinkt auf Ruhe
  if (!live || now - MTR.tf > 180) { MTR.tl = -90; MTR.tb.fill(0); }
  // Pegel: Anstieg ~40 ms, Abfall 26 dB/s; Spitzenmarke hält 1,2 s und fällt dann mit 14 dB/s
  MTR.l = MTR.tl > MTR.l ? MTR.l + (MTR.tl - MTR.l) * Math.min(1, dt * 25) : Math.max(MTR.tl, MTR.l - 26 * dt);
  if (MTR.l >= MTR.vp) { MTR.vp = MTR.l; MTR.vpT = now; } else if (now - MTR.vpT > 1200) MTR.vp = Math.max(-90, MTR.vp - 14 * dt);
  let busy = MTR.l > -61 || MTR.vp > -61;
  for (let i = 0; i < MTR.n; i++) {
    const t = MTR.tb[i], v = MTR.b[i];
    MTR.b[i] = t > v ? v + (t - v) * Math.min(1, dt * 30) : Math.max(t, v - 75 * dt);
    if (MTR.b[i] >= MTR.pk[i]) { MTR.pk[i] = MTR.b[i]; MTR.pkT[i] = now; } else if (now - MTR.pkT[i] > 450) MTR.pk[i] = Math.max(0, MTR.pk[i] - 45 * dt);
    if (MTR.b[i] > .3 || MTR.pk[i] > .3) busy = true;
  }
  if (!busy && MTR.idle) return;                   // alles in Ruhe und schon gezeichnet: nichts zu tun
  MTR.idle = !busy;
  setVu(MTR.l, MTR.vp);
  setSegMeter(MTR.l);
  const db = MTR.l > -60 ? `${Math.round(MTR.l)} dB` : '– dB', e = $('#oaDb');
  if (e && e.textContent !== db) e.textContent = db;
  drawSpectrum(NETCOL[MTR.src] || '#5ac8fa');
}
function drawSpectrum(col) {
  const c = $('#oaSpec'); if (!c) return;
  const w = c.clientWidth || 300, h = c.clientHeight || 150, dpr = window.devicePixelRatio || 1;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
  const g = c.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
  const axis = 13, top = 4, ph = h - axis - top, n = MTR.n, gap = Math.max(2, Math.round(w / n * 0.22)), bw = (w - gap * (n - 1)) / n;
  // Raster und leere Balken wie auf einem LCD
  g.fillStyle = 'rgba(207,239,255,.055)';
  for (let i = 0; i < n; i++) g.fillRect(i * (bw + gap), top, bw, ph);
  g.strokeStyle = 'rgba(207,239,255,.07)'; g.lineWidth = 1;
  [.25, .5, .75].forEach(f => { const y = Math.round(top + ph * f) + .5; g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke(); });
  // Balken: Farbe des sprechenden Netzes, nach oben heller, mit Glühen
  const gr = g.createLinearGradient(0, top + ph, 0, top);
  gr.addColorStop(0, col + 'cc'); gr.addColorStop(.6, col); gr.addColorStop(1, '#eafcff');
  g.save(); g.shadowColor = col; g.shadowBlur = 10; g.fillStyle = gr;
  g.beginPath();
  for (let i = 0; i < n; i++) { const v = MTR.b[i] / 100; if (v > .004) { const bh = v * ph; g.rect(i * (bw + gap), top + ph - bh, bw, bh); } }
  g.fill(); g.restore();
  // waagerechte Fugen -> Segmente wie bei einer LED-Kette
  g.save(); g.globalCompositeOperation = 'destination-out'; g.fillStyle = '#000';
  for (let y = top + ph - 4; y > top; y -= 4) g.fillRect(0, y, w, 1);
  g.restore();
  // Spitzenwerte
  g.fillStyle = 'rgba(255,255,255,.9)';
  for (let i = 0; i < n; i++) { const v = MTR.pk[i] / 100; if (v > .01) g.fillRect(i * (bw + gap), Math.round(top + ph - v * ph) - 2, bw, 2); }
  // Frequenzachse (logarithmisch)
  g.fillStyle = 'rgba(207,239,255,.45)'; g.font = '9px ' + cssVar('--n8-mono', 'monospace'); g.textBaseline = 'bottom';
  const lx = f => Math.log(f / MTR.f0) / Math.log(MTR.f1 / MTR.f0) * w;
  [[250, '250'], [500, '500'], [1000, '1k'], [2000, '2k'], [3000, '3k']].forEach(([f, t]) => {
    const x = lx(f), tw = g.measureText(t).width; g.fillText(t, Math.max(0, Math.min(w - tw, x - tw / 2)), h);
  });
  g.fillText('Hz', 0, h);
}
requestAnimationFrame(meterFrame);
function drawHours(hours, now) {
  const c = $('#oaHours'); if (!c || !hours) return;
  const w = c.clientWidth || 300, h = c.clientHeight || 70, dpr = window.devicePixelRatio || 1;
  if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
  const g = c.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
  const max = Math.max(1, ...hours), bw = w / 24, acc = cssVar('--accent', '#5ac8fa');
  hours.forEach((v, i) => {
    const bh = v ? Math.max(3, (v / max) * (h - 12)) : 2;
    g.fillStyle = i === now ? acc : v ? acc + '88' : 'rgba(255,255,255,.08)';
    g.fillRect(i * bw + 1.5, h - 10 - bh, bw - 3, bh);
  });
  g.fillStyle = 'rgba(235,240,250,.45)'; g.font = '9px ' + (cssVar('--n8-mono', 'monospace'));
  [0, 6, 12, 18].forEach(hh => g.fillText(String(hh).padStart(2, '0'), hh * bw + 1, h - 1));
}
const NETCOL = { frn: '#0a84ff', dmr: '#30d158', zello: '#ff9f0a' };
function vocQuality(v, base) {
  const f = k => (v?.[k] || 0) - (base?.[k] || 0);
  const frames = f('enc') + f('dec'), bad = f('errors') + f('timeouts') + f('late') + f('erasures');
  return { frames, bad, enc: f('enc'), dec: f('dec'), q: frames ? Math.max(0, 100 * (1 - bad / frames)) : null };
}
function renderInstruments(a) {
  const st = S.state || {}, v = st.vocoder;
  // Pegel und Spektrum zeichnet meterFrame(); hier nur die Werte des Durchgangs
  const now = Date.now() / 1000;
  if (a && OA.talk !== a.since) { OA.talk = a.since; OA.peak = -90; OA.sum = 0; OA.n = 0; OA.voc0 = v ? { ...v } : null; OA.src = a.source; }
  $('#oaLvlInfo').textContent = OA.n ? `Spitze ${Math.round(OA.peak)} dB · Ø ${Math.round(OA.sum / OA.n)} dB` + (a ? '' : ' (letzter Durchgang)') : 'Spitze – · Ø –';
  const tdy = S.today || {};
  $('#oaGraphInfo').textContent = a ? `${NET[a.source]?.label || a.source} · 0–4 kHz` : '0–4 kHz';
  $('#oaPkts').textContent = tdy.talks ? `Ø ${fmtDur((tdy.airtime || 0) / tdy.talks)} je Durchgang · ${tdy.talks} heute` : 'noch kein Durchgang heute';
  // Vocoder: Qualität des laufenden Durchgangs (wenn DMR beteiligt), sonst gesamt
  const ring = $('#oaVocRing');
  if (!v) {
    $('#oaVocQ').textContent = 'aus'; $('#oaVocT').innerHTML = 'kein Vocoder eingerichtet'; $('#oaVocF').textContent = '–';
    ring.style.strokeDashoffset = 113.1; return;
  }
  const dmrIn = a && (a.source === 'dmr' || (a.targets || []).includes('dmr'));
  const cur = dmrIn ? vocQuality(v, OA.voc0) : null, all = vocQuality(v, null);
  const show = cur && cur.frames ? cur : all;
  const q = show.q;
  $('#oaVocQ').textContent = q == null ? (v.online ? 'bereit' : 'offline') : `${q.toFixed(q >= 99.95 ? 0 : 1)} %`;
  ring.style.strokeDashoffset = 113.1 * (1 - (q == null ? 0 : q / 100));
  ring.style.stroke = q == null ? 'var(--text-dim)' : q >= 98 ? 'var(--green)' : q >= 90 ? 'var(--amber)' : 'var(--red)';
  $('#oaVocT').innerHTML = `${dmrIn ? 'dieser Durchgang' : 'gesamt'}<br>⇡ Enc <b>${show.enc}</b> · ⇣ Dec <b>${show.dec}</b><br>Fehler <b>${show.bad}</b>${v.restarts ? ` · Neustarts <b>${v.restarts}</b>` : ''}`;
  $('#oaVocF').textContent = `${v.online ? '●' : '○'} ${v.name || v.mode}${v.late ? ' · spät ' + v.late : ''}${v.timeouts ? ' · Timeouts ' + v.timeouts : ''}`;
}
function renderToday() {
  const t = S.today; if (!t) return;
  $('#oaTodayN').textContent = `${t.talks} Durchg.`;
  drawHours(t.hours, new Date().getHours());
  const by = t.by_source || {};
  $('#oaTodayF').textContent = `${fmtDur(t.airtime)} Sendezeit · ${t.stations} Stationen` + ORDER.filter(k => by[k]?.talks).map(k => ` · ${NET[k].label} ${by[k].talks}`).join('');
}
function renderOnAir() {
  const a = S.state?.active, box = $('#onair');
  const ports = S.state?.ports || {};
  // LEDs wie beim N8 Hotspot: RX Magenta · TX Rot · Dienst ok Grün (aus = Gelb, offline = Rot)
  const led = (id, cls) => { const e = $('#' + id); if (e) e.className = 'led ' + cls; };
  led('oaRx', a ? 'on m pulse' : '');
  led('oaTx', ORDER.some(k => ports[k]?.tx) ? 'on r' : '');
  ORDER.forEach(k => { const p = ports[k] || {}; led('led' + k[0].toUpperCase() + k.slice(1), !p.enabled ? 'dim' : p.online ? 'on g' : 'on r'); });
  const v = S.state?.vocoder; led('ledVoc', !v ? 'dim' : v.online ? 'on g' : 'on r');
  if (!a) {
    box.classList.remove('live');
    $('#stActive').textContent = '–';
    $('#oaKicker').textContent = 'Ruhe'; $('#oaRoute').innerHTML = '';
    const last = S.lh.find(x => x.status !== 'blocked');
    $('#oaName').textContent = 'Ruhe auf allen Netzen';
    if ($('#oaAv').dataset.k) { $('#oaAv').outerHTML = '<div class="big-av" id="oaAv"><span class="av-fb">N8</span></div>'; }
    $('#oaSub').innerHTML = last ? `Zuletzt: <b>${esc(last.name || last.callsign)}</b> ${badge(last.source)} · vor ${ago(last.ts_end || last.ts_start)} · ${fmtDur(last.duration)}` : 'Warte auf die nächste Durchsage …';
    box.style.removeProperty('--srccol');
    $('#oaTimer').textContent = '00:00';
    renderInstruments(null);
    return;
  }
  const t = a.talker, [cs] = splitName(t);
  box.classList.add('live');
  box.style.setProperty('--srccol', `var(--${a.source})`);
  $('#stActive').textContent = cs;
  const k = avatarKey(a.source, t);
  if ($('#oaAv').dataset.k !== a.source + k) { $('#oaAv').dataset.k = a.source + k; $('#oaAv').outerHTML = avatar(a.source, k, cs, 'big-av').replace('class="big-av', 'id="oaAv" data-k="' + esc(a.source + k) + '" class="big-av'); }
  $('#oaKicker').textContent = `On Air · über ${NET[a.source].label}`;
  $('#oaRoute').innerHTML = `${badge(a.source)} <span class="arrow">→</span> ${a.targets.length ? a.targets.map(x => badge(x)).join(' ') : '<span class="badge off">kein Ziel online</span>'}`;
  $('#oaName').textContent = t.name || cs;
  const frid = t.extra?.frid ? ' <span class="frid-tag" title="Registriert bei FreeRadioID.net">FRID</span>' : '';
  const parts = [t.detail, t.city, t.extra?.country, t.dmr_id ? 'ID ' + t.dmr_id : '', t.extra?.band].filter(Boolean).map(esc);
  $('#oaSub').innerHTML = parts.join(' · ') + frid;
  renderInstruments(a);
}

/* Segmentierte Pegelanzeige: 20 Segmente à 3 dB (−60 … 0 dBFS), grün bis −18, gelb bis −6, rot darüber, mit Spitzenwert */
const SEG = { n: 20, peak: -90, peakT: 0 };
(function buildSegMeter() {
  const m = $('#ssMeter'); if (!m) return;
  m.innerHTML = Array.from({ length: SEG.n }, (_, i) => {
    const db = -60 + (i + 1) * 3;
    return `<i class="${db > -6 ? 'r' : db > -18 ? 'y' : 'g'}"></i>`;
  }).join('');
})();
function setSegMeter(lvl) {
  const segs = $$('#ssMeter i'); if (!segs.length) return;
  const n = Math.max(0, Math.min(SEG.n, Math.round((lvl + 60) / 3)));
  const now = Date.now();
  if (lvl > SEG.peak || now - SEG.peakT > 1500) { SEG.peak = lvl; SEG.peakT = now; }
  const pk = Math.max(0, Math.min(SEG.n, Math.round((SEG.peak + 60) / 3))) - 1;
  const key = n * 100 + (SEG.peak > -60 ? pk : -1);
  if (key !== SEG.key) { SEG.key = key; segs.forEach((el, i) => { el.classList.toggle('lit', i < n); el.classList.toggle('peak', i === pk && SEG.peak > -60); }); }
  const t = lvl > -60 ? `${Math.round(lvl)} dB` : '', d = $('#ssMeterDb'); if (d.textContent !== t) d.textContent = t;
}
setInterval(() => {
  const a = S.state?.active;
  const ck = $('#lcdClock'); if (ck) ck.textContent = new Date().toLocaleTimeString(N8Kit.locale());
  if (a) { const d = Math.max(0, Date.now() / 1000 - a.since); $('#oaTimer').textContent = `${String(Math.floor(d / 60)).padStart(2, '0')}:${String(Math.floor(d % 60)).padStart(2, '0')}`; }
}, 250);

function routeChips(k) {
  const r = S.state?.routes || {};
  return ORDER.filter(o => o !== k).map(o => `<span class="badge ${r[k + '_' + o] ? o : 'dim'}" title="${NET[k].label} → ${NET[o].label}">→ ${NET[o].label} ${r[k + '_' + o] ? '✓' : '✕'}</span>`).join('');
}

function netLogo(k, icon) {
  const img = k === 'voc' ? '<img src="/static/n8crosslink-icon.svg" alt="" onload="this.classList.add(\'ok\')" onerror="this.remove()">'
    : `<img src="/api/neticon/${k}?d=${AVV}" alt="" onload="this.classList.add('ok')" onerror="this.remove()">`;
  return `<span class="nc-logo" data-k="${k}">${icon}${img}</span>`;
}
function renderNetCards() {
  const ports = S.state?.ports || {}, act = S.state?.active;
  const cards = ORDER.map(k => {
    const p = ports[k] || {}; const n = NET[k];
    const dot = !p.enabled ? 'warn' : p.online ? 'on' : 'off';
    let now = '';
    if (p.tx && p.tx_talker) now = `🔴 sendet <b>${esc(p.tx_talker.name)}</b> ${badge(p.tx_talker.source)}`;
    else if (p.rx && act?.source === k) now = `🟣 empfängt <b>${esc(act.talker.name)}</b>`;
    else if (p.rx) now = '🟡 Empfang gesperrt (Bridge belegt)';
    else now = `<span style="color:var(--text-dim)">${esc(p.enabled ? (p.online ? 'bereit' : (p.state || 'offline')) : 'deaktiviert')}</span>`;
    const meta = [];
    if (k === 'frn') { if (p.cluster) meta.push(p.cluster.on === 'master' ? 'Master' : '<span style="color:var(--amber)">Backup</span>'); if (p.access) meta.push('Zugang ' + esc(p.access)); }
    if (k === 'dmr') { meta.push(`Peer ${esc(p.peer_id)}`); if (p.stats) meta.push(`Pakete ⇣${p.stats.rx_pkts || 0} ⇡${p.stats.tx_pkts || 0}`); }
    if (k === 'zello') { if (p.users_online != null) meta.push(`${p.users_online} online`); }
    if (p.watchdog?.reconnects) meta.push(`🔁 ${p.watchdog.reconnects}`);
    const c = p.counters || {};
    meta.push(`⇣ ${c.rx || 0} · ⇡ ${c.tx || 0}`);
    return `<div class="net-card ${k} ${p.tx ? 'txing' : ''} ${p.rx && act?.source === k ? 'rxing' : ''}">
      <div class="nc-head">${netLogo(k, n.icon)}
        <div class="grow"><div class="nc-title"><span class="nc-dot ${dot}"></span>${n.label}</div><div class="nc-sub">${esc(p.detail || p.state || '')}</div></div>
        <div class="rt"><span class="rx ${p.rx ? 'on' : ''}">RX</span><span class="tx ${p.tx ? 'on' : ''}">TX</span></div></div>
      <div class="nc-now">${now}</div>
      <div class="nc-meta">${meta.filter(Boolean).map(m => `<span>${m}</span>`).join('<span>·</span>')}</div>
      <div class="nc-foot"><div class="nc-routes">${routeChips(k)}</div></div></div>`;
  });
  const v = S.state?.vocoder;
  if (v) {
    const q = vocQuality(v, null), dmrIn = act && (act.source === 'dmr' || (act.targets || []).includes('dmr'));
    cards.push(`<div class="net-card voc ${dmrIn ? 'rxing' : ''}">
      <div class="nc-head">${netLogo('voc', '🎛️')}
        <div class="grow"><div class="nc-title"><span class="nc-dot ${v.online ? 'on' : 'off'}"></span>Vocoder</div><div class="nc-sub">${esc(v.name || v.mode)}</div></div>
        <div class="rt"><span class="rx ${dmrIn ? 'on' : ''}">AMBE</span></div></div>
      <div class="nc-now">${dmrIn ? '🟣 wandelt <b>AMBE ⇄ PCM</b>' : `<span style="color:var(--text-dim)">${v.online ? 'bereit' : 'offline'}</span>`}</div>
      <div class="nc-meta"><span>Qualität ${q.q == null ? '–' : q.q.toFixed(1) + ' %'}</span><span>·</span><span>Enc ${v.enc || 0} · Dec ${v.dec || 0}</span>${q.bad ? `<span>·</span><span>Fehler ${q.bad}</span>` : ''}</div>
      <div class="nc-foot"><div class="nc-routes"><span class="badge dim">${esc(v.mode === 'n8vocoder' ? 'Software' : v.mode === 'usb' ? 'USB-Stick' : v.mode)}</span>${v.version ? `<span class="badge dim">${esc(String(v.version).split(' (')[0])}</span>` : ''}</div></div></div>`);
  }
  // Logos bleiben stehen (kein Neuladen/Flackern bei jeder Statusmeldung)
  const keep = {}; $$('#netGrid .nc-logo[data-k]').forEach(el => { keep[el.dataset.k] = el; });
  $('#netGrid').innerHTML = cards.join('');
  $$('#netGrid .nc-logo[data-k]').forEach(el => { const o = keep[el.dataset.k]; if (o) el.replaceWith(o); });
}

function renderRoom() {
  const p = S.state?.ports?.frn; const list = p?.clients || [];
  $('#roomCount').textContent = p?.online ? `${list.length} · ${p.net || ''}` : '';
  if (!p?.online) { $('#roomList').innerHTML = `<div class="empty">${p?.enabled ? 'Keine FRN-Verbindung.' : 'FRN ist deaktiviert.'}</div>`; return; }
  if (!list.length) { $('#roomList').innerHTML = '<div class="empty">Keine Stationen im Raum.</div>'; return; }
  const activeCs = S.state.active?.source === 'frn' ? S.state.active.talker.callsign : '';
  $('#roomList').innerHTML = `<table class="tbl"><thead><tr><th>Station</th><th>Ort</th><th>Band / Kanal</th><th>Typ</th></tr></thead><tbody>${
    list.map(c => `<tr ${c.callsign === activeCs ? 'style="background:rgba(255,45,209,.12)"' : ''}><td><div class="lh-user">${avatar('frn', c.callsign, c.callsign)}
      <div><div class="lh-cs">${esc(c.callsign)}${c.callsign === activeCs ? ' 🎙️' : ''}${c.muted ? ' 🔇' : ''}</div><div class="lh-name">${esc(c.name)}</div></div></div></td>
      <td>${esc(c.city)}${c.country ? ' · ' + esc(c.country) : ''}</td><td>${esc(c.band)}</td><td>${esc(c.type)}</td></tr>`).join('')}</tbody></table>`;
}

/* ---------- Last Heard ---------- */
async function loadLastHeard() {
  try { S.lh = await api('/api/lastheard?limit=' + S.lhLimit); } catch { return; }
  renderLH(); renderOnAir();
}
function renderLH() {
  const list = S.lh;
  $('#lhCount').textContent = list.length ? list.length : '';
  if (!list.length) { $('#lhList').innerHTML = '<div class="empty">Noch nichts gehört.</div>'; return; }
  $('#lhList').innerHTML = list.map(e => {
    const [cs, nm] = splitName(e);
    const live = e.status === 'live', blocked = e.status === 'blocked';
    const dur = live ? '<span class="badge ok">LIVE</span>' : fmtDur(e.duration);
    const status = blocked ? '<span class="badge warn">blockiert</span>' : e.status === 'timeout' ? '<span class="badge off">Time-Out</span>' : live ? '<span class="badge ok">on air</span>' : '<span class="badge">ok</span>';
    const targets = blocked ? '<span style="color:var(--text-dim)">–</span>' : (e.targets || []).length ? e.targets.map(t => badge(t)).join('') : '<span style="color:var(--text-dim)">kein Ziel</span>';
    return `<div class="lh-row ${live ? 'live' : ''} ${blocked ? 'blocked' : ''}">
      <div class="lh-time" title="${new Date(e.ts_start * 1000).toLocaleString(N8Kit.locale())}">${fmtTime(e.ts_start)}</div>
      <div class="lh-user">${avatar(e.source, avatarKey(e.source, e), cs)}<div style="min-width:0"><div class="lh-cs">${esc(cs)}</div>
        <div class="lh-name">${esc(nm)}${e.dmr_id ? ' · ' + e.dmr_id : ''}</div></div></div>
      <div>${badge(e.source)}</div>
      <div class="lh-detail">${esc(e.detail || '')}</div>
      <div class="lh-targets">${targets}</div>
      <div class="lh-dur">${dur}</div>
      <div class="lh-status">${status}</div></div>`;
  }).join('');
  $('#lhMore').classList.toggle('hidden', list.length < S.lhLimit);
}
$('#lhMore').addEventListener('click', () => { S.lhLimit += 25; loadLastHeard(); });
setInterval(() => { if (S.lh.length) renderLH(); }, 30000);

async function loadToday() {
  try {
    const s = await api('/api/stats?range=today');
    S.today = s; renderToday();
    $('#stTalks').textContent = s.talks; $('#stAir').textContent = fmtDur(s.airtime);
    $('#stStations').textContent = s.stations; $('#stBlocked').textContent = s.blocked;
  } catch { /* egal */ }
}

/* ---------- Ereignisse ---------- */
const EV = [];
async function loadEvents() {
  try { const l = await api('/api/events?limit=20'); EV.length = 0; l.reverse().forEach(addEvent); } catch { /* egal */ }
}
function addEvent(m) {
  EV.unshift(m); EV.length = Math.min(EV.length, 40);
  $('#evList').innerHTML = EV.map(e => `<div class="ev-row ${e.level === 'warn' ? 'warn' : ''}"><time>${new Date(e.ts * 1000).toLocaleTimeString(N8Kit.locale())}</time><div>${esc(e.text)}</div></div>`).join('');
}

/* ---------- Statistik ---------- */
$$('#rangeSeg button').forEach(b => b.addEventListener('click', () => {
  $$('#rangeSeg button').forEach(x => x.classList.toggle('active', x === b)); S.range = b.dataset.r; loadStats();
}));
async function loadStats() {
  let s; try { s = await api('/api/stats?range=' + S.range); } catch { return; }
  $('#s2Talks').textContent = s.talks; $('#s2Air').textContent = fmtDur(s.airtime);
  $('#s2Stations').textContent = s.stations; $('#s2Blocked').textContent = s.blocked;
  const max = Math.max(1, ...ORDER.map(k => s.by_source[k]?.airtime || 0));
  $('#srcBars').innerHTML = ORDER.map(k => {
    const d = s.by_source[k] || { talks: 0, airtime: 0 };
    return `<div class="bar-row">${badge(k)}<div class="bar"><i style="width:${d.airtime / max * 100}%;--col:var(--${k})"></i></div><div style="text-align:right;color:var(--text-dim)">${d.talks} · ${fmtDur(d.airtime)}</div></div>`;
  }).join('');
  const hm = Math.max(1, ...s.hours);
  $('#hours').innerHTML = s.hours.map((h, i) => `<div title="${i}–${i + 1} Uhr: ${h}" style="height:${h / hm * 100}%"></div>`).join('');
  $('#hoursLbl').innerHTML = s.hours.map((_, i) => `<span>${i % 3 === 0 ? i : ''}</span>`).join('');
  $('#topBody').innerHTML = s.top.length ? s.top.map(t => {
    const [cs, nm] = splitName({ name: t.name, callsign: t.callsign });
    return `<tr><td><div class="lh-user">${avatar(t.source, t.source === 'dmr' ? (t.dmr_id || '') : (t.source === 'zello' ? t.name : cs), cs)}<div><div class="lh-cs">${esc(cs)}</div><div class="lh-name">${esc(nm)}</div></div></div></td>
      <td>${badge(t.source)}</td><td class="num">${t.talks}</td><td class="num">${fmtDur(t.airtime)}</td></tr>`;
  }).join('') : '<tr><td colspan="4" class="empty">Keine Daten im Zeitraum.</td></tr>';
}

/* ---------- Netze-Details ---------- */
function kv(rows) { return `<dl class="kv">${rows.filter(r => r[1] !== undefined && r[1] !== null && r[1] !== '').map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join('')}</dl>`; }
function renderNetDetails() {
  const p = S.state?.ports || {}, v = S.state?.vocoder;
  const on = (x) => !x?.enabled ? '<span class="badge warn">deaktiviert</span>' : x.online ? '<span class="badge ok">online</span>' : `<span class="badge off">${esc(x.state || 'offline')}</span>`;
  const f = p.frn || {}, d = p.dmr || {}, z = p.zello || {};
  const wd = (x) => [['Watchdog', `${x.watchdog?.reconnects || 0} Wiederverbindungen · ${x.watchdog?.wd_restarts || 0} Neuaufbauten${x.watchdog?.wd_reason ? ' (zuletzt: ' + esc(x.watchdog.wd_reason) + ')' : ''}`],
    [x.online ? 'Online seit' : 'Offline seit', (x.online ? x.watchdog?.online_since : x.watchdog?.offline_since) ? new Date((x.online ? x.watchdog.online_since : x.watchdog.offline_since) * 1000).toLocaleString(N8Kit.locale()) : '–']];
  const card = (k, title, body) => `<div><h2 class="section-header">${NET[k]?.icon || '🎛️'} ${title}</h2><div class="card">${body}</div></div>`;
  $('#netDetails').innerHTML =
    card('frn', 'FRN – FreeRadioNetwork', kv([['Status', on(f)], ['Server', esc(f.server)], ['Raum', esc(f.net)], ['Zugang', esc(f.access)],
      ['Server-Version', esc(f.server_version)], ['Stationen im Raum', (f.clients || []).length], ['Sende-Status', esc(f.tx_state)],
      ['Info', esc(f.net_info)], ['Durchgänge', `⇣ ${f.counters?.rx || 0} empfangen · ⇡ ${f.counters?.tx || 0} gesendet`], ...wd(f)])) +
    card('dmr', 'DMR – HomeBrew (HBlink4 / FreeDMR)', kv([['Status', on(d)], ['Server', esc(d.server)], ['Login-Phase', esc(d.login)],
      ['Peer-ID', esc(d.peer_id)], ['Zeitschlitz', 'TS' + esc(d.slot)], ['RX-Talkgroup', esc(d.tg_rx)], ['TX-Talkgroup', esc(d.tg_tx)],
      ['Verbunden seit', d.since ? new Date(d.since * 1000).toLocaleString(N8Kit.locale()) : '–'],
      ['Ping / Pong', `${d.stats?.pings || 0} / ${d.stats?.pongs || 0}`], ['Pakete', `⇣ ${d.stats?.rx_pkts || 0} · ⇡ ${d.stats?.tx_pkts || 0}`],
      ['RX-/TX-Talkgroup-Name', `${esc(d.tg_rx_name || '–')} / ${esc(d.tg_tx_name || '–')}`],
      ['ID-Listen', d.userdb ? `${(d.userdb.count || 0).toLocaleString(N8Kit.locale())} DMR-IDs · ${(d.userdb.registered || 0).toLocaleString(N8Kit.locale())} FreeRadioID · ${(d.userdb.talkgroups || 0).toLocaleString(N8Kit.locale())} Talkgroups${d.userdb.updated ? ' · Stand ' + new Date(d.userdb.updated * 1000).toLocaleString(N8Kit.locale()) : ''}` : '–'], ...wd(d)])) +
    card('zello', 'Zello – Channel API', kv([['Status', on(z)], ['Server', esc(z.server)], ['Kanal', esc(z.channel)], ['Konto', esc(z.username)],
      ['Kanal-Status', esc(z.channel_status)], ['Benutzer online', z.users_online ?? '–'],
      ['Durchgänge', `⇣ ${z.counters?.rx || 0} · ⇡ ${z.counters?.tx || 0}`], ...wd(z)])) +
    card('voc', 'Vocoder (AMBE+2)', kv([['Status', v ? (v.online ? '<span class="badge ok">bereit</span>' : '<span class="badge off">offline</span>') : '<span class="badge warn">nicht gestartet</span>'],
      ['Betriebsart', esc(v?.name)], ['Gerät', esc(v?.product)], ['Version', esc(v?.version)],
      ['Rahmen', v ? `Encode ${v.enc} · Decode ${v.dec} · Timeouts ${v.timeouts} · Wiederholt ${v.retries ?? 0} · Neu geöffnet ${v.reopens ?? 0}` : '–'],
      ['Watchdog', v ? `${v.reopens || 0}× neu geöffnet` : '–']]));
}

/* ---------- Login / Setup ---------- */
let loginMode = 'login';
// N8 Kit 1.6: the same login window as in every N8 system (first start: create the superadmin)
function openLogin(mode = 'login') {
  const setup = mode === 'setup';
  N8Kit.login.open({
    logo: document.querySelector('header img.logo')?.src || '/static/n8crosslink-icon.svg',
    title: setup ? 'Superadmin anlegen' : (document.querySelector('header h1')?.textContent || 'N8 Crosslink'),
    subtitle: setup ? 'Erster Start: lege das Superadmin-Konto an (Passwort min. 8 Zeichen).' : 'Adminbereich der N8 Crosslink.',
    setup, minLength: setup ? 8 : 0,
    submit: async ({ username, password }) => {
      if (setup) await api('/api/setup', { method: 'POST', body: { username, password } });
      else await api('/api/login', { method: 'POST', body: { username, password } });
      setTimeout(async () => { await loadMe(); showTab('admin'); toast('Angemeldet als ' + username); }, 0);
    },
  });
}
$('#setupBtn').addEventListener('click', () => openLogin('setup'));
async function loadMe() {
  const before = S.me ? !!S.me.user : null;
  S.me = await api('/api/me');
  // Ohne Anmeldung liefert der Server keine IPs/Ports – nach An- oder Abmelden Live-Verbindung und Kopf neu laden
  if (before !== null && before !== !!S.me.user) { if (ws) ws.close(); loadInfo(); loadEvents(); }
  $('#setupBanner').hidden = true;
  $('#pwBanner').hidden = !S.me.default_password;
  $('#tabAdminBtn').hidden = !S.me.user;
  $('#listenMenu').hidden = !S.me.user;
  if (!S.me.user && typeof L !== 'undefined' && L.on) listenStop();
  // N8 Kit 1.6: 🔐 Anmelden – or avatar + name ▾ with admin area and log out, the same in every N8 system
  const ROLE = { superadmin: 'Superadmin', admin: 'Admin', user: 'Benutzer' };
  N8Kit.userMenu($('#userArea'), S.me.user && { name: S.me.user, role: S.me.role || 'admin' }, {
    btnClass: S.me.user ? 'hdr-btn' : 'hdr-btn login', roleLabel: ROLE[S.me.role] || S.me.role,
    onLogin: () => openLogin(S.me.setup_required ? 'setup' : 'login'),
    onLogout: async () => { await api('/api/logout', { method: 'POST' }); await loadMe(); showTab('live'); },
    items: [
      { icon: '⚙️', label: 'Adminbereich', onClick: () => showTab('admin') },
      { icon: '🔑', label: 'Passwort ändern', onClick: () => openOwnAccount() },
    ],
  });
  if (S.me.user) checkCrashes(before === false);      // gerade angemeldet: neue Abstürze sofort zeigen
}
async function loadInfo() {
  const i = await api('/api/info');
  $('#linksPop').innerHTML = (i.links || []).map(l => `<a href="${esc(l.url)}" target="_blank" rel="noopener">🔗 ${esc(l.name)}</a>`).join('') || '<a>Keine Links</a>';
  $('#announceBanner').hidden = !i.announcement; $('#announceText').textContent = i.announcement || '';
  if (i.nets_label) {   // nur die eingeschalteten Netze
    $('#serverName').textContent = [i.nets_label, i.server_name].filter(Boolean).join(' · ');
    if ($('#footNets')) $('#footNets').textContent = i.nets_label;
  }
}

/* ---------- Admin ---------- */
const F = (key, label, type = 'text', opt = {}) => ({ key, label, type, ...opt });
const SCHEMA = {
  general: { title: '🏠 Allgemein', fields: [
    F('title', 'Titel im Dashboard'), F('server_name', 'Servername / Domain'),
    F('hang_time_ms', 'Sperrzeit nach Aussendung (ms)', 'number', { help: 'Schützt vor Ping-Pong zwischen den Netzen' }),
    F('jitter_ms', 'Vorpuffer DMR/Zello-Ausgang (ms)', 'number', { help: 'FRN liefert 200-ms-Blöcke – 240 ms sind ein guter Wert' }),
    F('tot_s', 'Time-Out-Timer pro Durchgang (s)', 'number'), F('keep_days', 'Last Heard aufbewahren (Tage)', 'number'),
    F('watchdog_offline_s', 'Watchdog: Netz nach … s offline komplett neu aufbauen', 'number', { help: 'Zusätzlich zur normalen Wiederverbindung (Standard 120 s)' }),
    F('update_check', 'Stündlich (zur vollen Stunde) auf Updates prüfen', 'bool'),
    F('update_repo', 'GitHub-Repository für Updates'), F('update_branch', 'Branch'),
    F('portal_feed', '📰 Live-Daten für die Portal-Seite des adn-frn-server', 'bool', { wide: true, help: 'Das Portal zeigt Status, wer gerade spricht und Last Heard dieses Crosslinks als Widget – verschlüsselt mit dem Sync-Schlüssel, ohne IP-Adressen' }),
    F('portal_feed_key', 'Sync-Schlüssel für das Portal', 'password', { wide: true, help: 'Aus dem Portal kopieren (adn-frn-server: 📰 Portal → 🧩 Widgets → 🎲 Neuer Schlüssel), mindestens 24 Zeichen · leer lassen = unverändert' }),
    F('announcement', 'Hinweis-Banner im Dashboard', 'text', { wide: true }),
    F('links', 'Links-Menü (JSON-Liste mit name/url)', 'json', { wide: true }),
    F('announce_enabled', '🔊 Sprachansage des Rufzeichens am Anfang eines Durchgangs', 'bool', { wide: true, help: 'Computerstimme (espeak-ng) sagt das Rufzeichen an, danach folgt der Ton – der Durchgang läuft um die Länge der Ansage verzögert' }),
    F('announce_frn', 'Ansage nach FRN', 'bool'), F('announce_dmr', 'Ansage nach DMR', 'bool'), F('announce_zello', 'Ansage nach Zello', 'bool'),
    F('announce_spell', 'Rufzeichen sprechen als', 'select', { options: [['letters', 'Buchstaben (D O 1 T E S T)'], ['nato', 'NATO-Alphabet (Delta Oscar Eins …)']] }),
    F('announce_text', 'Ansagetext', 'text', { help: 'Platzhalter: {call} = Rufzeichen, {name} = Name – z. B. „{call}“ oder „{call} {name}“' }),
    F('announce_repeat_min', 'Je Station höchstens alle … Minuten', 'number', { help: '0 = bei jedem Durchgang' }),
    F('announce_without_call', 'Auch ohne Rufzeichen (Name ansagen)', 'bool'),
    F('announce_speed', 'Sprechtempo (Wörter/Min.)', 'number'), F('announce_level_db', 'Lautstärke (dBFS Spitze)', 'number', { step: 0.5 }),
    F('announce_pause_ms', 'Pause nach der Ansage (ms)', 'number'),
  ], extra: `<div class="banner" style="margin:12px 4px 0">🔊 <span class="grow">Ansage probehören – mit den Werten aus dem Formular: <input id="annCall" value="DO1TEST" style="width:120px;margin-left:8px;background:rgba(255,255,255,.06);color:inherit;border:1px solid rgba(255,255,255,.18);border-radius:8px;padding:5px 9px;font:inherit"></span>
      <button class="btn secondary" type="button" id="annBtn">▶ Ansage anhören</button></div>` },
  routes: { title: '🔀 Routing', custom: renderRoutes },
  audio: { title: '🎚️ Audio & AGC', fields: [
    F('agc_in_frn', 'AGC Eingang FRN', 'bool'), F('agc_in_dmr', 'AGC Eingang DMR', 'bool'), F('agc_in_zello', 'AGC Eingang Zello', 'bool'),
    F('agc_out_frn', 'AGC Ausgang FRN', 'bool'), F('agc_out_dmr', 'AGC Ausgang DMR', 'bool'), F('agc_out_zello', 'AGC Ausgang Zello', 'bool'),
    F('in_target_dbfs', 'Zielpegel Eingang (dBFS RMS)', 'number', { step: 0.5, help: 'Worauf jede Quelle geregelt wird, bevor sie verteilt wird. −20 dBFS ist ein guter Wert.' }),
    F('out_target_dbfs', 'Zielpegel Ausgang (dBFS RMS)', 'number', { step: 0.5, help: 'Pegel in jedes Netz. Für AMBE und Zello −18 dBFS; der Limiter hält die Spitzen unter der Decke.' }),
    F('agc_max_gain_db', 'Höchste Verstärkung (dB)', 'number', { step: 0.5, help: 'So viel hebt die AGC leise Stationen höchstens an (15 dB).' }),
    F('agc_max_cut_db', 'Höchste Absenkung (dB)', 'number', { step: 0.5, help: 'So viel nimmt sie laute Stationen höchstens zurück (20 dB).' }),
    F('agc_attack_ms', 'Angriffszeit (ms)', 'number', { help: 'Wie schnell sie bei zu lauten Stellen zurückregelt – schnell: 5–15 ms.' }),
    F('agc_release_ms', 'Rückstellzeit (ms)', 'number', { help: 'Wie schnell sie danach wieder anhebt – 200–500 ms klingt natürlich, kürzer „pumpt“.' }),
    F('agc_gate_dbfs', 'Torschwelle (dBFS)', 'number', { help: 'Darunter gilt es als Pause/Rauschen: die Verstärkung bleibt stehen, Rauschen wird nicht hochgezogen (−50 dBFS).' }),
    F('limiter_dbfs', 'Limiter-Decke (dBFS Spitze)', 'number', { step: 0.5, help: 'Keine Spitze geht darüber – nichts übersteuert (−1 dBFS).' }),
    F('frn_hpf_hz', 'FRN: Tiefen-Filter (Hz)', 'number', { help: 'Entfernt Rumpeln, Brummen und Wind aus dem FRN-Ton (GSM) – 100–150 Hz.' }),
    F('frn_presence_db', 'FRN: Mitten anheben (dB, 2,2 kHz)', 'number', { step: 0.5, help: 'GSM klingt dumpf – die Präsenz macht Stimmen verständlicher, für Zello und AMBE (3 dB).' }),
    F('frn_treble_db', 'FRN: Höhen anheben (dB, ab 3 kHz)', 'number', { step: 0.5, help: 'Etwas mehr Brillanz aus dem FRN-Ton (2 dB). Zu viel macht Rauschen hörbar.' }),
  ], extra: `<div class="banner" style="margin:12px 4px 0">🎚️ <span class="grow">Kette je Durchgang: <b>Quelle → (FRN: Tiefen-Filter, Mitten, Höhen) → AGC Eingang → Verteilung → AGC Ausgang je Netz → Limiter → Netz</b>. Nach DMR folgt zusätzlich die Mitten-/Höhenanhebung vor dem Encoder (🎛️ Vocoder → Vor dem Encoder). Änderungen wirken sofort, ohne Neustart.</span></div>` },
  frn: { title: '📻 FRN', fields: [
    F('enabled', 'FRN aktiv', 'bool'), F('server', 'Server'), F('port', 'Port', 'number'),
    F('backup_server', 'Backup-Server'), F('backup_port', 'Backup-Port', 'number'),
    F('cluster_auto', 'Master & Backup erkennen, Master hat Vorrang', 'bool', { help: 'Fragt das Dashboard des FRN-Servers (ADN-FRN-Server ab 2.21), wer Master und wer Backup ist. Der Master ist immer Priorität 1: nach einem Ausfall geht es zum Backup, und sobald der Master wieder läuft (3 Prüfungen im Minutentakt), zwischen zwei Durchgängen zurück zum Master. Ohne Erkennung gilt „Server“ vor „Backup-Server“.' }),
    F('email', 'E-Mail (FRN-Konto)'), F('password', 'Passwort (FRN)', 'password', { help: 'leer lassen = unverändert' }),
    F('callsign', 'Rufzeichen'), F('op_name', 'Name / Bezeichnung'),
    F('client_type', 'Client-Typ', 'select', { options: [[0, '0 – Crosslink'], [1, '1 – Gateway'], [2, '2 – PC Only']] }),
    F('band', 'Band / Kanal (BC)', 'text', { help: '„Crosslink“ oder z. B. 446.03125FM CTC131.8' }),
    F('net', 'Raum (Net)', 'room', { help: 'Liste vom FRN-Server – „🔄“ liest sie neu aus. Fehlt ein Raum (z. B. versteckt), „✏️ Anderer Raum …“ wählen.' }), F('description', 'Beschreibung'), F('country', 'Land'), F('city', 'Ort – Ortsteil / Locator'),
    F('version', 'Protokollversion'), F('rx_timeout_ms', 'Ende-Erkennung RX (ms)', 'number', { help: 'Kein Sprachpaket für diese Zeit = Durchgang beendet (SvxLink: 1000)' }),
    F('rx_gain_db', 'Pegel FRN → Bridge (dB)', 'number', { step: 0.5 }), F('tx_gain_db', 'Pegel Bridge → FRN (dB)', 'number', { step: 0.5 }),
    F('text_messages', 'Sprechername als FRN-Textnachricht', 'bool', { help: 'Vor jedem Durchgang aus DMR/Zello, z. B. „DO1TEST Tobias (DMR)“' }),
    F('text_targets', 'Textnachricht nur an diese Stationen (privat)', 'text', { help: 'Rufzeichen mit Komma, z. B. DL1ABC, DB0XYZ – leer = öffentlich an alle im Raum. Privat ploppt bei den übrigen Stationen nichts auf.' }),
    F('sysman_server', 'System Manager (für „Passwort anfordern“)', 'text', { help: 'Standard sysman.freeradionetwork.eu – bei eigenem FRN-Netz dessen System Manager' }),
    F('sysman_port', 'System-Manager-Port', 'number'),
  ], extra: `<div class="banner" style="margin:12px 4px 0">🔑 <span class="grow">Noch kein FRN-Passwort? Rufzeichen, Name, E-Mail, Band/Kanal, Land und Ort ausfüllen und anfordern – das Passwort kommt per E-Mail.</span>
      <button class="btn" type="button" id="frnPwBtn">📧 Passwort anfordern</button></div>
    <h2 class="section-header">📋 FRN-Fehlerprotokoll <span id="frnElBadge"></span></h2>
    <p style="padding:0 4px;color:var(--text-dim);font-size:13px">Bei Problemen zuerst hier schauen: Das öffentliche Fehlerprotokoll von freeradionetwork.de nennt den Grund für abgelehnte Anmeldungen (falsches FRN-Passwort, Mehrfachverbindung, Port nicht erreichbar …), den der FRN-Server selbst nicht mitteilt. Gezeigt werden Einträge zu deinem Rufzeichen und deinen FRN-Servern; N8 Crosslink schaut nach jeder Ablehnung von selbst hinein und schreibt den Grund ins Ereignisprotokoll.</p>
    <div class="card" id="frnElList"><div class="empty">lade …</div></div>
    <div class="form-actions" style="justify-content:flex-start"><button class="btn secondary" type="button" id="frnElReload">🔄 Neu laden</button>
      <a class="btn secondary" href="http://log.freeradionetwork.de:60080/error_log.php" target="_blank" rel="noopener">📋 Komplettes Fehlerprotokoll öffnen ↗</a></div>` },
  dmr: { title: '📡 DMR', fields: [
    F('enabled', 'DMR aktiv', 'bool'), F('host', 'Server (HBlink4 / FreeDMR)'), F('port', 'Port', 'number'), F('local_port', 'Eigener UDP-Port', 'number', { help: '0 = beliebiger freier Port · fest z. B. für Firewall-Regeln (alle Ports: 🔌 Ports)' }),
    F('password', 'Passwort (Passphrase)', 'password', { help: 'leer lassen = unverändert · Bei HBlink4-FreeRadioID: persönliches FreeRadioID-Passwort – mit der Server-Passphrase ist die Bridge nur Gast und darf nicht in TG 262 senden' }),
    F('peer_id', 'Peer-/Repeater-ID', 'number', { help: '7- oder 9-stellig, muss am Server erlaubt sein' }),
    F('callsign', 'Rufzeichen'), F('src_id', 'Quell-ID für Sendungen ins DMR', 'number'),
    F('use_db_id', 'Rufzeichen → eigene DMR-ID, falls in der ID-Datenbank', 'bool'),
    F('slot', 'Zeitschlitz', 'select', { options: [[1, 'TS1'], [2, 'TS2']] }),
    F('tg_rx', 'Empfangs-Talkgroup', 'number', { help: '0 = alle Gruppenrufe auf dem Zeitschlitz' }), F('tg_tx', 'Sende-Talkgroup', 'number'),
    F('color_code', 'Color Code', 'number'), F('options', 'Optionen (RPTO)', 'text', { help: 'z. B. TS2=262 – leer = Serverkonfiguration' }),
    F('talker_alias', 'Talker Alias (Stationsname) im Sprachrahmen senden', 'bool'),
    F('send_dmra', 'Zusätzlich DMRA-Pakete senden (nicht für HBlink4!)', 'bool'),
    F('rx_timeout_ms', 'Ende-Erkennung RX ohne Terminator (ms)', 'number'),
    F('rx_gain_db', 'Pegel DMR → Bridge (dB)', 'number', { step: 0.5 }), F('tx_gain_db', 'Pegel Bridge → DMR (dB)', 'number', { step: 0.5 }),
    F('rx_freq', 'RX-Frequenz (Hz)', 'number'), F('tx_freq', 'TX-Frequenz (Hz)', 'number'),
    F('latitude', 'Breite'), F('longitude', 'Länge'), F('location', 'Standort'), F('description', 'Beschreibung'), F('url', 'URL'),
  ] },
  zello: { title: '💬 Zello', fields: [
    F('enabled', 'Zello aktiv', 'bool'),
    F('server', 'WebSocket-Server', 'text', { help: 'Zello: wss://zello.io/ws · Zello Work: wss://zellowork.io/ws/NETZ' }),
    F('channel', 'Kanal'), F('username', 'Benutzername'), F('password', 'Passwort', 'password', { help: 'leer lassen = unverändert' }),
    F('auth_mode', 'Authentifizierung', 'select', { options: [['token', 'Entwickler-Token'], ['key', 'Issuer + Private Key (JWT)'], ['none', 'keine (Zello Work)']] }),
    F('auth_token', 'Auth-Token', 'password', { wide: true }), F('issuer', 'Issuer'),
    F('private_key', 'Private Key (PEM)', 'textarea', { wide: true, help: 'nur für „Issuer + Private Key“ – leer lassen = unverändert' }),
    F('sample_rate', 'Abtastrate Senden', 'select', { options: [[16000, '16 kHz (empfohlen)'], [8000, '8 kHz']] }),
    F('bitrate', 'Opus-Bitrate (bit/s)', 'number'), F('packet_ms', 'Paketlänge (ms)', 'select', { options: [[20, '20 ms'], [40, '40 ms'], [60, '60 ms']] }),
    F('send_text', 'Sprechername als Textnachricht in den Kanal', 'bool'),
    F('text_template', 'Text-Vorlage', 'text', { help: 'Platzhalter: {name} {callsign} {source} {detail}' }),
    F('rx_timeout_ms', 'Ende-Erkennung ohne stop_stream (ms)', 'number'),
    F('rx_gain_db', 'Pegel Zello → Bridge (dB)', 'number', { step: 0.5 }), F('tx_gain_db', 'Pegel Bridge → Zello (dB)', 'number', { step: 0.5 }),
  ] },
  vocoder: { title: '🎛️ Vocoder', custom: renderVocoder },
  ids: { title: '🗂️ ID-Listen & Avatare', custom: renderIds },
  appearance: { title: '🎨 Aussehen', custom: renderAppearance },
  backup: { title: '💾 Backup & Neuanfang', custom: renderBackup },
  users: { title: '👥 Benutzer', custom: () => accessView('users') },
  sessions: { title: '🔑 Sitzungen', custom: () => accessView('sessions') },
  audit: { title: '📜 Protokoll', custom: () => accessView('audit') },
  ports: { title: '🔌 Ports', custom: renderPorts },
  domains: { title: '🔒 Domains & HTTPS', custom: renderDomains },
  system: { title: '🛠️ Bridge & Ereignisse', custom: renderSystem },
  'sys-update': { title: '⬆️ Update', custom: () => sysView('update') },
  'sys-services': { title: '🧩 Dienste', custom: () => sysView('services') },
  'sys-perms': { title: '🔐 Berechtigungen & sudo', custom: () => sysView('perms') },
  'sys-keepalive': { title: '💓 Keep-Alive', custom: () => sysView('keepalive') },
  'sys-crashes': { title: '💥 Abstürze', custom: () => sysView('crashes') },
};
// Admin-Menü: derselbe Baum wie in allen N8-Systemen (N8 Kit) – Betrieb · Benutzer & Zugang · Darstellung · Netz & Domains · System
const ADMIN_GROUPS = [['betrieb', ['general', 'routes', 'audio', 'frn', 'dmr', 'zello', 'vocoder', 'ids']], ['zugang', ['users', 'sessions', 'audit']], ['darstellung', ['appearance']],
  ['netz', ['ports', 'domains']], ['system', ['system', 'sys-update', 'sys-services', 'sys-perms', 'sys-keepalive', 'sys-crashes', 'backup']]];
const ADMIN_OLD = { update: 'sys-update' };
// System → Update, Dienste, Berechtigungen & sudo, Keep-Alive: die N8-Kit-Ansichten, in allen N8-Systemen gleich
function sysView(name) {
  const el = $('#adminBody'); el.classList.remove('card');
  return N8Kit.sys.view(el, name, {
    req: (m, u, b) => api(u, m === 'GET' ? {} : { method: m, body: b || {} }), console: 'sudo /opt/n8crosslink/scripts/n8-admin.sh',
    update: { load: async (force) => { if (force) await api('/api/admin/update/check', { method: 'POST' }); return kitUpdate(await api('/api/admin/update')); },
              onInstall: () => startUpdate() },
    onAck: crashAcked,
  });
}
// Abstürze: Hinweisfenster nach der Anmeldung (N8 Kit), Zähler im Admin-Menü
async function checkCrashes(force) {
  const d = await N8Kit.sys.crashPopup({ req: (m, u, b) => api(u, m === 'GET' ? {} : { method: m, body: b || {} }), force, onAck: crashAcked,
    open: () => { S.adminSec = 'sys-crashes'; showTab('admin'); } });
  const n = d ? d.unacked || 0 : 0;
  if (n !== (S.crashNew || 0)) { S.crashNew = n; if (!$('#tab-admin')?.classList.contains('hidden') && S.me?.user) loadAdmin(); }
}
function crashAcked() { if (S.crashNew) { S.crashNew = 0; if (!$('#tab-admin')?.classList.contains('hidden')) loadAdmin(); } }

async function loadAdmin() {
  if (!S.me?.user) return;
  try { S.cfg = (await api('/api/admin/config')).config; } catch (e) { toast(e.message); return; }
  S.adminSec = ADMIN_OLD[S.adminSec] || S.adminSec;
  if (!SCHEMA[S.adminSec]) S.adminSec = 'general';
  N8Kit.nav.tree($('#adminNav'), ADMIN_GROUPS.map(([g, ids]) => ({ id: g, label: N8Kit.nav.GROUPS[g], items: ids.map(id => ({ id, label: SCHEMA[id].title,
      ...(id === 'sys-crashes' && S.crashNew ? { badge: String(S.crashNew), badgeClass: 'bad' } : {}) })) })),
    { active: S.adminSec, key: 'n8x-admin', onSelect: id => { S.adminSec = id; loadAdmin(); } });
  $('#adminBody').classList.add('card'); $('#adminBody').classList.remove('n8-sys');
  const sec = SCHEMA[S.adminSec];
  if (sec.custom) return sec.custom();
  renderForm(S.adminSec, sec.fields, sec.extra || '');
  if (S.adminSec === 'frn') { initRoomPick();
    $('#frnPwBtn').onclick = requestFrnPassword; $('#frnElReload').onclick = () => loadFrnErrorlog(true); loadFrnErrorlog(); }
  if (S.adminSec === 'general') $('#annBtn').onclick = previewAnnounce;
}

// FRN: Raum-Auswahl aus der Raumliste des Servers (live · Dashboard · kurze Anmeldung)
const ROOM_OTHER = '__other__';
function initRoomPick() {
  const sel = $('#f_frn_net'); if (!sel) return;
  $('#frnRoomsBtn').onclick = () => loadRooms(true);
  sel.onchange = () => {
    if (sel.value !== ROOM_OTHER) return;
    const cur = sel.dataset.prev || '';
    const v = (prompt('Name des Raums (genau wie auf dem FRN-Server):', cur) || '').trim();
    if (v && ![...sel.options].some(o => o.value === v)) sel.insertBefore(new Option(v + '  (eigene Eingabe)', v), sel.querySelector(`option[value="${ROOM_OTHER}"]`));
    sel.value = v || cur;
  };
  sel.onfocus = () => { if (sel.value !== ROOM_OTHER) sel.dataset.prev = sel.value; };
  ['#f_frn_server', '#f_frn_port'].forEach(q => { const el = $(q); if (el) el.addEventListener('change', () => loadRooms(true)); });
  loadRooms(false);
}
async function loadRooms(manual) {
  const sel = $('#f_frn_net'), note = $('#frnRoomsNote'), btn = $('#frnRoomsBtn'); if (!sel) return;
  const cur = sel.value, server = ($('#f_frn_server')?.value || '').trim(), port = ($('#f_frn_port')?.value || '').trim();
  note.textContent = 'Räume werden ausgelesen …'; note.className = 'room-note'; btn.disabled = true;
  try {
    const d = await api(`/api/admin/frn/rooms?server=${encodeURIComponent(server)}&port=${encodeURIComponent(port)}`);
    if ($('#f_frn_net') !== sel) return;
    const rooms = d.rooms || [];
    const names = rooms.map(r => r.name);
    const opts = rooms.map(r => [r.name, r.name + (r.clients != null ? `  · ${r.clients} ${r.clients === 1 ? 'Station' : 'Stationen'}` : '')]);
    if (cur && !names.includes(cur)) opts.unshift([cur, cur + (rooms.length ? '  (nicht in der Liste)' : '')]);
    if (!opts.length) opts.push(['', '– Raum wählen –']);
    sel.innerHTML = opts.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('') + `<option value="${ROOM_OTHER}">✏️ Anderer Raum …</option>`;
    sel.value = cur || opts[0][0];
    note.textContent = rooms.length ? `${rooms.length} ${rooms.length === 1 ? 'Raum' : 'Räume'} ${d.note || ''}` : (d.note || 'Keine Räume gefunden');
    note.className = 'room-note ' + (rooms.length ? 'ok' : 'warn');
    if (manual && rooms.length) toast(`🔄 ${rooms.length} Räume ausgelesen`);
  } catch (e) { note.textContent = '⚠️ ' + e.message; note.className = 'room-note warn'; }
  finally { btn.disabled = false; }
}

function fieldHtml(sec, f, val) {
  const id = `f_${sec}_${f.key}`, help = f.help ? `<small>${esc(f.help)}</small>` : '';
  if (f.type === 'bool') return `<div class="field ${f.wide ? 'wide' : ''}"><label class="switch"><input type="checkbox" id="${id}" ${val ? 'checked' : ''}><span></span>${esc(f.label)}</label>${help}</div>`;
  let input;
  if (f.type === 'room') input = `<div class="room-pick"><select id="${id}"><option value="${esc(val)}" selected>${esc(val || '– Raum wählen –')}</option></select>
    <button class="btn secondary" type="button" id="frnRoomsBtn" title="Räume vom FRN-Server auslesen">🔄</button></div><small id="frnRoomsNote" class="room-note">Räume werden ausgelesen …</small>`;
  else if (f.type === 'select') input = `<select id="${id}">${f.options.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(val) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
  else if (f.type === 'textarea') input = `<textarea id="${id}" placeholder="${val === '********' ? 'gesetzt – leer lassen = unverändert' : ''}">${val === '********' ? '' : esc(val)}</textarea>`;
  else if (f.type === 'json') input = `<textarea id="${id}">${esc(JSON.stringify(val, null, 2))}</textarea>`;
  else if (f.type === 'password') input = `<input type="password" id="${id}" autocomplete="new-password" placeholder="${val ? 'gesetzt – leer lassen = unverändert' : ''}">`;
  else input = `<input type="${f.type === 'number' ? 'number' : 'text'}" ${f.step ? `step="${f.step}"` : f.type === 'number' ? 'step="any"' : ''} id="${id}" value="${esc(val)}">`;
  return `<div class="field ${f.wide ? 'wide' : ''}"><label for="${id}">${esc(f.label)}</label>${input}${help}</div>`;
}
function readField(sec, f) {
  const el = $(`#f_${sec}_${f.key}`); if (!el) return undefined;
  if (f.type === 'bool') return el.checked;
  if (f.type === 'room' && el.value === ROOM_OTHER) return el.dataset.prev || '';
  if (f.type === 'json') { try { return JSON.parse(el.value); } catch { throw new Error(f.label + ': ungültiges JSON'); } }
  return el.value;
}
function renderForm(sec, fields, extraTop = '') {
  const c = S.cfg[sec];
  $('#adminBody').innerHTML = `${extraTop}<div class="form">${fields.map(f => fieldHtml(sec, f, c[f.key])).join('')}</div>
    <div class="form-actions"><button class="btn" id="saveBtn">💾 Speichern</button></div>`;
  $('#saveBtn').onclick = () => saveSection(sec, fields);
}
async function saveSection(sec, fields, extra = {}) {
  try {
    const vals = { ...extra };
    for (const f of fields) vals[f.key] = readField(sec, f);
    const r = await api('/api/admin/config', { method: 'POST', body: { [sec]: vals } });
    toast('✅ Gespeichert');
    if (r.restart_required) $('#restartBanner').hidden = false;
    loadInfo();
  } catch (e) { toast('⚠️ ' + e.message); }
}
$('#restartNowBtn').addEventListener('click', async () => {
  await api('/api/admin/restart', { method: 'POST' }); $('#restartBanner').hidden = true; toast('🔄 Bridge startet neu …');
});

function renderRoutes() {
  const r = S.cfg.routes;
  const cells = ORDER.map(src => `<div class="rl">${badge(src)} →</div>` + ORDER.map(dst => src === dst ? '<div class="cell" style="color:var(--text-dim)">—</div>' :
    `<div class="cell"><label class="switch"><input type="checkbox" id="r_${src}_${dst}" ${r[src + '_' + dst] ? 'checked' : ''}><span></span></label></div>`).join('')).join('');
  $('#adminBody').innerHTML = `<p style="padding:10px 4px 0;color:var(--text-dim);font-size:13px">Welche Quelle wird in welches Netz übertragen? Änderungen wirken sofort.</p>
    <div class="route-matrix"><div></div>${ORDER.map(k => `<div class="rh">${NET[k].label}</div>`).join('')}${cells}</div>
    <div class="form-actions"><button class="btn" id="saveBtn">💾 Speichern</button></div>`;
  $('#saveBtn').onclick = async () => {
    const vals = {}; for (const s of ORDER) for (const d of ORDER) if (s !== d) vals[s + '_' + d] = $(`#r_${s}_${d}`).checked;
    await api('/api/admin/config', { method: 'POST', body: { routes: vals } }); toast('✅ Routing gespeichert');
  };
}

function renderVocoder() {
  const c = S.cfg.vocoder, mode = c.vocoder_mode;
  const opts = [
    ['n8vocoder', '🧠 N8schicht-Vocoder (Software)', 'AMBE+2 in Software – Fork des DroidStar-Codecs, auf Verständlichkeit abgestimmt. Ohne Zusatzhardware und ohne qemu; läuft als eigener Prozess (x86 und ARM).'],
    ['usb', '🔌 USB-Stick (AMBE3000)', 'ThumbDV, DVstick 30, DV3000 direkt per USB/seriell. Beste Qualität, kein Zusatzdienst nötig.'],
    ['ambeserver', '🌐 AMBEserver (Netz)', 'AMBE3000 an einem anderen Rechner hinter AMBEserver (UDP 2460).'],
    ['none', '🧪 Test ohne Vocoder', 'Nur zum Testen der Verbindungen – DMR-Audio ist dann stumm.'],
  ];
  const fields = {
    n8vocoder: [F('n8vocoder_lib', 'Bibliothek (leer = automatisch)', 'text', { help: 'Standard: /opt/n8crosslink/lib/libn8vocoder.so' })],
    usb: [F('usb_device', 'Gerät', 'text', { help: 'z. B. /dev/ttyUSB0 oder /dev/serial/by-id/…' }),
      F('usb_baud', 'Baudrate', 'select', { options: [[460800, '460800 (ThumbDV / DVstick 30)'], [230400, '230400 (DV3000 Pi-Hat)'], [921600, '921600']] }),
      F('usb_send_init', 'Init-Pakete (Reset/Rate) senden', 'bool')],
    ambeserver: [F('ambeserver_host', 'AMBEserver Adresse'), F('ambeserver_port', 'AMBEserver Port', 'number'), F('ambeserver_send_init', 'Init-Pakete senden', 'bool')],
    none: [],
  };
  const sel = window._vocSel || (fields[mode] ? mode : 'n8vocoder');
  const common = [F('vocoder_enc_gain_db', 'Pegel vor dem Kodieren (dB)', 'number', { step: 0.5 }), F('vocoder_dec_gain_db', 'Pegel nach dem Dekodieren (dB)', 'number', { step: 0.5 }),
    ...(sel === 'usb' || sel === 'ambeserver' ? [F('vocoder_timeout_ms', 'Antwortzeit je Rahmen (ms)', 'number')] : []),
    F('vocoder_restart_s', 'Watchdog: neu öffnen nach (s) ohne Antwort', 'number')];
  const flds = [...fields[sel], ...common];
  const v = S.state?.vocoder;
  $('#adminBody').innerHTML = `<div class="voc-choice">${opts.map(([k, t, d]) => `<div class="voc-opt ${k === sel ? 'active' : ''}" data-m="${k}"><b>${t}${k === mode ? ' · aktiv' : ''}</b><small>${d}</small>${k === 'n8vocoder' ? '<button class="btn secondary" type="button" id="vocTuneBtn" style="margin-top:8px">🎚️ Klang-Einstellungen</button>' : ''}</div>`).join('')}</div>
    <div class="form">${flds.map(f => fieldHtml('vocoder', f, c[f.key])).join('')}
      <div class="field wide"><label>Aktueller Zustand</label><div>${v ? `${v.online ? '<span class="badge ok">bereit</span>' : '<span class="badge off">offline</span>'} ${esc(v.name)} ${esc(v.product || '')} ${esc(v.version || '')} · Encode ${v.enc} · Decode ${v.dec} · Timeouts ${v.timeouts} · Wiederholt ${v.retries ?? 0} · Neu geöffnet ${v.reopens ?? 0}` : '<span class="badge warn">nicht gestartet</span>'}</div>
      <small id="vocTestRes"></small></div></div>
    <pre id="mdOut" style="font-size:11.5px;white-space:pre-wrap;color:var(--text-dim);padding:0 4px"></pre>
    <div class="form-actions">${sel === 'usb' ? '<button class="btn secondary" id="scanBtn">🔍 USB-Geräte suchen</button>' : ''}
      ${sel === 'n8vocoder' ? '<button class="btn secondary" id="mdBtn">🔨 Vocoder bauen / aktualisieren</button>' : ''}
      <button class="btn secondary" id="vocTestBtn">🧪 Vocoder testen</button><button class="btn" id="saveBtn">💾 Speichern &amp; neu starten</button></div>`;
  $$('.voc-opt').forEach(o => o.onclick = (ev) => { if (ev.target.id === 'vocTuneBtn') return; window._vocSel = o.dataset.m; renderVocoder(); });
  if ($('#vocTuneBtn')) $('#vocTuneBtn').onclick = (ev) => { ev.stopPropagation(); openVocTune(); };
  $('#saveBtn').onclick = async () => {
    await saveSection('vocoder', flds, { vocoder_mode: sel });
    await api('/api/admin/restart', { method: 'POST' }); $('#restartBanner').hidden = true;
    window._vocSel = null; toast('🔄 Vocoder gespeichert, Bridge startet neu …'); setTimeout(loadAdmin, 2500);
  };
  if ($('#mdBtn')) $('#mdBtn').onclick = async () => {
    if (!confirm('N8schicht-Vocoder jetzt aus den mitgelieferten Quellen neu bauen? (Compiler wird bei Bedarf installiert, Funktionstest – dauert ca. 1–5 Minuten)')) return;
    $('#mdOut').textContent = 'baue … (bitte warten)';
    try { const r = await api('/api/admin/vocoder/build', { method: 'POST' }); $('#mdOut').textContent = r.message; toast(r.ok ? '✅ N8schicht-Vocoder bereit' : '⚠️ siehe Ausgabe');
      if (r.ok) { await api('/api/admin/restart', { method: 'POST' }); } }
    catch (e) { $('#mdOut').textContent = '⚠️ ' + e.message; }
  };
  $('#vocTestBtn').onclick = async () => {
    $('#vocTestRes').textContent = 'teste …';
    try { const r = await api('/api/admin/vocoder-test', { method: 'POST' }); $('#vocTestRes').textContent = (r.ok ? '✅ ' : '⚠️ ') + r.message; }
    catch (e) { $('#vocTestRes').textContent = '⚠️ ' + e.message; }
  };
  if ($('#scanBtn')) $('#scanBtn').onclick = async () => {
    const l = await api('/api/admin/serial-ports'); toast(l.length ? 'Gefunden: ' + l.join(', ') : 'Kein USB-Seriell-Gerät gefunden');
    if (l.length) $('#f_vocoder_usb_device').value = l.find(x => x.includes('by-id')) || l[0];
  };
}

// 👥 Benutzer & 🔑 Sitzungen – die Ansichten des N8 Kit nach dem Vorbild von HBlink4-FreeRadioID, gleich in allen N8-Systemen
function accessView(name) {
  const el = $('#adminBody'); el.classList.remove('card');
  return N8Kit.access.view(el, name, {
    req: (m, u, b) => api(u, m === 'GET' ? {} : { method: m, body: b || {} }), me: { username: S.me.user, role: S.me.role || 'admin' },
    roles: [{ id: 'superadmin', label: 'Superadmin', assign: 'superadmin' }, { id: 'admin', label: 'Admin', assign: 'all' }],
    fields: ['display_name'], toast: (m, bad) => toast((bad ? '⚠️ ' : '✅ ') + m),
    intro: 'Wer sich am Adminbereich anmelden darf. Superadmins dürfen zusätzlich Backups wiederherstellen, alles zurücksetzen und andere Superadmins verwalten.',
    locked: (u, me) => u.username === me.username ? '' : (u.role === 'superadmin' && me.role !== 'superadmin' ? 'nur Superadmin' : ''),
    openSelf: name === 'users' && S.openSelf ? (S.openSelf = false, true) : false,
    onSelfPassword: () => { if (S.me.role === 'superadmin') toast('🔐 Neue Backups verschlüsselt jetzt das neue Passwort. Ältere Backups öffnest du weiter mit dem alten Passwort.'); loadMe(); },
  });
}

// ---------------------------------------------------------------- 🔌 Ports – alles an einer Stelle (wie „HTTPS & web“ bei HBlink4)
async function renderPorts() {
  let d; try { d = await api('/api/admin/ports'); } catch (e) { $('#adminBody').innerHTML = `<div class="empty">⚠️ ${esc(e.message)}</div>`; return; }
  const v = d.values;
  const row = (key, label, dir, proto, help, min = 1) => `<tr><td><b>${esc(label)}</b><div class="lh-name">${help}</div></td>
      <td><span class="badge ${dir === 'ein' ? 'warn' : ''}">${dir === 'ein' ? '⬇ eingehend' : '⬆ ausgehend'}</span> <span class="badge">${proto}</span></td>
      <td class="num"><input type="number" class="pt-in" data-k="${key}" min="${min}" max="65535" value="${esc(v[key] ?? '')}"></td></tr>`;
  const zport = (() => { try { const u = new URL(d.zello_server); return u.port || (u.protocol === 'wss:' ? '443' : '80'); } catch (e) { return '443'; } })();
  const restartNote = d.running.web_port !== v['general.web_port'] || d.running.web_host !== v['general.web_host']
    ? `<div class="banner">♻️ <span class="grow">Gespeichert, aber noch nicht aktiv: Das Webinterface läuft noch auf ${esc(d.running.web_host)}:${esc(d.running.web_port)}. Dienst neu starten, damit ${esc(v['general.web_host'])}:${esc(v['general.web_port'])} gilt.</span><button class="btn" id="ptSvc">♻️ Dienst neu starten</button></div>` : '';
  $('#adminBody').innerHTML = `<h2 class="section-header">🔌 Ports</h2>
    <p style="padding:0 4px;color:var(--text-dim);font-size:13px">Alle Ports von N8 Crosslink an einer Stelle. <b>Eingehend</b> heißt: in Firewall/Router freigeben, wenn von außen erreichbar sein soll. <b>Ausgehend</b>: die Gegenstelle muss erreichbar sein. Gespeichert wird alles mit einem Knopf; was einen Neustart braucht, steht danach oben.</p>
    ${restartNote}
    <h2 class="section-header">🌐 Webinterface</h2>
    <div class="card"><table class="tbl"><tbody>
      <tr><td><b>Web-Adresse (Bind)</b><div class="lh-name">0.0.0.0 = alle Schnittstellen (IPv4) · :: = alle (IPv4 und IPv6) · 127.0.0.1 = nur dieser Rechner (dann nur über die Domain)</div></td>
        <td><span class="badge warn">⬇ eingehend</span></td><td class="num"><input type="text" class="pt-in" data-k="general.web_host" value="${esc(v['general.web_host'] || '0.0.0.0')}" style="width:150px"></td></tr>
      ${row('general.web_port', 'Web-Port', 'ein', 'TCP', 'Webinterface und Live-Daten (http://IP:Port). Unter 1024 (z. B. 80) geht ohne root – nginx braucht dann andere Ports. Neustart des Dienstes.')}
    </tbody></table></div>
    <h2 class="section-header">🔒 Domains &amp; HTTPS (nginx)</h2>
    <div class="card"><table class="tbl"><tbody>
      ${row('https.http_port', 'HTTP-Port', 'ein', 'TCP', 'http:// der Domains und Let\'s-Encrypt-Prüfung. Let\'s Encrypt kommt immer auf Port 80 – ein anderer Port nur mit Weiterleitung im Router (außen 80 → innen dieser Port).')}
      ${row('https.https_port', 'HTTPS-Port', 'ein', 'TCP', 'https:// der Domains (Standard 443; sonst https://domain:Port). Wird sofort auf alle Domains angewandt.')}
    </tbody></table></div>
    <h2 class="section-header">📻 FRN · 📡 DMR · 🎛️ Vocoder · 💬 Zello</h2>
    <div class="card"><table class="tbl"><tbody>
      ${row('frn.port', 'FRN-Server-Port', 'aus', 'TCP', `zu ${esc(d.frn_server || '–')} (Standard 10024)`)}
      ${row('frn.backup_port', 'FRN-Backup-Port', 'aus', 'TCP', 'zum Backup-Server, falls eingetragen')}
      ${row('frn.sysman_port', 'FRN-System-Manager-Port', 'aus', 'TCP', 'Anmeldung/Passwort beim SystemManager (Standard 10025)')}
      ${row('dmr.port', 'DMR-Server-Port', 'aus', 'UDP', `zu ${esc(d.dmr_host || '–')} (HBlink4/FreeDMR, Standard 62031)`)}
      ${row('dmr.local_port', 'DMR – eigener UDP-Port', 'aus', 'UDP', 'Absender-Port der Brücke · 0 = beliebig (Standard) · fest für Firewall-Regeln oder NAT', 0)}
      ${row('vocoder.ambeserver_port', 'AMBEserver-Port', 'aus', 'UDP', `nur Betriebsart AMBEserver (${esc(d.ambeserver_host || '127.0.0.1')}, Standard 2460)${d.vocoder_mode === 'ambeserver' ? '' : ' – gerade nicht in Gebrauch'}`)}
      <tr><td><b>Zello</b><div class="lh-name">WebSocket ${esc(d.zello_server || '–')} – Port steht in der Adresse (💬 Zello)</div></td><td><span class="badge">⬆ ausgehend</span> <span class="badge">TCP</span></td><td class="num"><code>${esc(zport)}</code></td></tr>
    </tbody></table></div>
    <div class="form-actions" style="justify-content:flex-start"><button class="btn" id="ptSave">💾 Ports speichern</button></div>
    <pre id="ptOut" style="font-size:11.5px;white-space:pre-wrap;color:var(--text-dim);padding:0 4px"></pre>`;
  if ($('#ptSvc')) $('#ptSvc').onclick = async () => { await api('/api/admin/service-restart', { method: 'POST' }); toast('♻️ Dienst startet neu – danach unter der neuen Adresse öffnen'); };
  $('#ptSave').onclick = async (e) => {
    const body = {};
    $$('.pt-in').forEach(i => { body[i.dataset.k] = i.type === 'number' ? Number(i.value) : i.value.trim(); });
    e.target.disabled = true;
    try {
      const r = await api('/api/admin/ports', { method: 'POST', body });
      const lines = [r.changed && r.changed.length ? 'Geändert: ' + r.changed.join(', ') : (r.message || 'Nichts geändert')];
      if (r.nginx) lines.push('nginx: ' + (r.nginx.message || ''));
      if (r.restart_bridge) { lines.push('FRN/DMR/Vocoder: gilt nach einem Neustart der Brücke.'); $('#restartBanner').hidden = false; }
      $('#ptOut').textContent = lines.join('\n'); toast('✅ Ports gespeichert');
      if (r.restart_service) renderPorts();
    } catch (err) { toast('⚠️ ' + err.message); }
    e.target.disabled = false;
  };
}

// ---------------------------------------------------------------- Domains & HTTPS (Let's Encrypt)
async function renderDomains() {
  $('#adminBody').innerHTML = '<div class="empty">Lade Domains …</div>';
  let d;
  try { d = await api('/api/admin/domains'); } catch (e) { $('#adminBody').innerHTML = `<div class="empty">⚠️ ${esc(e.message)}</div>`; return; }
  const set = d.settings || {};
  const days = c => c && c.days != null ? (c.days < 0 ? 'abgelaufen' : `noch ${c.days} Tage`) : '';
  const certBadge = s => !s.cert ? '<span class="badge warn">kein Zertifikat</span>'
    : s.cert.staging ? '<span class="badge warn">Test-Zertifikat</span>'
    : s.cert.days != null && s.cert.days < 14 ? `<span class="badge off">${esc(days(s.cert))}</span>` : `<span class="badge ok">gültig · ${esc(days(s.cert))}</span>`;
  const conflict = [Number(d.http_port || 80), Number(d.https_port || 443)].includes(Number(d.web_port));
  const deps = d.nginx && d.certbot;
  const hint = d.missing ? `<div class="banner">⚠️ <span class="grow">${esc(d.message)}</span></div>`
    : !d.ok ? `<div class="banner">⚠️ <span class="grow">${esc(d.message || 'Status nicht lesbar')}</span></div>`
    : conflict ? `<div class="banner">⚠️ <span class="grow">N8 Crosslink lauscht selbst auf Port ${esc(d.web_port)}, den nginx für HTTP/HTTPS braucht – unter <b>🔌 Ports</b> den Web-Port (z. B. 8070) oder die nginx-Ports ändern.</span></div>`
    : !deps ? `<div class="banner">📦 <span class="grow">Für Let's Encrypt braucht es <b>nginx</b> und <b>certbot</b> auf diesem Rechner.</span><button class="btn" id="dmDeps">📦 Benötigte Pakete installieren</button></div>`
    : d.port80 && d.port80 !== 'nginx' ? `<div class="banner">⚠️ <span class="grow">Port ${esc(d.http_port || 80)} belegt <b>${esc(d.port80)}</b> – nginx kann dort nicht lauschen. Let's Encrypt prüft die Domain über Port 80.</span></div>` : '';
  const rows = (d.sites || []).map(s => `<tr><td><b>${esc(s.domain)}</b>${s.legacy ? ' <span class="badge">vom Installer</span>' : ''}
      <div class="lh-name">${s.dns && s.dns.length ? 'DNS: ' + s.dns.map(esc).join(', ') : '⚠️ DNS: kein Eintrag gefunden'} · Ports ${esc((s.listen || []).join('/'))} → 127.0.0.1:${esc(s.upstream || '?')}${s.ports_ok === false ? ' · <b style="color:#ffd60a">passt nicht zu den Ports</b>' : ''}</div></td>
      <td>${s.https ? '<span class="badge ok">HTTPS</span>' : '<span class="badge warn">nur HTTP</span>'} ${certBadge(s)}
        ${s.cert ? `<div class="lh-name">${esc(s.cert.issuer || '')} · bis ${esc(s.cert.expires || '')}</div>` : ''}</td>
      <td class="num"><a class="btn secondary" href="https://${esc(s.domain)}/" target="_blank" rel="noopener">↗</a>
        ${s.cert ? `<button class="btn secondary" data-renew="${esc(s.domain)}">🔄 Erneuern</button>` : `<button class="btn secondary" data-retry="${esc(s.domain)}">🔒 Zertifikat holen</button>`}
        <button class="btn secondary" data-rm="${esc(s.domain)}">Entfernen</button></td></tr>`).join('');
  const anyHttps = (d.sites || []).some(s => s.https);
  const mismatch = (d.sites || []).some(s => s.ports_ok === false);
  $('#adminBody').innerHTML = `<h2 class="section-header">🔒 Domains &amp; HTTPS ${d.renew_timer ? '<span class="badge ok">automatische Erneuerung an</span>' : deps ? '<span class="badge warn">Erneuerung nicht geplant</span>' : ''}</h2>
    <p style="padding:0 4px;color:var(--text-dim);font-size:13px">Eigene Domains für dieses Webinterface mit kostenlosem Zertifikat von <b>Let's Encrypt</b>. nginx nimmt die Domain auf Port ${esc(d.http_port || 80)}/${esc(d.https_port || 443)} an und leitet zu N8 Crosslink (127.0.0.1:${esc(d.web_port)}) weiter; certbot holt das Zertifikat und erneuert es automatisch rechtzeitig vor Ablauf. Voraussetzung: Die Domain zeigt per DNS auf diesen Server und Port 80 (Let's Encrypt prüft immer dort – sonst Weiterleitung im Router) und ${esc(d.https_port || 443)} sind aus dem Internet erreichbar.</p>
    ${hint}
    <p style="padding:0 4px;color:var(--text-dim);font-size:13px">nginx lauscht auf <b>HTTP ${esc(d.http_port || 80)}</b> und <b>HTTPS ${esc(d.https_port || 443)}</b> und leitet zu 127.0.0.1:${esc(d.web_port)} – ändern unter <a href="#" id="dmPorts">🔌 Ports</a>.</p>
    ${mismatch ? `<div class="banner warn">⚠️ <span class="grow">Mindestens eine Domain nutzt noch andere Ports als eingestellt.</span><button class="btn" id="dmApply">🔁 Ports auf alle Domains anwenden</button></div>` : ''}
    <div class="card">${rows ? `<table class="tbl"><thead><tr><th>Domain</th><th>Zertifikat</th><th></th></tr></thead><tbody>${rows}</tbody></table>` : '<div class="empty">Noch keine Domain.</div>'}</div>
    <h2 class="section-header">➕ Domain hinzufügen</h2>
    <div class="form"><div class="field"><label>Domain</label><input type="text" id="dmName" placeholder="crosslink.example.org" autocomplete="off"></div>
      <div class="field"><label>E-Mail für Let's Encrypt</label><input type="text" inputmode="email" id="dmMail" value="${esc(set.email || '')}" placeholder="sysop@example.org" autocomplete="email"><small>Für Hinweise zum Ablauf des Zertifikats</small></div>
      <div class="field wide"><label class="switch"><input type="checkbox" id="dmStaging" ${set.staging ? 'checked' : ''}><span></span>Test-Zertifikat (Let's-Encrypt-Staging, zum Ausprobieren ohne Limits)</label></div></div>
    <div class="form-actions" style="justify-content:flex-start"><button class="btn" id="dmAdd" ${!d.ok || conflict || !deps ? 'disabled' : ''}>🔒 Domain anlegen &amp; Zertifikat holen</button></div>
    <pre id="dmOut" style="font-size:11.5px;white-space:pre-wrap;color:var(--text-dim);padding:0 4px"></pre>
    ${anyHttps ? `<h2 class="section-header">🛡️ Nur noch über HTTPS</h2><div class="form"><div class="field wide"><label class="switch"><input type="checkbox" id="dmLocal" ${d.web_host === '127.0.0.1' ? 'checked' : ''}><span></span>Webinterface nur noch über die Domain erreichbar (lauscht auf 127.0.0.1 statt allen Schnittstellen)</label>
      <small>Danach ist http://IP:${esc(d.web_port)} von außen zu. Der Dienst startet dafür neu.</small></div></div>` : ''}`;
  const out = (r) => { $('#dmOut').textContent = (r.message || '') + (r.log ? '\n\n' + r.log : ''); toast((r.ok ? '✅ ' : '⚠️ ') + (r.message || '')); };
  const busy = (b, t) => { b.disabled = true; b.textContent = t; $('#dmOut').textContent = 'Läuft – das kann bis zu einer Minute dauern …'; };
  $('#dmPorts').onclick = (e) => { e.preventDefault(); S.adminSec = 'ports'; loadAdmin(); };
  if ($('#dmApply')) $('#dmApply').onclick = async (e) => { busy(e.target, '🔁 …'); out(await api('/api/admin/ports/apply', { method: 'POST' })); renderDomains(); };
  if ($('#dmDeps')) $('#dmDeps').onclick = async (e) => { busy(e.target, '📦 Installiere …'); out(await api('/api/admin/domains/deps', { method: 'POST' })); renderDomains(); };
  const add = async (domain, btn) => {
    const email = $('#dmMail').value.trim();
    if (!email) { toast('⚠️ Bitte die E-Mail für Let\'s Encrypt eintragen'); $('#dmMail').focus(); return; }
    busy(btn, '🔒 Hole Zertifikat …');
    try { out(await api('/api/admin/domains', { method: 'POST', body: { domain, email, staging: $('#dmStaging').checked } })); } catch (e) { toast('⚠️ ' + e.message); }
    renderDomains();
  };
  $('#dmAdd').onclick = (e) => { const v = $('#dmName').value.trim(); if (!v) { $('#dmName').focus(); return; } add(v, e.target); };
  $$('[data-retry]').forEach(b => b.onclick = () => add(b.dataset.retry, b));
  $$('[data-renew]').forEach(b => b.onclick = async () => { busy(b, '🔄 …'); out(await api(`/api/admin/domains/${encodeURIComponent(b.dataset.renew)}/renew`, { method: 'POST' })); renderDomains(); });
  $$('[data-rm]').forEach(b => b.onclick = async () => {
    if (!confirm(`${b.dataset.rm} entfernen? Weiterleitung und Zertifikat werden gelöscht.`)) return;
    out(await api(`/api/admin/domains/${encodeURIComponent(b.dataset.rm)}`, { method: 'DELETE' })); renderDomains();
  });
  if ($('#dmLocal')) $('#dmLocal').onchange = async (e) => {
    const on = e.target.checked;
    if (!confirm(on ? 'Webinterface nur noch über die Domain erreichbar machen? Der Dienst startet neu.' : 'Webinterface wieder an allen Schnittstellen öffnen? Der Dienst startet neu.')) { e.target.checked = !on; return; }
    await api('/api/admin/domains/local-only', { method: 'POST', body: { on } }); toast('♻️ Dienst startet neu …');
  };
}

async function renderSystem() {
  const [ev, sy] = await Promise.all([api('/api/admin/events?limit=150'), api('/api/admin/system')]);
  $('#adminBody').innerHTML = `<h2 class="section-header">Bridge</h2>
    <div class="form-actions" style="justify-content:flex-start">
      <button class="btn" id="sysRestart">🔄 Bridge neu starten</button>
      <button class="btn secondary" id="sysSvc">♻️ Dienst neu starten</button>
      <button class="btn secondary" id="sysUdb">🗂️ ID-Listen aktualisieren</button>
      <a class="btn secondary" href="/api/admin/export">⬇️ Konfiguration exportieren</a>
      <label class="btn secondary" style="cursor:pointer">⬆️ Importieren<input type="file" id="sysImp" accept=".json" hidden></label>
      ${sy.reboot ? `<button class="btn danger" id="sysReboot" ${sy.sudo ? '' : 'disabled'}>⏻ Server neu starten</button>` : ''}</div>
    <h2 class="section-header">Ereignisprotokoll</h2>
    <div class="ev-list">${ev.map(e => `<div class="ev-row ${e.level === 'warn' ? 'warn' : ''}"><time>${new Date(e.ts * 1000).toLocaleString(N8Kit.locale())}</time><div>${esc(e.text)}</div></div>`).join('') || '<div class="empty">Leer.</div>'}</div>`;
  if ($('#sysReboot')) $('#sysReboot').onclick = async () => { if (!confirm('Den ganzen Server jetzt neu starten?')) return; const r = await api('/api/admin/system/reboot', { method: 'POST' }); toast(r.message); };
  $('#sysRestart').onclick = async () => { await api('/api/admin/restart', { method: 'POST' }); toast('🔄 Bridge startet neu …'); };
  $('#sysSvc').onclick = async () => { if (!confirm('Dienst komplett neu starten? Das Dashboard ist ein paar Sekunden weg.')) return; await api('/api/admin/service-restart', { method: 'POST' }); toast('♻️ Dienst startet neu …'); };
  $('#sysUdb').onclick = async () => { const r = await api('/api/admin/ids/update', { method: 'POST' }); toast(r.message); };
  $('#sysImp').onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try { await api('/api/admin/import', { method: 'POST', body: JSON.parse(await f.text()) }); toast('✅ Importiert'); $('#restartBanner').hidden = false; }
    catch (err) { toast('⚠️ ' + err.message); }
  };
}

const IDS_FIELDS = [
  F('subscriber_csv_url', 'FreeRadioID: alle DMR-IDs (CSV)', 'text', { wide: true }),
  F('subscriber_json_url', 'FreeRadioID: alle DMR-IDs (JSON, Ersatz)', 'text', { wide: true }),
  F('local_json_url', 'FreeRadioID: registrierte IDs (JSON)', 'text', { wide: true }),
  F('local_csv_url', 'FreeRadioID: registrierte IDs (CSV, Ersatz)', 'text', { wide: true }),
  F('user_api_url', 'FreeRadioID: Einzelabfrage unbekannter IDs ({id})', 'text', { wide: true }),
  F('radioid_fallback_url', 'Ersatzquelle RadioID.net (CSV)', 'text', { wide: true }),
  F('talkgroups_url', 'Talkgroup-Namen (JSON)', 'text', { wide: true }),
  F('avatars', 'Avatare anzeigen', 'bool'), F('only_registered', 'Nur FreeRadioID-registrierte IDs abfragen', 'bool'),
  F('match_callsign', 'FRN-/Zello-Rufzeichen → FreeRadioID-Avatar', 'bool'),
  F('avatar_url', 'Avatar-URL DMR ({id})', 'text', { wide: true }),
  F('zello_avatar_url', 'Avatar-URL Zello ({username}, optional)', 'text', { wide: true, help: 'Die Zello Channel API liefert keine Profilbilder – hier eine eigene Quelle eintragen oder unten Bilder hochladen' }),
];
async function renderIds() {
  const i = await api('/api/admin/ids'); const L = i.lists, A = i.avatars;
  const dt = (t) => t ? new Date(t * 1000).toLocaleString(N8Kit.locale()) : 'noch nie';
  const c = S.cfg.ids;
  $('#adminBody').innerHTML = `${kv([
      ['DMR-IDs', `${L.users.toLocaleString(N8Kit.locale())} · Stand ${dt(L.users_updated)}`], ['Quelle', esc(L.users_source)],
      ['Bei FreeRadioID registriert', `${L.registered.toLocaleString(N8Kit.locale())} · Stand ${dt(L.frid_updated)}`],
      ['Talkgroup-Namen', `${L.talkgroups.toLocaleString(N8Kit.locale())} · Stand ${dt(L.tg_updated)}`],
      ['Avatare im Cache', `${A.with_avatar} mit Bild (${(A.bytes / 1024).toFixed(0)} KB) · ${A.without} ohne · zuletzt aktualisiert ${dt(A.refreshed)}`],
      ['Zeitplan', 'ID-Listen und Avatare 1× täglich automatisch, sofort per Knopf']])}
    <div class="form-actions" style="justify-content:flex-start">
      <button class="btn" id="idsUpd" ${i.busy ? 'disabled' : ''}>🗂️ ID-Listen jetzt aktualisieren</button>
      <button class="btn secondary" id="avUpd" ${i.avatars_busy ? 'disabled' : ''}>🖼️ Avatare jetzt aktualisieren</button></div>
    <h2 class="section-header">Zello-Avatare (eigene Bilder)</h2>
    <div class="form"><div class="field"><label>Zello-Benutzername</label><input type="text" id="zaUser"></div>
      <div class="field"><label>Bild (PNG/JPEG/WebP/GIF)</label><input type="file" id="zaFile" accept="image/*"></div></div>
    <div class="form-actions" style="justify-content:flex-start"><button class="btn" id="zaBtn">⬆️ Hochladen</button></div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;padding:4px">${i.uploads.map(u => `<span class="badge zello" style="padding:4px 4px 4px 4px;gap:6px">${avatar('zello', u, u)} ${esc(u)} <button class="btn secondary" style="padding:2px 8px" data-zdel="${esc(u)}">✕</button></span>`).join('') || '<span style="color:var(--text-dim);font-size:13px">Noch keine eigenen Bilder.</span>'}</div>
    <h2 class="section-header">Quellen</h2>
    <div class="form">${IDS_FIELDS.map(f => fieldHtml('ids', f, c[f.key])).join('')}</div>
    <div class="form-actions"><button class="btn" id="saveBtn">💾 Speichern</button></div>`;
  $('#idsUpd').onclick = async () => { toast((await api('/api/admin/ids/update', { method: 'POST' })).message); setTimeout(renderIds, 1500); };
  $('#avUpd').onclick = async () => { toast((await api('/api/admin/avatars/refresh', { method: 'POST' })).message); setTimeout(renderIds, 1500); };
  $('#saveBtn').onclick = () => saveSection('ids', IDS_FIELDS);
  $('#zaBtn').onclick = async () => {
    const f = $('#zaFile').files[0], user = $('#zaUser').value.trim();
    if (!f || !user) return toast('Benutzername und Bild angeben');
    const b64 = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(f); });
    try { await api('/api/admin/avatars/upload', { method: 'POST', body: { username: user, image: b64 } }); toast('✅ Avatar gespeichert'); renderIds(); }
    catch (e) { toast('⚠️ ' + e.message); }
  };
  $$('[data-zdel]').forEach(b => b.onclick = async () => { await api('/api/admin/avatars/upload/' + encodeURIComponent(b.dataset.zdel), { method: 'DELETE' }); renderIds(); });
}

// N8 Kit: gleicher Hinweis, gleiche Kachel und gleicher Fortschritt wie in den anderen N8schicht-Projekten
function updNotes(t) {
  return t ? esc(t).replace(/^### (.*)$/gm, '<b>$1</b>').replace(/^## (.*)$/gm, '<h4 style="margin:8px 0 4px">$1</h4>').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\n/g, '<br>') : '';
}
function kitUpdate(u) {
  if (!u) return null;
  return { available: !!u.available, current: u.current, latest: u.latest || '', notes: updNotes(u.notes), checked: u.checked,
           can_install: !!(u.available && (u.systemd ?? true)), error: u.error || '', result: u.result || null, log: u.log || '',
           schedule: S.cfg?.general && !S.cfg.general.update_check ? 'aus' : 'stündlich zur vollen Stunde',
           reason: u.systemd === false ? 'Update-Dienst fehlt – einmal <code>sudo /opt/n8crosslink/update.sh</code> ausführen.' : '',
           extra: [['Update-Dienst', u.systemd ? '<span class="n8-badge ok">eingerichtet</span>' : '<span class="n8-badge warn">fehlt</span>']] };
}
async function startUpdate(u) {
  if (!u) { try { u = await api('/api/admin/update'); } catch (e) { toast(e.message); return; } }
  const k = kitUpdate(u);
  return N8Kit.update.run({
    from: k.current, to: k.latest, text: k.notes,
    install: async () => {
      const r = await api('/api/admin/update/now', { method: 'POST' });
      if (!r.ok) throw new Error(r.message || 'Update konnte nicht gestartet werden');
      $('#updateBanner').hidden = true;
      return r;
    },
    version: async () => (await api('/api/me')).version,
    timeout: 600000,
  });
}
function openOwnAccount() { S.openSelf = true; S.adminSec = 'users'; showTab('admin'); }
$('#pwChangeBtn')?.addEventListener('click', openOwnAccount);

$('#spOk').addEventListener('click', () => $('#statusModal').classList.remove('open'));

/* ---------- FRN: öffentliches Fehlerprotokoll (freeradionetwork.de) ---------- */
async function loadFrnErrorlog(force) {
  const box = $('#frnElList'); if (!box) return;
  box.innerHTML = '<div class="empty">lade das Fehlerprotokoll …</div>';
  let d; try { d = await api('/api/admin/frn/errorlog' + (force ? '?force=1' : '')); } catch (e) { box.innerHTML = `<div class="empty">⚠️ ${esc(e.message)}</div>`; return; }
  const n = d.mine.reduce((a, g) => a + g.count, 0);
  $('#frnElBadge').innerHTML = d.error ? '<span class="badge warn">nicht erreichbar</span>' : n ? `<span class="badge off">${n} Einträge zu dir</span>` : '<span class="badge ok">nichts zu dir</span>';
  const row = (g) => `<tr><td style="white-space:nowrap">${esc(g.ts.slice(8, 10) + '.' + g.ts.slice(5, 7) + '. ' + g.ts.slice(11, 16))}${g.count > 1 ? `<div class="lh-name">${g.count}× seit ${esc(g.first.slice(11, 16))}</div>` : ''}</td>
      <td><span class="badge">${g.kind === 'Client' ? '👤 Client' : '🖥️ Server'}</span><div class="lh-name">${esc(g.id)}${g.name ? ', ' + esc(g.name) : ''}</div></td>
      <td><b>${esc(g.message)}</b>${g.hint ? `<div style="margin-top:3px">💡 ${esc(g.hint)}</div>` : g.hint_en ? `<div class="lh-name">${esc(g.hint_en)}</div>` : ''}</td></tr>`;
  const scope = `Rufzeichen ${esc(d.scope.callsigns.join(', ') || '–')} · Server ${esc(d.scope.servers.join(', ') || '–')}`;
  box.innerHTML = (d.error ? `<div class="empty">⚠️ ${esc(d.error)}</div>` : '')
    + (d.mine.length ? `<table class="tbl"><thead><tr><th>Zeit</th><th>Wer</th><th>Meldung</th></tr></thead><tbody>${d.mine.map(row).join('')}</tbody></table>`
      : d.error ? '' : `<div class="empty">✅ Keine Einträge zu dir in den letzten ${d.total} Einträgen des Protokolls${d.span ? ` (${esc(d.span[0].slice(11, 16))}–${esc(d.span[1].slice(11, 16))} Uhr)` : ''}.</div>`)
    + `<div class="lh-name" style="padding:8px 12px">${scope}${d.others && d.others.length ? ` · andere Stationen im Protokoll: ${d.others.slice(0, 6).map(g => esc(g.id)).join(', ')}` : ''}</div>`;
}

/* ---------- FRN: Passwort anfordern ---------- */
async function requestFrnPassword() {
  const v = {};
  for (const k of ['callsign', 'op_name', 'email', 'band', 'description', 'country', 'city', 'sysman_server', 'sysman_port']) {
    const el = $(`#f_frn_${k}`); if (el) v[k] = el.value.trim();
  }
  const miss = [['callsign', 'Rufzeichen'], ['op_name', 'Name'], ['email', 'E-Mail'], ['band', 'Band/Kanal'], ['country', 'Land'], ['city', 'Ort']].filter(([k]) => !v[k]).map(([, l]) => l);
  if (miss.length) return statusPopup('err', 'Angaben fehlen', 'Bitte ausfüllen: ' + miss.join(', '));
  if (!confirm(`FRN-Passwort für „${v.callsign}, ${v.op_name}“ an ${v.email} anfordern?`)) return;
  statusPopup('busy', 'Passwort wird angefordert …', `Verbinde mit ${v.sysman_server || 'sysman.freeradionetwork.eu'}:${v.sysman_port || 10025}`);
  try {
    const r = await api('/api/admin/frn/request-password', { method: 'POST', body: v });
    statusPopup(r.ok ? 'ok' : 'err', r.title, r.message);
  } catch (e) { statusPopup('err', 'Fehler', e.message); }
}

/* ---------- Sprachansage probehören ---------- */
async function previewAnnounce() {
  const v = { callsign: $('#annCall').value.trim() };
  for (const k of ['announce_spell', 'announce_text', 'announce_speed', 'announce_level_db', 'announce_pause_ms']) {
    const el = $(`#f_general_${k}`); if (el) v[k] = el.value;
  }
  try {
    const r = await fetch('/api/admin/announce/preview', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-N8': '1' }, body: JSON.stringify(v) });
    if (!r.ok) { const j = await r.json().catch(() => ({})); return toast('⚠️ ' + (j.detail || 'Ansage nicht möglich')); }
    const a = new Audio(URL.createObjectURL(await r.blob())); a.play();
  } catch (e) { toast('⚠️ ' + e.message); }
}

/* ---------- N8schicht-Vocoder: Klang-Popup ---------- */
const VT = { data: null, profile: 'n8schicht', own: { enc: {}, dec: {}, post: {} }, timer: null };
const VT_SIDES = [['dec', '🔊 Decoder – DMR → FRN / Zello (was man hört)'], ['post', '✨ Nachbearbeitung'], ['pre', '🎚️ Vor dem Encoder – Quelle aufbereiten (FRN / Zello → DMR)'], ['enc', '🎙️ Encoder – FRN / Zello → DMR (was ins DMR geht)']];
async function openVocTune() {
  try { VT.data = await api('/api/admin/vocoder/params'); } catch (e) { return toast('⚠️ ' + e.message); }
  VT.profile = VT.data.profile;
  const own = S.cfg?.vocoder?.n8vocoder_options || {};
  VT.own = { enc: { ...(own.enc || {}) }, dec: { ...(own.dec || {}) }, post: { ...(own.post || {}) }, pre: { ...(own.pre || {}) } };
  $('#vpInfo').textContent = VT.data.active ? 'Der N8schicht-Vocoder ist aktiv – Änderungen wirken sofort im laufenden Betrieb (ohne Neustart).'
    : 'Hinweis: Der N8schicht-Vocoder ist gerade nicht aktiv. Werte werden gespeichert und gelten, sobald er läuft. Probehören geht trotzdem.';
  renderVocTune();
  $('#vocModal').classList.add('open');
}
function vtValue(p) {
  const o = VT.own[p.side] || {};
  if (p.key in o) return o[p.key];
  return VT.profile === 'n8schicht' ? p.n8schicht : p.droidstar;
}
function fmtV(p, v) { return p.step >= 1 ? String(Math.round(v)) : Number(v).toFixed(p.step < 0.1 ? 2 : 1); }
function renderVocTune() {
  const d = VT.data;
  $('#vpProfiles').innerHTML = `<span style="font-size:13px;color:var(--text-dim);align-self:center">Grundabstimmung:</span>` +
    [['n8schicht', '⭐ N8schicht (verständlich)'], ['droidstar', 'DroidStar-Original']].map(([k, l]) => `<button class="btn secondary ${VT.profile === k ? 'active' : ''}" data-p="${k}">${l}</button>`).join('');
  $$('#vpProfiles button').forEach(b => b.onclick = () => { VT.profile = b.dataset.p; renderVocTune(); scheduleVt(); });
  $('#vpBody').innerHTML = VT_SIDES.map(([side, title]) => `<h3 class="vp-sec">${title}</h3>` + d.params.filter(p => p.side === side).map(p => {
    const v = vtValue(p), changed = p.key in (VT.own[p.side] || {});
    const isBool = p.min === 0 && p.max === 1 && p.step === 1;
    return `<div class="vp-row"><label for="vp_${p.side}_${p.key}">${esc(p.label)}</label>
      <input type="range" id="vp_${p.side}_${p.key}" data-side="${p.side}" data-key="${p.key}" min="${p.min}" max="${p.max}" step="${p.step}" value="${v}">
      <span class="vp-val ${changed ? 'changed' : ''}" id="vpv_${p.side}_${p.key}">${isBool ? (v >= 0.5 ? 'an' : 'aus') : fmtV(p, v)}</span>
      <small>${esc(p.help)} · DroidStar ${fmtV(p, p.droidstar)} · N8schicht ${fmtV(p, p.n8schicht)}</small></div>`;
  }).join('')).join('');
  $$('#vpBody input[type=range]').forEach(el => el.oninput = () => {
    const p = d.params.find(x => x.side === el.dataset.side && x.key === el.dataset.key);
    const v = parseFloat(el.value); (VT.own[p.side] ||= {})[p.key] = v;
    const isBool = p.min === 0 && p.max === 1 && p.step === 1;
    const lab = $(`#vpv_${p.side}_${p.key}`); lab.textContent = isBool ? (v >= 0.5 ? 'an' : 'aus') : fmtV(p, v); lab.classList.add('changed');
    scheduleVt();
  });
}
function scheduleVt() {   // live übernehmen, kurz entprellt
  clearTimeout(VT.timer);
  VT.timer = setTimeout(saveVt, 450);
}
async function saveVt(final) {
  try {
    const r = await api('/api/admin/vocoder/options', { method: 'POST', body: { profile: VT.profile, options: VT.own } });
    S.cfg.vocoder.n8vocoder_profile = VT.profile; S.cfg.vocoder.n8vocoder_options = JSON.parse(JSON.stringify(VT.own));
    if (r.bad?.length) toast('⚠️ Nicht übernommen: ' + r.bad.join(', '));
    else if (final) toast(r.live ? '✅ Klang übernommen (live)' : '💾 Gespeichert – gilt, sobald der N8schicht-Vocoder läuft');
  } catch (e) { toast('⚠️ ' + e.message); }
}
async function runVtPreview() {
  const body = { profile: VT.profile, options: VT.own, text: $('#vpText').value.trim() };
  const f = $('#vpWav').files[0];
  if (f) {
    if (f.size > 8 * 1024 * 1024) return toast('⚠️ WAV-Datei zu groß (max. 8 MB)');
    body.wav = await new Promise(res => { const r = new FileReader(); r.onload = () => res(r.result); r.readAsDataURL(f); });
  }
  $('#vpResult').innerHTML = '<p style="margin-top:10px"><span class="spinner"></span> kodiere und dekodiere …</p>';
  try {
    const r = await api('/api/admin/vocoder/preview', { method: 'POST', body });
    const m = r.metrics || {};
    const q = [m.estoi != null ? `Verständlichkeit (ESTOI) <b>${m.estoi}</b>` : '', m.pesq_nb != null ? `Qualität (PESQ) <b>${m.pesq_nb}</b>` : ''].filter(Boolean).join(' · ');
    $('#vpResult').innerHTML = `<div class="vp-res"><div><small>Eingang (8 kHz, ${r.seconds} s)</small><audio controls src="data:audio/wav;base64,${r.orig}"></audio></div>
        <div><small>Nach DMR (Encoder → Decoder)</small><audio controls src="data:audio/wav;base64,${r.out}"></audio></div></div>
      <div class="vp-metrics">Bandbreite bis <b>${m.bandwidth_hz || '–'} Hz</b> (von max. 4000 Hz bei 8 kHz) · Pegel ${m.level_in_dbfs} → ${m.level_out_dbfs} dBFS · Laufzeit ${m.delay_ms} ms${q ? ' · ' + q : ''}</div>
      <div class="vp-bands">${(m.bands || []).map(b => `<div title="Abweichung Ausgang zu Eingang">${b.from}–${b.to} Hz<b style="color:${Math.abs(b.dev_db) <= 3 ? '#30d158' : Math.abs(b.dev_db) <= 8 ? '#ffd60a' : '#ff453a'}">${b.dev_db > 0 ? '+' : ''}${b.dev_db} dB</b></div>`).join('')}</div>`;
  } catch (e) { $('#vpResult').innerHTML = `<p style="color:#ff453a;margin-top:10px">⚠️ ${esc(e.message)}</p>`; }
}
$('#vpClose').addEventListener('click', () => { clearTimeout(VT.timer); $('#vocModal').classList.remove('open'); loadAdmin(); });
$('#vpSave').addEventListener('click', () => { clearTimeout(VT.timer); saveVt(true); });
$('#vpReset').addEventListener('click', () => { if (!confirm('Alle eigenen Werte löschen und die Grundabstimmung verwenden?')) return; VT.own = { enc: {}, dec: {}, post: {}, pre: {} }; renderVocTune(); saveVt(true); });
$('#vpRun').addEventListener('click', runVtPreview);
$('#vpWav').addEventListener('change', () => { const f = $('#vpWav').files[0]; if (f) toast('📂 ' + f.name + ' – jetzt „Testen“'); });

/* ---------- Backup & Neuanfang ---------- */
function renderBackup() {
  $('#adminBody').innerHTML = `
    <div class="banner warn" style="margin:12px 0;align-items:flex-start">🔐 <div class="grow"><b>WICHTIG – Superadmin-Passwort = Schlüssel des Backups</b><br>
      Das Backup wird vollständig verschlüsselt (AES-256-GCM, kein Klartext). Der Schlüssel ist das <b>Passwort des Superadmins</b> zum Zeitpunkt des Backups.
      Ohne dieses Passwort lässt sich das Backup <b>nicht</b> wiederherstellen – auch nicht vom Entwickler.
      Bitte das Superadmin-Passwort im <b>Passwortsafe</b> aufbewahren (z. B. zusammen mit dem Backup-Dateinamen).</div></div>
    <h2 class="section-header">Backup herunterladen</h2>
    <p style="color:var(--text-dim);font-size:13px;padding:0 4px">Enthält alles: Einstellungen inkl. Zugangsdaten (FRN, DMR, Zello), Benutzer, Last Heard, Statistik, Ereignisse, ID-Listen, Talkgroups und Avatare.</p>
    <div class="form"><div class="field"><label>Superadmin-Passwort (dein aktuelles Passwort)</label><input type="password" id="bkPw" autocomplete="current-password"></div></div>
    <div class="form-actions" style="justify-content:flex-start"><button class="btn" id="bkBtn">💾 Verschlüsseltes Backup erstellen</button><span id="bkMsg" style="font-size:13px;color:var(--text-dim)"></span></div>

    <h2 class="section-header">Backup wiederherstellen</h2>
    <div class="form"><div class="field"><label>Backupdatei (.n8xbak)</label><input type="file" id="rsFile" accept=".n8xbak"></div>
      <div class="field"><label>Superadmin-Passwort zum Zeitpunkt des Backups</label><input type="password" id="rsPw" autocomplete="off"></div></div>
    <div class="form-actions" style="justify-content:flex-start"><button class="btn secondary" id="rsCheck">🔍 Prüfen</button><button class="btn" id="rsBtn" disabled>♻️ Wiederherstellen</button></div>
    <div id="rsInfo" style="padding:0 4px"></div>

    <h2 class="section-header">Von vorn beginnen</h2>
    <p style="color:var(--text-dim);font-size:13px;padding:0 4px">Vorher am besten ein Backup erstellen. Komplett deinstallieren geht auf dem Server mit <code>sudo /opt/n8crosslink/uninstall.sh</code> (siehe Doku „Deinstallation“).</p>
    <div class="form"><div class="field"><label>Was zurücksetzen?</label><select id="rsScope">
        <option value="history">Last Heard, Statistik und Ereignisse löschen</option>
        <option value="settings">Alle Einstellungen auf Standard (Benutzer und Verlauf bleiben)</option>
        <option value="all">Alles – wie neu installiert (Login danach n8schicht / n8schicht)</option></select></div>
      <div class="field"><label>Superadmin-Passwort zur Bestätigung</label><input type="password" id="rsPw2" autocomplete="current-password"></div></div>
    <div class="form-actions" style="justify-content:flex-start"><button class="btn danger" id="rsReset">⚠️ Zurücksetzen</button></div>`;
  const b64 = (f) => new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(f); });
  $('#bkBtn').onclick = async () => {
    $('#bkMsg').textContent = 'verschlüssele …';
    const r = await fetch('/api/admin/backup', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-N8': '1' }, body: JSON.stringify({ password: $('#bkPw').value }) });
    if (!r.ok) { let d = {}; try { d = await r.json(); } catch { /* leer */ } $('#bkMsg').textContent = '⚠️ ' + (d.detail || r.statusText); return; }
    const name = (r.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || 'n8crosslink-backup.n8xbak';
    const url = URL.createObjectURL(await r.blob()); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
    $('#bkPw').value = ''; $('#bkMsg').textContent = '✅ ' + name + ' – Passwort im Passwortsafe aufbewahren!';
  };
  let file64 = null;
  $('#rsCheck').onclick = async () => {
    const f = $('#rsFile').files[0]; if (!f) return toast('Bitte eine .n8xbak-Datei wählen');
    file64 = await b64(f);
    try {
      const r = await api('/api/admin/restore/inspect', { method: 'POST', body: { file: file64, password: $('#rsPw').value } }); const m = r.manifest;
      $('#rsInfo').innerHTML = kv([['Erstellt', new Date(m.created * 1000).toLocaleString(N8Kit.locale()) + ' von ' + esc(m.created_by)], ['Version', esc(m.version)], ['Rechner', esc(m.host)],
        ['Inhalt', esc((m.contents || []).join(', '))], ['Umfang', `${m.counts?.users} Benutzer · ${(m.counts?.dmr_ids || 0).toLocaleString(N8Kit.locale())} DMR-IDs · ${m.counts?.talkgroups} TGs · ${m.counts?.avatars} Avatare`]]);
      $('#rsBtn').disabled = false;
    } catch (e) { $('#rsInfo').innerHTML = `<div class="err">⚠️ ${esc(e.message)}</div>`; $('#rsBtn').disabled = true; }
  };
  $('#rsBtn').onclick = async () => {
    if (!confirm('Backup jetzt einspielen? Alle aktuellen Daten werden ersetzt, die Bridge startet neu.')) return;
    try { await api('/api/admin/restore', { method: 'POST', body: { file: file64, password: $('#rsPw').value } }); toast('✅ Backup eingespielt – bitte neu anmelden'); setTimeout(() => location.reload(), 2000); }
    catch (e) { toast('⚠️ ' + e.message); }
  };
  $('#rsReset').onclick = async () => {
    const sc = $('#rsScope').value;
    if (!confirm(`Wirklich zurücksetzen: ${$('#rsScope').selectedOptions[0].text}?`)) return;
    try { const r = await api('/api/admin/reset', { method: 'POST', body: { scope: sc, password: $('#rsPw2').value } }); toast('✅ Zurückgesetzt'); setTimeout(() => location.reload(), r.relogin ? 1500 : 800); }
    catch (e) { toast('⚠️ ' + e.message); }
  };
}

/* ---------- Mithören (nur angemeldete Admins) ---------- */
const L = { ws: null, ctx: null, gain: null, next: 0, on: false };
function listenStart() {
  L.ctx = L.ctx || new (window.AudioContext || window.webkitAudioContext)();
  L.ctx.resume();
  if (!L.gain) { L.gain = L.ctx.createGain(); L.gain.connect(L.ctx.destination); }
  L.gain.gain.value = $('#listenVol').value / 100;
  L.ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/audio');
  L.ws.binaryType = 'arraybuffer';
  L.ws.onmessage = (ev) => {
    if (typeof ev.data === 'string') { const m = JSON.parse(ev.data); if (m.type === 'start') L.next = 0; return; }
    const pcm = new Int16Array(ev.data), buf = L.ctx.createBuffer(1, pcm.length, 8000), ch = buf.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 32768;
    const src = L.ctx.createBufferSource(); src.buffer = buf; src.connect(L.gain);
    const now = L.ctx.currentTime;
    if (L.next < now + 0.05 || L.next > now + 1.0) L.next = now + 0.25;   // Jitterpuffer 250 ms
    src.start(L.next); L.next += buf.duration;
  };
  L.ws.onclose = (ev) => { if (L.on && ev.code !== 4401) setTimeout(() => { if (L.on) listenStart(); }, 2000); else listenStop(); };
  L.on = true; $('#listenBtn').classList.add('on'); $('#listenLbl').textContent = ' Mithören aktiv'; $('#ssListen').hidden = false;
}
function listenStop() {
  L.on = false; if (L.ws) { L.ws.onclose = null; L.ws.close(); L.ws = null; }
  $('#listenBtn').classList.remove('on'); $('#listenLbl').textContent = ' Mithören'; $('#ssListen').hidden = true;
}
$('#listenBtn').addEventListener('click', () => L.on ? listenStop() : listenStart());
function setListenVol(v, save = true) {
  $('#listenVol').value = v; $('#listenVolVal').textContent = v + ' %';
  if (L.gain) L.gain.gain.value = v / 100;
  if (save) try { localStorage.setItem('n8x_listen_vol', String(v)); } catch { /* privater Modus */ }
}
$('#listenVol').addEventListener('input', () => setListenVol(parseInt($('#listenVol').value, 10)));
$('#listenCaret').addEventListener('click', (e) => { e.stopPropagation(); $('#linksMenu').classList.remove('open'); $('#listenMenu').classList.toggle('open'); });
$('#listenPop').addEventListener('click', (e) => e.stopPropagation());
document.addEventListener('click', () => $('#listenMenu').classList.remove('open'));
try { const v = parseInt(localStorage.getItem('n8x_listen_vol'), 10); if (v >= 0 && v <= 200) setListenVol(v, false); } catch { /* ohne Speicher */ }

/* ---------- Start ---------- */
(async () => {
  try { await loadMe(); await loadInfo(); } catch { /* offline */ }
  connectWS();
  const h = location.hash.slice(1);
  if (['stats', 'nets'].includes(h) || (h === 'admin' && S.me?.user)) showTab(h);
})();

// ------------------------------------------------------------ 🎨 Aussehen (N8 Theme 2, wie in den anderen N8schicht-Projekten)
async function renderAppearance() {
  const { theme } = await api('/api/theme');
  $('#adminBody').innerHTML = `<div class="card" style="padding:16px">
      <p style="color:var(--text-dim);font-size:13px;margin-bottom:12px">Gleiche Farbtechnik wie HBlink4-FreeRadioID, adn-frn-server und N8-HotSpot:
        Profil wählen, dann jede Farbe ändern – die ganze Seite zeigt es sofort, gespeichert wird erst mit „Speichern“.</p>
      <div id="apEditor">${N8Theme.editorHtml(theme, 'ap')}</div>
      <div class="form-actions" style="justify-content:flex-start">
        <button class="btn" id="apSave">💾 Aussehen speichern</button>
        <button class="btn secondary" id="apReset">↺ N8-Standard</button></div></div>`;
  const root = $('#apEditor');
  N8Theme.bindEditor(root, t => N8Theme.apply(t));
  $('#apSave').onclick = async () => {
    try { const r = await api('/api/admin/theme', { method: 'POST', body: { theme: N8Theme.readEditor(root) } }); N8Theme.apply(r.theme); toast('Aussehen gespeichert'); }
    catch (e) { toast(e.message); }
  };
  $('#apReset').onclick = () => { N8Theme.setEditor(root, { preset: 'n8' }); N8Theme.apply({ preset: 'n8' }); };
}
