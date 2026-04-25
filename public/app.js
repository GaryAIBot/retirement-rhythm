const statusBadge = document.getElementById('statusBadge');
const planForm = document.getElementById('planForm');
const personInput = document.getElementById('personInput');
const locationInput = document.getElementById('locationInput');
const vibeInput = document.getElementById('vibeInput');
const focusInput = document.getElementById('focusInput');
const demoBtn = document.getElementById('demoBtn');
const saveBtn = document.getElementById('saveBtn');
const refreshSavedBtn = document.getElementById('refreshSavedBtn');
const headline = document.getElementById('headline');
const summaryText = document.getElementById('summaryText');
const researchText = document.getElementById('researchText');
const rhythmList = document.getElementById('rhythmList');
const ideasList = document.getElementById('ideasList');
const safetyList = document.getElementById('safetyList');
const sources = document.getElementById('sources');
const savedStatus = document.getElementById('savedStatus');
const savedList = document.getElementById('savedList');

let currentPlan = null;

function setStatus(text, bad = false) {
  statusBadge.textContent = text;
  statusBadge.classList.toggle('bad', bad);
}

function renderList(el, items, empty) {
  el.innerHTML = '';
  if (!items || !items.length) {
    const li = document.createElement('li');
    li.textContent = empty;
    li.className = 'muted';
    el.appendChild(li);
    return;
  }
  for (const item of items) {
    const li = document.createElement('li');
    li.textContent = item;
    el.appendChild(li);
  }
}

function renderSources(items) {
  sources.innerHTML = '';
  if (!items || !items.length) {
    sources.innerHTML = '<p class="muted">Noch keine Quellen.</p>';
    return;
  }
  for (const item of items) {
    const a = document.createElement('a');
    a.href = item.url;
    a.target = '_blank';
    a.rel = 'noreferrer';
    a.className = 'source';
    a.innerHTML = `<strong>${item.title || item.url}</strong><span>${item.url}</span>`;
    sources.appendChild(a);
  }
}

function renderRhythm(items) {
  rhythmList.innerHTML = '';
  if (!items || !items.length) {
    rhythmList.innerHTML = '<p class="muted">Noch kein Tagesrhythmus.</p>';
    return;
  }
  for (const item of items) {
    const card = document.createElement('article');
    card.className = 'rhythm-card';
    card.innerHTML = `<strong>${item.time} · ${item.title}</strong><p>${item.note}</p>`;
    rhythmList.appendChild(card);
  }
}

function renderSaved(items) {
  savedList.innerHTML = '';
  if (!items || !items.length) {
    savedStatus.textContent = 'Noch keine gespeicherten Pläne.';
    return;
  }
  savedStatus.textContent = `${items.length} gespeicherte${items.length === 1 ? 'r Plan' : ' Pläne'} in Neon.`;
  for (const item of items) {
    const card = document.createElement('article');
    card.className = 'saved-card';
    card.innerHTML = `
      <div class="saved-meta">
        <strong>${item.personName} · ${item.location}</strong>
        <span>${item.createdAt ? new Date(item.createdAt).toLocaleString('de-CH') : ''}</span>
      </div>
      <p><strong>${item.headline}</strong></p>
      <p class="muted">${item.summary}</p>
    `;
    savedList.appendChild(card);
  }
}

function renderPlan(data) {
  currentPlan = data;
  headline.textContent = data.plan.headline;
  summaryText.textContent = data.plan.summary;
  researchText.textContent = data.research.summary || 'Keine Recherchezusammenfassung erhalten.';
  renderRhythm(data.plan.rhythm || []);
  renderList(ideasList, data.plan.activity_ideas, 'Keine Ideen erhalten.');
  renderList(safetyList, data.plan.safety_notes, 'Keine Hinweise erhalten.');
  renderSources(data.research.sources || []);
}

async function loadSaved() {
  savedStatus.textContent = 'Lade gespeicherte Pläne…';
  try {
    const res = await fetch('/api/saved-plans');
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.detail || 'Gespeicherte Pläne konnten nicht geladen werden');
    renderSaved(data.items || []);
  } catch (error) {
    savedStatus.textContent = error.message;
    savedList.innerHTML = '';
  }
}

async function run(url) {
  setStatus('Erstelle Plan...');
  try {
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.detail || 'Anfrage fehlgeschlagen');
    renderPlan(data);
    setStatus('Bereit');
  } catch (error) {
    setStatus('Fehler', true);
    headline.textContent = 'Anfrage fehlgeschlagen';
    summaryText.textContent = error.message;
  }
}

async function saveCurrentPlan() {
  if (!currentPlan?.plan?.headline) {
    savedStatus.textContent = 'Bitte zuerst einen Plan erstellen.';
    return;
  }
  savedStatus.textContent = 'Speichere Plan…';
  try {
    const res = await fetch('/api/saved-plans', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        personName: currentPlan.person,
        location: currentPlan.location,
        headline: currentPlan.plan.headline,
        summary: currentPlan.plan.summary,
        plan: currentPlan.plan,
      })
    });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.detail || 'Plan konnte nicht gespeichert werden');
    savedStatus.textContent = 'Plan in Neon gespeichert.';
    await loadSaved();
  } catch (error) {
    savedStatus.textContent = error.message;
  }
}

planForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const person = personInput.value.trim();
  const location = locationInput.value.trim();
  const vibe = vibeInput.value.trim();
  const focus = focusInput.value.trim();
  if (!person || !location || !focus || !vibe) return;
  await run(`/api/plan?person=${encodeURIComponent(person)}&location=${encodeURIComponent(location)}&focus=${encodeURIComponent(focus)}&vibe=${encodeURIComponent(vibe)}`);
});

demoBtn.addEventListener('click', async () => {
  await run('/api/demo');
});

saveBtn.addEventListener('click', async () => {
  await saveCurrentPlan();
});

refreshSavedBtn.addEventListener('click', async () => {
  await loadSaved();
});

(async () => {
  try {
    const res = await fetch('/api/health');
    const data = await res.json();
    const good = data.hasOpenAI && data.hasGoogle && data.hasDatabase;
    setStatus(good ? 'Bereit' : 'Setup unvollständig', !good);
  } catch {
    setStatus('Backend nicht erreichbar', true);
  }
  await loadSaved();
})();
