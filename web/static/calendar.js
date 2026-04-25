'use strict';

// ── Element refs ────────────────────────────────────────────────
const apptList  = document.getElementById('apptList');
const cntBadge  = document.getElementById('cntBadge');
const mOk       = document.getElementById('mOk');
const mGcal     = document.getElementById('mGcal');
const mGwarn    = document.getElementById('mGwarn');
const mErr      = document.getElementById('mErr');
const editingId = document.getElementById('editingId');
const formTitle = document.getElementById('formTitle');
const cancelBtn = document.getElementById('cancelBtn');
const saveBtn   = document.getElementById('saveBtn');
const saveLbl   = document.getElementById('saveLbl');
const apptForm  = document.getElementById('apptForm');

// Form fields
const fName    = document.getElementById('f_name');
const fContact = document.getElementById('f_contact');
const fDate    = document.getElementById('f_date');
const fTime    = document.getElementById('f_time');
const fType    = document.getElementById('f_type');
const fProp    = document.getElementById('f_prop');
const fNotes   = document.getElementById('f_notes');

const TODAY = new Date().toISOString().slice(0, 10);

let _all  = [];
let _map  = new Map();
let _filt = 'all';
let _q    = '';

// ── Helpers ─────────────────────────────────────────────────────
const esc = s => String(s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');

const DE_D = ['So','Mo','Di','Mi','Do','Fr','Sa'];
const DE_M = ['Januar','Februar','März','April','Mai','Juni',
              'Juli','August','September','Oktober','November','Dezember'];

function dateLabel(iso) {
  const d = new Date(iso + 'T00:00:00');
  const diff = Math.round((d - new Date(TODAY + 'T00:00:00')) / 86400000);
  const s = `${d.getDate()}. ${DE_M[d.getMonth()]}`;
  if (diff ===  0) return { txt: `Heute · ${s}`,   today: true };
  if (diff ===  1) return { txt: `Morgen · ${s}`,  today: false };
  if (diff === -1) return { txt: `Gestern · ${s}`, today: false };
  return { txt: `${DE_D[d.getDay()]} · ${s}`, today: false };
}

// ── Filter & render ──────────────────────────────────────────────
function setF(f) {
  _filt = f;
  document.querySelectorAll('.chip').forEach(c =>
    c.classList.toggle('on', c.dataset.f === f));
  render();
}

function onSearch() {
  _q = (document.getElementById('srchIn').value || '').toLowerCase().trim();
  render();
}

function filtered() {
  const we = new Date(TODAY);
  we.setDate(we.getDate() + 7);
  const wes = we.toISOString().slice(0, 10);
  let r = _all;
  if (_filt === 'today')    r = r.filter(a => a.date === TODAY);
  if (_filt === 'week')     r = r.filter(a => a.date >= TODAY && a.date <= wes);
  if (_filt === 'upcoming') r = r.filter(a => a.date >= TODAY);
  if (_q) r = r.filter(a =>
    a.client_name.toLowerCase().includes(_q) ||
    (a.client_contact||'').toLowerCase().includes(_q) ||
    (a.property_id||'').toLowerCase().includes(_q) ||
    (a.notes||'').toLowerCase().includes(_q)
  );
  return r;
}

function render() {
  const items = filtered();

  if (!items.length) {
    const empty = !_all.length;
    apptList.innerHTML = `<div class="empty">
      <div class="empty-ico">${empty ? '📋' : '🔍'}</div>
      <h3>${empty ? 'Noch keine Termine' : 'Keine Treffer'}</h3>
      <p>${empty ? 'Erstelle deinen ersten Termin.' : 'Filter oder Suche anpassen.'}</p>
    </div>`;
    return;
  }

  const sorted = [...items].sort((a, b) => (a.date+a.time) < (b.date+b.time) ? -1 : 1);
  const groups = new Map();
  sorted.forEach(a => {
    if (!groups.has(a.date)) groups.set(a.date, []);
    groups.get(a.date).push(a);
  });

  let html = '';
  for (const [date, appts] of groups) {
    const { txt, today } = dateLabel(date);
    html += `<div class="dg">
      <div class="dg-lbl${today ? ' today' : ''}">${esc(txt)}</div>
      ${appts.map(card).join('')}
    </div>`;
  }
  apptList.innerHTML = html;
}

function card(a) {
  const isToday = a.date === TODAY;
  const isCall  = a.type === 'Call';
  const id      = esc(a.appointment_id);
  const [h, m]  = (a.time || '00:00').split(':');

  // SVG icons inline for clean rendering
  const icoHome = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`;
  const icoPhone = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 13.5a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.56 2.69h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 10.91a16 16 0 0 0 6.18 6.18l1.28-.9a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>`;
  const icoEdit = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`;
  const icoTrash = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>`;

  return `<div class="ac${isToday ? ' today' : ''}" id="ac-${id}">
    <div class="at">
      <div class="at-hm">${esc(h)}:${esc(m)}</div>
      <div class="at-uhr">Uhr</div>
      <div class="at-dot${isCall ? ' call' : ''}"></div>
    </div>
    <div class="ab">
      <div class="ab-r1">
        <div class="ab-name" title="${esc(a.client_name)}">${esc(a.client_name)}</div>
        <span class="ab-type${isCall ? ' call' : ''}">${esc(a.type)}</span>
      </div>
      <div class="ab-meta">
        ${a.property_id    ? `<span class="ab-chip">${icoHome}${esc(a.property_id)}</span>` : ''}
        ${a.client_contact ? `<span class="ab-chip">${icoPhone}${esc(a.client_contact)}</span>` : ''}
      </div>
      ${a.notes ? `<div class="ab-notes">${esc(a.notes)}</div>` : ''}
    </div>
    <div class="aa">
      <button class="aa-btn e" onclick="editAppt('${id}')">${icoEdit} Bearbeiten</button>
      <button class="aa-btn d" onclick="delAppt('${id}')">${icoTrash} Löschen</button>
    </div>
  </div>`;
}

// ── Load ─────────────────────────────────────────────────────────
async function load() {
  try {
    const r = await fetch('/calendar/all');
    const d = await r.json();
    _all = d.appointments || [];
    _map.clear();
    _all.forEach(a => _map.set(a.appointment_id, a));
    const n = _all.length;
    cntBadge.textContent = n + ' Termin' + (n !== 1 ? 'e' : '');
    cntBadge.style.display = n ? 'inline-flex' : 'none';
    render();
  } catch {
    apptList.innerHTML = '<div class="alert alert-error">Laden fehlgeschlagen.</div>';
  }
}

// ── Alerts ───────────────────────────────────────────────────────
let _alertTimer;
function showAlerts(ok, gcalSynced, gcalConfigured, gcalError) {
  [mOk, mGcal, mGwarn, mErr].forEach(el => el.style.display = 'none');
  if (ok) mOk.style.display = 'block';
  if (gcalSynced) { mGcal.style.display = 'block'; }
  else if (gcalConfigured) {
    const d = document.getElementById('mGwarnD');
    if (d && gcalError) d.textContent = ' (' + gcalError + ')';
    mGwarn.style.display = 'block';
  }
  clearTimeout(_alertTimer);
  _alertTimer = setTimeout(() => [mOk, mGcal, mGwarn].forEach(el => el.style.display = 'none'), 10000);
}

function showErr(msg) {
  mErr.textContent = msg;
  mErr.style.display = 'block';
  [mOk, mGcal, mGwarn].forEach(el => el.style.display = 'none');
  mErr.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Form helpers ─────────────────────────────────────────────────
function setTitles(editing) {
  const t = editing ? 'Termin bearbeiten' : 'Neuen Termin erstellen';
  const ts = editing ? 'Termin bearbeiten' : 'Neuer Termin';
  formTitle.textContent = t;
  document.getElementById('dTitle').textContent = ts;
  saveLbl.textContent = editing ? 'Änderungen speichern' : 'Termin speichern';
  cancelBtn.style.display = editing ? 'inline-flex' : 'none';
}

function resetForm() {
  editingId.value = '';
  apptForm.reset();
  setTitles(false);
  mErr.style.display = 'none';
}

// ── Edit ─────────────────────────────────────────────────────────
function editAppt(id) {
  const a = _map.get(id);
  if (!a) return;
  editingId.value = a.appointment_id;
  fName.value    = a.client_name    || '';
  fContact.value = a.client_contact || '';
  fDate.value    = a.date           || '';
  fTime.value    = a.time           || '';
  fType.value    = a.type           || 'Besichtigung';
  fProp.value    = a.property_id    || '';
  fNotes.value   = a.notes          || '';
  setTitles(true);
  [mOk, mGcal, mGwarn, mErr].forEach(el => el.style.display = 'none');

  if (window.innerWidth <= 900) {
    openDrawer();
  } else {
    document.getElementById('formCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
    fName.focus();
  }
}

function cancelEdit() {
  resetForm();
  if (window.innerWidth <= 900) closeDrawer();
}

// ── Submit ───────────────────────────────────────────────────────
apptForm.addEventListener('submit', async e => {
  e.preventDefault();
  [mOk, mGcal, mGwarn, mErr].forEach(el => el.style.display = 'none');

  const name = fName.value.trim();
  const date = fDate.value;
  const time = fTime.value;
  if (!name) return showErr('Kundenname ist erforderlich.');
  if (!date) return showErr('Datum ist erforderlich.');
  if (!time) return showErr('Uhrzeit ist erforderlich.');

  const editing = !!editingId.value;
  saveBtn.disabled = true;
  saveLbl.textContent = 'Speichern…';

  const body = {
    client_name:    name,
    client_contact: fContact.value.trim(),
    date, time,
    type:        fType.value,
    property_id: fProp.value.trim(),
    notes:       fNotes.value.trim(),
  };
  if (editing) body.appointment_id = editingId.value;

  try {
    const res = await fetch(editing ? '/calendar/update' : '/calendar/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) { showErr(data.error || 'Fehler beim Speichern.'); return; }
    resetForm();
    closeDrawer();
    showAlerts(true, data.gcal_synced || false, data.gcal_configured || false, data.gcal_error || null);
    await load();
  } catch {
    showErr('Netzwerkfehler — bitte erneut versuchen.');
  } finally {
    saveBtn.disabled = false;
    saveLbl.textContent = editing ? 'Änderungen speichern' : 'Termin speichern';
  }
});

// ── Delete ───────────────────────────────────────────────────────
async function delAppt(id) {
  if (!confirm('Termin wirklich löschen?')) return;
  if (editingId.value === id) cancelEdit();
  const el = document.getElementById('ac-' + id);
  if (el) { el.classList.add('out'); await new Promise(r => setTimeout(r, 180)); }
  try {
    const res = await fetch('/calendar/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ appointment_id: id }),
    });
    if (res.ok) load();
    else if (el) el.classList.remove('out');
  } catch {
    alert('Fehler beim Löschen.');
    if (el) el.classList.remove('out');
  }
}

// ── Drawer ───────────────────────────────────────────────────────
const dOverlay = document.getElementById('dOverlay');
const dSlot    = document.getElementById('dSlot');
const calSide  = document.getElementById('calSide');
const formCard = document.getElementById('formCard');

function openDrawer() {
  dSlot.appendChild(formCard);         // move form card into drawer
  dOverlay.classList.add('open');
  document.body.style.overflow = 'hidden';
  setTimeout(() => fName.focus(), 300);
}

function closeDrawer() {
  dOverlay.classList.remove('open');
  document.body.style.overflow = '';
  // move form card back to sidebar
  calSide.insertBefore(formCard, calSide.firstChild);
}

function onOvClick(e) {
  if (e.target === dOverlay) closeDrawer();
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && dOverlay.classList.contains('open')) closeDrawer();
});

// ── GCal settings ────────────────────────────────────────────────
async function loadGcal() {
  try {
    const r = await fetch('/api/profile');
    if (!r.ok) return;
    const d = await r.json();
    const inp = document.getElementById('gcalIn');
    if (inp && d.gcal_calendar_id) inp.value = d.gcal_calendar_id;
  } catch {}
}

async function saveGcal() {
  const inp = document.getElementById('gcalIn');
  const msg = document.getElementById('gcalMsg');
  const btn = document.getElementById('gcalBtn');
  const val = (inp.value || '').trim();
  if (!val) {
    msg.style.cssText = 'display:block; color:var(--red)';
    msg.textContent = 'Bitte eine Kalender-ID eingeben.'; return;
  }
  btn.disabled = true; btn.textContent = 'Speichern…'; msg.style.display = 'none';
  try {
    const res = await fetch('/api/profile', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gcal_calendar_id: val }),
    });
    const d = await res.json();
    msg.textContent = res.ok ? '✓ Kalender-ID gespeichert.' : (d.error || 'Fehler.');
    msg.style.cssText = `display:block; color:${res.ok ? 'var(--green)' : 'var(--red)'}`;
  } catch {
    msg.textContent = 'Netzwerkfehler.';
    msg.style.cssText = 'display:block; color:var(--red)';
  } finally {
    btn.disabled = false; btn.textContent = 'Kalender-ID speichern';
  }
}

// ── Init ─────────────────────────────────────────────────────────
load();
loadGcal();
