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
  const todayTag = isToday
    ? `<div class="appt-today-tag">● Heute</div>`
    : '';

  return `<div class="appt-card${isToday ? ' today' : ''}" id="appt-${escHtml(a.appointment_id)}">
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
      ${a.client_contact
        ? `<div class="appt-contact">📞 ${escHtml(a.client_contact)}</div>`
        : ''}
      ${a.notes
        ? `<div class="appt-notes">${escHtml(a.notes)}</div>`
        : ''}
    </div>
    <div style="display:flex; flex-direction:column; gap:.5rem; flex-shrink:0;">
      <button class="btn btn-outline btn-sm del-btn"
        style="color:var(--blue); border-color:var(--blue);"
        onclick="editAppointment(${JSON.stringify(a)})">
        Bearbeiten
      </button>
      <button class="btn btn-outline btn-sm del-btn"
        style="color:var(--red); border-color:var(--red-border);"
        onclick="deleteAppointment('${escHtml(a.appointment_id)}')">
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

function editAppointment(a) {
  editingId.value = a.appointment_id;
  form.client_name.value    = a.client_name    || '';
  form.client_contact.value = a.client_contact || '';
  form.date.value           = a.date           || '';
  form.time.value           = a.time           || '';
  form.type.value           = a.type           || 'Besichtigung';
  form.property_id.value    = a.property_id    || '';
  form.notes.value          = a.notes          || '';

  formTitle.textContent   = 'Termin bearbeiten';
  submitLabel.textContent = 'Änderungen speichern';
  cancelBtn.style.display = 'inline-flex';

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
  submitLabel.textContent = 'Termin speichern';
  cancelBtn.style.display = 'none';
  formError.style.display = 'none';
}

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
  submitBtn.innerHTML = '<span class="spinner"></span> Speichern…';

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
    submitBtn.innerHTML = `<span id="submitBtnLabel">${isEditing ? 'Änderungen speichern' : 'Termin speichern'}</span>`;
    // Re-grab label reference after innerHTML reset
    const newLabel = document.getElementById('submitBtnLabel');
    if (!isEditing) {
      submitBtn.innerHTML = '<span id="submitBtnLabel">Termin speichern</span>';
    }
  }
});

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

loadAppointments();
