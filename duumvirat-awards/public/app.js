const ballot = document.getElementById('ballot');

const ERRORS = {
  rate_limited: 'Слишком много попыток. Попробуйте позже.',
  default: 'Не удалось отправить голос. Попробуйте ещё раз.',
};

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
    const retry = el('button', 'button', 'Повторить');
    retry.type = 'button';
    retry.addEventListener('click', onRetry);
    wrap.append(retry);
    ballot.append(wrap);
  }
}

function renderCategory(category, index, votedId) {
  const article = el('article', 'category');
  article.id = `nomination-${category.id}`;
  const form = el('form');
  form.noValidate = true;

  const fieldset = el('fieldset');
  const legend = el('legend');
  legend.append(
    el('span', 'category-num', String(index + 1).padStart(2, '0')),
    el('span', 'category-title', category.title),
  );
  const options = el('div', 'options');
  const inputs = category.candidates.map((candidate) => {
    const label = el('label', 'option');
    const input = el('input');
    input.type = 'radio';
    input.name = category.id;
    input.value = candidate.id;
    const mark = el('span', 'option-mark', '✓');
    mark.setAttribute('aria-hidden', 'true');
    label.append(input, mark, el('span', 'option-name', candidate.name));
    options.append(label);
    return input;
  });
  fieldset.append(legend, options);

  const actions = el('div', 'actions');
  const submit = el('button', 'button', 'Отдать голос');
  submit.type = 'submit';
  submit.disabled = true;
  const status = el('p', 'status');
  status.setAttribute('role', 'status');
  actions.append(submit, status);
  form.append(fieldset, actions);
  article.append(form);

  const setStatus = (text, kind) => {
    status.textContent = text;
    status.className = kind ? `status is-${kind}` : 'status';
  };

  const lock = (candidateId, message = 'Ваш голос принят') => {
    const chosen = inputs.find((input) => input.value === candidateId);
    if (chosen) {
      chosen.checked = true;
      chosen.closest('.option').append(el('span', 'option-tag', 'Ваш выбор'));
    }
    fieldset.disabled = true;
    submit.hidden = true;
    article.classList.add('is-voted');
    setStatus(message, 'success');
  };

  form.addEventListener('change', () => {
    submit.disabled = false;
    setStatus('');
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const candidateId = inputs.find((input) => input.checked)?.value;
    if (!candidateId || submit.disabled) return;

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
      if (response.ok) return lock(candidateId);
      if (response.status === 409) {
        return lock(data.candidateId || candidateId, 'Вы уже голосовали в этой номинации');
      }
      throw new Error(data.error);
    } catch (error) {
      // Keep the selection so the visitor can retry without choosing again.
      submit.disabled = false;
      submit.textContent = 'Повторить';
      setStatus(ERRORS[error.message] || ERRORS.default, 'error');
    }
  });

  if (votedId) lock(votedId);
  return article;
}

async function load() {
  ballot.setAttribute('aria-busy', 'true');
  showMessage('Загружаем номинации…');
  try {
    const response = await fetch('/api/ballot');
    if (!response.ok) throw new Error('load failed');
    const { categories, voted } = await response.json();
    ballot.replaceChildren(
      ...categories.map((category, index) => renderCategory(category, index, voted[category.id])),
    );
  } catch {
    showMessage('Не удалось загрузить номинации.', load);
  } finally {
    ballot.setAttribute('aria-busy', 'false');
  }
}

load();
