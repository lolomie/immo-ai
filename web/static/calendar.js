const form = document.getElementById('appointmentForm');
const list = document.getElementById('appointmentList');
const countBadge = document.getElementById('apptCount');
const formError = document.getElementById('formError');
const formSuccess = document.getElementById('formSuccess');
const submitBtn = document.getElementById('submitBtn');

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
  countBadge.textContent = count + ' Termin' + (count !== 1 ? 'e' : '');
  countBadge.style.display = count ? 'inline-flex' : 'none';

  if (!count) {
    list.innerHTML = `<div class="empty-state">
      <div class="empty-state-icon">📋</div>
      <h3>Noch keine Termine</h3>
      <p>Erstelle deinen ersten Termin links.</p>
    </div>`;
    return;
  }

  const sorted = [...appointments].sort((a, b) => (a.date + a.time) < (b.date + b.time) ? -1 : 1);
  list.innerHTML = sorted.map(a => {
    const dateStr = a.date.split('-').reverse().join('.');
    const isCall = a.type === 'Call';
    return `<div class="appt-card">
      <div style="flex:1; min-width:0;">
        <div class="appt-title">
          ${escHtml(a.client_name)}
          <span class="appt-badge${isCall ? ' call' : ''}">${escHtml(a.type)}</span>
        </div>
        <div class="appt-meta">
          ${dateStr} um ${escHtml(a.time)} Uhr
          ${a.property_id ? '· Objekt: ' + escHtml(a.property_id) : ''}
          ${a.client_contact ? '· ' + escHtml(a.client_contact) : ''}
        </div>
        ${a.notes ? `<div style="font-size:.8rem; color:var(--slate); margin-top:.35rem;">${escHtml(a.notes)}</div>` : ''}
      </div>
      <button class="btn btn-danger btn-sm" onclick="deleteAppointment('${escHtml(a.appointment_id)}')">Löschen</button>
    </div>`;
  }).join('');
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
}

function showSuccess() {
  formSuccess.style.display = 'block';
  formError.style.display = 'none';
  setTimeout(() => { formSuccess.style.display = 'none'; }, 3000);
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  formError.style.display = 'none';
  formSuccess.style.display = 'none';

  const client_name = form.client_name.value.trim();
  const date = form.date.value;
  const time = form.time.value;

  if (!client_name) return showError('Kundenname ist erforderlich.');
  if (!date) return showError('Datum ist erforderlich.');
  if (!time) return showError('Uhrzeit ist erforderlich.');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return showError('Ungültiges Datumsformat.');
  if (!/^\d{2}:\d{2}$/.test(time)) return showError('Ungültiges Uhrzeitformat.');

  submitBtn.disabled = true;
  submitBtn.innerHTML = '<span class="spinner"></span> Speichern…';

  try {
    const res = await fetch('/calendar/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        property_id: form.property_id.value.trim(),
        client_name,
        client_contact: form.client_contact.value.trim(),
        date,
        time,
        type: form.type.value,
        notes: form.notes.value.trim(),
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      showError(data.error || 'Fehler beim Speichern.');
    } else {
      form.reset();
      showSuccess();
      loadAppointments();
    }
  } catch {
    showError('Netzwerkfehler – bitte erneut versuchen.');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Termin speichern';
  }
});

async function deleteAppointment(id) {
  if (!confirm('Termin wirklich löschen?')) return;
  try {
    const res = await fetch('/calendar/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ appointment_id: id }),
    });
    if (res.ok) loadAppointments();
  } catch {
    alert('Fehler beim Löschen.');
  }
}

loadAppointments();
