const form        = document.getElementById('appointmentForm');
const list        = document.getElementById('appointmentList');
const countBadge  = document.getElementById('apptCount');
const formError   = document.getElementById('formError');
const formSuccess = document.getElementById('formSuccess');
const gcalSuccess = document.getElementById('gcalSuccess');
const gcalWarning = document.getElementById('gcalWarning');
const submitBtn   = document.getElementById('submitBtn');
const submitLabel = document.getElementById('submitBtnLabel');
const formTitle   = document.getElementById('formTitle');
const editingId   = document.getElementById('editingId');
const cancelBtn   = document.getElementById('cancelEditBtn');

const TODAY = new Date().toISOString().slice(0, 10);

const _apptMap = new Map();
let _allAppointments = [];
let _currentFilter = 'all';
let _currentSearch = '';

// ── Helpers ────────────────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function escAttr(str) {
  return String(str).replace(/['"&<>]/g, c => ({
    "'": '&#39;', '"': '&quot;', '&': '&amp;', '<': '&lt;', '>': '&gt;'
  }[c]));
}

const DE_DAYS   = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
const DE_MONTHS = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                   'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];

function formatDateLabel(dateStr) {
  const d     = new Date(dateStr + 'T00:00:00');
  const today = new Date(TODAY + 'T00:00:00');
  const diff  = Math.round((d - today) / 86400000);
  const num   = d.getDate();
  const mon   = DE_MONTHS[d.getMonth()];
  const day   = DE_DAYS[d.getDay()];

  if (diff === 0)  return { label: `Heute · ${num}. ${mon}`,   isToday: true };
  if (diff === 1)  return { label: `Morgen · ${num}. ${mon}`,  isToday: false };
  if (diff === -1) return { label: `Gestern · ${num}. ${mon}`, isToday: false };
  return { label: `${day} · ${num}. ${mon}`, isToday: false };
}

// ── Filter / Search ────────────────────────────────────────────────────────────

function setFilter(f) {
  _currentFilter = f;
  document.querySelectorAll('.filter-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.filter === f)
  );
  renderFiltered();
}

function onSearch() {
  _currentSearch = (document.getElementById('searchInput').value || '').toLowerCase().trim();
  renderFiltered();
}

function getFiltered() {
  const weekEnd = new Date(TODAY);
  weekEnd.setDate(weekEnd.getDate() + 7);
  const weekEndStr = weekEnd.toISOString().slice(0, 10);

  let items = _allAppointments;
  switch (_currentFilter) {
    case 'today':    items = items.filter(a => a.date === TODAY); break;
    case 'week':     items = items.filter(a => a.date >= TODAY && a.date <= weekEndStr); break;
    case 'upcoming': items = items.filter(a => a.date >= TODAY); break;
  }
  if (_currentSearch) {
    const q = _currentSearch;
    items = items.filter(a =>
      a.client_name.toLowerCase().includes(q) ||
      (a.client_contact && a.client_contact.toLowerCase().includes(q)) ||
      (a.property_id    && a.property_id.toLowerCase().includes(q)) ||
      (a.notes          && a.notes.toLowerCase().includes(q))
    );
  }
  return items;
}

// ── Load & render ──────────────────────────────────────────────────────────────

async function loadAppointments() {
  try {
    const res  = await fetch('/calendar/all');
    const data = await res.json();
    const appts = data.appointments || [];
    _allAppointments = appts;
    _apptMap.clear();
    appts.forEach(a => _apptMap.set(a.appointment_id, a));
    const count = appts.length;
    if (count > 0) {
      countBadge.textContent = count + ' Termin' + (count !== 1 ? 'e' : '');
      countBadge.style.display = 'inline-flex';
    } else {
      countBadge.style.display = 'none';
    }
    renderFiltered();
  } catch {
    list.innerHTML = '<div class="alert alert-error">Termine konnten nicht geladen werden.</div>';
  }
}

function renderFiltered() {
  const items = getFiltered();

  if (!items.length) {
    const isGlobalEmpty = !_allAppointments.length;
    list.innerHTML = `
      <div class="cal-empty">
        <div class="cal-empty-icon">${isGlobalEmpty ? '📋' : '🔍'}</div>
        <h3>${isGlobalEmpty ? 'Noch keine Termine' : 'Keine Treffer'}</h3>
        <p>${isGlobalEmpty ? 'Erstelle deinen ersten Termin.' : 'Filter oder Suche anpassen.'}</p>
      </div>`;
    return;
  }

  const sorted = [...items].sort((a, b) =>
    (a.date + a.time) < (b.date + b.time) ? -1 : 1
  );

  const groups = new Map();
  sorted.forEach(a => {
    if (!groups.has(a.date)) groups.set(a.date, []);
    groups.get(a.date).push(a);
  });

  let html = '';
  for (const [date, appts] of groups) {
    const { label, isToday } = formatDateLabel(date);
    html += `<div class="date-group">
      <div class="date-group-label${isToday ? ' is-today' : ''}">${escHtml(label)}</div>
      ${appts.map(renderCard).join('')}
    </div>`;
  }
  list.innerHTML = html;
}

function renderCard(a) {
  const isToday = a.date === TODAY;
  const isCall  = a.type === 'Call';
  const id      = escAttr(a.appointment_id);
  const [h, m]  = (a.time || '00:00').split(':');

  return `<div class="appt-card${isToday ? ' is-today' : ''}" id="appt-${id}">
    <div class="appt-time-col">
      <div class="appt-time-hm">${escHtml(h)}:${escHtml(m)}</div>
      <div class="appt-time-uhr">Uhr</div>
      <div class="appt-dot${isCall ? ' call' : ''}"></div>
    </div>
    <div class="appt-body">
      <div class="appt-top">
        <div class="appt-name" title="${escAttr(a.client_name)}">${escHtml(a.client_name)}</div>
        <span class="appt-type-badge${isCall ? ' call' : ''}">${escHtml(a.type)}</span>
      </div>
      <div class="appt-meta-row">
        ${a.property_id    ? `<span class="appt-meta-chip"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>${escHtml(a.property_id)}</span>` : ''}
        ${a.client_contact ? `<span class="appt-meta-chip"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 13.5 19.79 19.79 0 0 1 1.6 4.9 2 2 0 0 1 3.56 2.69h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 10.91a16 16 0 0 0 6.18 6.18l1.28-.9a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>${escHtml(a.client_contact)}</span>` : ''}
      </div>
      ${a.notes ? `<div class="appt-notes-box">${escHtml(a.notes)}</div>` : ''}
    </div>
    <div class="appt-actions">
      <button class="appt-btn edit" onclick="editAppointment('${id}')">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
        Bearbeiten
      </button>
      <button class="appt-btn del" onclick="deleteAppointment('${id}')">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>
        Löschen
      </button>
    </div>
  </div>`;
}

// ── Banners ────────────────────────────────────────────────────────────────────

function showError(msg) {
  formError.textContent = msg;
  formError.style.display = 'block';
  formSuccess.style.display = 'none';
  gcalSuccess.style.display = 'none';
  gcalWarning.style.display = 'none';
  formError.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function showSuccess(gcalSynced, gcalConfigured, gcalError) {
  formSuccess.style.display = 'block';
  formError.style.display   = 'none';
  if (gcalSynced) {
    gcalSuccess.style.display = 'block';
    gcalWarning.style.display = 'none';
  } else if (gcalConfigured) {
    const detail = document.getElementById('gcalWarningDetail');
    if (detail && gcalError) detail.textContent = ' (' + gcalError + ')';
    gcalWarning.style.display = 'block';
    gcalSuccess.style.display = 'none';
  } else {
    gcalSuccess.style.display = 'none';
    gcalWarning.style.display = 'none';
  }
  setTimeout(() => {
    formSuccess.style.display = 'none';
    gcalSuccess.style.display = 'none';
    gcalWarning.style.display = 'none';
  }, 12000);
}

// ── Edit mode ──────────────────────────────────────────────────────────────────

function _setFormLabels(editing) {
  const label = editing ? 'Termin bearbeiten' : 'Neuen Termin erstellen';
  formTitle.textContent = label;
  const mTitle = document.getElementById('mobileFormTitle');
  if (mTitle) mTitle.textContent = label;
  if (submitLabel) submitLabel.textContent = editing ? 'Änderungen speichern' : 'Termin speichern';
  cancelBtn.style.display = editing ? 'inline-flex' : 'none';
}

function editAppointment(id) {
  const a = _apptMap.get(id);
  if (!a) return;

  editingId.value           = a.appointment_id;
  form.client_name.value    = a.client_name    || '';
  form.client_contact.value = a.client_contact || '';
  form.date.value           = a.date           || '';
  form.time.value           = a.time           || '';
  form.type.value           = a.type           || 'Besichtigung';
  form.property_id.value    = a.property_id    || '';
  form.notes.value          = a.notes          || '';

  _setFormLabels(true);
  ['formSuccess', 'gcalSuccess', 'gcalWarning', 'formError'].forEach(elId => {
    const el = document.getElementById(elId);
    if (el) el.style.display = 'none';
  });

  if (window.innerWidth <= 900) {
    openMobileForm();
  } else {
    document.getElementById('calLeftCol').scrollIntoView({ behavior: 'smooth', block: 'start' });
    form.client_name.focus();
  }
}

function cancelEdit() {
  editingId.value = '';
  form.reset();
  _setFormLabels(false);
  formError.style.display = 'none';
}

// ── Form submit ────────────────────────────────────────────────────────────────

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  formError.style.display   = 'none';
  formSuccess.style.display = 'none';
  gcalSuccess.style.display = 'none';
  gcalWarning.style.display = 'none';

  const client_name = form.client_name.value.trim();
  const date        = form.date.value;
  const time        = form.time.value;

  if (!client_name) return showError('Kundenname ist erforderlich.');
  if (!date)        return showError('Datum ist erforderlich.');
  if (!time)        return showError('Uhrzeit ist erforderlich.');

  submitBtn.disabled = true;
  if (submitLabel) submitLabel.textContent = 'Speichern…';

  const currentEditId = editingId.value;
  const isEditing     = !!currentEditId;
  const url           = isEditing ? '/calendar/update' : '/calendar/create';
  const payload = {
    property_id:    form.property_id.value.trim(),
    client_name,
    client_contact: form.client_contact.value.trim(),
    date, time,
    type:  form.type.value,
    notes: form.notes.value.trim(),
  };
  if (isEditing) payload.appointment_id = currentEditId;

  try {
    const res  = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      showError(data.error || 'Fehler beim Speichern.');
    } else {
      cancelEdit();
      closeMobileForm();
      showSuccess(data.gcal_synced || false, data.gcal_configured || false, data.gcal_error || null);
      loadAppointments();
    }
  } catch {
    showError('Netzwerkfehler – bitte erneut versuchen.');
  } finally {
    submitBtn.disabled = false;
    if (submitLabel) submitLabel.textContent = isEditing ? 'Änderungen speichern' : 'Termin speichern';
  }
});

// ── Delete ─────────────────────────────────────────────────────────────────────

async function deleteAppointment(id) {
  if (!confirm('Termin wirklich löschen?')) return;
  if (editingId.value === id) cancelEdit();

  const card = document.getElementById('appt-' + id);
  if (card) {
    card.classList.add('removing');
    await new Promise(r => setTimeout(r, 200));
  }

  try {
    const res = await fetch('/calendar/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ appointment_id: id }),
    });
    if (res.ok) loadAppointments();
  } catch {
    alert('Fehler beim Löschen.');
    if (card) card.classList.remove('removing');
  }
}

// ── Mobile drawer ──────────────────────────────────────────────────────────────

function openMobileForm() {
  document.getElementById('calLeftCol').classList.add('mobile-open');
  document.body.style.overflow = 'hidden';
}

function closeMobileForm() {
  document.getElementById('calLeftCol').classList.remove('mobile-open');
  document.body.style.overflow = '';
}

document.getElementById('calLeftCol').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closeMobileForm();
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeMobileForm();
});

// ── GCal settings ──────────────────────────────────────────────────────────────

async function loadGcalId() {
  try {
    const res  = await fetch('/api/profile');
    if (!res.ok) return;
    const data = await res.json();
    const inp  = document.getElementById('gcalIdInput');
    if (inp && data.gcal_calendar_id) inp.value = data.gcal_calendar_id;
  } catch {}
}

async function saveGcalId() {
  const inp = document.getElementById('gcalIdInput');
  const msg = document.getElementById('gcalSaveMsg');
  const btn = document.getElementById('gcalSaveBtn');
  const val = (inp.value || '').trim();

  if (!val) {
    msg.textContent   = 'Bitte eine Kalender-ID eingeben.';
    msg.style.color   = 'var(--red)';
    msg.style.display = 'block';
    return;
  }
  btn.disabled    = true;
  btn.textContent = 'Speichern…';
  msg.style.display = 'none';

  try {
    const res  = await fetch('/api/profile', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gcal_calendar_id: val }),
    });
    const data = await res.json();
    msg.textContent = res.ok ? '✓ Kalender-ID gespeichert.' : (data.error || 'Fehler.');
    msg.style.color = res.ok ? 'var(--green)' : 'var(--red)';
  } catch {
    msg.textContent = 'Netzwerkfehler.';
    msg.style.color = 'var(--red)';
  } finally {
    msg.style.display = 'block';
    btn.disabled    = false;
    btn.textContent = 'Kalender-ID speichern';
  }
}

// ── Init ───────────────────────────────────────────────────────────────────────

loadAppointments();
loadGcalId();
