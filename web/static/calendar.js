const form        = document.getElementById('appointmentForm');
const list        = document.getElementById('appointmentList');
const countBadge  = document.getElementById('apptCount');
const formError   = document.getElementById('formError');
const formSuccess = document.getElementById('formSuccess');
const gcalSuccess = document.getElementById('gcalSuccess');
const gcalWarning = document.getElementById('gcalWarning');
const submitBtn   = document.getElementById('submitBtn');
const formTitle   = document.getElementById('formTitle');
const editingId   = document.getElementById('editingId');
const cancelBtn   = document.getElementById('cancelEditBtn');

const TODAY = new Date().toISOString().slice(0, 10);

// Store all loaded appointments by ID so onclick can reference them safely
const _apptMap = new Map();

// ── Load & render ──────────────────────────────────────────────────────────────

async function loadAppointments() {
  try {
    const res = await fetch('/calendar/all');
    const data = await res.json();
    renderList(data.appointments || []);
  } catch {
    list.innerHTML = '<div class="alert alert-error">Termine konnten nicht geladen werden.</div>';
  }
}

function renderList(appointments) {
  _apptMap.clear();
  appointments.forEach(a => _apptMap.set(a.appointment_id, a));

  const count = appointments.length;
  if (count > 0) {
    countBadge.textContent = count + ' Termin' + (count !== 1 ? 'e' : '');
    countBadge.style.display = 'inline-flex';
  } else {
    countBadge.style.display = 'none';
  }

  if (!count) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📋</div>
        <h3>Noch keine Termine</h3>
        <p style="color:var(--slate); font-size:.875rem; margin-top:.375rem;">
          Erstelle deinen ersten Termin links.
        </p>
      </div>`;
    return;
  }

  const sorted = [...appointments].sort((a, b) =>
    (a.date + a.time) < (b.date + b.time) ? -1 : 1
  );

  const todayAppts    = sorted.filter(a => a.date === TODAY);
  const upcomingAppts = sorted.filter(a => a.date !== TODAY);

  let html = '';

  if (todayAppts.length) {
    html += `<div class="today-section">
      <div class="today-section-label">Heute</div>
      ${todayAppts.map(renderCard).join('')}
    </div>`;
  }

  if (upcomingAppts.length) {
    const label = todayAppts.length ? 'Weitere Termine' : 'Anstehende Termine';
    html += `<div>
      <div class="upcoming-section-label">${label}</div>
      ${upcomingAppts.map(renderCard).join('')}
    </div>`;
  }

  list.innerHTML = html;
}

function renderCard(a) {
  const isToday = a.date === TODAY;
  const dateStr = a.date.split('-').reverse().join('.');
  const isCall  = a.type === 'Call';
  const todayTag = isToday ? `<div class="appt-today-tag">● Heute</div>` : '';
  const id = escAttr(a.appointment_id);

  return `<div class="appt-card${isToday ? ' today' : ''}" id="appt-${id}">
    <div style="flex:1; min-width:0;">
      ${todayTag}
      <div class="appt-title">
        ${escHtml(a.client_name)}
        <span class="appt-badge${isCall ? ' call' : ''}">${escHtml(a.type)}</span>
      </div>
      <div class="appt-meta">
        ${dateStr} · ${escHtml(a.time)} Uhr
        ${a.property_id ? `· <strong>${escHtml(a.property_id)}</strong>` : ''}
      </div>
      ${a.client_contact ? `<div class="appt-contact">📞 ${escHtml(a.client_contact)}</div>` : ''}
      ${a.notes ? `<div class="appt-notes">${escHtml(a.notes)}</div>` : ''}
    </div>
    <div style="display:flex; flex-direction:column; gap:.5rem; flex-shrink:0;">
      <button class="btn btn-outline btn-sm del-btn"
        style="color:var(--blue); border-color:var(--blue);"
        onclick="editAppointment('${id}')">
        Bearbeiten
      </button>
      <button class="btn btn-outline btn-sm del-btn"
        style="color:var(--red); border-color:var(--red-border);"
        onclick="deleteAppointment('${id}')">
        Löschen
      </button>
    </div>
  </div>`;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escAttr(str) {
  return String(str).replace(/['"&<>]/g, c => ({
    "'": '&#39;', '"': '&quot;', '&': '&amp;', '<': '&lt;', '>': '&gt;'
  }[c]));
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

function showSuccess(gcalSynced, gcalConfigured) {
  formSuccess.style.display = 'block';
  formError.style.display = 'none';
  if (gcalSynced) {
    gcalSuccess.style.display = 'block';
    gcalWarning.style.display = 'none';
  } else if (gcalConfigured) {
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
  }, 5000);
}

// ── Edit mode ──────────────────────────────────────────────────────────────────

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

  formTitle.textContent     = 'Termin bearbeiten';
  submitBtn.textContent     = 'Änderungen speichern';
  cancelBtn.style.display   = 'inline-flex';

  formSuccess.style.display = 'none';
  gcalSuccess.style.display = 'none';
  gcalWarning.style.display = 'none';
  formError.style.display   = 'none';

  form.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function cancelEdit() {
  editingId.value = '';
  form.reset();
  formTitle.textContent   = 'Neuen Termin erstellen';
  submitBtn.textContent   = 'Termin speichern';
  cancelBtn.style.display = 'none';
  formError.style.display = 'none';
}

// ── Form submit (create / update) ──────────────────────────────────────────────

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  formError.style.display   = 'none';
  formSuccess.style.display = 'none';
  gcalSuccess.style.display = 'none';
  gcalWarning.style.display = 'none';

  const client_name = form.client_name.value.trim();
  const date = form.date.value;
  const time = form.time.value;

  if (!client_name) return showError('Kundenname ist erforderlich.');
  if (!date)        return showError('Datum ist erforderlich.');
  if (!time)        return showError('Uhrzeit ist erforderlich.');

  submitBtn.disabled = true;
  submitBtn.textContent = 'Speichern…';

  const currentEditId = editingId.value;
  const isEditing = !!currentEditId;
  const url = isEditing ? '/calendar/update' : '/calendar/create';

  const payload = {
    property_id:    form.property_id.value.trim(),
    client_name,
    client_contact: form.client_contact.value.trim(),
    date,
    time,
    type:  form.type.value,
    notes: form.notes.value.trim(),
  };
  if (isEditing) payload.appointment_id = currentEditId;

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      showError(data.error || 'Fehler beim Speichern.');
    } else {
      cancelEdit();
      showSuccess(data.gcal_synced || false, data.gcal_configured || false);
      loadAppointments();
    }
  } catch {
    showError('Netzwerkfehler – bitte erneut versuchen.');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = isEditing ? 'Änderungen speichern' : 'Termin speichern';
  }
});

// ── Delete ─────────────────────────────────────────────────────────────────────

async function deleteAppointment(id) {
  if (!confirm('Termin wirklich löschen?')) return;

  if (editingId.value === id) cancelEdit();

  const card = document.getElementById('appt-' + id);
  if (card) {
    card.classList.add('removing');
    await new Promise(r => setTimeout(r, 220));
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

// ── GCal settings ──────────────────────────────────────────────────────────────

async function loadGcalId() {
  try {
    const res = await fetch('/api/profile');
    if (!res.ok) return;
    const data = await res.json();
    const input = document.getElementById('gcalIdInput');
    if (input && data.gcal_calendar_id) input.value = data.gcal_calendar_id;
  } catch {}
}

async function saveGcalId() {
  const input = document.getElementById('gcalIdInput');
  const msg   = document.getElementById('gcalSaveMsg');
  const btn   = document.getElementById('gcalSaveBtn');
  const val   = (input.value || '').trim();

  if (!val) {
    msg.textContent = 'Bitte eine Kalender-ID (E-Mail) eingeben.';
    msg.style.color = 'var(--red)';
    msg.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Speichern…';
  msg.style.display = 'none';

  try {
    const res = await fetch('/api/profile', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gcal_calendar_id: val }),
    });
    const data = await res.json();
    if (res.ok) {
      msg.textContent = '✓ Kalender-ID gespeichert.';
      msg.style.color = 'var(--green)';
    } else {
      msg.textContent = data.error || 'Fehler beim Speichern.';
      msg.style.color = 'var(--red)';
    }
  } catch {
    msg.textContent = 'Netzwerkfehler.';
    msg.style.color = 'var(--red)';
  } finally {
    msg.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Kalender-ID speichern';
  }
}

// ── Init ───────────────────────────────────────────────────────────────────────

loadAppointments();
loadGcalId();
