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
  const t = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  return d.toDateString() === now.toDateString() ? t : d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }) + ' ' + t;
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
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2800); }
async function api(path, opts = {}) {
  const o = { headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin', ...opts };
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
  $('#ssVocLbl').innerHTML = '&nbsp;' + esc(v ? (v.mode === 'md380' ? 'md380-emu' : v.mode === 'usb' ? 'USB-Stick' : v.mode) + (v.online ? '' : ' offline') : 'aus');
  $('#ssInfo').textContent = st.active ? '' : 'Ruhe';
  renderOnAir(); renderNetCards(); renderRoom();
  const up = st.update;
  $('#updateBanner').hidden = !(S.me?.user && up?.available);
  if (up?.available) $('#updateText').innerHTML = `Update verfügbar: <b>${esc(up.current)}</b> → <b>${esc(up.latest)}</b>`;
  if ($('#tab-nets') && !$('#tab-nets').classList.contains('hidden')) renderNetDetails();
}

function renderOnAir() {
  const a = S.state?.active, box = $('#onair');
  if (!a) {
    box.classList.remove('live');
    $('#stActive').textContent = '–';
    $('#oaKicker').textContent = 'On Air';
    const last = S.lh.find(x => x.status !== 'blocked');
    $('#oaName').textContent = 'Ruhe auf allen Netzen';
    if ($('#oaAv').dataset.k) { $('#oaAv').outerHTML = '<div class="big-av" id="oaAv"><span class="av-fb">N8</span></div>'; }
    $('#oaSub').innerHTML = last ? `Zuletzt: <b>${esc(last.name || last.callsign)}</b> ${badge(last.source)} · vor ${ago(last.ts_end || last.ts_start)}` : 'Warte auf die nächste Durchsage …';
    box.style.removeProperty('--srccol');
    $('#oaTimer').textContent = ''; $('#oaMeter').style.width = '0';
    return;
  }
  const t = a.talker, [cs, nm] = splitName(t);
  box.classList.add('live');
  box.style.setProperty('--srccol', `var(--${a.source})`);
  $('#stActive').textContent = cs;
  const k = avatarKey(a.source, t);
  if ($('#oaAv').dataset.k !== a.source + k) { $('#oaAv').dataset.k = a.source + k; $('#oaAv').outerHTML = avatar(a.source, k, cs, 'big-av').replace('class="big-av', 'id="oaAv" data-k="' + esc(a.source + k) + '" class="big-av'); }
  $('#oaKicker').textContent = `On Air · über ${NET[a.source].label}`;
  $('#oaName').textContent = t.name || cs;
  const tg = a.targets.length ? a.targets.map(k => badge(k)).join(' ') : '<span class="badge off">kein Ziel online</span>';
  const frid = t.extra?.frid ? ' <span class="frid-tag" title="Registriert bei FreeRadioID.net">FRID</span>' : '';
  $('#oaSub').innerHTML = `${badge(a.source)} <span class="arrow">→</span> ${tg} · ${esc(t.detail || '')}${t.city ? ' · ' + esc(t.city) : ''}${t.dmr_id ? ' · ID ' + t.dmr_id : ''}${frid}`;
  const lvl = S.state.ports[a.source]?.rx_level ?? -90;
  $('#oaMeter').style.width = Math.max(0, Math.min(100, (lvl + 60) / 60 * 100)) + '%';
}
setInterval(() => {
  const a = S.state?.active;
  if (a) $('#oaTimer').textContent = fmtDur(Date.now() / 1000 - a.since);
}, 250);

function routeChips(k) {
  const r = S.state?.routes || {};
  return ORDER.filter(o => o !== k).map(o => `<span class="badge ${r[k + '_' + o] ? o : 'dim'}" title="${NET[k].label} → ${NET[o].label}">→ ${NET[o].label} ${r[k + '_' + o] ? '✓' : '✕'}</span>`).join('');
}

function renderNetCards() {
  const ports = S.state?.ports || {};
  $('#netGrid').innerHTML = ORDER.map(k => {
    const p = ports[k] || {}; const n = NET[k];
    const pill = !p.enabled ? '<span class="badge warn">AUS</span>' : p.online ? '<span class="badge ok">ONLINE</span>' : '<span class="badge off">OFFLINE</span>';
    let now = '';
    if (p.tx && p.tx_talker) now = `🔴 sendet: <b>${esc(p.tx_talker.name)}</b> ${badge(p.tx_talker.source)}`;
    else if (p.rx && S.state.active?.source === k) now = `🟢 empfängt: <b>${esc(S.state.active.talker.name)}</b>`;
    else if (p.rx) now = '🟡 Empfang gesperrt (Bridge belegt)';
    else now = `<span style="color:var(--text-dim)">${esc(p.enabled ? (p.online ? 'bereit' : (p.state || 'offline')) : 'deaktiviert')}</span>`;
    const meta = [];
    if (k === 'frn') { meta.push(esc(p.server || '')); if (p.access) meta.push('Zugang ' + esc(p.access)); }
    if (k === 'dmr') { meta.push(esc(p.server || '')); meta.push(`Peer ${esc(p.peer_id)}`); meta.push(`RX TG ${esc(p.tg_rx)}${p.tg_rx_name ? ' ' + esc(p.tg_rx_name) : ''} · TX TG ${esc(p.tg_tx)}${p.tg_tx_name ? ' ' + esc(p.tg_tx_name) : ''} · TS${esc(p.slot)}`); }
    if (p.watchdog?.reconnects) meta.push(`🔁 ${p.watchdog.reconnects}`);
    if (k === 'zello') { meta.push(esc(p.username || '')); }
    const c = p.counters || {};
    meta.push(`⇣ ${c.rx || 0} · ⇡ ${c.tx || 0}`);
    return `<div class="net-card ${k} ${p.tx ? 'txing' : ''} ${p.rx && S.state.active?.source === k ? 'rxing' : ''}">
      <div class="nc-head"><div class="nc-icon">${n.icon}</div>
        <div class="grow"><div class="nc-title">${n.label}</div><div class="nc-sub">${esc(p.detail || p.state || '')}</div></div>
        <div class="rt"><span class="rx ${p.rx ? 'on' : ''}">RX</span><span class="tx ${p.tx ? 'on' : ''}">TX</span></div>${pill}</div>
      <div class="nc-now">${now}</div>
      <div class="nc-meta">${meta.filter(Boolean).map(m => `<span>${m}</span>`).join('<span>·</span>')}</div>
      <div class="nc-routes">${routeChips(k)}</div></div>`;
  }).join('');
}

function renderRoom() {
  const p = S.state?.ports?.frn; const list = p?.clients || [];
  $('#roomCount').textContent = p?.online ? `${list.length} · ${p.net || ''}` : '';
  if (!p?.online) { $('#roomList').innerHTML = `<div class="empty">${p?.enabled ? 'Keine FRN-Verbindung.' : 'FRN ist deaktiviert.'}</div>`; return; }
  if (!list.length) { $('#roomList').innerHTML = '<div class="empty">Keine Stationen im Raum.</div>'; return; }
  const activeCs = S.state.active?.source === 'frn' ? S.state.active.talker.callsign : '';
  $('#roomList').innerHTML = `<table class="tbl"><thead><tr><th>Station</th><th>Ort</th><th>Band / Kanal</th><th>Typ</th></tr></thead><tbody>${
    list.map(c => `<tr ${c.callsign === activeCs ? 'style="background:rgba(48,209,88,.12)"' : ''}><td><div class="lh-user">${avatar('frn', c.callsign, c.callsign)}
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
      <div class="lh-time" title="${new Date(e.ts_start * 1000).toLocaleString('de-DE')}">${fmtTime(e.ts_start)}</div>
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
  $('#evList').innerHTML = EV.map(e => `<div class="ev-row ${e.level === 'warn' ? 'warn' : ''}"><time>${new Date(e.ts * 1000).toLocaleTimeString('de-DE')}</time><div>${esc(e.text)}</div></div>`).join('');
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
    [x.online ? 'Online seit' : 'Offline seit', (x.online ? x.watchdog?.online_since : x.watchdog?.offline_since) ? new Date((x.online ? x.watchdog.online_since : x.watchdog.offline_since) * 1000).toLocaleString('de-DE') : '–']];
  const card = (k, title, body) => `<div><h2 class="section-header">${NET[k]?.icon || '🎛️'} ${title}</h2><div class="card">${body}</div></div>`;
  $('#netDetails').innerHTML =
    card('frn', 'FRN – FreeRadioNetwork', kv([['Status', on(f)], ['Server', esc(f.server)], ['Raum', esc(f.net)], ['Zugang', esc(f.access)],
      ['Server-Version', esc(f.server_version)], ['Stationen im Raum', (f.clients || []).length], ['Sende-Status', esc(f.tx_state)],
      ['Info', esc(f.net_info)], ['Durchgänge', `⇣ ${f.counters?.rx || 0} empfangen · ⇡ ${f.counters?.tx || 0} gesendet`], ...wd(f)])) +
    card('dmr', 'DMR – HomeBrew (HBlink4 / FreeDMR)', kv([['Status', on(d)], ['Server', esc(d.server)], ['Login-Phase', esc(d.login)],
      ['Peer-ID', esc(d.peer_id)], ['Zeitschlitz', 'TS' + esc(d.slot)], ['RX-Talkgroup', esc(d.tg_rx)], ['TX-Talkgroup', esc(d.tg_tx)],
      ['Verbunden seit', d.since ? new Date(d.since * 1000).toLocaleString('de-DE') : '–'],
      ['Ping / Pong', `${d.stats?.pings || 0} / ${d.stats?.pongs || 0}`], ['Pakete', `⇣ ${d.stats?.rx_pkts || 0} · ⇡ ${d.stats?.tx_pkts || 0}`],
      ['RX-/TX-Talkgroup-Name', `${esc(d.tg_rx_name || '–')} / ${esc(d.tg_tx_name || '–')}`],
      ['ID-Listen', d.userdb ? `${(d.userdb.count || 0).toLocaleString('de-DE')} DMR-IDs · ${(d.userdb.registered || 0).toLocaleString('de-DE')} FreeRadioID · ${(d.userdb.talkgroups || 0).toLocaleString('de-DE')} Talkgroups${d.userdb.updated ? ' · Stand ' + new Date(d.userdb.updated * 1000).toLocaleString('de-DE') : ''}` : '–'], ...wd(d)])) +
    card('zello', 'Zello – Channel API', kv([['Status', on(z)], ['Server', esc(z.server)], ['Kanal', esc(z.channel)], ['Konto', esc(z.username)],
      ['Kanal-Status', esc(z.channel_status)], ['Benutzer online', z.users_online ?? '–'],
      ['Durchgänge', `⇣ ${z.counters?.rx || 0} · ⇡ ${z.counters?.tx || 0}`], ...wd(z)])) +
    card('voc', 'Vocoder (AMBE+2)', kv([['Status', v ? (v.online ? '<span class="badge ok">bereit</span>' : '<span class="badge off">offline</span>') : '<span class="badge warn">nicht gestartet</span>'],
      ['Betriebsart', esc(v?.name)], ['Gerät', esc(v?.product)], ['Version', esc(v?.version)],
      ['Rahmen', v ? `Encode ${v.enc} · Decode ${v.dec} · Timeouts ${v.timeouts}` : '–'],
      ['Watchdog', v ? `${v.reopens || 0}× neu geöffnet` : '–']]));
}

/* ---------- Login / Setup ---------- */
let loginMode = 'login';
function openLogin(mode = 'login') {
  loginMode = mode;
  $('#loginTitle').textContent = mode === 'setup' ? '🧭 Superadmin anlegen' : '🔐 Anmelden';
  $('#loginHint').textContent = mode === 'setup' ? 'Erster Start: lege das Superadmin-Konto an (Passwort min. 8 Zeichen).' : 'Adminbereich der N8 Crosslink.';
  $('#lPass2Wrap').hidden = mode !== 'setup'; $('#lOk').textContent = mode === 'setup' ? 'Anlegen' : 'Anmelden';
  $('#lErr').textContent = ''; $('#loginModal').classList.add('open'); setTimeout(() => $('#lUser').focus(), 50);
}
$('#lCancel').addEventListener('click', () => $('#loginModal').classList.remove('open'));
$('#lPass').addEventListener('keydown', e => { if (e.key === 'Enter' && loginMode === 'login') $('#lOk').click(); });
$('#lOk').addEventListener('click', async () => {
  const username = $('#lUser').value.trim(), password = $('#lPass').value;
  try {
    if (loginMode === 'setup') {
      if (password !== $('#lPass2').value) throw new Error('Passwörter stimmen nicht überein');
      await api('/api/setup', { method: 'POST', body: { username, password } });
    } else await api('/api/login', { method: 'POST', body: { username, password } });
    $('#loginModal').classList.remove('open'); $('#lPass').value = ''; $('#lPass2').value = '';
    await loadMe(); showTab('admin'); toast('Angemeldet als ' + username);
  } catch (e) { $('#lErr').textContent = e.message; }
});
$('#setupBtn').addEventListener('click', () => openLogin('setup'));
async function loadMe() {
  S.me = await api('/api/me');
  $('#setupBanner').hidden = true;
  $('#pwBanner').hidden = !S.me.default_password;
  $('#tabAdminBtn').hidden = !S.me.user;
  $('#userArea').innerHTML = S.me.user
    ? `<button class="hdr-btn" id="logoutBtn" title="Abmelden">👤 ${esc(S.me.user)} · ⎋</button>`
    : `<button class="hdr-btn login" id="loginBtn">🔐 Login</button>`;
  if (S.me.user) $('#logoutBtn').onclick = async () => { await api('/api/logout', { method: 'POST' }); await loadMe(); showTab('live'); };
  else $('#loginBtn').onclick = () => openLogin(S.me.setup_required ? 'setup' : 'login');
}
async function loadInfo() {
  const i = await api('/api/info');
  $('#linksPop').innerHTML = (i.links || []).map(l => `<a href="${esc(l.url)}" target="_blank" rel="noopener">🔗 ${esc(l.name)}</a>`).join('') || '<a>Keine Links</a>';
  $('#announceBanner').hidden = !i.announcement; $('#announceText').textContent = i.announcement || '';
}

/* ---------- Admin ---------- */
const F = (key, label, type = 'text', opt = {}) => ({ key, label, type, ...opt });
const SCHEMA = {
  general: { title: '🏠 Allgemein', fields: [
    F('title', 'Titel im Dashboard'), F('server_name', 'Servername / Domain'),
    F('web_host', 'Web-Adresse (Bind)', 'text', { help: '0.0.0.0 = alle Schnittstellen · Neustart des Dienstes nötig' }),
    F('web_port', 'Web-Port', 'number', { help: 'Neustart des Dienstes nötig' }),
    F('hang_time_ms', 'Sperrzeit nach Aussendung (ms)', 'number', { help: 'Schützt vor Ping-Pong zwischen den Netzen' }),
    F('jitter_ms', 'Vorpuffer DMR/Zello-Ausgang (ms)', 'number', { help: 'FRN liefert 200-ms-Blöcke – 240 ms sind ein guter Wert' }),
    F('tot_s', 'Time-Out-Timer pro Durchgang (s)', 'number'), F('keep_days', 'Last Heard aufbewahren (Tage)', 'number'),
    F('watchdog_offline_s', 'Watchdog: Netz nach … s offline komplett neu aufbauen', 'number', { help: 'Zusätzlich zur normalen Wiederverbindung (Standard 120 s)' }),
    F('update_check', 'Stündlich (zur vollen Stunde) auf Updates prüfen', 'bool'),
    F('update_repo', 'GitHub-Repository für Updates'), F('update_branch', 'Branch'),
    F('announcement', 'Hinweis-Banner im Dashboard', 'text', { wide: true }),
    F('links', 'Links-Menü (JSON-Liste mit name/url)', 'json', { wide: true }),
  ] },
  routes: { title: '🔀 Routing', custom: renderRoutes },
  frn: { title: '📻 FRN', fields: [
    F('enabled', 'FRN aktiv', 'bool'), F('server', 'Server'), F('port', 'Port', 'number'),
    F('backup_server', 'Backup-Server'), F('backup_port', 'Backup-Port', 'number'),
    F('email', 'E-Mail (FRN-Konto)'), F('password', 'Passwort (FRN)', 'password', { help: 'leer lassen = unverändert' }),
    F('callsign', 'Rufzeichen'), F('op_name', 'Name / Bezeichnung'),
    F('client_type', 'Client-Typ', 'select', { options: [[0, '0 – Crosslink'], [1, '1 – Gateway'], [2, '2 – PC Only']] }),
    F('band', 'Band / Kanal (BC)', 'text', { help: '„Crosslink“ oder z. B. 446.03125FM CTC131.8' }),
    F('net', 'Raum (Net)'), F('description', 'Beschreibung'), F('country', 'Land'), F('city', 'Ort – Ortsteil / Locator'),
    F('version', 'Protokollversion'), F('rx_timeout_ms', 'Ende-Erkennung RX (ms)', 'number', { help: 'Kein Sprachpaket für diese Zeit = Durchgang beendet (SvxLink: 1000)' }),
    F('rx_gain_db', 'Pegel FRN → Bridge (dB)', 'number', { step: 0.5 }), F('tx_gain_db', 'Pegel Bridge → FRN (dB)', 'number', { step: 0.5 }),
    F('text_messages', 'Sprechername als FRN-Textnachricht (experimentell)', 'bool'),
  ] },
  dmr: { title: '📡 DMR', fields: [
    F('enabled', 'DMR aktiv', 'bool'), F('host', 'Server (HBlink4 / FreeDMR)'), F('port', 'Port', 'number'),
    F('password', 'Passwort (Passphrase)', 'password', { help: 'leer lassen = unverändert' }),
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
  update: { title: '⬆️ Updates', custom: renderUpdate },
  users: { title: '👥 Benutzer', custom: renderUsers },
  system: { title: '🛠️ System', custom: renderSystem },
};

async function loadAdmin() {
  if (!S.me?.user) return;
  try { S.cfg = (await api('/api/admin/config')).config; } catch (e) { toast(e.message); return; }
  $('#adminNav').innerHTML = Object.entries(SCHEMA).map(([k, v]) => `<button data-s="${k}" class="${k === S.adminSec ? 'active' : ''}">${v.title}</button>`).join('');
  $$('#adminNav button').forEach(b => b.onclick = () => { S.adminSec = b.dataset.s; loadAdmin(); });
  const sec = SCHEMA[S.adminSec];
  if (sec.custom) return sec.custom();
  renderForm(S.adminSec, sec.fields);
}

function fieldHtml(sec, f, val) {
  const id = `f_${sec}_${f.key}`, help = f.help ? `<small>${esc(f.help)}</small>` : '';
  if (f.type === 'bool') return `<div class="field ${f.wide ? 'wide' : ''}"><label class="switch"><input type="checkbox" id="${id}" ${val ? 'checked' : ''}><span></span>${esc(f.label)}</label>${help}</div>`;
  let input;
  if (f.type === 'select') input = `<select id="${id}">${f.options.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(val) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
  else if (f.type === 'textarea') input = `<textarea id="${id}" placeholder="${val === '********' ? 'gesetzt – leer lassen = unverändert' : ''}">${val === '********' ? '' : esc(val)}</textarea>`;
  else if (f.type === 'json') input = `<textarea id="${id}">${esc(JSON.stringify(val, null, 2))}</textarea>`;
  else if (f.type === 'password') input = `<input type="password" id="${id}" autocomplete="new-password" placeholder="${val ? 'gesetzt – leer lassen = unverändert' : ''}">`;
  else input = `<input type="${f.type === 'number' ? 'number' : 'text'}" ${f.step ? `step="${f.step}"` : f.type === 'number' ? 'step="any"' : ''} id="${id}" value="${esc(val)}">`;
  return `<div class="field ${f.wide ? 'wide' : ''}"><label for="${id}">${esc(f.label)}</label>${input}${help}</div>`;
}
function readField(sec, f) {
  const el = $(`#f_${sec}_${f.key}`); if (!el) return undefined;
  if (f.type === 'bool') return el.checked;
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
    ['md380', '🧠 md380-emu (Software)', 'Ohne Zusatzhardware. Läuft nativ auf ARM (Raspberry Pi), auf x86 über qemu-user. Standard UDP 127.0.0.1:2470.'],
    ['usb', '🔌 USB-Stick (AMBE3000)', 'ThumbDV, DVstick 30, DV3000 direkt per USB/seriell. Beste Qualität, kein Zusatzdienst nötig.'],
    ['ambeserver', '🌐 AMBEserver (Netz)', 'AMBE3000 an einem anderen Rechner hinter AMBEserver (UDP 2460).'],
    ['none', '🧪 Test ohne Vocoder', 'Nur zum Testen der Verbindungen – DMR-Audio ist dann stumm.'],
  ];
  const fields = {
    md380: [F('md380_host', 'md380-emu Adresse'), F('md380_port', 'md380-emu Port', 'number'), F('md380_send_init', 'Init-Pakete (Reset/Rate) senden', 'bool')],
    usb: [F('usb_device', 'Gerät', 'text', { help: 'z. B. /dev/ttyUSB0 oder /dev/serial/by-id/…' }),
      F('usb_baud', 'Baudrate', 'select', { options: [[460800, '460800 (ThumbDV / DVstick 30)'], [230400, '230400 (DV3000 Pi-Hat)'], [921600, '921600']] }),
      F('usb_send_init', 'Init-Pakete (Reset/Rate) senden', 'bool')],
    ambeserver: [F('ambeserver_host', 'AMBEserver Adresse'), F('ambeserver_port', 'AMBEserver Port', 'number'), F('ambeserver_send_init', 'Init-Pakete senden', 'bool')],
    none: [],
  };
  const common = [F('vocoder_enc_gain_db', 'Pegel vor dem Kodieren (dB)', 'number', { step: 0.5 }), F('vocoder_dec_gain_db', 'Pegel nach dem Dekodieren (dB)', 'number', { step: 0.5 })];
  const sel = window._vocSel || mode;
  const flds = [...fields[sel], ...common];
  const v = S.state?.vocoder;
  $('#adminBody').innerHTML = `<div class="voc-choice">${opts.map(([k, t, d]) => `<div class="voc-opt ${k === sel ? 'active' : ''}" data-m="${k}"><b>${t}${k === mode ? ' · aktiv' : ''}</b><small>${d}</small></div>`).join('')}</div>
    <div class="form">${flds.map(f => fieldHtml('vocoder', f, c[f.key])).join('')}
      <div class="field wide"><label>Aktueller Zustand</label><div>${v ? `${v.online ? '<span class="badge ok">bereit</span>' : '<span class="badge off">offline</span>'} ${esc(v.name)} ${esc(v.product || '')} · Encode ${v.enc} · Decode ${v.dec} · Timeouts ${v.timeouts}` : '<span class="badge warn">nicht gestartet</span>'}</div>
      <small id="vocTestRes"></small></div></div>
    <div class="form-actions">${sel === 'usb' ? '<button class="btn secondary" id="scanBtn">🔍 USB-Geräte suchen</button>' : ''}
      <button class="btn secondary" id="vocTestBtn">🧪 Vocoder testen</button><button class="btn" id="saveBtn">💾 Speichern &amp; neu starten</button></div>`;
  $$('.voc-opt').forEach(o => o.onclick = () => { window._vocSel = o.dataset.m; renderVocoder(); });
  $('#saveBtn').onclick = async () => {
    await saveSection('vocoder', flds, { vocoder_mode: sel });
    await api('/api/admin/restart', { method: 'POST' }); $('#restartBanner').hidden = true;
    window._vocSel = null; toast('🔄 Vocoder gespeichert, Bridge startet neu …'); setTimeout(loadAdmin, 2500);
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

async function renderUsers() {
  const list = await api('/api/admin/users');
  $('#adminBody').innerHTML = `<table class="tbl" style="margin:8px 0"><thead><tr><th>Benutzer</th><th>Rolle</th><th>Angelegt</th><th></th></tr></thead><tbody>
    ${list.map(u => `<tr><td>👤 ${esc(u.username)}</td><td>${esc(u.role)}</td><td>${u.created ? new Date(u.created * 1000).toLocaleDateString('de-DE') : ''}</td>
    <td class="num">${u.username === S.me.user ? '<span class="badge">du</span>' : `<button class="btn secondary" data-del="${esc(u.username)}">Löschen</button>`}</td></tr>`).join('')}</tbody></table>
    <div class="form"><div class="field"><label>Neuer Benutzer / Passwort ändern</label><input type="text" id="nuUser" placeholder="Benutzername"></div>
    <div class="field"><label>Passwort (min. 8 Zeichen)</label><input type="password" id="nuPass" autocomplete="new-password"></div></div>
    <div class="form-actions"><button class="btn" id="nuBtn">💾 Speichern</button></div>`;
  $$('[data-del]').forEach(b => b.onclick = async () => { if (confirm('Benutzer ' + b.dataset.del + ' löschen?')) { await api('/api/admin/users/' + encodeURIComponent(b.dataset.del), { method: 'DELETE' }); renderUsers(); } });
  $('#nuBtn').onclick = async () => {
    try { await api('/api/admin/users', { method: 'POST', body: { username: $('#nuUser').value.trim(), password: $('#nuPass').value } }); toast('✅ Benutzer gespeichert'); renderUsers(); }
    catch (e) { toast('⚠️ ' + e.message); }
  };
}

async function renderSystem() {
  const [ev, sy] = await Promise.all([api('/api/admin/events?limit=150'), api('/api/admin/system')]);
  const stCls = (a) => a === 'active' ? 'ok' : a === 'failed' ? 'off' : 'warn';
  const ACT = { start: '▶️ Start', stop: '⏹️ Stopp', restart: '🔄 Neustart', enable: '✅ Autostart an', disable: '🚫 Autostart aus' };
  const unitsHtml = sy.units.length ? `<table class="tbl"><thead><tr><th>Dienst</th><th>Status</th><th>Autostart</th><th></th></tr></thead><tbody>${
    sy.units.map(u => `<tr><td><b>${esc(u.label)}</b><div class="lh-name">${esc(u.unit)}</div></td>
      <td><span class="badge ${stCls(u.active)}">${esc(u.active)}</span></td><td><span class="badge ${u.enabled === 'enabled' ? 'ok' : ''}">${esc(u.enabled)}</span></td>
      <td class="num">${u.actions.map(a => `<button class="btn secondary" style="padding:4px 10px;margin:2px" data-unit="${esc(u.unit)}" data-act="${a}" ${sy.sudo ? '' : 'disabled'}>${ACT[a] || a}</button>`).join('')}</td></tr>`).join('')}</tbody></table>`
    : '<div class="empty">Keine Dienste freigegeben.</div>';
  $('#adminBody').innerHTML = `<h2 class="section-header">Dienste ${sy.sudo ? '<span class="badge ok">sudo bereit</span>' : '<span class="badge warn">sudo nicht eingerichtet – einmal sudo /opt/n8crosslink/update.sh ausführen</span>'}</h2>
    <div class="card">${unitsHtml}</div>
    <div class="form-actions" style="justify-content:flex-start">
      <button class="btn secondary" id="sysPerm" ${sy.sudo && sy.fix_perms ? '' : 'disabled'}>🔐 Berechtigungen prüfen &amp; korrigieren</button>
      ${sy.reboot ? `<button class="btn danger" id="sysReboot" ${sy.sudo ? '' : 'disabled'}>⏻ Server neu starten</button>` : ''}</div>
    <pre id="sysOut" style="font-size:11.5px;white-space:pre-wrap;color:var(--text-dim);padding:0 4px"></pre>
    <h2 class="section-header">Bridge</h2>
    <div class="form-actions" style="justify-content:flex-start">
      <button class="btn" id="sysRestart">🔄 Bridge neu starten</button>
      <button class="btn secondary" id="sysSvc">♻️ Dienst neu starten</button>
      <button class="btn secondary" id="sysUdb">🗂️ ID-Listen aktualisieren</button>
      <a class="btn secondary" href="/api/admin/export">⬇️ Konfiguration exportieren</a>
      <label class="btn secondary" style="cursor:pointer">⬆️ Importieren<input type="file" id="sysImp" accept=".json" hidden></label></div>
    <h2 class="section-header">Ereignisprotokoll</h2>
    <div class="ev-list">${ev.map(e => `<div class="ev-row ${e.level === 'warn' ? 'warn' : ''}"><time>${new Date(e.ts * 1000).toLocaleString('de-DE')}</time><div>${esc(e.text)}</div></div>`).join('') || '<div class="empty">Leer.</div>'}</div>`;
  $$('[data-unit]').forEach(b => b.onclick = async () => {
    const self = b.dataset.unit === 'n8crosslink.service';
    if (['stop', 'disable'].includes(b.dataset.act) || self) { if (!confirm(`${b.textContent.trim()} – ${b.dataset.unit}?`)) return; }
    const r = await api('/api/admin/system/unit', { method: 'POST', body: { unit: b.dataset.unit, action: b.dataset.act } });
    toast((r.ok ? '✅ ' : '⚠️ ') + (r.message || '')); if (!self) setTimeout(renderSystem, 1500);
  });
  if ($('#sysPerm')) $('#sysPerm').onclick = async () => { $('#sysOut').textContent = 'prüfe …'; const r = await api('/api/admin/system/fix-perms', { method: 'POST' }); $('#sysOut').textContent = r.message; toast(r.ok ? '✅ Berechtigungen geprüft' : '⚠️ Fehler'); };
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
  const dt = (t) => t ? new Date(t * 1000).toLocaleString('de-DE') : 'noch nie';
  const c = S.cfg.ids;
  $('#adminBody').innerHTML = `${kv([
      ['DMR-IDs', `${L.users.toLocaleString('de-DE')} · Stand ${dt(L.users_updated)}`], ['Quelle', esc(L.users_source)],
      ['Bei FreeRadioID registriert', `${L.registered.toLocaleString('de-DE')} · Stand ${dt(L.frid_updated)}`],
      ['Talkgroup-Namen', `${L.talkgroups.toLocaleString('de-DE')} · Stand ${dt(L.tg_updated)}`],
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

async function renderUpdate() {
  const u = await api('/api/admin/update');
  const md = (t) => esc(t).replace(/^### (.*)$/gm, '<b>$1</b>').replace(/^## (.*)$/gm, '<h3 style="margin:8px 0 4px">$1</h3>').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\n/g, '<br>');
  $('#adminBody').innerHTML = `${kv([
      ['Installiert', `<b>${esc(u.current)}</b>`],
      ['Auf GitHub', u.latest ? `<b>${esc(u.latest)}</b> ${u.available ? '<span class="badge ok">Update verfügbar</span>' : '<span class="badge">aktuell</span>'}` : '–'],
      ['Zuletzt geprüft', u.checked ? new Date(u.checked * 1000).toLocaleString('de-DE') : '–'],
      ['Automatische Prüfung', S.cfg.general.update_check ? 'stündlich zur vollen Stunde' : 'aus'],
      ['Update-Dienst', u.systemd ? '<span class="badge ok">eingerichtet</span>' : '<span class="badge warn">fehlt – einmal sudo /opt/n8crosslink/update.sh ausführen</span>'],
      ...(u.error ? [['Fehler', esc(u.error)]] : [])])}
    <div class="form-actions" style="justify-content:flex-start">
      <button class="btn secondary" id="upCheck">🔍 Jetzt prüfen</button>
      <button class="btn" id="upNow" ${u.available && u.systemd ? '' : 'disabled'}>⬆️ Update jetzt installieren</button></div>
    ${u.notes ? `<h2 class="section-header">Änderungen</h2><div class="card" style="font-size:13px;line-height:1.5;padding:12px">${md(u.notes)}</div>` : ''}
    ${u.log ? `<h2 class="section-header">Update-Protokoll</h2><pre style="font-size:11.5px;white-space:pre-wrap;color:var(--text-dim);padding:8px 4px">${esc(u.log)}</pre>` : ''}`;
  $('#upCheck').onclick = async () => { toast('Prüfe …'); await api('/api/admin/update/check', { method: 'POST' }); renderUpdate(); };
  $('#upNow').onclick = () => startUpdate();
}
async function startUpdate() {
  if (!confirm('Update jetzt installieren? Der Dienst startet dabei neu (ca. 1 Minute).')) return;
  const r = await api('/api/admin/update/now', { method: 'POST' }); toast(r.message);
  if (!r.ok) return;
  const old = S.me.version; let tries = 0;
  const poll = setInterval(async () => {
    tries++;
    try { const m = await api('/api/me'); if (m.version !== old) { clearInterval(poll); toast('✅ Aktualisiert auf ' + m.version); setTimeout(() => location.reload(), 1200); } } catch { /* Neustart */ }
    if (tries > 90) { clearInterval(poll); toast('Update dauert ungewöhnlich lange – Admin → Updates → Protokoll'); }
  }, 3000);
}
$('#updateNowBtn')?.addEventListener('click', () => startUpdate());
$('#updateInfoBtn')?.addEventListener('click', () => { S.adminSec = 'update'; showTab('admin'); });
$('#pwChangeBtn')?.addEventListener('click', () => { S.adminSec = 'users'; showTab('admin'); });

/* ---------- Start ---------- */
(async () => {
  try { await loadMe(); await loadInfo(); } catch { /* offline */ }
  connectWS();
  const h = location.hash.slice(1);
  if (['stats', 'nets'].includes(h) || (h === 'admin' && S.me?.user)) showTab(h);
})();
