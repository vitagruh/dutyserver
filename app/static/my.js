(() => {
  'use strict';

  const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
  const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  const WD = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

  const state = { data: null, month: '', selected: new Set(), kind: 'unavailable', reason: '' };

  const el = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

  function parseISO(value) { return new Date(value + 'T12:00:00'); }
  function isoOf(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  }
  function fmtLong(value) {
    if (!value) return '—';
    const d = parseISO(value);
    return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`;
  }
  function fmtShort(value) {
    if (!value) return '—';
    const d = parseISO(value);
    return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`;
  }
  function monthLabel(month) {
    const [year, m] = month.split('-').map(Number);
    return `${MONTHS[m - 1]} ${year}`;
  }
  function shiftMonth(month, delta) {
    const [year, m] = month.split('-').map(Number);
    const d = new Date(year, m - 1 + delta, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  }
  function plural(n, one, few, many) {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
    return many;
  }

  function toast(message, kind = 'success') {
    const node = el('toast');
    node.textContent = message;
    node.className = `toast toast--${kind}`;
    node.hidden = false;
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => { node.hidden = true; }, 5200);
  }

  async function api(url, options = {}) {
    const opts = { ...options, headers: { ...(options.headers || {}) } };
    if (opts.body && typeof opts.body !== 'string') {
      opts.body = JSON.stringify(opts.body);
      opts.headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(url, opts);
    if (response.status === 401) {
      location.href = '/login';
      throw new Error('Сессия истекла — войдите заново');
    }
    const text = await response.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!response.ok) {
      let detail = data && typeof data === 'object' ? data.detail : data;
      if (Array.isArray(detail)) detail = detail.map((item) => item.msg || JSON.stringify(item)).join('; ');
      throw new Error(typeof detail === 'string' && detail ? detail : 'Ошибка запроса');
    }
    return data;
  }

  const act = (fn) => (...args) => {
    Promise.resolve().then(() => fn(...args)).catch((error) => toast(error.message || String(error), 'error'));
  };

  async function load() {
    try {
      state.data = await api('/api/me');
    } catch (error) {
      el('view').innerHTML = `
        <div class="empty-state" style="margin-top:40px">
          <strong>Кабинет недоступен</strong>
          ${esc(error.message || 'Не удалось загрузить данные')}
        </div>
      `;
      return;
    }
    const user = state.data.user;
    const nameNode = el('myUserName');
    if (nameNode) nameNode.textContent = user.personName || user.username;
    if (!state.month) state.month = state.data.today.slice(0, 7);
    render();
  }

  async function logout() {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch {
      /* сессия могла истечь — всё равно уходим на вход */
    }
    location.href = '/login';
  }

  function requestsByDate() {
    const map = new Map();
    for (const request of state.data.requests) {
      let cursor = parseISO(request.dateFrom);
      const finish = parseISO(request.dateTo);
      let guard = 0;
      while (cursor <= finish && guard < 400) {
        const iso = isoOf(cursor);
        if (!map.has(iso)) map.set(iso, []);
        map.get(iso).push(request);
        cursor = new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate() + 1);
        guard += 1;
      }
    }
    return map;
  }

  function render() {
    const data = state.data;
    const user = data.user;
    const person = data.person;
    const today = data.today;
    const horizonTo = data.horizonTo;
    const duties = new Map(data.duties.map((duty) => [duty.date, duty]));
    const holidays = new Map(data.holidays.map((holiday) => [holiday.date, holiday.name]));
    const requests = requestsByDate();
    const pending = data.requests.filter((item) => item.status === 'pending').length;
    const approved = data.requests.filter((item) => item.status === 'approved').length;

    document.title = `${person.name} — мои дежурства`;
    el('unitName').textContent = data.unitName;
    el('todayLabel').textContent = `сегодня ${fmtLong(today)}`;

    const [year, monthNum] = state.month.split('-').map(Number);
    const first = new Date(year, monthNum - 1, 1);
    const offset = (first.getDay() + 6) % 7;
    const gridFrom = new Date(year, monthNum - 1, 1 - offset);
    const cells = [];
    for (let index = 0; index < 42; index += 1) {
      const day = new Date(gridFrom.getFullYear(), gridFrom.getMonth(), gridFrom.getDate() + index);
      const iso = isoOf(day);
      const inMonth = day.getMonth() === monthNum - 1;
      const weekend = day.getDay() === 0 || day.getDay() === 6;
      const holiday = holidays.get(iso);
      const requestList = requests.get(iso) || [];
      const disabled = !inMonth || iso < today || iso > horizonTo;
      const classes = ['day'];
      if (!inMonth) classes.push('day--out');
      if (weekend) classes.push('day--weekend');
      if (holiday) classes.push('day--holiday');
      if (iso === today) classes.push('day--today');
      if (disabled && inMonth) classes.push('day--disabled');
      if (state.selected.has(iso)) classes.push('day--selected');

      const chips = [];
      const duty = duties.get(iso);
      if (duty) {
        const status = duty.status === 'done' ? 'выполнено' : duty.status === 'missed' ? 'неявка' : 'план';
        chips.push(`<span class="mini mini--duty">дежурство · ${status}</span>`);
      }
      for (const request of requestList) {
        if (request.kind === 'preferred') {
          chips.push(`<span class="mini mini--pref">просьба${request.status === 'declined' ? ' · отклонена' : ''}</span>`);
        } else if (request.status === 'approved') {
          chips.push('<span class="mini mini--req-approved">не могу · согласовано</span>');
        } else if (request.status === 'pending') {
          chips.push('<span class="mini mini--req">заявка · не могу</span>');
        }
      }
      if (state.selected.has(iso)) chips.push('<span class="mini mini--duty">выбрано</span>');

      cells.push(`
        <button type="button" class="${classes.join(' ')}" data-day="${iso}" ${disabled ? 'disabled' : ''}>
          <span class="day__top">
            <span class="day__num">${day.getDate()}</span>
            <span class="day__tags">${holiday ? '<span class="tag tag--holiday">праздник</span>' : ''}</span>
          </span>
          ${holiday ? `<span class="day__holiday">${esc(holiday)}</span>` : ''}
          ${chips.join('')}
        </button>
      `);
    }

    const canPrev = state.month > today.slice(0, 7);
    const canNext = state.month < horizonTo.slice(0, 7);
    const selectedDays = [...state.selected].sort();
    const requestRows = [...data.requests]
      .sort((a, b) => b.dateFrom.localeCompare(a.dateFrom))
      .map((request) => `
        <div class="my-request">
          <div>
            <div>
              <b>${fmtShort(request.dateFrom)}${request.dateFrom !== request.dateTo ? ` – ${fmtLong(request.dateTo)}` : ''}</b>
              <span class="pill pill--${request.kind === 'unavailable' ? 'unavailable' : 'preferred'}">${esc(request.kindLabel)}</span>
              <span class="pill pill--${request.status === 'approved' ? 'used' : request.status === 'declined' ? 'declined' : 'pending'}">${esc(request.statusLabel)}</span>
            </div>
            <div class="my-request__meta">${request.days} ${plural(request.days, 'день', 'дня', 'дней')}${request.reason ? ` · ${esc(request.reason)}` : ''}</div>
          </div>
          ${request.status === 'pending' ? `<button class="btn btn--sm btn--ghost" type="button" data-cancel="${request.id}">Отозвать</button>` : ''}
        </div>
      `).join('');

    el('view').innerHTML = `
      <div class="my-head">
        <div>
          <h2>${esc(person.name)}</h2>
          <p>${esc(person.note || 'Отметьте дни, когда вы не можете дежурить')}</p>
        </div>
        <div class="head-actions">
          <span class="pill pill--role-${esc(user.role)}">${esc(user.roleLabel)}</span>
          <span class="pill pill--pending">ожидают: ${pending}</span>
          <span class="pill pill--used">согласовано: ${approved}</span>
        </div>
      </div>

      ${person.active ? '' : '<div class="banner banner--danger" style="margin-bottom:16px">Сотрудник деактивирован — новые заявки недоступны.</div>'}

      <div class="kpis">
        <div class="kpi">
          <span class="kpi__label">Лимит заявок</span>
          <span class="kpi__value">${data.monthLimit || '—'}</span>
          <span class="kpi__sub">дней в месяц на сотрудника</span>
        </div>
        <div class="kpi">
          <span class="kpi__label">Горизонт планирования</span>
          <span class="kpi__value">${data.horizonDays}</span>
          <span class="kpi__sub">дней вперёд, до ${fmtLong(horizonTo)}</span>
        </div>
        <div class="kpi">
          <span class="kpi__label">Выбрано сейчас</span>
          <span class="kpi__value">${selectedDays.length}</span>
          <span class="kpi__sub">${plural(selectedDays.length, 'день', 'дня', 'дней')} в новой заявке</span>
        </div>
      </div>

      <div class="my-grid">
        <section class="panel" style="margin-top:0">
          <div class="panel__head">
            <div class="month-nav">
              <button class="icon-btn icon-btn--lg" type="button" data-shift="-1" ${canPrev ? '' : 'disabled'} aria-label="Предыдущий месяц">‹</button>
              <h3>${monthLabel(state.month)}</h3>
              <button class="icon-btn icon-btn--lg" type="button" data-shift="1" ${canNext ? '' : 'disabled'} aria-label="Следующий месяц">›</button>
            </div>
            <span class="small muted">нажмите на день, чтобы выбрать или снять</span>
          </div>
          <div class="calendar-wrap" style="box-shadow:none;border:0;padding:0">
            <div class="calendar my-calendar" style="min-width:0">
              ${WD.map((name) => `<div class="calendar__dow">${name}</div>`).join('')}
              ${cells.join('')}
            </div>
          </div>
          <div class="my-legend" style="margin-top:12px">
            <span><i style="background:var(--accent-soft);border:1px solid var(--accent-line)"></i>дежурство</span>
            <span><i style="background:#fff1dc"></i>заявка ожидает</span>
            <span><i style="background:var(--danger-soft)"></i>«не могу» согласовано</span>
            <span><i style="background:var(--info-soft)"></i>просьба не назначать</span>
          </div>
        </section>

        <div class="my-aside">
          <section class="panel" style="margin-top:0">
            <div class="panel__head"><h3>Новая заявка</h3></div>
            <form id="requestForm" class="form">
              <div class="my-kind">
                <label class="my-kind__option ${state.kind === 'unavailable' ? 'is-active' : ''}">
                  <input type="radio" name="kind" value="unavailable" ${state.kind === 'unavailable' ? 'checked' : ''}>
                  <span><b>Не могу дежурить</b><span>После согласования дни исключаются из графика.</span></span>
                </label>
                <label class="my-kind__option ${state.kind === 'preferred' ? 'is-active' : ''}">
                  <input type="radio" name="kind" value="preferred" ${state.kind === 'preferred' ? 'checked' : ''}>
                  <span><b>Предпочитаю не дежурить</b><span>Мягкая просьба: по возможности выберут другого.</span></span>
                </label>
              </div>
              <div class="field" style="margin-top:12px">
                <label for="requestReason">Причина (необязательно)</label>
                <input id="requestReason" type="text" name="reason" maxlength="200" value="${esc(state.reason)}" placeholder="например, учёба, семейные обстоятельства">
              </div>
              <div class="small muted" style="margin-top:8px">
                ${selectedDays.length
                  ? `Выбрано: ${selectedDays.map(fmtShort).join(', ')}`
                  : 'Дни не выбраны. Отметьте их в календаре.'}
              </div>
              <div class="btn-row" style="margin-top:12px">
                <button class="btn btn--primary" type="submit" ${selectedDays.length ? '' : 'disabled'}>Отправить на согласование</button>
                <button class="btn btn--ghost" type="button" id="clearSelection" ${selectedDays.length ? '' : 'disabled'}>Очистить</button>
              </div>
            </form>
          </section>

          <section class="panel" style="margin-top:0">
            <div class="panel__head">
              <h3>Мои заявки</h3>
              <span class="small muted">${data.requests.length}</span>
            </div>
            ${requestRows || '<div class="empty-state" style="padding:20px">Заявок пока нет.</div>'}
            <div class="small muted" style="margin-top:10px">
              Согласованные «не могу» блокируют назначение. Ожидающие заявки планировщик видит,
              но они не исключают из графика до согласования.
            </div>
          </section>

          <section class="panel" style="margin-top:0">
            <div class="panel__head">
              <h3>Аккаунт</h3>
              <span class="small muted">${esc(user.username)}</span>
            </div>
            <div class="account-row">
              <span><b>${esc(user.personName || person.name)}</b></span>
              <span class="small muted">${esc(user.roleLabel)}</span>
            </div>
            <form id="passwordForm" class="form" style="margin-top:12px">
              <div class="field">
                <label for="currentPassword">Текущий пароль</label>
                <input id="currentPassword" type="password" autocomplete="current-password" required>
              </div>
              <div class="field">
                <label for="newPassword">Новый пароль</label>
                <input id="newPassword" type="password" autocomplete="new-password" minlength="6" required>
              </div>
              <button class="btn btn--ghost btn--block" type="submit">Сменить пароль</button>
            </form>
          </section>
        </div>
      </div>
      <div class="note-panel" style="margin-top:16px">
        <strong>Как это работает.</strong>
        Заявки подаются на ${data.horizonDays} дней вперёд и не более ${data.monthLimit || '∞'} дней в месяц.
        Планировщик согласует или отклонит их; при согласовании дни «не могу» исключаются из распределения.
        Отозвать можно только заявку, ожидающую согласования.
      </div>
    `;

    bind();
  }

  function bind() {
    const view = el('view');
    view.querySelectorAll('[data-day]').forEach((button) => {
      button.addEventListener('click', () => {
        if (button.disabled) return;
        const iso = button.dataset.day;
        state.reason = el('requestReason')?.value || '';
        if (state.selected.has(iso)) state.selected.delete(iso);
        else state.selected.add(iso);
        render();
      });
    });
    view.querySelectorAll('[data-shift]').forEach((button) => {
      button.addEventListener('click', () => {
        state.month = shiftMonth(state.month, Number(button.dataset.shift));
        render();
      });
    });
    view.querySelectorAll('input[name="kind"]').forEach((input) => {
      input.addEventListener('change', () => {
        state.kind = input.value;
        state.reason = el('requestReason')?.value || '';
        render();
      });
    });
    const clear = el('clearSelection');
    if (clear) clear.addEventListener('click', () => { state.selected.clear(); render(); });

    const form = el('requestForm');
    if (form) {
      form.addEventListener('submit', act(async (event) => {
        event.preventDefault();
        const reason = form.querySelector('[name="reason"]').value.trim();
        const dates = [...state.selected].sort();
        if (!dates.length) { toast('Выберите дни в календаре', 'error'); return; }
        const result = await api('/api/me/requests', {
          method: 'POST',
          body: { dates, kind: state.kind, reason },
        });
        state.selected.clear();
        state.reason = '';
        const total = result.created.reduce((sum, item) => sum + item.days, 0);
        toast(`Заявка отправлена на согласование: ${total} ${plural(total, 'день', 'дня', 'дней')}`);
        await load();
      }));
    }

    const passForm = el('passwordForm');
    if (passForm) {
      passForm.addEventListener('submit', act(async (event) => {
        event.preventDefault();
        const current = el('currentPassword').value;
        const next = el('newPassword').value;
        if (next.length < 8) { toast('Пароль должен быть не короче 8 символов', 'error'); return; }
        await api('/api/auth/password', {
          method: 'POST',
          body: { current_password: current, new_password: next },
        });
        passForm.reset();
        toast('Пароль изменён');
      }));
    }

    view.querySelectorAll('[data-cancel]').forEach((button) => {
      button.addEventListener('click', act(async () => {
        if (!confirm('Отозвать заявку?')) return;
        await api(`/api/me/requests/${button.dataset.cancel}`, { method: 'DELETE' });
        toast('Заявка отозвана');
        await load();
      }));
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    const out = el('logoutBtn');
    if (out) out.addEventListener('click', logout);
    load();
  });
})();
