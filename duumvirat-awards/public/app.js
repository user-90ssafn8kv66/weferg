import { icon, heroCrystals } from '/art.js';

const ballot = document.getElementById('ballot');
const dialog = document.getElementById('vote-dialog');
const form = dialog.querySelector('form');
const fieldset = dialog.querySelector('fieldset');
const options = dialog.querySelector('.options');
const submit = dialog.querySelector('button[type="submit"]');
const status = dialog.querySelector('.status');
const backButton = dialog.querySelector('.ghost');

const ERRORS = {
  rate_limited: 'Слишком много попыток. Попробуйте позже.',
  default: 'Не удалось отправить голос. Попробуйте ещё раз.',
};

let voted = {};
let current = null;
const cards = new Map();

// Static artwork from art.js, never user data.
document.getElementById('hero-crystals').innerHTML = heroCrystals();

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function showMessage(text, onRetry) {
  const message = el('p', 'ballot-message', text);
  message.setAttribute('role', 'status');
  ballot.replaceChildren(message);
  if (onRetry) {
    const wrap = el('p', 'ballot-message');
    const retry = el('button', 'gem', 'Повторить');
    retry.type = 'button';
    retry.addEventListener('click', onRetry);
    wrap.append(retry);
    ballot.append(wrap);
  }
}

function setStatus(text, kind) {
  status.textContent = text;
  status.className = kind ? `status is-${kind}` : 'status';
}

function candidateName(category, candidateId) {
  return category.candidates.find((candidate) => candidate.id === candidateId)?.name;
}

function refreshCard(category) {
  const { card, cardStatus, button } = cards.get(category.id);
  const name = candidateName(category, voted[category.id]);
  card.classList.toggle('is-voted', Boolean(name));
  cardStatus.textContent = name ? `Ваш голос: ${name}` : 'Сделай выбор';
  button.textContent = name ? 'Голос принят' : 'Проголосовать';
  button.disabled = Boolean(name);
}

function renderCard(category) {
  const card = el('article', 'card');
  const art = el('div', 'card-icon');
  art.innerHTML = icon(category.icon);
  const cardStatus = el('p', 'card-status');
  const button = el('button', 'gem');
  button.type = 'button';
  button.addEventListener('click', () => openDialog(category));
  card.append(art, el('h3', 'card-title', category.title), cardStatus, button);
  cards.set(category.id, { card, cardStatus, button });
  refreshCard(category);
  return card;
}

function lockDialog(candidateId, message) {
  const chosen = options.querySelector(`input[value="${CSS.escape(candidateId)}"]`);
  if (chosen) {
    chosen.checked = true;
    chosen.closest('.option').append(el('span', 'option-tag', 'Ваш выбор'));
  }
  fieldset.disabled = true;
  submit.hidden = true;
  backButton.hidden = false;
  dialog.classList.add('is-locked');
  setStatus(message, 'success');
}

function openDialog(category) {
  current = category;
  dialog.querySelector('.vote-icon').innerHTML = icon(category.icon);
  dialog.querySelector('#vote-title').textContent = category.title;
  options.replaceChildren(
    ...category.candidates.map((candidate) => {
      const label = el('label', 'option');
      const input = el('input');
      input.type = 'radio';
      input.name = 'candidate';
      input.value = candidate.id;
      const mark = el('span', 'option-mark');
      mark.setAttribute('aria-hidden', 'true');
      label.append(input, mark, el('span', 'option-name', candidate.name));
      return label;
    }),
  );
  fieldset.disabled = false;
  submit.hidden = false;
  submit.disabled = true;
  submit.textContent = 'Отдать голос';
  backButton.hidden = true;
  dialog.classList.remove('is-locked');
  setStatus('');
  dialog.showModal();
}

form.addEventListener('change', () => {
  submit.disabled = false;
  setStatus('');
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const category = current;
  const candidateId = options.querySelector('input:checked')?.value;
  if (!category || !candidateId || submit.disabled) return;

  // The dialog may have been closed or reused while the request was in flight.
  const stillShown = () => dialog.open && current === category;
  const accept = (id, message) => {
    voted[category.id] = id;
    refreshCard(category);
    if (stillShown()) lockDialog(id, message);
  };

  submit.disabled = true;
  submit.textContent = 'Отправляем…';
  setStatus('');
  try {
    const response = await fetch('/api/vote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ categoryId: category.id, candidateId }),
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok) return accept(candidateId, 'Ваш голос принят');
    if (response.status === 409) {
      return accept(data.candidateId || candidateId, 'Вы уже голосовали');
    }
    throw new Error(data.error);
  } catch (error) {
    if (!stillShown()) return;
    // Keep the selection so the visitor can retry without choosing again.
    submit.disabled = false;
    submit.textContent = 'Повторить';
    setStatus(ERRORS[error.message] || ERRORS.default, 'error');
  }
});

dialog.querySelector('.vote-close').addEventListener('click', () => dialog.close());
backButton.addEventListener('click', () => dialog.close());
dialog.addEventListener('click', (event) => {
  if (event.target === dialog) dialog.close();
});

async function load() {
  ballot.setAttribute('aria-busy', 'true');
  showMessage('Загружаем номинации…');
  try {
    const response = await fetch('/api/ballot');
    if (!response.ok) throw new Error('load failed');
    const data = await response.json();
    voted = data.voted;
    cards.clear();
    ballot.replaceChildren(...data.categories.map(renderCard));
  } catch {
    showMessage('Не удалось загрузить номинации.', load);
  } finally {
    ballot.setAttribute('aria-busy', 'false');
  }
}

load();
