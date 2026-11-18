(() => {
  'use strict';

  const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
  const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  const WD = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
  const WD_FULL = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];

  const STATUS_LABEL = { planned: 'Плановое', done: 'Выполнено', missed: 'Неявка', cancelled: 'Отменено' };
  const SOURCE_LABEL = { manual: 'Вручную', auto: 'Автораспределение', draw: 'Жребий' };
  const COMP_LABEL = { pending: 'Не оформлен', scheduled: 'Запланирован', used: 'Использован', declined: 'Отказ' };
  const KIND_LABEL = { vacation: 'Отпуск', sick: 'Болезнь', trip: 'Командировка', other: 'Другое' };
  const KIND_SHORT = { vacation: 'отпуск', sick: 'болезнь', trip: 'командировка', other: 'отсутствие' };
  const REQ_KIND_LABEL = { unavailable: 'Не может дежурить', preferred: 'Предпочитает не дежурить' };
  const REQ_KIND_SHORT = { unavailable: 'не может', preferred: 'просит не назначать' };
  const REQ_STATUS_LABEL = { pending: 'Ожидает согласования', approved: 'Согласована', declined: 'Отклонена' };
  const ROLE_LABEL = { admin: 'Администратор', teamlead: 'Тимлид', employee: 'Сотрудник' };
  const NOTIFY_STATUS = { pending: 'В очереди', sent: 'Отправлено', error: 'Ошибка', skipped: 'Пропущено' };
  const DRAW_MODE_LABEL = { load: 'По нагрузке', month: 'Дежурства за месяц', equal: 'Равные шансы' };

  const S = {
    month: null,
    data: null,
    tab: 'schedule',
    today: '',
    settings: null,
    people: [],
    holidays: [],
    user: null,
    compsFilter: 'all',
    requestsFilter: 'pending',
    requestsData: null,
    statsData: null,
    compsData: null,
    stats: null,
    coverageData: null,
    usersData: null,
    notifications: null,
  };

  const el = (id) => document.getElementById(id);
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  /* ---------- utils ---------- */

  const ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ESC_MAP[ch]);
  }

  function parseISO(value) { return new Date(value + 'T12:00:00'); }

  function fmtShort(value) {
    if (!value) return '—';
    const d = parseISO(value);
    return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`;
  }

  function fmtLong(value) {
    if (!value) return '—';
    const d = parseISO(value);
    return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`;
  }

  function fullDate(value) {
    const d = parseISO(value);
    return `${d.getDate()} ${MONTHS_GEN[d.getMonth()]} ${d.getFullYear()}, ${WD_FULL[(d.getDay() + 6) % 7].toLowerCase()}`;
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

  function lastDayOfMonth(month) {
    const [year, m] = month.split('-').map(Number);
    const d = new Date(year, m, 0);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  function addDays(value, days) {
    const d = parseISO(value);
    d.setDate(d.getDate() + days);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  function pct(probability) {
    const value = Number(probability || 0) * 100;
    if (!value) return '0%';
    return value >= 10 ? `${value.toFixed(0)}%` : `${value.toFixed(1)}%`;
  }

  function initials(name) {
    const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '—';
    return (parts[0][0] + (parts[1] ? parts[1][0] : '')).toUpperCase();
  }

  function plural(n, one, few, many) {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
    return many;
  }

  function shortHash(value) {
    if (!value) return '';
    return `${value.slice(0, 10)}…${value.slice(-6)}`;
  }

  function proofBadge(item, label = 'пруф') {
    if (!item || !item.proofUrl) return '<span class="pill">архив</span>';
    return `<a class="pill pill--proof" href="${esc(item.proofUrl)}" target="_blank" rel="noopener" title="SHA-256 ${esc(item.proofHash || '')}">${label} · ${esc(shortHash(item.proofHash))}</a>`;
  }

  function showLoading() {
    el('view').innerHTML = '<div class="loading">Загрузка…</div>';
  }

  function toast(message, kind = 'success') {
    const node = el('toast');
    node.textContent = message;
    node.className = `toast toast--${kind}`;
    node.hidden = false;
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => { node.hidden = true; }, 4600);
  }

  const act = (fn) => (...args) => {
    Promise.resolve()
      .then(() => fn(...args))
      .catch((error) => toast(error.message || String(error), 'error'));
  };

  async function api(url, options = {}) {
    const opts = { ...options, headers: { ...(options.headers || {}) } };
    if (opts.body && typeof opts.body !== 'string') {
      opts.body = JSON.stringify(opts.body);
      opts.headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(url, opts);
    if (response.status === 401) {
      window.location.href = '/login';
      throw new Error('Требуется вход');
    }
    const text = await response.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!response.ok) {
      let detail = data && typeof data === 'object' ? data.detail : data;
      if (Array.isArray(detail)) {
        detail = detail.map((item) => item.msg || JSON.stringify(item)).join('; ');
      }
      throw new Error(typeof detail === 'string' && detail ? detail : 'Ошибка запроса');
    }
    return data;
  }

  /* ---------- modal ---------- */

  function openModal({ title, body, foot = '', wide = false, bind = null }) {
    el('modalTitle').textContent = title;
    el('modalBody').innerHTML = body;
    el('modalFoot').innerHTML = foot;
    el('modalFoot').hidden = !foot;
    el('modalPanel').classList.toggle('modal__panel--wide', Boolean(wide));
    el('modal').hidden = false;
    document.body.classList.add('modal-open');
    if (bind) bind(el('modalBody'), el('modalFoot'));
  }

  function closeModal() {
    el('modal').hidden = true;
    document.body.classList.remove('modal-open');
  }

  /* ---------- data loading ---------- */

  function applyChrome() {
    document.title = `${S.settings.unit_name} — суточные дежурства`;
    el('unitName').textContent = S.settings.unit_name;
    el('todayLabel').textContent = fmtLong(S.today);
    const pending = S.data?.compSummary?.pending ?? 0;
    const badge = el('compBadge');
    badge.hidden = pending === 0;
    badge.textContent = String(pending);
    const pendingRequests = S.data?.requestSummary?.pending ?? 0;
    const requestBadge = el('requestBadge');
    requestBadge.hidden = pendingRequests === 0;
    requestBadge.textContent = String(pendingRequests);
    const coverageOpen = S.data?.coverageSummary?.open ?? 0;
    const coverageBadge = el('coverageBadge');
    coverageBadge.hidden = coverageOpen === 0;
    coverageBadge.textContent = String(coverageOpen);
  }

  function applyRoleChrome() {
    const user = S.user;
    if (!user) return;
    const chip = el('userChip');
    chip.hidden = false;
    el('userName').textContent = user.personName || user.username;
    el('userRole').textContent = ROLE_LABEL[user.role] || user.role;
    $$('#tabs .tab[data-admin-only]').forEach((button) => {
      button.hidden = user.role !== 'admin';
    });
  }

  function isAdmin() {
    return S.user && S.user.role === 'admin';
  }

  async function loadSchedule(month) {
    const query = month ? `?month=${encodeURIComponent(month)}` : '';
    const data = await api('/api/schedule' + query);
    S.data = data;
    S.month = data.month;
    S.today = data.today;
    S.settings = data.settings;
    S.people = data.people;
    S.holidays = data.holidays;
    applyChrome();
    await renderTab();
  }

  async function renderTab() {
    if (!S.data) return;
    try {
      if (S.tab === 'schedule') renderSchedule();
      else if (S.tab === 'people') await renderPeople();
      else if (S.tab === 'requests') await renderRequests();
      else if (S.tab === 'coverage') await renderCoverage();
      else if (S.tab === 'comps') await renderComps();
      else if (S.tab === 'absences') await renderAbsences();
      else if (S.tab === 'stats') await renderStats();
      else if (S.tab === 'users') await renderUsers();
      else if (S.tab === 'settings') await renderSettings();
    } catch (error) {
      toast(error.message || 'Не удалось загрузить раздел', 'error');
    }
  }

  async function switchTab(tab) {
    S.tab = tab;
    $$('#tabs .tab').forEach((button) => {
      button.classList.toggle('is-active', button.dataset.tab === tab);
    });
    await renderTab();
  }

  /* ---------- calendar ---------- */

  function dayCell(day) {
    const num = Number(day.date.slice(8, 10));
    const classes = ['day'];
    if (!day.inMonth) classes.push('day--out');
    if (day.weekend) classes.push('day--weekend');
    if (day.holiday) classes.push('day--holiday');
    if (day.date === S.today) classes.push('day--today');
    if (day.duty) classes.push('day--has-duty');

    const tags = [];
    if (day.date === S.today) tags.push('<span class="tag tag--today">сегодня</span>');
    if (day.holiday) tags.push(`<span class="tag tag--holiday" title="${esc(day.holiday)}">праздник</span>`);

    let content = '';
    if (day.duty) {
      const meta = [];
      if (day.duty.source !== 'manual') meta.push(SOURCE_LABEL[day.duty.source].toLowerCase());
      if (day.duty.status !== 'planned') meta.push(STATUS_LABEL[day.duty.status].toLowerCase());
      content = `
        <span class="duty">
          <span class="avatar">${esc(initials(day.duty.personName))}</span>
          <span class="duty__name">${esc(day.duty.personName)}</span>
          <span class="dot dot--${day.duty.status}" title="${esc(STATUS_LABEL[day.duty.status])}"></span>
        </span>
        ${meta.length ? `<span class="duty__meta">${esc(meta.join(' · '))}</span>` : ''}
      `;
    } else {
      content = '<span class="day__empty">+</span>';
    }

    const chips = [];
    (day.rests || []).forEach((rest) => {
      chips.push(`<span class="mini mini--rest" title="Отсыпной после дежурства ${fmtShort(rest.dutyDate)}">отсыпной · ${esc(rest.personName)}</span>`);
    });
    (day.comps || []).forEach((comp) => {
      chips.push(`<span class="mini mini--comp">отгул · ${esc(comp.personName)}</span>`);
    });
    (day.absences || []).forEach((absence) => {
      chips.push(`<span class="mini mini--abs" title="${esc(KIND_LABEL[absence.kind])}">${KIND_SHORT[absence.kind] || 'отсутствие'} · ${esc(absence.personName)}</span>`);
    });
    (day.requests || []).forEach((request) => {
      const preferred = request.kind === 'preferred';
      const approved = request.status === 'approved';
      const cls = preferred ? 'mini--pref' : (approved ? 'mini--req-approved' : 'mini--req');
      const label = preferred ? 'просит' : (approved ? 'не может' : 'не может · ждёт');
      const title = `${REQ_KIND_LABEL[request.kind] || request.kind} · ${fmtShort(request.dateFrom)}–${fmtShort(request.dateTo)}${request.reason ? ` · ${request.reason}` : ''}`;
      chips.push(`<span class="mini ${cls}" title="${esc(title)}">${label} · ${esc(request.personName)}</span>`);
    });

    return `
      <button type="button" class="${classes.join(' ')}" data-day="${day.date}">
        <span class="day__top">
          <span class="day__num">${num}</span>
          <span class="day__tags">${tags.join('')}</span>
        </span>
        ${day.holiday ? `<span class="day__holiday">${esc(day.holiday)}</span>` : ''}
        ${content}
        ${chips.join('')}
      </button>
    `;
  }

  function renderDrawLog(draws) {
    if (!draws.length) return '';
    return `
      <section class="panel">
        <div class="panel__head">
          <h3>Журнал розыгрышей и пруфы</h3>
          <span class="small muted">каждый розыгрыш запечатан SHA-256 и воспроизводится</span>
        </div>
        ${draws.slice(0, 8).map((draw) => `
          <details class="draw-log__item">
            <summary>
              <span class="draw-log__date">${fmtShort(draw.date)}</span>
              <strong>${esc(draw.winnerName)}</strong>
              <span class="muted small">${esc(DRAW_MODE_LABEL[draw.mode] || draw.mode || 'жребий')}</span>
              <span class="muted small">seed ${draw.seed}</span>
              ${proofBadge(draw)}
            </summary>
            <div class="table-wrap">
              <table class="table table--compact">
                <thead><tr><th>Кандидат</th><th class="num">Дежурств</th><th class="num">Выходных</th><th class="num">Нагрузка</th><th style="width:120px">Вероятность</th><th></th></tr></thead>
                <tbody>
                  ${(draw.candidates || []).map((candidate) => `
                    <tr>
                      <td>${esc(candidate.name)}</td>
                      <td class="num">${candidate.total}</td>
                      <td class="num">${candidate.weekend}</td>
                      <td class="num">${Number(candidate.weighted).toFixed(2)}</td>
                      <td><div class="prob"><span class="prob__value">${pct(candidate.probability)}</span><div class="bar"><i style="width:${(Number(candidate.probability) * 100).toFixed(1)}%"></i></div></div></td>
                      <td>${candidate.winner ? '<span class="pill pill--used">выбран</span>' : ''}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
            <div class="draw-log__proof small muted">
              ${draw.proofHash
                ? `SHA-256 <code>${esc(draw.proofHash)}</code> · <a href="${esc(draw.proofUrl)}" target="_blank" rel="noopener">открыть пруф</a>`
                : 'Создан до включения пруфов: seed сохранён, криптографическая печать недоступна.'}
            </div>
          </details>
        `).join('')}
      </section>
    `;
  }

  function renderSchedule() {
    const monthDays = S.data.days.filter((day) => day.inMonth);
    const dutyCount = monthDays.filter((day) => day.duty).length;
    const weekendDutyCount = monthDays.filter((day) => day.duty && day.dayOff).length;
    const activePeople = S.data.people.filter((person) => person.active).length;
    const pendingComps = S.data.compSummary.pending || 0;
    const holidayCount = monthDays.filter((day) => day.holiday).length;

    el('view').innerHTML = `
      <div class="page-head">
        <div class="month-nav">
          <button class="icon-btn icon-btn--lg" type="button" id="prevMonth" aria-label="Предыдущий месяц">‹</button>
          <h2 class="month-title">${monthLabel(S.month)}</h2>
          <button class="icon-btn icon-btn--lg" type="button" id="nextMonth" aria-label="Следующий месяц">›</button>
          <button class="btn btn--ghost btn--sm" type="button" id="todayBtn">Сегодня</button>
        </div>
        <div class="head-actions">
          <button class="btn btn--primary" type="button" id="rouletteOpenBtn">Рулетка</button>
          <button class="btn btn--ghost" type="button" id="autoPlanBtn">Автораспределение</button>
          <a class="btn btn--ghost" href="/api/export/schedule.xlsx?month=${encodeURIComponent(S.month)}">Excel для печати</a>
          <a class="btn btn--ghost" href="/api/export/schedule-bw.xlsx?month=${encodeURIComponent(S.month)}">ЧБ для печати</a>
          <a class="btn btn--ghost" href="/api/export?month=${encodeURIComponent(S.month)}">Экспорт CSV</a>
        </div>
      </div>

      <div class="kpis">
        <div class="kpi">
          <span class="kpi__label">Дежурств в месяце</span>
          <span class="kpi__value">${dutyCount}</span>
          <span class="kpi__sub">из ${monthDays.length} ${plural(monthDays.length, 'дня', 'дней', 'дней')}</span>
        </div>
        <div class="kpi ${weekendDutyCount ? 'kpi--warn' : 'kpi--muted'}">
          <span class="kpi__label">Выходных дежурств</span>
          <span class="kpi__value">${weekendDutyCount}</span>
          <span class="kpi__sub">${holidayCount ? `${holidayCount} ${plural(holidayCount, 'праздник', 'праздника', 'праздников')} в месяце` : 'дают право на отгул'}</span>
        </div>
        <div class="kpi">
          <span class="kpi__label">Активных сотрудников</span>
          <span class="kpi__value">${activePeople}</span>
          <span class="kpi__sub">участвуют в распределении</span>
        </div>
        <div class="kpi ${pendingComps ? 'kpi--warn' : 'kpi--muted'}">
          <span class="kpi__label">Отгулов к оформлению</span>
          <span class="kpi__value">${pendingComps}</span>
          <span class="kpi__sub">за выходные дежурства</span>
        </div>
      </div>

      <div class="legend">
        <span class="legend__item"><i class="swatch swatch--duty"></i>дежурство</span>
        <span class="legend__item"><i class="swatch swatch--rest"></i>отсыпной</span>
        <span class="legend__item"><i class="swatch swatch--comp"></i>отгул</span>
        <span class="legend__item"><i class="swatch swatch--abs"></i>отпуск / болезнь</span>
        <span class="legend__item"><i class="swatch swatch--req"></i>заявка «не могу»</span>
        <span class="legend__item"><i class="swatch swatch--pref"></i>просит не назначать</span>
        <span class="legend__item"><i class="swatch swatch--weekend"></i>выходной</span>
        <span class="legend__item">нажмите на день, чтобы назначить или разыграть</span>
      </div>

      <div class="calendar-wrap">
        <div class="calendar">
          ${WD.map((name) => `<div class="calendar__dow">${name}</div>`).join('')}
          ${S.data.days.map(dayCell).join('')}
        </div>
      </div>

      ${renderDrawLog(S.data.draws || [])}

      <div class="note-panel">
        <strong>Правила:</strong>
        после суточного дежурства — обязательный отсыпной
        (${S.settings.rest_days} ${plural(S.settings.rest_days, 'день', 'дня', 'дней')});
        минимальный интервал между дежурствами — ${S.settings.min_gap_days}
        ${plural(S.settings.min_gap_days, 'день', 'дня', 'дней')}.
        Выходное или праздничное дежурство даёт право на отгул в рабочий день
        (${S.settings.comp_valid_days} ${plural(S.settings.comp_valid_days, 'день', 'дня', 'дней')} после дежурства).
      </div>
    `;

    el('prevMonth').addEventListener('click', act(() => loadSchedule(shiftMonth(S.month, -1))));
    el('nextMonth').addEventListener('click', act(() => loadSchedule(shiftMonth(S.month, 1))));
    el('todayBtn').addEventListener('click', act(() => loadSchedule(S.today.slice(0, 7))));
    el('autoPlanBtn').addEventListener('click', () => openAutoPlan());
    el('rouletteOpenBtn').addEventListener('click', () => openRoulettePicker());
    $$('#view [data-day]').forEach((node) => {
      node.addEventListener('click', act(() => openDay(node.dataset.day)));
    });
  }

  /* ---------- people ---------- */

  function personCell(person) {
    return `
      <div class="person-cell">
        <span class="avatar">${esc(initials(person.name))}</span>
        <div class="person-cell__text">
          <div class="person-cell__name">${esc(person.name)}</div>
          ${person.note ? `<div class="person-cell__note">${esc(person.note)}</div>` : ''}
        </div>
      </div>
    `;
  }

  async function renderPeople() {
    showLoading();
    const data = await api('/api/stats');
    S.statsData = data;
    const rows = [...data.stats].sort((a, b) =>
      (Number(b.active) - Number(a.active))
      || (b.load.weighted - a.load.weighted)
      || a.name.localeCompare(b.name, 'ru')
    );

    el('view').innerHTML = `
      <div class="page-head">
        <div>
          <h2 class="page-title">Сотрудники</h2>
          <p class="page-sub">Активные участвуют в автораспределении и жеребьёвке. Личный кабинет сотрудник получает через учётную запись — вкладка «Аккаунты».</p>
        </div>
        <div class="head-actions">
          <button class="btn btn--primary" type="button" id="addPersonBtn">Добавить сотрудника</button>
        </div>
      </div>

      ${rows.length ? `
        <div class="panel" style="margin-top:0">
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>Сотрудник</th>
                  <th>Статус</th>
                  <th class="num">Дежурств</th>
                  <th class="num">Выходных</th>
                  <th>Нагрузка</th>
                  <th class="num">Последнее</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                ${rows.map((person) => `
                  <tr class="${person.active ? '' : 'row--inactive'}">
                    <td>${personCell(person)}</td>
                    <td>${person.active ? '<span class="pill pill--used">активен</span>' : '<span class="pill">неактивен</span>'}</td>
                    <td class="num">${person.load.total}</td>
                    <td class="num">${person.load.weekend}</td>
                    <td>
                      <div class="load-cell">
                        <div class="bar"><i style="width:${Math.min(100, person.load.weighted * 8)}%"></i></div>
                        <span>${person.load.weighted.toFixed(2)}</span>
                      </div>
                    </td>
                    <td class="num">${person.lastDuty ? fmtShort(person.lastDuty) : '—'}</td>
                    <td class="nowrap">
                      <button class="btn btn--sm btn--ghost" type="button" data-edit-person="${person.id}">Изменить</button>
                      <button class="btn btn--sm ${person.active ? 'btn--danger' : ''}" type="button" data-toggle-person="${person.id}" data-active="${person.active ? 1 : 0}">
                        ${person.active ? 'Деактивировать' : 'Активировать'}
                      </button>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      ` : `
        <div class="empty-state">
          <strong>Список пуст</strong>
          Добавьте сотрудников, чтобы начать планирование.
        </div>
      `}
    `;

    el('addPersonBtn').addEventListener('click', () => openPersonModal(null));
    $$('[data-edit-person]').forEach((button) => {
      button.addEventListener('click', () => {
        const person = rows.find((item) => item.id === Number(button.dataset.editPerson));
        if (person) openPersonModal(person);
      });
    });
    $$('[data-toggle-person]').forEach((button) => {
      button.addEventListener('click', act(async () => {
        const isActive = button.dataset.active === '1';
        if (isActive && !confirm('Деактивировать сотрудника? Он перестанет участвовать в новых распределениях, существующие дежурства останутся.')) {
          return;
        }
        await api(`/api/people/${button.dataset.togglePerson}`, {
          method: 'PATCH',
          body: { active: !isActive },
        });
        toast(isActive ? 'Сотрудник деактивирован' : 'Сотрудник активирован');
        await loadSchedule(S.month);
      }));
    });
  }

  function openPersonModal(person) {
    const isEdit = Boolean(person);
    openModal({
      title: isEdit ? 'Данные сотрудника' : 'Новый сотрудник',
      body: `
        <form id="personForm" class="form">
          <div class="field">
            <label for="personName">ФИО или позывной</label>
            <input id="personName" name="name" type="text" required maxlength="120" value="${esc(person?.name || '')}" autocomplete="off">
          </div>
          <div class="field">
            <label for="personNote">Примечание</label>
            <input id="personNote" name="note" type="text" maxlength="200" value="${esc(person?.note || '')}" placeholder="подразделение, должность — необязательно">
          </div>
          <div class="field">
            <label for="personEmail">Email для уведомлений</label>
            <input id="personEmail" name="email" type="email" maxlength="200" value="${esc(person?.email || '')}" placeholder="name@example.by">
          </div>
          <div class="field">
            <label for="personChat">Rocket.Chat</label>
            <input id="personChat" name="rocketchat" type="text" maxlength="200" value="${esc(person?.rocketchat || '')}" placeholder="@username или #канал">
            <span class="hint">Используется, если у учётной записи не заполнен свой контакт.</span>
          </div>
          ${isEdit ? `
            <label class="check">
              <input type="checkbox" name="active" ${person.active ? 'checked' : ''}>
              Активен — участвует в распределении
            </label>
          ` : ''}
        </form>
      `,
      foot: `
        <button class="btn" type="button" data-close>Отмена</button>
        <button class="btn btn--primary" type="submit" form="personForm">Сохранить</button>
      `,
      bind: (body) => {
        $('#personForm', body).addEventListener('submit', act(async (event) => {
          event.preventDefault();
          const form = new FormData(event.target);
          const payload = {
            name: form.get('name'),
            note: form.get('note') || '',
            email: form.get('email') || '',
            rocketchat: form.get('rocketchat') || '',
          };
          if (isEdit) {
            payload.active = form.get('active') === 'on';
            await api(`/api/people/${person.id}`, { method: 'PATCH', body: payload });
            toast('Данные обновлены');
          } else {
            await api('/api/people', { method: 'POST', body: payload });
            toast('Сотрудник добавлен');
          }
          closeModal();
          await loadSchedule(S.month);
        }));
      },
    });
  }

  /* ---------- comps ---------- */

  async function renderComps(refresh = true) {
    if (refresh || !S.compsData) {
      showLoading();
      S.compsData = await api('/api/comps');
    }
    const data = S.compsData;
    const filter = S.compsFilter;
    const items = data.comps.filter((item) => filter === 'all' || item.status === filter);

    const filters = [
      ['all', 'Все', data.comps.length],
      ['pending', 'К оформлению', data.counts.pending],
      ['scheduled', 'Запланированы', data.counts.scheduled],
      ['used', 'Использованы', data.counts.used],
      ['declined', 'Отказ', data.counts.declined],
    ];

    el('view').innerHTML = `
      <div class="page-head">
        <div>
          <h2 class="page-title">Отгулы за выходные дежурства</h2>
          <p class="page-sub">Один отгул за каждое дежурство в выходной или праздничный день. Дата — на выбор сотрудника, в пределах ${data.compValidDays} дней после дежурства.</p>
        </div>
        <div class="head-actions">
          <a class="btn btn--ghost" href="/api/export?month=${encodeURIComponent(S.month)}">Экспорт CSV</a>
        </div>
      </div>

      ${data.compEnabled ? '' : '<div class="banner banner--danger">Отгулы отключены в настройках.</div>'}

      <div class="kpis">
        <div class="kpi ${data.counts.pending ? 'kpi--warn' : 'kpi--muted'}">
          <span class="kpi__label">К оформлению</span>
          <span class="kpi__value">${data.counts.pending}</span>
          <span class="kpi__sub">ещё не выбрана дата</span>
        </div>
        <div class="kpi">
          <span class="kpi__label">Запланировано</span>
          <span class="kpi__value">${data.counts.scheduled}</span>
          <span class="kpi__sub">дата уже назначена</span>
        </div>
        <div class="kpi">
          <span class="kpi__label">Использовано</span>
          <span class="kpi__value">${data.counts.used}</span>
          <span class="kpi__sub">отгул предоставлен</span>
        </div>
        <div class="kpi kpi--muted">
          <span class="kpi__label">Отказ</span>
          <span class="kpi__value">${data.counts.declined}</span>
          <span class="kpi__sub">отгул не требуется</span>
        </div>
      </div>

      <div class="filter-row">
        ${filters.map(([value, label, count]) => `
          <button class="filter ${filter === value ? 'is-active' : ''}" type="button" data-filter="${value}">
            ${label} <span>${count}</span>
          </button>
        `).join('')}
      </div>

      ${items.length ? `
        <div class="panel" style="margin-top:0">
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>Сотрудник</th>
                  <th>Дежурство</th>
                  <th>Срок выбора</th>
                  <th>Дата отгула</th>
                  <th>Статус</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                ${items.map((item) => {
                  const upcoming = item.duty_date > data.today;
                  let actions = '';
                  if (data.compEnabled) {
                    if (item.status === 'pending' || item.status === 'declined') {
                      if (!item.expired) {
                        actions += `<button class="btn btn--sm btn--primary" type="button" data-comp-open="${item.duty_id}" data-mode="scheduled">Оформить</button>`;
                      }
                      if (item.status === 'pending') {
                        actions += `<button class="btn btn--sm btn--ghost" type="button" data-comp-set="${item.duty_id}" data-status="declined">Отказ</button>`;
                      }
                    } else if (item.status === 'scheduled') {
                      actions += `<button class="btn btn--sm" type="button" data-comp-set="${item.duty_id}" data-status="used">Использован</button>`;
                      actions += `<button class="btn btn--sm btn--ghost" type="button" data-comp-open="${item.duty_id}" data-mode="scheduled">Дата</button>`;
                      actions += `<button class="btn btn--sm btn--ghost" type="button" data-comp-set="${item.duty_id}" data-status="pending">Сброс</button>`;
                    }
                  }
                  return `
                    <tr class="${item.personActive ? '' : 'row--inactive'}">
                      <td>${personCell({ name: item.personName, note: item.personActive ? '' : 'неактивен' })}</td>
                      <td class="nowrap">
                        ${fmtLong(item.duty_date)}
                        ${upcoming ? ' <span class="pill pill--planned">впереди</span>' : ''}
                      </td>
                      <td class="nowrap">
                        ${fmtLong(item.valid_until)}
                        ${item.expired ? ' <span class="pill pill--danger">срок истёк</span>' : ''}
                      </td>
                      <td class="nowrap">${item.choice_date ? fmtLong(item.choice_date) : '—'}</td>
                      <td><span class="pill pill--${item.status}">${COMP_LABEL[item.status]}</span></td>
                      <td class="nowrap">${actions || '<span class="muted">—</span>'}</td>
                    </tr>
                  `;
                }).join('')}
              </tbody>
            </table>
          </div>
        </div>
      ` : `
        <div class="empty-state">
          <strong>Нет записей</strong>
          Отгулы появляются автоматически после назначения дежурства на выходной или праздник.
        </div>
      `}
    `;

    $$('[data-filter]').forEach((button) => {
      button.addEventListener('click', () => {
        S.compsFilter = button.dataset.filter;
        renderComps(false).catch((error) => toast(error.message, 'error'));
      });
    });

    $$('[data-comp-open]').forEach((button) => {
      button.addEventListener('click', () => {
        const item = data.comps.find((entry) => entry.duty_id === Number(button.dataset.compOpen));
        if (item) openCompDateModal(item, button.dataset.mode || 'scheduled');
      });
    });

    $$('[data-comp-set]').forEach((button) => {
      button.addEventListener('click', act(async () => {
        const item = data.comps.find((entry) => entry.duty_id === Number(button.dataset.compSet));
        if (!item) return;
        const status = button.dataset.status;
        if (status === 'declined' && !confirm('Отказаться от отгула за это дежурство?')) return;
        if (status === 'used' && !item.choice_date) {
          openCompDateModal(item, 'used');
          return;
        }
        await api(`/api/comps/${item.duty_id}`, {
          method: 'PUT',
          body: { status, date: item.choice_date || null },
        });
        toast('Отгул обновлён');
        await loadSchedule(S.month);
      }));
    });
  }

  function openCompDateModal(item, mode) {
    const min = addDays(item.duty_date, 1);
    const max = item.valid_until;
    const isUsed = mode === 'used';
    openModal({
      title: isUsed ? 'Отметить отгул использованным' : 'Оформление отгула',
      body: `
        <div class="banner">
          ${esc(item.personName)} · дежурство ${fmtLong(item.duty_date)}<br>
          Отгул можно выбрать с ${fmtLong(min)} по ${fmtLong(max)}, только на рабочий день, свободный от дежурств и отсутствий.
        </div>
        <form id="compForm" class="form">
          <div class="field">
            <label for="compDateInput">Дата отгула</label>
            <input id="compDateInput" name="date" type="date" required min="${min}" max="${max}" value="${esc(item.choice_date || '')}">
          </div>
        </form>
      `,
      foot: `
        <button class="btn" type="button" data-close>Отмена</button>
        <button class="btn btn--primary" type="submit" form="compForm">${isUsed ? 'Отметить использованным' : 'Сохранить'}</button>
      `,
      bind: (body) => {
        $('#compForm', body).addEventListener('submit', act(async (event) => {
          event.preventDefault();
          const date = new FormData(event.target).get('date');
          await api(`/api/comps/${item.duty_id}`, {
            method: 'PUT',
            body: { status: isUsed ? 'used' : 'scheduled', date },
          });
          toast('Отгул обновлён');
          closeModal();
          await loadSchedule(S.month);
        }));
      },
    });
  }

  /* ---------- requests ---------- */

  async function renderRequests(refresh = true) {
    if (refresh || !S.requestsData) {
      showLoading();
      S.requestsData = await api('/api/requests');
    }
    const data = S.requestsData;
    const filter = S.requestsFilter;
    const items = data.requests.filter((item) => filter === 'all' || item.status === filter);

    const filters = [
      ['all', 'Все', data.requests.length],
      ['pending', 'Ждут согласования', data.counts.pending],
      ['approved', 'Согласованы', data.counts.approved],
      ['declined', 'Отклонены', data.counts.declined],
    ];

    el('view').innerHTML = `
      <div class="page-head">
        <div>
          <h2 class="page-title">Заявки сотрудников</h2>
          <p class="page-sub">Сотрудник отмечает дни в личном кабинете. «Не могу» после согласования жёстко исключает из назначений; «предпочитаю» — мягкий приоритет, автораспределение обходит его, если есть альтернатива.</p>
          <p class="page-sub">Отпуск и командировку сотрудник подаёт периодом «с … по …»: после согласования создаётся отсутствие.</p>
        </div>
        <div class="head-actions">
          ${isAdmin() ? '<button class="btn btn--ghost" type="button" id="requestsToLinks">Учётные записи</button>' : ''}
        </div>
      </div>

      <div class="kpis">
        <div class="kpi ${data.counts.pending ? 'kpi--warn' : 'kpi--muted'}">
          <span class="kpi__label">Ждут согласования</span>
          <span class="kpi__value">${data.counts.pending}</span>
          <span class="kpi__sub">проверьте дни и конфликты</span>
        </div>
        <div class="kpi">
          <span class="kpi__label">Согласованы</span>
          <span class="kpi__value">${data.counts.approved}</span>
          <span class="kpi__sub">учитываются в распределении</span>
        </div>
        <div class="kpi kpi--muted">
          <span class="kpi__label">Отклонены</span>
          <span class="kpi__value">${data.counts.declined}</span>
          <span class="kpi__sub">на график не влияют</span>
        </div>
        <div class="kpi kpi--muted">
          <span class="kpi__label">Правила приёма</span>
          <span class="kpi__value">${S.settings.request_month_limit || '∞'}</span>
          <span class="kpi__sub">дней в месяц · горизонт ${S.settings.request_horizon_days} дн.</span>
        </div>
      </div>

      <div class="filter-row">
        ${filters.map(([value, label, count]) => `
          <button class="filter ${filter === value ? 'is-active' : ''}" type="button" data-req-filter="${value}">
            ${label} <span>${count}</span>
          </button>
        `).join('')}
      </div>

      ${items.length ? `
        <div class="panel" style="margin-top:0">
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>Сотрудник</th>
                  <th>Период</th>
                  <th class="num">Дней</th>
                  <th>Тип</th>
                  <th>Причина</th>
                  <th>Статус</th>
                  <th class="num">Создана</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                ${items.map((item) => {
                  const period = item.dateFrom === item.dateTo
                    ? fmtLong(item.dateFrom)
                    : `${fmtLong(item.dateFrom)} — ${fmtLong(item.dateTo)}`;
                  const actions = [];
                  if (item.status !== 'approved') {
                    actions.push(`<button class="btn btn--sm btn--primary" type="button" data-req-decide="${item.id}" data-req-origin="${esc(item.origin)}" data-status="approved">Согласовать</button>`);
                  }
                  if (item.status !== 'declined') {
                    actions.push(`<button class="btn btn--sm btn--ghost" type="button" data-req-decide="${item.id}" data-req-origin="${esc(item.origin)}" data-was-approved="${item.status === 'approved' ? '1' : '0'}" data-status="declined">${item.status === 'approved' ? 'Отменить' : 'Отклонить'}</button>`);
                  }
                  actions.push(`<button class="btn btn--sm btn--danger" type="button" data-req-del="${item.id}" data-req-origin="${esc(item.origin)}">Удалить</button>`);
                  return `
                    <tr>
                      <td>${personCell({ name: item.personName, note: '' })}</td>
                      <td class="nowrap">${period}</td>
                      <td class="num">${item.days}</td>
                      <td><span class="pill pill--${esc(item.kind)}">${esc(item.kindLabel)}</span></td>
                      <td class="muted small">${esc(item.reason || '—')}</td>
                      <td><span class="pill pill--${esc(item.status)}">${esc(item.statusLabel)}</span></td>
                      <td class="num nowrap">${item.createdAt ? fmtLong(item.createdAt.slice(0, 10)) : '—'}</td>
                      <td class="nowrap">${actions.join(' ')}</td>
                    </tr>
                  `;
                }).join('')}
              </tbody>
            </table>
          </div>
        </div>
      ` : `
        <div class="empty-state">
          <strong>${filter === 'all' ? 'Заявок пока нет' : 'В этом статусе заявок нет'}</strong>
          Сотрудник подаёт заявки из личного кабинета. Учётные записи создаются в разделе «Аккаунты».
        </div>
      `}

      <div class="note-panel">
        <strong>Как это работает.</strong>
        <span>Заявка «не могу» после согласования исключает сотрудника из назначений на выбранные дни —
        как отпуск. Заявка «предпочитаю» не запрещает назначение, но автораспределение выбирает
        других сотрудников, если это не увеличивает нагрузку. Согласовать заявку нельзя, пока на эти
        дни у сотрудника есть действующее дежурство: сначала переназначьте его.</span>
        <span>Отпуск и командировка подаются периодом и после согласования становятся отсутствием.</span>
      </div>
    `;

    const linksButton = el('requestsToLinks');
    if (linksButton) linksButton.addEventListener('click', () => switchTab('users'));
    $$('[data-req-filter]').forEach((button) => {
      button.addEventListener('click', () => {
        S.requestsFilter = button.dataset.reqFilter;
        renderRequests(false).catch((error) => toast(error.message, 'error'));
      });
    });
    $$('[data-req-decide]').forEach((button) => {
      button.addEventListener('click', act(async () => {
        const status = button.dataset.status;
        if (status === 'declined') {
          const message = button.dataset.wasApproved === '1'
            ? (button.dataset.reqOrigin === 'absence'
              ? 'Отменить заявку и удалить оформленное отсутствие?'
              : 'Отменить согласованную заявку?')
            : 'Отклонить заявку сотрудника?';
          if (!confirm(message)) return;
        }
        const url = button.dataset.reqOrigin === 'absence'
          ? `/api/absence-requests/${button.dataset.reqDecide}`
          : `/api/requests/${button.dataset.reqDecide}`;
        await api(url, {
          method: 'PATCH',
          body: { status },
        });
        toast(status === 'approved' ? 'Заявка согласована' : 'Заявка отклонена');
        S.requestsData = null;
        await loadSchedule(S.month);
      }));
    });
    $$('[data-req-del]').forEach((button) => {
      button.addEventListener('click', act(async () => {
        if (!confirm('Удалить заявку без возможности восстановления?')) return;
        const url = button.dataset.reqOrigin === 'absence'
          ? `/api/absence-requests/${button.dataset.reqDel}`
          : `/api/requests/${button.dataset.reqDel}`;
        await api(url, { method: 'DELETE' });
        toast('Заявка удалена');
        S.requestsData = null;
        await loadSchedule(S.month);
      }));
    });
  }

  /* ---------- absences ---------- */

  /* ---------- coverage ---------- */

  async function renderCoverage(refresh = true) {
    if (refresh || !S.coverageData) {
      showLoading();
      S.coverageData = await api('/api/coverage');
    }
    const data = S.coverageData;
    const days = data.days || [];

    el('view').innerHTML = `
      <div class="page-head">
        <div>
          <h2 class="page-title">Дни без доступных сотрудников</h2>
          <p class="page-sub">Дни горизонта, где ни один активный сотрудник не может дежурить по правилам. Для решения показываются кандидаты с коэффициентом: отсыпной, отпуска, интервалы и согласованные заявки не блокируют назначение, а фиксируются как отступления.</p>
        </div>
        <div class="head-actions">
          <button class="btn btn--ghost" type="button" id="coverageRefresh">Обновить</button>
        </div>
      </div>

      <div class="kpis">
        <div class="kpi ${days.length ? 'kpi--warn' : ''}">
          <span class="kpi__label">Требуют решения</span>
          <span class="kpi__value">${days.length}</span>
          <span class="kpi__sub">до ${fmtLong(data.dateTo)}</span>
        </div>
        <div class="kpi kpi--muted">
          <span class="kpi__label">Снято с контроля</span>
          <span class="kpi__value">${data.reviewed.length}</span>
          <span class="kpi__sub">осознанно оставлены без дежурства</span>
        </div>
        <div class="kpi">
          <span class="kpi__label">Решений тимлида</span>
          <span class="kpi__value">${data.overrides.length}</span>
          <span class="kpi__sub">назначения поверх правил</span>
        </div>
        <div class="kpi kpi--muted">
          <span class="kpi__label">Горизонт проверки</span>
          <span class="kpi__value">${Math.round((parseISO(data.dateTo) - parseISO(data.dateFrom)) / 86400000) + 1}</span>
          <span class="kpi__sub">${fmtShort(data.dateFrom)} — ${fmtShort(data.dateTo)}</span>
        </div>
      </div>

      ${days.length ? `
        <div class="panel" style="margin-top:0">
          <div class="panel__head">
            <h3>Требуют решения</h3>
            <span class="small muted">назначение поверх правил фиксируется в журнале</span>
          </div>
          <div class="table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>День</th>
                  <th>Почему нет кандидатов</th>
                  <th>Кандидаты для решения</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                ${days.map((day) => `
                  <tr>
                    <td class="nowrap">
                      <b>${fmtLong(day.date)}</b>
                      ${day.holiday ? `<div class="small muted">${esc(day.holiday)}</div>` : ''}
                    </td>
                    <td class="nowrap">
                      <span class="pill ${day.dayOff ? 'pill--unavailable' : 'pill--pending'}">${esc(day.weekdayName)}${day.dayOff ? ' · выходной' : ''}</span>
                    </td>
                    <td>
                      <div class="coverage-reasons">
                        ${day.reasons.map((item) => `<span class="mini mini--req">${esc(item.reason)}${item.count > 1 ? ` ×${item.count}` : ''}</span>`).join('')}
                      </div>
                      ${day.absents.length ? `<div class="small muted">Отсутствуют: ${esc(day.absents.join(', '))}</div>` : ''}
                      ${day.unavailable.length ? `<div class="small muted">Согласовано «не могу»: ${esc(day.unavailable.join(', '))}</div>` : ''}
                      ${day.pending.length ? `<div class="small muted">Ждут согласования: ${esc(day.pending.join(', '))}</div>` : ''}
                    </td>
                    <td>
                      ${(day.candidates || []).length ? `
                        <div class="candidate-chips">
                          ${day.candidates.slice(0, 4).map((item) => `
                            <span class="candidate-chip" title="${esc(item.conflicts.length ? `Отступления: ${item.conflicts.join('; ')}` : 'Без отступлений')}">
                              <b>${esc(item.personName)}</b>
                              <span class="pill pill--coef">коэф. ${Number(item.weight).toFixed(2)}</span>
                              <span class="small muted">${pct(item.probability)}</span>
                            </span>
                          `).join('')}
                          ${day.candidates.length > 4 ? `<span class="small muted">ещё ${day.candidates.length - 4}</span>` : ''}
                        </div>
                      ` : '<span class="small muted">нет доступных</span>'}
                    </td>
                    <td class="nowrap">
                      <button class="btn btn--sm btn--primary" type="button" data-coverage-assign="${day.date}">Назначить</button>
                      <button class="btn btn--sm btn--ghost" type="button" data-coverage-dismiss="${day.date}">Снять с контроля</button>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      ` : `
        <div class="empty-state">
          <strong>На горизонте все дни покрыты</strong>
          На каждый будущий день есть хотя бы один доступный сотрудник, либо день снят с контроля.
        </div>
      `}

      ${data.reviewed.length ? `
        <section class="panel">
          <div class="panel__head"><h3>Снято с контроля</h3></div>
          <div class="table-wrap">
            <table class="table table--compact">
              <thead><tr><th>Дата</th><th>Комментарий</th><th>Кто</th><th></th></tr></thead>
              <tbody>
                ${data.reviewed.map((item) => `
                  <tr>
                    <td class="nowrap">${fmtLong(item.date)}</td>
                    <td class="muted small">${esc(item.note || '—')}</td>
                    <td class="small">${esc(item.username || '—')}</td>
                    <td><button class="btn btn--sm btn--ghost" type="button" data-coverage-reopen="${item.date}">Вернуть в контроль</button></td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </section>
      ` : ''}

      ${data.overrides.length ? `
        <section class="panel">
          <div class="panel__head"><h3>Назначения поверх правил</h3></div>
          <div class="table-wrap">
            <table class="table table--compact">
              <thead><tr><th>Дата</th><th>Сотрудник</th><th>Причина</th><th>Кто</th></tr></thead>
              <tbody>
                ${data.overrides.map((item) => `
                  <tr>
                    <td class="nowrap">${fmtLong(item.date)}</td>
                    <td>${esc(item.person_name)}</td>
                    <td class="muted small">${esc(item.reason)}</td>
                    <td class="small">${esc(item.username || '—')}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </section>
      ` : ''}
    `;

    el('coverageRefresh').addEventListener('click', act(async () => {
      S.coverageData = null;
      S.requestsData = null;
      await renderCoverage();
    }));
    $$('[data-coverage-assign]').forEach((button) => {
      button.addEventListener('click', act(() => openCoverageAssign(button.dataset.coverageAssign)));
    });
    $$('[data-coverage-dismiss]').forEach((button) => {
      button.addEventListener('click', act(() => openCoverageDismiss(button.dataset.coverageDismiss)));
    });
    $$('[data-coverage-reopen]').forEach((button) => {
      button.addEventListener('click', act(async () => {
        await api(`/api/coverage/${button.dataset.coverageReopen}`, { method: 'DELETE' });
        toast('День возвращён в контроль');
        S.coverageData = null;
        await loadSchedule(S.month);
        await renderCoverage();
      }));
    });
  }

  async function openCoverageAssign(day) {
    const gap = (S.coverageData?.days || []).find((item) => item.date === day);
    const pool = gap?.candidates || [];
    const active = S.people.filter((person) => person.active);
    openModal({
      title: `Назначение на ${fmtLong(day)}`,
      body: `
        <div class="banner banner--danger">
          Отпуска, отсыпной, интервалы и согласованные заявки не мешают решению тимлида.
          Коэффициент — вес при жеребьёвке, процент — его вероятность; отступления сохраняются в журнале.
        </div>
        <form id="coverageAssignForm" class="form">
          <div class="field">
            <label>Кандидат и коэффициент</label>
            ${pool.length ? `
              <div class="candidate-list">
                ${pool.map((item, index) => `
                  <label class="candidate">
                    <input type="radio" name="person_id" value="${item.personId}" ${index === 0 ? 'checked' : ''} required>
                    <span class="candidate__main">
                      <span class="candidate__head">
                        <b>${esc(item.personName)}</b>
                        <span class="pill pill--coef">коэф. ${Number(item.weight).toFixed(2)}</span>
                        <span class="pill pill--prob">${pct(item.probability)}</span>
                        <span class="small muted">нагрузка ${Number(item.load).toFixed(2)}</span>
                      </span>
                      ${item.conflicts.length
                        ? `<span class="candidate__warn">Отступления: ${esc(item.conflicts.join('; '))}</span>`
                        : '<span class="candidate__ok">Без отступлений по отпускам и отсыпным</span>'}
                    </span>
                  </label>
                `).join('')}
              </div>
            ` : `
              <select name="person_id" required>
                ${active.map((person) => `<option value="${person.id}">${esc(person.name)}</option>`).join('')}
              </select>
              <span class="hint">Все сотрудники заняты в этот день или находятся на отгуле.</span>
            `}
          </div>
          <div class="field">
            <label for="coverageReason">Причина решения</label>
            <textarea id="coverageReason" name="reason" rows="3" maxlength="300" required placeholder="например: критическая смена, сотрудник дал согласие"></textarea>
          </div>
          ${gap && gap.reasons.length ? `
            <div class="field">
              <label>Почему день без покрытия</label>
              <div class="coverage-reasons">
                ${gap.reasons.map((item) => `<span class="mini mini--req">${esc(item.reason)}${item.count > 1 ? ` ×${item.count}` : ''}</span>`).join('')}
              </div>
            </div>
          ` : ''}
        </form>
      `,
      foot: `
        <button class="btn" type="button" data-close>Отмена</button>
        <button class="btn btn--primary" type="submit" form="coverageAssignForm">Назначить</button>
      `,
      bind: (body) => {
        $('#coverageAssignForm', body).addEventListener('submit', act(async (event) => {
          event.preventDefault();
          const form = new FormData(event.target);
          const result = await api(`/api/coverage/${day}/assign`, {
            method: 'POST',
            body: {
              person_id: Number(form.get('person_id')),
              reason: form.get('reason'),
            },
          });
          const warnings = (result.warnings || []).filter(Boolean);
          toast(warnings.length
            ? `Назначено с отступлениями: ${warnings.join('; ')}`
            : 'Дежурство назначено');
          closeModal();
          S.coverageData = null;
          S.requestsData = null;
          await loadSchedule(S.month);
          await renderCoverage();
        }));
      },
    });
  }

  function openCoverageDismiss(day) {
    openModal({
      title: `Снять с контроля: ${fmtLong(day)}`,
      body: `
        <div class="banner">
          День останется без дежурства. Он исчезнет из списка «Требуют решения»;
          вернуть его можно кнопкой «Вернуть в контроль».
        </div>
        <form id="coverageDismissForm" class="form">
          <div class="field">
            <label for="coverageNote">Комментарий</label>
            <textarea id="coverageNote" name="note" rows="3" maxlength="300" placeholder="обоснование решения"></textarea>
          </div>
        </form>
      `,
      foot: `
        <button class="btn" type="button" data-close>Отмена</button>
        <button class="btn btn--danger" type="submit" form="coverageDismissForm">Снять с контроля</button>
      `,
      bind: (body) => {
        $('#coverageDismissForm', body).addEventListener('submit', act(async (event) => {
          event.preventDefault();
          const form = new FormData(event.target);
          await api(`/api/coverage/${day}/dismiss`, {
            method: 'POST',
            body: { note: form.get('note') || '' },
          });
          toast('День снят с контроля');
          closeModal();
          S.coverageData = null;
          await loadSchedule(S.month);
          await renderCoverage();
        }));
      },
    });
  }

  /* ---------- accounts ---------- */

  async function renderUsers(refresh = true) {
    if (!isAdmin()) {
      el('view').innerHTML = '<div class="empty-state"><strong>Доступно только администратору</strong></div>';
      return;
    }
    if (refresh || !S.usersData) {
      showLoading();
      S.usersData = await api('/api/users');
    }
    const data = S.usersData;
    const users = data.users;
    const admins = users.filter((user) => user.role === 'admin' && user.active).length;
    const linked = users.filter((user) => user.personId).length;

    el('view').innerHTML = `
      <div class="page-head">
        <div>
          <h2 class="page-title">Учётные записи</h2>
          <p class="page-sub">Роли: администратор настраивает систему и уведомления, тимлид планирует дежурства и разбирает заявки, сотрудник видит личный кабинет и подаёт заявки.</p>
        </div>
        <div class="head-actions">
          <button class="btn btn--primary" type="button" id="addUserBtn">Добавить аккаунт</button>
        </div>
      </div>

      <div class="kpis">
        <div class="kpi">
          <span class="kpi__label">Всего аккаунтов</span>
          <span class="kpi__value">${users.length}</span>
          <span class="kpi__sub">${users.filter((user) => user.active).length} активных</span>
        </div>
        <div class="kpi">
          <span class="kpi__label">Администраторы</span>
          <span class="kpi__value">${admins}</span>
          <span class="kpi__sub">минимум один обязателен</span>
        </div>
        <div class="kpi">
          <span class="kpi__label">Привязаны к сотрудникам</span>
          <span class="kpi__value">${linked}</span>
          <span class="kpi__sub">получают личный кабинет</span>
        </div>
        <div class="kpi kpi--muted">
          <span class="kpi__label">Без привязки</span>
          <span class="kpi__value">${users.length - linked}</span>
          <span class="kpi__sub">тимлиды и администраторы</span>
        </div>
      </div>

      <div class="panel" style="margin-top:0">
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>Логин</th>
                <th>Роль</th>
                <th>Сотрудник</th>
                <th>Контакты</th>
                <th>Статус</th>
                <th class="num">Вход</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${users.map((user) => `
                <tr class="${user.active ? '' : 'row--inactive'}">
                  <td><b>${esc(user.username)}</b></td>
                  <td><span class="pill pill--role-${esc(user.role)}">${esc(user.roleLabel)}</span></td>
                  <td>${user.personName ? esc(user.personName) : '<span class="muted small">не привязан</span>'}</td>
                  <td class="small">
                    ${user.email ? `<div>✉ ${esc(user.email)}</div>` : ''}
                    ${user.rocketchat ? `<div>@ ${esc(user.rocketchat)}</div>` : ''}
                    ${!user.email && !user.rocketchat ? '<span class="muted">—</span>' : ''}
                  </td>
                  <td>${user.active ? '<span class="pill pill--used">активен</span>' : '<span class="pill">заблокирован</span>'}</td>
                  <td class="num nowrap small">${user.lastLoginAt ? fmtShort(user.lastLoginAt.slice(0, 10)) : '—'}</td>
                  <td class="nowrap">
                    <button class="btn btn--sm btn--ghost" type="button" data-edit-user="${user.id}">Изменить</button>
                    ${user.id === S.user.id ? '<span class="small muted">это вы</span>' : `
                      <button class="btn btn--sm" type="button" data-toggle-user="${user.id}" data-active="${user.active ? 1 : 0}">
                        ${user.active ? 'Заблокировать' : 'Разблокировать'}
                      </button>
                      <button class="btn btn--sm btn--danger" type="button" data-delete-user="${user.id}">Удалить</button>
                    `}
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>

      <div class="note-panel">
        <strong>Пароли.</strong> Хранятся в виде PBKDF2-SHA256 с солью. Смена пароля завершает
        прежние сессии. Сессия — подписанная HttpOnly cookie на 12 часов.
      </div>
    `;

    el('addUserBtn').addEventListener('click', () => openUserModal(null, data));
    $$('[data-edit-user]').forEach((button) => {
      button.addEventListener('click', () => {
        const user = users.find((item) => item.id === Number(button.dataset.editUser));
        if (user) openUserModal(user, data);
      });
    });
    $$('[data-toggle-user]').forEach((button) => {
      button.addEventListener('click', act(async () => {
        const active = button.dataset.active === '1';
        if (active && !confirm('Заблокировать аккаунт? Пользователь потеряет доступ к системе.')) return;
        await api(`/api/users/${button.dataset.toggleUser}`, {
          method: 'PATCH',
          body: { active: !active },
        });
        toast(active ? 'Аккаунт заблокирован' : 'Аккаунт разблокирован');
        S.usersData = null;
        await renderUsers();
      }));
    });
    $$('[data-delete-user]').forEach((button) => {
      button.addEventListener('click', act(async () => {
        if (!confirm('Удалить аккаунт? Сотрудник и его история сохранятся.')) return;
        await api(`/api/users/${button.dataset.deleteUser}`, { method: 'DELETE' });
        toast('Аккаунт удалён');
        S.usersData = null;
        await renderUsers();
      }));
    });
  }

  function openUserModal(user, data) {
    const isEdit = Boolean(user);
    const linkedPeople = [...data.availablePeople];
    if (isEdit && user.personId && !linkedPeople.some((person) => person.id === user.personId)) {
      linkedPeople.unshift({ id: user.personId, name: user.personName || 'Текущий сотрудник' });
    }
    const roleLabels = data.roleLabels || ROLE_LABEL;
    openModal({
      title: isEdit ? `Аккаунт ${user.username}` : 'Новый аккаунт',
      body: `
        <form id="userForm" class="form">
          <div class="settings-grid">
            <div class="field">
              <label for="userLogin">Логин</label>
              <input id="userLogin" name="username" type="text" maxlength="40" required autocomplete="off" value="${esc(user?.username || '')}">
            </div>
            <div class="field">
              <label for="userPassword">${isEdit ? 'Новый пароль' : 'Пароль'}</label>
              <input id="userPassword" name="password" type="password" minlength="8" maxlength="128" ${isEdit ? '' : 'required'} autocomplete="new-password" placeholder="${isEdit ? 'оставьте пустым, чтобы не менять' : 'не короче 8 символов'}">
            </div>
            <div class="field">
              <label for="userRole">Роль</label>
              <select id="userRole" name="role">
                ${Object.entries(roleLabels).map(([value, label]) => `
                  <option value="${value}" ${user?.role === value ? 'selected' : ''}>${esc(label)}</option>
                `).join('')}
              </select>
            </div>
            <div class="field">
              <label for="userPerson">Сотрудник</label>
              <select id="userPerson" name="person_id">
                <option value="">— не привязан —</option>
                ${linkedPeople.map((person) => `
                  <option value="${person.id}" ${user?.personId === person.id ? 'selected' : ''}>${esc(person.name)}</option>
                `).join('')}
              </select>
              <span class="hint">Сотруднику нужна привязка для личного кабинета.</span>
            </div>
            <div class="field">
              <label for="userEmail">Email для уведомлений</label>
              <input id="userEmail" name="email" type="email" maxlength="200" value="${esc(user?.email || '')}">
            </div>
            <div class="field">
              <label for="userChat">Rocket.Chat</label>
              <input id="userChat" name="rocketchat" type="text" maxlength="200" value="${esc(user?.rocketchat || '')}" placeholder="@username">
            </div>
          </div>
          <label class="check">
            <input type="checkbox" name="active" ${!user || user.active ? 'checked' : ''}>
            Аккаунт активен
          </label>
        </form>
      `,
      foot: `
        <button class="btn" type="button" data-close>Отмена</button>
        <button class="btn btn--primary" type="submit" form="userForm">Сохранить</button>
      `,
      bind: (body) => {
        $('#userForm', body).addEventListener('submit', act(async (event) => {
          event.preventDefault();
          const form = new FormData(event.target);
          const payload = {
            username: form.get('username'),
            role: form.get('role'),
            person_id: form.get('person_id') ? Number(form.get('person_id')) : null,
            email: form.get('email') || '',
            rocketchat: form.get('rocketchat') || '',
            active: form.get('active') === 'on',
          };
          const password = form.get('password');
          if (password) payload.password = password;
          if (isEdit) {
            await api(`/api/users/${user.id}`, { method: 'PATCH', body: payload });
            toast('Аккаунт обновлён');
            if (password && user.id === S.user.id) {
              window.location.href = '/login';
              return;
            }
          } else {
            await api('/api/users', { method: 'POST', body: payload });
            toast('Аккаунт создан');
          }
          closeModal();
          S.usersData = null;
          await renderUsers();
        }));
      },
    });
  }

  async function renderAbsences() {
    showLoading();
    const data = await api('/api/absences');
    const activePeople = S.people.filter((person) => person.active);
    const absences = data.absences || [];

    el('view').innerHTML = `
      <div class="page-head">
        <div>
          <h2 class="page-title">Отсутствия</h2>
          <p class="page-sub">Отпуск, болезнь и командировка исключают сотрудника из распределения на выбранные дни.</p>
        </div>
      </div>

      <section class="panel" style="margin-top:0">
        <div class="panel__head"><h3>Добавить отсутствие</h3></div>
        ${activePeople.length ? `
          <form id="absenceForm" class="form form--inline">
            <div class="field">
              <label for="absPerson">Сотрудник</label>
              <select id="absPerson" name="person_id" required>
                ${activePeople.map((person) => `<option value="${person.id}">${esc(person.name)}</option>`).join('')}
              </select>
            </div>
            <div class="field">
              <label for="absFrom">С</label>
              <input id="absFrom" type="date" name="date_from" required value="${S.today}">
            </div>
            <div class="field">
              <label for="absTo">По</label>
              <input id="absTo" type="date" name="date_to" required value="${S.today}">
            </div>
            <div class="field">
              <label for="absKind">Тип</label>
              <select id="absKind" name="kind">
                <option value="vacation">Отпуск</option>
                <option value="sick">Болезнь</option>
                <option value="trip">Командировка</option>
                <option value="other">Другое</option>
              </select>
            </div>
            <div class="field">
              <label for="absNote">Примечание</label>
              <input id="absNote" type="text" name="note" maxlength="200" placeholder="необязательно">
            </div>
            <button class="btn btn--primary" type="submit">Добавить</button>
          </form>
        ` : '<div class="banner">Нет активных сотрудников.</div>'}
      </section>

      ${absences.length ? `
        <section class="panel">
          <div class="panel__head"><h3>Все отсутствия</h3><span class="small muted">${absences.length}</span></div>
          <div class="table-wrap">
            <table class="table">
              <thead><tr><th>Сотрудник</th><th>Период</th><th class="num">Дней</th><th>Тип</th><th>Примечание</th><th></th></tr></thead>
              <tbody>
                ${absences.map((absence) => {
                  const days = Math.round((parseISO(absence.date_to) - parseISO(absence.date_from)) / 86400000) + 1;
                  const current = absence.date_from <= S.today && absence.date_to >= S.today;
                  return `
                    <tr>
                      <td>${personCell({ name: absence.person_name || '—', note: '' })}</td>
                      <td class="nowrap">
                        ${fmtLong(absence.date_from)} — ${fmtLong(absence.date_to)}
                        ${current ? ' <span class="pill pill--planned">сейчас</span>' : ''}
                      </td>
                      <td class="num">${days}</td>
                      <td>${esc(KIND_LABEL[absence.kind] || absence.kind)}</td>
                      <td class="muted small">${esc(absence.note || '—')}</td>
                      <td class="nowrap"><button class="btn btn--sm btn--danger" type="button" data-del-absence="${absence.id}">Удалить</button></td>
                    </tr>
                  `;
                }).join('')}
              </tbody>
            </table>
          </div>
        </section>
      ` : `
        <div class="empty-state" style="margin-top:16px">
          <strong>Отсутствий нет</strong>
          Добавьте отпуск или командировку, чтобы они учитывались при назначении.
        </div>
      `}
    `;

    const form = el('absenceForm');
    if (form) {
      form.addEventListener('submit', act(async (event) => {
        event.preventDefault();
        const values = new FormData(event.target);
        await api('/api/absences', {
          method: 'POST',
          body: {
            person_id: Number(values.get('person_id')),
            date_from: values.get('date_from'),
            date_to: values.get('date_to'),
            kind: values.get('kind'),
            note: values.get('note') || '',
          },
        });
        toast('Отсутствие добавлено');
        await loadSchedule(S.month);
      }));
    }

    $$('[data-del-absence]').forEach((button) => {
      button.addEventListener('click', act(async () => {
        if (!confirm('Удалить отсутствие?')) return;
        await api(`/api/absences/${button.dataset.delAbsence}`, { method: 'DELETE' });
        toast('Отсутствие удалено');
        await loadSchedule(S.month);
      }));
    });
  }

  /* ---------- stats ---------- */

  function fairnessLabel(cv) {
    if (cv <= 0.1) return 'равномерно';
    if (cv <= 0.25) return 'умеренный разброс';
    return 'есть перекос';
  }

  async function renderStats() {
    showLoading();
    const data = await api('/api/stats');
    S.stats = data;
    const rows = [...data.stats].sort((a, b) =>
      (Number(b.active) - Number(a.active))
      || (b.load.weighted - a.load.weighted)
      || a.name.localeCompare(b.name, 'ru')
    );
    const activeRows = rows.filter((row) => row.active);
    const maxLoad = Math.max(1, ...activeRows.map((row) => row.load.weighted));
    const cv = data.fairness.cv || 0;
    const maxWeekday = Math.max(1, ...(data.weekdays || []).map((item) => item.total));
    const weekdayTotals = Array.from({ length: 7 }, (_, index) =>
      rows.reduce((sum, row) => sum + Number((row.byWeekday || [])[index] || 0), 0)
    );
    const weightedTotal = rows.reduce((sum, row) => sum + Number(row.load.weighted || 0), 0);

    const balance = activeRows
      .map((row) => ({
        ...row,
        delta: Number((Number(row.load.weighted) - data.fairness.mean).toFixed(2)),
      }))
      .sort((a, b) => b.delta - a.delta || a.name.localeCompare(b.name, 'ru'));
    const maxDelta = Math.max(0.5, ...balance.map((row) => Math.abs(row.delta)));
    const overCount = balance.filter((row) => row.delta > 0.5).length;
    const underCount = balance.filter((row) => row.delta < -0.5).length;

    const heatMax = Math.max(1, ...rows.flatMap((row) => row.byMonth || []));
    const heatClass = (count) => {
      if (!count) return 'heat heat--0';
      const ratio = count / heatMax;
      if (ratio <= 0.25) return 'heat heat--1';
      if (ratio <= 0.5) return 'heat heat--2';
      if (ratio <= 0.75) return 'heat heat--3';
      return 'heat heat--4';
    };

    const weekendRows = activeRows
      .filter((row) => row.load.total > 0)
      .sort((a, b) =>
        (b.weekendShare - a.weekendShare)
        || (b.load.weekend - a.load.weekend)
        || a.name.localeCompare(b.name, 'ru'));

    const coverage = data.coverage || {};
    const horizonDays = Number(coverage.horizonDays || 0);
    const unassigned = Number(coverage.unassigned || 0);
    const coveredPct = horizonDays
      ? Math.round(((horizonDays - unassigned) / horizonDays) * 100)
      : 100;
    const draws = data.draws || [];

    el('view').innerHTML = `
      <div class="page-head">
        <div>
          <h2 class="page-title">Статистика и равномерность</h2>
          <p class="page-sub">Нагрузка: будни — 1, выходные и праздники — ${data.weekendWeight}. Дашборды показывают перекос, покрытие и проверяемость жеребьёвок.</p>
        </div>
        <div class="head-actions">
          <a class="btn btn--ghost" href="/api/export">Экспорт CSV</a>
        </div>
      </div>

      <div class="kpis kpis--six">
        <div class="kpi">
          <span class="kpi__label">Активных сотрудников</span>
          <span class="kpi__value">${data.totals.people}</span>
          <span class="kpi__sub">в распределении</span>
        </div>
        <div class="kpi">
          <span class="kpi__label">Дежурств всего</span>
          <span class="kpi__value">${data.totals.duties}</span>
          <span class="kpi__sub">${data.totals.weekend} выходных и праздничных</span>
        </div>
        <div class="kpi">
          <span class="kpi__label">Средняя нагрузка</span>
          <span class="kpi__value">${data.fairness.mean.toFixed(2)}</span>
          <span class="kpi__sub">разброс ${data.fairness.spread.toFixed(2)}</span>
        </div>
        <div class="kpi ${cv <= 0.1 ? '' : 'kpi--warn'}">
          <span class="kpi__label">Коэффициент вариации</span>
          <span class="kpi__value">${(cv * 100).toFixed(1)}%</span>
          <span class="kpi__sub">${fairnessLabel(cv)}</span>
        </div>
        <div class="kpi ${coverage.open ? 'kpi--warn' : 'kpi--muted'}">
          <span class="kpi__label">Дни без покрытия</span>
          <span class="kpi__value">${coverage.open || 0}</span>
          <span class="kpi__sub">горизонт ${horizonDays} дн. · без дежурного ${unassigned}</span>
        </div>
        <div class="kpi ${data.totals.compsPending ? 'kpi--warn' : 'kpi--muted'}">
          <span class="kpi__label">Отгулы</span>
          <span class="kpi__value">${data.totals.compsPending} / ${data.totals.compsScheduled || 0}</span>
          <span class="kpi__sub">ожидают / запланированы · использовано ${data.totals.compsUsed}</span>
        </div>
      </div>

      <section class="panel" style="margin-top:0">
        <div class="panel__head">
          <h3>Справедливость нагрузки</h3>
          <span class="small muted">отклонение от средней ${data.fairness.mean.toFixed(2)} · перегружены ${overCount} · недогружены ${underCount}</span>
        </div>
        ${balance.length ? `
          <div class="balance">
            <div class="balance__axis"><span>недогрузка</span><span>средняя</span><span>перегрузка</span></div>
            ${balance.map((row) => {
              const width = (Math.abs(row.delta) / maxDelta) * 50;
              const side = row.delta > 0 ? 'over' : (row.delta < 0 ? 'under' : 'flat');
              const style = row.delta > 0
                ? `left:50%;width:${width.toFixed(2)}%`
                : `right:50%;width:${width.toFixed(2)}%`;
              return `
                <div class="balance-row" title="${esc(row.name)}: ${row.load.weighted.toFixed(2)}">
                  <span class="balance-row__name">${esc(row.name)}</span>
                  <div class="balance-row__track">
                    <span class="balance-row__zero"></span>
                    ${row.delta ? `<i class="balance-row__fill balance-row__fill--${side}" style="${style}"></i>` : ''}
                  </div>
                  <span class="balance-row__value ${side === 'over' ? 'is-over' : (side === 'under' ? 'is-under' : '')}">${row.delta > 0 ? '+' : ''}${row.delta.toFixed(2)}</span>
                </div>
              `;
            }).join('')}
          </div>
        ` : '<div class="empty-state">Пока нет активных сотрудников для сравнения.</div>'}
        <div class="small muted" style="margin-top:10px">Красный — нагрузка выше средней более чем на 0.5; зелёный — ниже более чем на 0.5.</div>
      </section>

      <section class="panel" style="margin-top:0">
        <div class="panel__head">
          <h3>Тепловая карта: сотрудник × месяц</h3>
          <span class="small muted">${esc((data.months || [])[0]?.label || '')} — ${esc((data.months || [])[(data.months || []).length - 1]?.label || '')}</span>
        </div>
        <div class="table-wrap">
          <table class="table table--compact heatmap">
            <thead>
              <tr>
                <th>Сотрудник</th>
                ${(data.months || []).map((item) => `<th class="num" title="${esc(item.label)}">${esc(item.label.slice(0, 2))}</th>`).join('')}
                <th class="num">Σ</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map((person) => `
                <tr class="${person.active ? '' : 'row--inactive'}">
                  <td class="heatmap__name">${esc(person.name)}</td>
                  ${(person.byMonth || []).map((count, index) => `
                    <td class="num ${heatClass(Number(count))}" title="${esc((data.months || [])[index]?.label || '')}: ${count}">
                      ${count || ''}
                    </td>
                  `).join('')}
                  <td class="num"><b>${person.load.total}</b></td>
                </tr>
              `).join('')}
              <tr class="row--total">
                <td>Итого</td>
                ${(data.months || []).map((item) => `<td class="num">${item.total}</td>`).join('')}
                <td class="num"><b>${data.totals.duties}</b></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <div class="grid-2">
        <section class="panel" style="margin-top:0">
          <div class="panel__head">
            <h3>Дежурства по дням недели</h3>
            <span class="small muted">все активные дежурства</span>
          </div>
          <div class="weekday-list">
            ${(data.weekdays || []).map((item) => `
              <div class="weekday-row">
                <span class="weekday-row__name">${esc(item.name)}</span>
                <div class="bar weekday-row__bar"><i style="width:${(item.total / maxWeekday) * 100}%"></i></div>
                <span class="weekday-row__value">${item.total}</span>
                <span class="weekday-row__note">${item.dayOff ? `из них ${item.dayOff} вых.` : 'будни'}</span>
              </div>
            `).join('')}
          </div>
          <div class="small muted" style="margin-top:10px">Выходные и праздники учитываются с весом ${data.weekendWeight}.</div>
        </section>

        <section class="panel" style="margin-top:0">
          <div class="panel__head">
            <h3>Покрытие горизонта</h3>
            <span class="small muted">${horizonDays} ${plural(horizonDays, 'день', 'дня', 'дней')} вперёд</span>
          </div>
          <div class="coverage-meter">
            <div class="coverage-meter__value">${coveredPct}%</div>
            <div class="coverage-meter__text">
              <b>${horizonDays - unassigned}</b> из ${horizonDays} дней закрыты дежурным
              <span class="small muted">${unassigned} ${plural(unassigned, 'день', 'дня', 'дней')} без назначения</span>
            </div>
            <div class="bar bar--thick"><i style="width:${coveredPct}%"></i></div>
          </div>
          <div class="metric-list">
            <div><span>Требуют решения</span><b class="${coverage.open ? 'is-warn' : ''}">${coverage.open || 0}</b></div>
            <div><span>Снято с контроля</span><b>${coverage.dismissed || 0}</b></div>
            <div><span>Ручных решений</span><b>${coverage.overrides || 0}</b></div>
            <div><span>Заявки в работе</span><b>${data.requests.pending}</b></div>
          </div>
          <div class="btn-row">
            <button class="btn btn--sm" type="button" data-goto-tab="coverage">Открыть дни без покрытия</button>
          </div>
        </section>
      </div>

      <section class="panel" style="margin-top:0">
        <div class="panel__head">
          <h3>Доля выходных и праздничных дежурств</h3>
          <span class="small muted">кто чаще дежурит в нерабочие дни · шкала 0–100%</span>
        </div>
        ${weekendRows.length ? `
          <div class="share-grid">
            ${weekendRows.map((row) => `
              <div class="share-row" title="${esc(row.name)}: ${row.load.weekend} из ${row.load.total}">
                <span class="share-row__name">${esc(row.name)}</span>
                <div class="bar share-row__bar ${row.weekendShare >= 0.4 ? 'bar--warm' : ''}">
                  <i style="width:${Math.min(100, Number(row.weekendShare || 0) * 100)}%"></i>
                </div>
                <span class="share-row__value">${row.load.weekend} / ${row.load.total}</span>
                <span class="share-row__pct">${Math.round(Number(row.weekendShare || 0) * 100)}%</span>
              </div>
            `).join('')}
          </div>
        ` : '<div class="empty-state">Нет дежурств для расчёта доли выходных.</div>'}
      </section>

      <section class="panel" style="margin-top:0">
        <div class="panel__head">
          <h3>Матрица: сотрудник × день недели</h3>
          <span class="small muted">в ячейке — количество дежурств</span>
        </div>
        <div class="table-wrap">
          <table class="table table--compact weekday-matrix">
            <thead>
              <tr>
                <th>Сотрудник</th>
                ${(data.weekdays || []).map((item) => `<th class="num ${item.weekday >= 5 ? 'cell--weekend-head' : ''}">${esc(item.short)}</th>`).join('')}
                <th class="num">Всего</th>
                <th class="num">Взвеш.</th>
                <th class="num">Отгулы</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map((person) => `
                <tr class="${person.active ? '' : 'row--inactive'}">
                  <td>${personCell({ name: person.name, note: person.active ? (person.note || '') : 'неактивен' })}</td>
                  ${Array.from({ length: 7 }, (_, index) => {
                    const count = Number((person.byWeekday || [])[index] || 0);
                    return `<td class="num ${index >= 5 ? 'cell--weekend' : ''} ${count ? '' : 'cell--zero'}">${count}</td>`;
                  }).join('')}
                  <td class="num"><b>${person.load.total}</b></td>
                  <td class="num">${Number(person.load.weighted).toFixed(2)}</td>
                  <td class="num nowrap">${person.comps.pending} / ${person.comps.scheduled} / ${person.comps.used}</td>
                </tr>
              `).join('')}
              <tr class="row--total">
                <td>Итого</td>
                ${weekdayTotals.map((total, index) => `<td class="num ${index >= 5 ? 'cell--weekend' : ''}">${total}</td>`).join('')}
                <td class="num"><b>${weekdayTotals.reduce((sum, value) => sum + value, 0)}</b></td>
                <td class="num">${weightedTotal.toFixed(2)}</td>
                <td class="num">—</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="small muted" style="margin-top:8px">Выходные и праздничные дни учитываются с весом ${data.weekendWeight}; отгулы: ожидает / запланирован / использован.</div>
      </section>

      <section class="panel" style="margin-top:0">
        <div class="panel__head">
          <h3>Нагрузка по сотрудникам</h3>
          <span class="small muted">Δ — отклонение от средней; отгулы: ожидает / запланирован / использован</span>
        </div>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>Сотрудник</th>
                <th class="num">Всего</th>
                <th class="num">Будни</th>
                <th class="num">Выходные</th>
                <th>Взвешенная нагрузка</th>
                <th class="num">Δ</th>
                <th class="num">План / вып. / неявка</th>
                <th class="num">Отгулы</th>
                <th class="num">Последнее</th>
                <th class="num">Следующее</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map((person) => {
                const delta = Number(person.load.weighted) - data.fairness.mean;
                return `
                <tr class="${person.active ? '' : 'row--inactive'}">
                  <td>${personCell({ name: person.name, note: person.active ? (person.note || '') : 'неактивен' })}</td>
                  <td class="num">${person.load.total}</td>
                  <td class="num">${person.load.weekday}</td>
                  <td class="num">${person.load.weekend}</td>
                  <td>
                    <div class="load-cell">
                      <div class="bar ${person.load.weighted > data.fairness.mean * 1.25 ? 'bar--warm' : ''}">
                        <i style="width:${(person.load.weighted / maxLoad) * 100}%"></i>
                      </div>
                      <span>${Number(person.load.weighted).toFixed(2)}</span>
                    </div>
                  </td>
                  <td class="num ${delta > 0.5 ? 'is-over' : (delta < -0.5 ? 'is-under' : '')}">${delta > 0 ? '+' : ''}${delta.toFixed(2)}</td>
                  <td class="num nowrap">${person.counts.planned} / ${person.counts.done} / ${person.counts.missed}</td>
                  <td class="num nowrap">${person.comps.pending} / ${person.comps.scheduled} / ${person.comps.used}</td>
                  <td class="num">${person.lastDuty ? fmtShort(person.lastDuty) : '—'}</td>
                  <td class="num">${person.nextDuty ? fmtShort(person.nextDuty) : '—'}</td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel" style="margin-top:0">
        <div class="panel__head">
          <h3>Аудит жеребьёвок</h3>
          <span class="small muted">последние ${draws.length} · пруф пересчитывается при открытии</span>
        </div>
        ${draws.length ? `
          <div class="table-wrap">
            <table class="table table--compact">
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Режим</th>
                  <th>Победитель</th>
                  <th class="num">Seed</th>
                  <th>Пруф</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                ${draws.map((item) => `
                  <tr>
                    <td class="num">${fmtShort(item.date)}</td>
                    <td>${esc(item.modeLabel || DRAW_MODE_LABEL[item.mode] || item.mode)}</td>
                    <td><b>${esc(item.winner)}</b></td>
                    <td class="num mono">${item.seed}</td>
                    <td>${proofBadge(item, 'открыть')}</td>
                    <td>${item.verified === true
                      ? '<span class="pill pill--used">проверен</span>'
                      : (item.verified === false
                        ? '<span class="pill pill--danger">не совпал</span>'
                        : '<span class="pill">архив</span>')}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        ` : '<div class="empty-state" style="padding:24px">Жеребьёвок пока не было. Пруф появится после первого розыгрыша.</div>'}
      </section>

      <div class="note-panel">
        <strong>Взвешенная нагрузка</strong> = число будних дежурств × 1 + число выходных/праздничных × ${data.weekendWeight}.
        При жеребьёвке вес кандидата равен <b>(Lmax − L + 1)<sup>${data.fairnessPower}</sup></b>, вероятность — вес / сумма весов отмеченных кандидатов.
        Каждый розыгрыш запечатан SHA-256; ссылка «пруф» открывает пакет с seed, случайным числом и весами для независимой проверки.
      </div>
    `;

    $$('#view [data-goto-tab]').forEach((button) => {
      button.addEventListener('click', () => switchTab(button.dataset.gotoTab));
    });
  }

  /* ---------- settings ---------- */

  async function renderSettings() {
    const s = S.settings;
    const currentYear = Number(S.today.slice(0, 4));
    const holidays = [...S.holidays].sort((a, b) => a.date.localeCompare(b.date));
    if (isAdmin()) {
      S.notifications = await api('/api/notifications?limit=30');
    }
    const journal = S.notifications?.notifications || [];

    el('view').innerHTML = `
      <div class="page-head">
        <div>
          <h2 class="page-title">Настройки</h2>
          <p class="page-sub">Правила распределения, сроки отгулов и календарь праздников.</p>
        </div>
      </div>

      <div class="grid-2">
        <section class="panel settings-form" style="margin-top:0">
          <div class="panel__head"><h3>Правила дежурств</h3></div>
          <form id="settingsForm" class="form">
            <div class="settings-grid">
              <div class="field field--wide">
                <label for="setUnit">Название подразделения</label>
                <input id="setUnit" type="text" name="unit_name" maxlength="80" value="${esc(s.unit_name)}">
              </div>
              <div class="field">
                <label for="setRest">Отсыпной после дежурства, дней</label>
                <input id="setRest" type="number" name="rest_days" min="0" max="7" value="${s.rest_days}">
                <span class="hint">1 — следующий день недоступен для назначений.</span>
              </div>
              <div class="field">
                <label for="setGap">Минимальный интервал, дней</label>
                <input id="setGap" type="number" name="min_gap_days" min="1" max="30" value="${s.min_gap_days}">
                <span class="hint">Не меньше отсыпного + 1.</span>
              </div>
              <div class="field">
                <label for="setWeight">Вес выходного дежурства</label>
                <input id="setWeight" type="number" name="weekend_weight" min="1" max="3" step="0.1" value="${s.weekend_weight}">
                <span class="hint">Насколько выходное дежурство «тяжелее» буднего при расчёте нагрузки.</span>
              </div>
              <div class="field">
                <label for="setPower">Степень справедливости</label>
                <input id="setPower" type="number" name="fairness_power" min="1" max="4" value="${s.fairness_power}">
                <span class="hint">1 — мягко, 3–4 — сильный приоритет менее загруженным.</span>
              </div>
              <div class="field">
                <label for="setValid">Срок выбора отгула, дней</label>
                <input id="setValid" type="number" name="comp_valid_days" min="1" max="365" value="${s.comp_valid_days}">
                <span class="hint">Сколько дней после выходного дежурства доступен отгул.</span>
              </div>
              <div class="field">
                <label for="setHistory">История для нагрузки, дней</label>
                <input id="setHistory" type="number" name="history_days" min="0" max="3650" value="${s.history_days}">
                <span class="hint">0 — учитывать всю историю.</span>
              </div>
              <div class="field">
                <label for="setReqLimit">Лимит заявок, дней в месяц</label>
                <input id="setReqLimit" type="number" name="request_month_limit" min="0" max="31" value="${s.request_month_limit}">
                <span class="hint">Сколько дней в месяц сотрудник может отметить. 0 — без лимита.</span>
              </div>
              <div class="field">
                <label for="setReqHorizon">Горизонт заявок, дней</label>
                <input id="setReqHorizon" type="number" name="request_horizon_days" min="1" max="365" value="${s.request_horizon_days}">
                <span class="hint">На сколько дней вперёд принимаются заявки.</span>
              </div>
              <div class="field field--wide">
                <label class="check">
                  <input type="checkbox" name="comp_enabled" ${s.comp_enabled ? 'checked' : ''}>
                  Давать отгул за дежурство в выходные и праздники
                </label>
              </div>
            </div>
            <div class="btn-row">
              <button class="btn btn--primary" type="submit">Сохранить настройки</button>
            </div>
          </form>
        </section>

        <section class="panel" style="margin-top:0">
          <div class="panel__head">
            <h3>Праздники</h3>
            <span class="small muted">${holidays.length} ${plural(holidays.length, 'день', 'дня', 'дней')}</span>
          </div>
          <div class="form-row" style="margin-bottom:10px">
            <form id="holidayForm" class="form-row" style="flex:1">
              <input type="date" name="date" required>
              <input type="text" name="name" placeholder="Название" maxlength="120" style="flex:1;min-width:130px">
              <button class="btn btn--sm btn--primary" type="submit">Добавить</button>
            </form>
          </div>
          <form id="seedForm" class="form-row" style="margin-bottom:6px">
            <input type="number" name="year" min="2000" max="2100" value="${currentYear}" style="max-width:110px">
            <button class="btn btn--sm" type="submit">Заполнить праздники РБ</button>
          </form>
          <div class="small muted" style="margin-bottom:12px">
            Государственные праздники РБ (10 нерабочих дней) подгружаются автоматически при запуске
            для прошлого, текущего и следующего года. Удалённые вручную даты повторно не добавляются.
          </div>
          ${holidays.length ? `
            <div class="holiday-list">
              ${holidays.map((holiday) => `
                <div class="holiday-row">
                  <span class="holiday-row__date">${fmtLong(holiday.date)}</span>
                  <span class="holiday-row__name">${esc(holiday.name)}</span>
                  <button class="icon-btn" type="button" data-del-holiday="${holiday.date}" title="Удалить" aria-label="Удалить">×</button>
                </div>
              `).join('')}
            </div>
          ` : '<div class="empty-state" style="padding:24px">Праздники не заданы. Выходными считаются только суббота и воскресенье.</div>'}
        </section>
      </div>

      ${isAdmin() ? `
        <section class="panel">
          <div class="panel__head">
            <h3>Уведомления</h3>
            <span class="small muted">email и Rocket.Chat</span>
          </div>
          <form id="notifyForm" class="form">
            <div class="check-row">
              <label class="check"><input type="checkbox" name="notifications_enabled" ${s.notifications_enabled ? 'checked' : ''}> Включить уведомления</label>
              <label class="check"><input type="checkbox" name="notify_on_request" ${s.notify_on_request ? 'checked' : ''}> Новые заявки</label>
              <label class="check"><input type="checkbox" name="notify_on_decision" ${s.notify_on_decision ? 'checked' : ''}> Решения по заявкам</label>
              <label class="check"><input type="checkbox" name="notify_on_coverage" ${s.notify_on_coverage ? 'checked' : ''}> Дни без покрытия</label>
            </div>
            <div class="settings-grid">
              <div class="field">
                <label for="smtpHost">SMTP-сервер</label>
                <input id="smtpHost" name="smtp_host" type="text" maxlength="200" value="${esc(s.smtp_host)}" placeholder="smtp.example.by">
              </div>
              <div class="field">
                <label for="smtpPort">Порт</label>
                <input id="smtpPort" name="smtp_port" type="number" min="1" max="65535" value="${s.smtp_port}">
              </div>
              <div class="field">
                <label for="smtpUser">Пользователь SMTP</label>
                <input id="smtpUser" name="smtp_user" type="text" maxlength="200" value="${esc(s.smtp_user)}" autocomplete="off">
              </div>
              <div class="field">
                <label for="smtpPassword">Пароль SMTP</label>
                <input id="smtpPassword" name="smtp_password" type="password" maxlength="200" autocomplete="new-password" placeholder="${s.smtp_password_set ? 'сохранён — оставьте пустым' : 'не задан'}">
              </div>
              <div class="field">
                <label for="smtpFrom">Адрес отправителя</label>
                <input id="smtpFrom" name="smtp_from" type="email" maxlength="200" value="${esc(s.smtp_from)}" placeholder="duty@example.by">
              </div>
              <div class="field">
                <label for="chatWebhook">Rocket.Chat webhook</label>
                <input id="chatWebhook" name="rocketchat_webhook" type="url" maxlength="500" value="${esc(s.rocketchat_webhook)}" placeholder="https://chat.example.by/hooks/…">
              </div>
              <div class="field">
                <label for="publicUrl">Адрес системы</label>
                <input id="publicUrl" name="public_url" type="url" maxlength="300" value="${esc(s.public_url)}">
                <span class="hint">Добавляется в письма как ссылка на систему.</span>
              </div>
              <div class="field field--wide">
                <label class="check"><input type="checkbox" name="smtp_tls" ${s.smtp_tls ? 'checked' : ''}> STARTTLS при отправке email</label>
              </div>
            </div>
            <div class="btn-row">
              <button class="btn btn--primary" type="submit">Сохранить уведомления</button>
            </div>
          </form>

          <div class="panel__subhead">
            <h4>Проверка каналов</h4>
            <span class="small muted">сообщение уйдёт на контакты вашей учётной записи</span>
          </div>
          <div class="btn-row" style="margin-bottom:14px">
            <button class="btn btn--sm" type="button" id="testEmailBtn">Тест email</button>
            <button class="btn btn--sm" type="button" id="testChatBtn">Тест Rocket.Chat</button>
            <button class="btn btn--sm btn--ghost" type="button" id="retryNotifyBtn">Повторить ошибки</button>
          </div>

          <div class="panel__subhead">
            <h4>Журнал отправки</h4>
            <span class="small muted">последние ${journal.length}</span>
          </div>
          ${journal.length ? `
            <div class="table-wrap">
              <table class="table table--compact">
                <thead><tr><th>Когда</th><th>Канал</th><th>Получатель</th><th>Тема</th><th>Статус</th><th>Ошибка</th></tr></thead>
                <tbody>
                  ${journal.map((item) => `
                    <tr>
                      <td class="nowrap small">${item.createdAt ? `${fmtShort(item.createdAt.slice(0, 10))} ${esc(item.createdAt.slice(11, 16))}` : '—'}</td>
                      <td><span class="pill">${item.channel === 'email' ? 'email' : 'Rocket.Chat'}</span></td>
                      <td class="small">${esc(item.recipient)}</td>
                      <td class="small">${esc(item.subject || item.event)}</td>
                      <td><span class="pill pill--notify-${esc(item.status)}">${NOTIFY_STATUS[item.status] || item.status}</span></td>
                      <td class="small muted">${esc(item.error || '')}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          ` : '<div class="empty-state" style="padding:22px">Сообщений пока не было. Уведомления ставятся в очередь при событиях заявок и покрытия.</div>'}
        </section>

        <section class="panel">
          <div class="panel__head">
            <h3>Резервная копия</h3>
            <span class="small muted">SQLite</span>
          </div>
          <p class="small muted">Снимок базы целиком: сотрудники, график, заявки, отсутствия, настройки и учётные записи. Файл создаётся согласованно и скачивается в формате SQLite.</p>
          <div class="btn-row">
            <a class="btn btn--primary" href="/api/backup">Скачать копию базы</a>
          </div>
        </section>
      ` : ''}

      <section class="panel">
        <div class="panel__head"><h3>Как работает распределение</h3></div>
        <div class="rule-list">
          <div><b>1. Доступность.</b> Кандидат исключается, если он в отпуске/на больничном, уже дежурит в этот день, находится на отсыпном, нарушает минимальный интервал или у него оформлен отгул.</div>
          <div><b>2. Нагрузка.</b> Буднее дежурство = 1, выходное или праздничное = ${s.weekend_weight}. Отгулы не уменьшают нагрузку — дополнительная тяжесть выходного уже учтена коэффициентом.</div>
          <div><b>3. Вероятность.</b> Среди отмеченных доступных кандидатов вес = <b>(Lmax − L + 1)<sup>${s.fairness_power}</sup></b>. Меньшая нагрузка даёт больший вес; при равной нагрузке шансы равны.</div>
          <div><b>4. Аудит.</b> Каждая жеребьёвка сохраняется с seed и таблицей вероятностей. Один и тот же seed воспроизводит результат.</div>
          <div><b>5. Автораспределение.</b> Заполняет только пустые дни, выбирая сотрудников с минимальной нагрузкой; при равенстве — случайно.</div>
          <div><b>6. Заявки сотрудников.</b> «Не могу» после согласования исключает из назначений на выбранные дни; «предпочитаю» — мягкий приоритет: автораспределение обходит такого сотрудника, если есть альтернатива без роста нагрузки. Жёсткие правила (отсыпной, интервал, отсутствия) остаются в силе.</div>
        </div>
      </section>
    `;

    el('settingsForm').addEventListener('submit', act(async (event) => {
      event.preventDefault();
      const form = new FormData(event.target);
      await api('/api/settings', {
        method: 'PUT',
        body: {
          unit_name: form.get('unit_name'),
          rest_days: Number(form.get('rest_days')),
          min_gap_days: Number(form.get('min_gap_days')),
          weekend_weight: Number(form.get('weekend_weight')),
          fairness_power: Number(form.get('fairness_power')),
          comp_valid_days: Number(form.get('comp_valid_days')),
          history_days: Number(form.get('history_days')),
          request_month_limit: Number(form.get('request_month_limit')),
          request_horizon_days: Number(form.get('request_horizon_days')),
          comp_enabled: form.get('comp_enabled') === 'on',
        },
      });
      toast('Настройки сохранены');
      await loadSchedule(S.month);
    }));

    el('holidayForm').addEventListener('submit', act(async (event) => {
      event.preventDefault();
      const form = new FormData(event.target);
      await api('/api/holidays', {
        method: 'POST',
        body: { date: form.get('date'), name: form.get('name') || '' },
      });
      toast('Праздник добавлен');
      await loadSchedule(S.month);
    }));

    el('seedForm').addEventListener('submit', act(async (event) => {
      event.preventDefault();
      const form = new FormData(event.target);
      const year = Number(form.get('year'));
      const result = await api('/api/holidays/seed', { method: 'POST', body: { year } });
      toast(`Добавлено ${result.inserted} ${plural(result.inserted, 'праздник', 'праздника', 'праздников')} за ${year} год`);
      await loadSchedule(S.month);
    }));

    $$('[data-del-holiday]').forEach((button) => {
      button.addEventListener('click', act(async () => {
        if (!confirm('Удалить праздник?')) return;
        await api(`/api/holidays/${button.dataset.delHoliday}`, { method: 'DELETE' });
        toast('Праздник удалён');
        await loadSchedule(S.month);
      }));
    });

    const notifyForm = el('notifyForm');
    if (notifyForm) {
      notifyForm.addEventListener('submit', act(async (event) => {
        event.preventDefault();
        const form = new FormData(event.target);
        const payload = {
          notifications_enabled: form.get('notifications_enabled') === 'on',
          notify_on_request: form.get('notify_on_request') === 'on',
          notify_on_decision: form.get('notify_on_decision') === 'on',
          notify_on_coverage: form.get('notify_on_coverage') === 'on',
          smtp_host: form.get('smtp_host'),
          smtp_port: Number(form.get('smtp_port')),
          smtp_user: form.get('smtp_user'),
          smtp_from: form.get('smtp_from'),
          smtp_tls: form.get('smtp_tls') === 'on',
          rocketchat_webhook: form.get('rocketchat_webhook'),
          public_url: form.get('public_url'),
        };
        const password = form.get('smtp_password');
        if (password) payload.smtp_password = password;
        await api('/api/settings', { method: 'PUT', body: payload });
        toast('Настройки уведомлений сохранены');
        await loadSchedule(S.month);
      }));

      el('testEmailBtn').addEventListener('click', act(async () => {
        const result = await api('/api/notifications/test', {
          method: 'POST',
          body: { channel: 'email' },
        });
        if (result.status === 'sent') toast('Тестовое письмо отправлено');
        else toast(result.error || 'Не удалось отправить письмо', 'error');
        await renderSettings();
      }));
      el('testChatBtn').addEventListener('click', act(async () => {
        const result = await api('/api/notifications/test', {
          method: 'POST',
          body: { channel: 'rocketchat' },
        });
        if (result.status === 'sent') toast('Сообщение в Rocket.Chat отправлено');
        else toast(result.error || 'Не удалось отправить сообщение', 'error');
        await renderSettings();
      }));
      el('retryNotifyBtn').addEventListener('click', act(async () => {
        const result = await api('/api/notifications/retry', { method: 'POST', body: {} });
        toast(`Повторно отправлено: ${result.sent}`);
        await renderSettings();
      }));
    }
  }

  /* ---------- auto plan ---------- */

  function openAutoPlan() {
    const from = `${S.month}-01`;
    const to = lastDayOfMonth(S.month);
    openModal({
      title: 'Автораспределение',
      body: `
        <div class="banner">
          Заполняются только пустые дни. Выбирается сотрудник с минимальной взвешенной нагрузкой;
          при равенстве — жребий. Отсыпной, минимальный интервал, отгулы, отсутствия и согласованные
          заявки «не могу» учитываются автоматически; «предпочитаю» — мягкий приоритет.
        </div>
        <form id="autoForm" class="form">
          <div class="settings-grid">
            <div class="field">
              <label for="autoFrom">С</label>
              <input id="autoFrom" type="date" name="date_from" value="${from}" required>
            </div>
            <div class="field">
              <label for="autoTo">По</label>
              <input id="autoTo" type="date" name="date_to" value="${to}" required>
            </div>
            <div class="field field--wide">
              <label for="autoSeed">Seed (необязательно)</label>
              <input id="autoSeed" type="number" name="seed" min="0" placeholder="случайный — оставьте пустым">
              <span class="hint">Одинаковый seed и одинаковые данные дают одинаковый график.</span>
            </div>
          </div>
        </form>
      `,
      foot: `
        <button class="btn" type="button" data-close>Отмена</button>
        <button class="btn btn--primary" type="submit" form="autoForm" id="autoSubmit">Распределить</button>
      `,
      bind: (body) => {
        $('#autoForm', body).addEventListener('submit', act(async (event) => {
          event.preventDefault();
          const form = new FormData(event.target);
          const payload = {
            date_from: form.get('date_from'),
            date_to: form.get('date_to'),
          };
          const seed = form.get('seed');
          if (seed !== null && String(seed).trim() !== '') payload.seed = Number(seed);
          const button = el('autoSubmit');
          button.disabled = true;
          button.textContent = 'Распределяю…';
          try {
            const result = await api('/api/auto-plan', { method: 'POST', body: payload });
            await loadSchedule(S.month);
            showAutoResult(result);
          } finally {
            button.disabled = false;
            button.textContent = 'Распределить';
          }
        }));
      },
    });
  }

  function showAutoResult(result) {
    const hardSkips = result.skipped.filter((item) => item.reason !== 'день уже занят');
    const occupied = result.skipped.length - hardSkips.length;
    openModal({
      title: 'Автораспределение завершено',
      wide: true,
      body: `
        <div class="winner-card">
          <div>
            <div class="winner-card__name">Назначено ${result.count} ${plural(result.count, 'дежурство', 'дежурства', 'дежурств')}</div>
            <div class="winner-card__prob">seed <code>${result.seed}</code>${occupied ? ` · занятых дней пропущено: ${occupied}` : ''}</div>
          </div>
        </div>
        ${result.assigned.length ? `
          <div class="table-wrap">
            <table class="table table--compact">
              <thead><tr><th>Дата</th><th>Сотрудник</th><th>Тип дня</th><th class="num">Нагрузка до назначения</th></tr></thead>
              <tbody>
                ${result.assigned.map((item) => `
                  <tr>
                    <td class="nowrap">${fmtLong(item.date)}</td>
                    <td>${esc(item.person_name)}</td>
                    <td>${item.weekend ? '<span class="pill pill--pending">выходной</span>' : 'рабочий'}</td>
                    <td class="num">${Number(item.load_before).toFixed(2)}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        ` : '<div class="banner">Свободных дней для распределения нет.</div>'}
        ${hardSkips.length ? `
          <div class="day-section" style="margin-top:10px">
            <div class="section-label">Не заполнено</div>
            <div class="table-wrap">
              <table class="table table--compact">
                <thead><tr><th>Дата</th><th>Причина</th></tr></thead>
                <tbody>
                  ${hardSkips.map((item) => `<tr><td class="nowrap">${fmtLong(item.date)}</td><td>${esc(item.reason)}</td></tr>`).join('')}
                </tbody>
              </table>
            </div>
          </div>
        ` : ''}
      `,
      foot: '<button class="btn btn--primary" type="button" data-close>Готово</button>',
    });
  }

  /* ---------- day modal ---------- */

  async function openDay(dateStr) {
    let candidateData;
    try {
      candidateData = await api(`/api/candidates?date=${encodeURIComponent(dateStr)}`);
    } catch (error) {
      toast(error.message, 'error');
      return;
    }
    const day = (S.data?.days || []).find((item) => item.date === dateStr) || {
      rests: [], comps: [], absences: [], holiday: candidateData.holiday, dayOff: candidateData.dayOff,
    };

    let compItem = null;
    if (candidateData.duty && candidateData.dayOff && candidateData.rules.comp_enabled) {
      try {
        const comps = await api('/api/comps');
        compItem = (comps.comps || []).find((item) => item.duty_id === candidateData.duty.id) || null;
      } catch { /* not critical for the day card */ }
    }

    const foot = candidateData.duty
      ? '<button class="btn" type="button" data-close>Закрыть</button>'
      : `
        <div class="foot-info small muted">Отметьте претендентов. Жеребьёвка пройдёт только среди них.</div>
        <button class="btn btn--ghost" type="button" id="rouletteBtn">Рулетка</button>
        <button class="btn btn--primary" type="button" id="drawBtn" disabled>Провести жеребьёвку</button>
      `;

    openModal({
      title: fullDate(dateStr),
      wide: true,
      body: buildDayBody(dateStr, candidateData, day, compItem),
      foot,
      bind: (body, footEl) => bindDayModal(dateStr, candidateData, body, footEl),
    });
  }

  function buildDayBody(dateStr, candidateData, day, compItem) {
    let html = '';
    if (candidateData.holiday) {
      html += `<div class="banner banner--holiday">Праздничный день: ${esc(candidateData.holiday)}. Дежурство учитывается как выходное.</div>`;
    } else if (candidateData.dayOff) {
      html += '<div class="banner banner--weekend">Выходной день. За дежурство положен отгул на выбор.</div>';
    } else {
      html += '<div class="banner">Рабочий день. После дежурства на следующий день — отсыпной.</div>';
    }

    const events = [];
    (day.rests || []).forEach((rest) => {
      events.push(`<span class="mini mini--rest">отсыпной · ${esc(rest.personName)}</span>`);
    });
    (day.comps || []).forEach((comp) => {
      events.push(`<span class="mini mini--comp">отгул · ${esc(comp.personName)}</span>`);
    });
    (day.absences || []).forEach((absence) => {
      events.push(`<span class="mini mini--abs">${KIND_SHORT[absence.kind] || 'отсутствие'} · ${esc(absence.personName)}</span>`);
    });
    (day.requests || []).forEach((request) => {
      const preferred = request.kind === 'preferred';
      const approved = request.status === 'approved';
      const cls = preferred ? 'mini--pref' : (approved ? 'mini--req-approved' : 'mini--req');
      const label = preferred ? 'просит' : (approved ? 'не может' : 'не может · ждёт');
      events.push(`<span class="mini ${cls}">${label} · ${esc(request.personName)}</span>`);
    });
    if (events.length) html += `<div class="day-events">${events.join('')}</div>`;

    if (candidateData.duty) {
      const duty = candidateData.duty;
      const currentStatus = duty.status;
      html += `
        <section class="day-section">
          <div class="section-label">Дежурный</div>
          <div class="duty-hero">
            <span class="avatar avatar--lg">${esc(initials(duty.personName))}</span>
            <div>
              <div class="duty-hero__name">${esc(duty.personName)}</div>
              <div class="duty-hero__meta">
                ${SOURCE_LABEL[duty.source] || duty.source} · ${STATUS_LABEL[currentStatus] || currentStatus}
                ${duty.note ? ` · ${esc(duty.note)}` : ''}
              </div>
            </div>
          </div>
          <div class="btn-row">
            <button class="btn btn--sm" type="button" data-duty-status="done" ${currentStatus === 'done' ? 'disabled' : ''}>Выполнено</button>
            <button class="btn btn--sm" type="button" data-duty-status="missed" ${currentStatus === 'missed' ? 'disabled' : ''}>Неявка</button>
            <button class="btn btn--sm" type="button" data-duty-status="planned" ${currentStatus === 'planned' ? 'disabled' : ''}>Вернуть в план</button>
            <button class="btn btn--sm btn--danger" type="button" data-duty-remove>Снять дежурство</button>
          </div>
        </section>
      `;
      if (candidateData.dayOff) {
        html += buildCompSection(dateStr, candidateData, compItem);
      }
    } else {
      html += buildCandidatesSection(candidateData);
    }
    return html;
  }

  function buildCompSection(dateStr, candidateData, compItem) {
    if (!candidateData.rules.comp_enabled) {
      return `
        <section class="day-section">
          <div class="section-label">Отгул</div>
          <div class="banner">Отгулы отключены в настройках.</div>
        </section>
      `;
    }
    const status = compItem?.status || 'pending';
    const choiceDate = compItem?.choice_date || '';
    const min = addDays(dateStr, 1);
    const max = compItem?.valid_until || addDays(dateStr, candidateData.rules.comp_valid_days);
    let controls = '';
    if (status === 'declined') {
      controls = '<button class="btn btn--sm" type="button" data-comp="pending">Вернуть в ожидание</button>';
    } else if (status === 'used') {
      controls = '<button class="btn btn--sm btn--ghost" type="button" data-comp="pending">Сбросить отметку</button>';
    } else {
      controls = `
        <div class="form-row">
          <input type="date" id="compDate" min="${min}" max="${max}" value="${esc(choiceDate)}">
          <button class="btn btn--sm btn--primary" type="button" data-comp="scheduled">${choiceDate ? 'Перенести' : 'Оформить'}</button>
          ${status === 'scheduled' ? '<button class="btn btn--sm" type="button" data-comp="used">Отметить использованным</button>' : ''}
          ${status === 'scheduled' ? '<button class="btn btn--sm btn--ghost" type="button" data-comp="pending">Сброс</button>' : ''}
          <button class="btn btn--sm btn--ghost" type="button" data-comp="declined">Отказ</button>
        </div>
      `;
    }
    return `
      <section class="day-section">
        <div class="section-head">
          <div class="section-label">Отгул за выходное дежурство</div>
          <span class="pill pill--${status}">${COMP_LABEL[status]}</span>
        </div>
        <div class="comp-box">
          <div class="small muted">
            Срок выбора — до ${fmtLong(max)}. Только рабочий день, свободный от дежурств, отсыпных и отсутствий.
            ${choiceDate ? `<br>Выбранная дата: <b>${fmtLong(choiceDate)}</b>.` : ''}
          </div>
          <div style="margin-top:8px">${controls}</div>
        </div>
      </section>
    `;
  }

  function buildCandidatesSection(candidateData) {
    const candidates = candidateData.candidates || [];
    const eligibleCount = candidates.filter((candidate) => candidate.eligible).length;
    if (!candidates.length) {
      return '<div class="empty-state">Нет активных сотрудников.</div>';
    }
    return `
      <section class="day-section">
        <div class="section-head">
          <div>
            <div class="section-label">Кандидаты на дежурство</div>
            <div class="small muted">Доступно: ${eligibleCount} из ${candidates.length}. Отметьте участников жеребьёвки.</div>
          </div>
        </div>
        ${eligibleCount ? '' : '<div class="banner banner--danger">Нет доступных сотрудников. День попадёт в раздел «Требуют решения»: тимлид может назначить дежурного поверх правил или снять день с контроля.</div>'}
        <div class="table-wrap">
          <table class="table cand-table">
            <thead>
              <tr>
                <th style="width:34px"></th>
                <th>Сотрудник</th>
                <th class="num">Всего</th>
                <th class="num">Выходных</th>
                <th class="num">Нагрузка</th>
                <th style="width:130px">Вероятность</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${candidates.map((candidate) => `
                <tr class="${candidate.eligible ? 'row--selected' : 'row--blocked'}" data-pid="${candidate.person_id}">
                  <td>
                    <input class="cand-check" type="checkbox" data-pid="${candidate.person_id}"
                      ${candidate.eligible ? 'checked' : 'disabled'} aria-label="Участвует в жеребьёвке">
                  </td>
                  <td>
                    <div class="person-cell">
                      <span class="avatar">${esc(initials(candidate.person_name))}</span>
                      <div class="person-cell__text">
                        <div class="person-cell__name">${esc(candidate.person_name)}</div>
                        ${candidate.eligible ? '' : `<div class="reason">${esc(candidate.reasons.join('; '))}</div>`}
                        ${candidate.warnings && candidate.warnings.length ? `<div class="warn-note">${esc(candidate.warnings.join('; '))}</div>` : ''}
                      </div>
                    </div>
                  </td>
                  <td class="num">${candidate.load.total}</td>
                  <td class="num">${candidate.load.weekend}</td>
                  <td class="num">${Number(candidate.load.weighted).toFixed(2)}</td>
                  <td>
                    <div class="prob">
                      <span class="prob__value" data-prob>${candidate.eligible ? pct(candidate.probability) : '—'}</span>
                      <div class="bar"><i data-bar style="width:${(Number(candidate.probability) * 100).toFixed(1)}%"></i></div>
                    </div>
                  </td>
                  <td class="nowrap">
                    ${candidate.eligible ? `<button class="btn btn--sm btn--primary" type="button" data-assign="${candidate.person_id}">Назначить</button>` : ''}
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
        <div class="formula">
          <b>Вес</b> = (Lmax − L + 1)<sup>${candidateData.rules.fairness_power}</sup>, где L — взвешенная нагрузка
          (выходное дежурство = ${candidateData.rules.weekend_weight}). <b>Вероятность</b> = вес / сумма весов отмеченных доступных кандидатов.
          Отсыпной: ${candidateData.rules.rest_days} дн.; минимальный интервал: ${candidateData.rules.min_gap_days} дн.
        </div>
      </section>
    `;
  }

  function bindDayModal(dateStr, candidateData, body, footEl) {
    const duty = candidateData.duty;

    if (duty) {
      $$('[data-duty-status]', body).forEach((button) => {
        button.addEventListener('click', act(async () => {
          await api(`/api/duties/${duty.id}`, {
            method: 'PATCH',
            body: { status: button.dataset.dutyStatus },
          });
          toast('Статус дежурства обновлён');
          await loadSchedule(S.month);
          await openDay(dateStr);
        }));
      });

      const removeButton = $('[data-duty-remove]', body);
      removeButton.addEventListener('click', act(async () => {
        if (!confirm('Снять дежурство с этого дня?')) return;
        await api(`/api/duties/${duty.id}`, { method: 'DELETE' });
        toast('Дежурство снято');
        await loadSchedule(S.month);
        await openDay(dateStr);
      }));

      $$('[data-comp]', body).forEach((button) => {
        button.addEventListener('click', act(async () => {
          const status = button.dataset.comp;
          let date = null;
          if (status === 'scheduled' || status === 'used') {
            date = $('#compDate', body)?.value || null;
            if (!date) {
              toast('Укажите дату отгула', 'error');
              return;
            }
          }
          await api(`/api/comps/${duty.id}`, {
            method: 'PUT',
            body: { status, date },
          });
          toast('Отгул обновлён');
          await loadSchedule(S.month);
          await openDay(dateStr);
        }));
      });
      return;
    }

    const checked = new Set(
      candidateData.candidates.filter((candidate) => candidate.eligible).map((candidate) => candidate.person_id)
    );

    const recalc = () => {
      const power = Number(candidateData.rules.fairness_power || 2);
      const pool = candidateData.candidates.filter((candidate) =>
        candidate.eligible && checked.has(candidate.person_id));
      const maxLoad = pool.reduce((max, candidate) => Math.max(max, Number(candidate.load.weighted)), 0);
      const weights = new Map();
      let sum = 0;
      pool.forEach((candidate) => {
        const weight = Math.pow(maxLoad - Number(candidate.load.weighted) + 1, power);
        weights.set(candidate.person_id, weight);
        sum += weight;
      });

      candidateData.candidates.forEach((candidate) => {
        const row = $(`tr[data-pid="${candidate.person_id}"]`, body);
        if (!row) return;
        const isChosen = candidate.eligible && checked.has(candidate.person_id);
        row.classList.toggle('row--selected', isChosen);
        const probability = sum && weights.has(candidate.person_id)
          ? weights.get(candidate.person_id) / sum
          : 0;
        const probEl = $('[data-prob]', row);
        if (probEl) probEl.textContent = candidate.eligible ? pct(probability) : '—';
        const barEl = $('[data-bar]', row);
        if (barEl) barEl.style.width = `${(probability * 100).toFixed(1)}%`;
      });

      const drawButton = el('drawBtn');
      if (drawButton) {
        drawButton.textContent = `Провести жеребьёвку (${pool.length})`;
        drawButton.disabled = pool.length === 0;
      }
    };

    $$('.cand-check', body).forEach((checkbox) => {
      checkbox.addEventListener('change', () => {
        const personId = Number(checkbox.dataset.pid);
        if (checkbox.checked) checked.add(personId);
        else checked.delete(personId);
        recalc();
      });
    });

    $$('[data-assign]', body).forEach((button) => {
      button.addEventListener('click', act(async () => {
        const personId = Number(button.dataset.assign);
        await api('/api/duties', {
          method: 'POST',
          body: { date: dateStr, person_id: personId },
        });
        toast('Дежурство назначено');
        closeModal();
        await loadSchedule(S.month);
      }));
    });

    const rouletteButton = el('rouletteBtn');
    if (rouletteButton) {
      rouletteButton.addEventListener('click', act(async () => {
        await openRoulette(dateStr);
      }));
    }

    const drawButton = el('drawBtn');
    if (drawButton) {
      drawButton.addEventListener('click', act(async () => {
        const ids = [...checked];
        if (!ids.length) return;
        const previous = drawButton.textContent;
        drawButton.disabled = true;
        drawButton.textContent = 'Жеребьёвка…';
        try {
          const result = await api('/api/draw', {
            method: 'POST',
            body: { date: dateStr, candidate_ids: ids },
          });
          await loadSchedule(S.month);
          showDrawResult(result);
        } catch (error) {
          drawButton.disabled = false;
          drawButton.textContent = previous;
          throw error;
        }
      }));
    }

    recalc();
  }

  function showDrawResult(result) {
    const candidates = result.candidates || [];
    openModal({
      title: 'Розыгрыш проведён',
      wide: true,
      body: `
        <div class="winner-card">
          <span class="avatar">${esc(initials(result.winner.personName))}</span>
          <div>
            <div class="winner-card__name">${esc(result.winner.personName)}</div>
            <div class="winner-card__prob">
              ${pct(result.winner.probability)} · нагрузка ${Number(result.winner.load.weighted).toFixed(2)}
              · ${fmtLong(result.date)}
            </div>
          </div>
        </div>
        <div class="proof-strip">
          <div>
            <span class="proof-strip__label">${esc(DRAW_MODE_LABEL[result.mode] || 'Жребий')} · seed</span>
            <code>${result.seed}</code>
            ${result.roll !== undefined ? `<span class="proof-strip__label">· roll</span> <code>${Number(result.roll).toFixed(12)}</code>` : ''}
          </div>
          ${result.proofUrl
            ? `<a class="btn btn--sm btn--primary" href="${esc(result.proofUrl)}" target="_blank" rel="noopener">Пруф · SHA-256</a>`
            : ''}
        </div>
        ${result.proofHash ? `<div class="small muted" style="margin:-4px 0 12px">SHA-256 <code>${esc(result.proofHash)}</code></div>` : ''}
        <div class="table-wrap">
          <table class="table table--compact">
            <thead><tr><th>Кандидат</th><th class="num">Дежурств</th><th class="num">Выходных</th><th class="num">Нагрузка</th><th style="width:130px">Вероятность</th><th></th></tr></thead>
            <tbody>
              ${candidates.map((candidate) => `
                <tr class="${candidate.winner ? 'row--selected' : ''}">
                  <td>${esc(candidate.name)}</td>
                  <td class="num">${candidate.total}</td>
                  <td class="num">${candidate.weekend}</td>
                  <td class="num">${Number(candidate.weighted).toFixed(2)}</td>
                  <td><div class="prob"><span class="prob__value">${pct(candidate.probability)}</span><div class="bar"><i style="width:${(Number(candidate.probability) * 100).toFixed(1)}%"></i></div></div></td>
                  <td>${candidate.winner ? '<span class="pill pill--used">выбран</span>' : ''}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `,
      foot: '<button class="btn btn--primary" type="button" data-close>Готово</button>',
    });
  }

  /* ---------- roulette ---------- */

  const ROULETTE_COLORS = [
    '#a8443c', '#3a3733', '#3c5a80', '#7a5420', '#5a3a58', '#3a6650',
    '#8a3a34', '#42566b', '#94443c', '#4a463f', '#2f5f62', '#6b442e',
  ];

  const ROULETTE_RADIUS = 176;

  function roulettePoint(angle, radius) {
    const rad = (angle * Math.PI) / 180;
    return [200 + radius * Math.sin(rad), 200 - radius * Math.cos(rad)];
  }

  function rouletteArc(start, end, radius = ROULETTE_RADIUS) {
    const [x0, y0] = roulettePoint(start, radius);
    const [x1, y1] = roulettePoint(end, radius);
    const large = end - start > 180 ? 1 : 0;
    return `M 200 200 L ${x0.toFixed(2)} ${y0.toFixed(2)} `
      + `A ${radius} ${radius} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z`;
  }

  function rouletteParticipants(data, mode) {
    const equal = mode === 'equal';
    return data.candidates
      .filter((candidate) => candidate.eligible)
      .map((candidate, index) => ({
        id: candidate.person_id,
        name: candidate.person_name,
        monthDuties: Number(candidate.month_duties || 0),
        probability: Number(equal ? candidate.equal_probability : candidate.month_probability),
        weight: Number(equal ? candidate.equal_weight : candidate.month_weight),
        conflicts: candidate.conflicts || [],
        color: ROULETTE_COLORS[index % ROULETTE_COLORS.length],
      }));
  }

  function rouletteSectors(participants) {
    let angle = 0;
    return participants.map((participant, index) => {
      const span = participant.probability * 360;
      const sector = {
        ...participant,
        start: angle,
        end: index === participants.length - 1 ? 360 : angle + span,
      };
      angle = sector.end;
      return sector;
    });
  }

  function rouletteWheelSvg(participants) {
    const sectors = rouletteSectors(participants);
    const single = sectors.length === 1;
    const shapes = sectors.map((sector) => (single
      ? `<circle cx="200" cy="200" r="${ROULETTE_RADIUS}" fill="${sector.color}"></circle>`
      : `<path d="${rouletteArc(sector.start, sector.end)}" fill="${sector.color}" `
        + 'stroke="#ffffff" stroke-width="1.5"></path>'
    )).join('');
    const labels = sectors.map((sector) => {
      const span = sector.end - sector.start;
      if (span < 14) return '';
      const mid = single ? 0 : (sector.start + sector.end) / 2;
      const size = Math.min(16, Math.max(9, span / 2.4));
      return `
        <g transform="rotate(${mid.toFixed(2)} 200 200)">
          <text x="200" y="${single ? 96 : 118}" text-anchor="middle"
            class="roulette__label" style="font-size:${size.toFixed(1)}px">${esc(initials(sector.name))}</text>
        </g>
      `;
    }).join('');
    return `
      <svg viewBox="0 0 400 400" role="img" aria-label="Колесо рулетки, участников: ${sectors.length}">
        <circle cx="200" cy="200" r="186" fill="#ffffff" stroke="#dbe6ea" stroke-width="2"></circle>
        <g data-rotor class="roulette__rotor">${shapes}${labels}</g>
        <circle cx="200" cy="200" r="54" fill="#ffffff" stroke="#cfe0e4" stroke-width="3"></circle>
        <text x="200" y="209" text-anchor="middle" class="roulette__hub-text" data-hub-text>?</text>
      </svg>
    `;
  }

  function rouletteListHtml(participants) {
    return participants.map((participant) => `
      <div class="roulette-list__row" data-roulette-row="${participant.id}">
        <span class="roulette-list__dot" style="background:${participant.color}"></span>
        <div class="roulette-list__text">
          <div class="roulette-list__name">${esc(participant.name)}</div>
          <div class="small muted">${participant.monthDuties} ${plural(participant.monthDuties, 'дежурство', 'дежурства', 'дежурств')} в этом месяце</div>
          ${participant.conflicts?.length ? `<div class="small muted">отклонения: ${esc(participant.conflicts.join('; '))}</div>` : ''}
        </div>
        <span class="roulette-list__prob">${pct(participant.probability)}</span>
      </div>
    `).join('');
  }

  function rouletteFormulaHtml(data, mode) {
    if (mode === 'equal') {
      return '<b>Равные шансы.</b> Дежурства не учитываются: у каждого участника вес 1, '
        + 'вероятность = 1 / число участников.';
    }
    return `<b>С учётом дежурств за месяц.</b> Вес = (M<sub>max</sub> − M + 1)<sup>${data.fairness_power}</sup>, `
      + `где M — число дежурств в ${monthLabel(data.month)}. Чем меньше дежурств, тем выше шанс.`;
  }

  function rouletteHint(mode, data) {
    return mode === 'equal'
      ? 'У всех участников одинаковый шанс — дежурства не учитываются.'
      : `Шанс выше у тех, кто меньше дежурил в ${monthLabel(data.month)}.`;
  }

  function rouletteWinnerHtml(result, participants) {
    const winner = participants.find((participant) => participant.id === result.winner.personId);
    const monthDuties = winner ? winner.monthDuties : Number(result.winner.monthDuties || 0);
    return `
      <div class="winner-card">
        <span class="avatar">${esc(initials(result.winner.personName))}</span>
        <div>
          <div class="winner-card__name">${esc(result.winner.personName)}</div>
          <div class="winner-card__prob">
            ${pct(result.winner.probability)} · ${monthDuties} ${plural(monthDuties, 'дежурство', 'дежурства', 'дежурств')} в месяце
            · ${fmtLong(result.date)}
          </div>
        </div>
        <span class="pill pill--used" style="margin-left:auto">назначен</span>
      </div>
      ${result.deviations?.length ? `
        <div class="banner banner--weekend small">Отклонения от правил: ${esc(result.deviations.join('; '))}</div>
      ` : ''}
      <div class="proof-strip">
        <div>
          <span class="proof-strip__label">${esc(DRAW_MODE_LABEL[result.mode] || 'Рулетка')} · seed</span>
          <code>${result.seed}</code>
          ${result.roll !== undefined ? `<span class="proof-strip__label">· roll</span> <code>${Number(result.roll).toFixed(12)}</code>` : ''}
        </div>
        ${result.proofUrl
          ? `<a class="btn btn--sm btn--primary" href="${esc(result.proofUrl)}" target="_blank" rel="noopener">Открыть пруф</a>`
          : ''}
      </div>
      ${result.proofHash ? `<div class="small muted" style="margin:6px 0 0">SHA-256 <code>${esc(result.proofHash)}</code></div>` : ''}
    `;
  }

  function buildRouletteBody(data) {
    const eligible = data.candidates.filter((candidate) => candidate.eligible);
    const blocked = data.candidates.filter((candidate) => !candidate.eligible);
    const dayType = data.holiday
      ? `Праздник: ${esc(data.holiday)}`
      : (data.dayOff ? 'Выходной день' : 'Рабочий день');
    const head = `
      <div class="roulette__top">
        <div>
          <div class="roulette__date">${esc(fullDate(data.date))}</div>
          <div class="small muted">${dayType} · выбранный сотрудник сразу получает дежурство</div>
          ${data.duty ? `<div class="small muted">${esc(`Сейчас дежурит: ${data.duty.personName} — день будет переигран`)}</div>` : ''}
        </div>
        <div class="segmented" role="group" aria-label="Режим рулетки">
          <button type="button" class="segmented__btn is-active" data-roulette-mode="month" aria-pressed="true">Дежурства за месяц</button>
          <button type="button" class="segmented__btn" data-roulette-mode="equal" aria-pressed="false">Равные шансы</button>
        </div>
      </div>
      <label class="check" style="margin-bottom:14px">
        <input type="checkbox" id="rouletteRelaxed" ${data.relaxed ? 'checked' : ''}>
        <span>Не блокировать интервал, отгул и заявки — исключать только отпуск и отсыпной</span>
      </label>
    `;
    if (!eligible.length) {
      return `
        <div class="roulette">${head}
          <div class="banner banner--danger">
            ${data.relaxed
              ? 'Нет сотрудников вне отпуска и отсыпного.'
              : 'Нет доступных сотрудников: у всех есть отпуск, отсыпной, интервал или согласованная заявка. Включите послабление выше или разберите день в разделе «Требуют решения».'}
          </div>
        </div>
      `;
    }
    const participants = rouletteParticipants(data, 'month');
    return `
      <div class="roulette">
        ${head}
        <div id="rouletteResult"></div>
        <div class="roulette__grid">
          <div class="roulette__stage">
            <div class="roulette__pointer" aria-hidden="true"></div>
            <div class="roulette__wheel" id="rouletteWheel">${rouletteWheelSvg(participants)}</div>
          </div>
          <div class="roulette__side">
            <div class="section-label">Участники</div>
            <div class="roulette-list" id="rouletteList">${rouletteListHtml(participants)}</div>
            <div class="formula" id="rouletteFormula">${rouletteFormulaHtml(data, 'month')}</div>
            ${blocked.length ? `
              <details class="roulette-blocked">
                <summary>Не участвуют: ${blocked.length}</summary>
                <ul>
                  ${blocked.map((candidate) => `
                    <li><b>${esc(candidate.person_name)}</b> — ${esc(candidate.reasons.join('; '))}</li>
                  `).join('')}
                </ul>
              </details>
            ` : ''}
          </div>
        </div>
      </div>
    `;
  }

  function spinRouletteWheel(body, participants, winnerId) {
    return new Promise((resolve) => {
      const wheel = $('#rouletteWheel', body);
      const rotor = wheel ? $('[data-rotor]', wheel) : null;
      const winner = rouletteSectors(participants)
        .find((sector) => sector.id === winnerId);
      if (!rotor || !winner) {
        resolve();
        return;
      }
      const mid = (winner.start + winner.end) / 2;
      const span = winner.end - winner.start;
      const jitter = (Math.random() - 0.5) * Math.min(8, span * 0.5);
      const rotation = 360 * 6 + (360 - mid) + jitter;
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        rotor.style.transition = 'none';
        rotor.style.transform = `rotate(${rotation}deg)`;
        resolve();
        return;
      }
      rotor.style.transition = 'none';
      rotor.style.transform = 'rotate(0deg)';
      void rotor.getBoundingClientRect();
      requestAnimationFrame(() => {
        rotor.style.transition = 'transform 4.4s cubic-bezier(.1,.75,.12,1)';
        rotor.style.transform = `rotate(${rotation}deg)`;
      });
      setTimeout(resolve, 4600);
    });
  }

  function bindRoulette(data, body, footEl, replace) {
    const eligible = data.candidates.filter((candidate) => candidate.eligible);
    const relaxedToggle = $('#rouletteRelaxed', body);
    if (relaxedToggle) {
      relaxedToggle.addEventListener('change', act(async () => {
        await openRoulette(data.date, {
          replace,
          relaxed: relaxedToggle.checked,
        });
      }));
    }
    if (!eligible.length) return;

    let mode = 'month';
    let spinning = false;
    let finished = false;
    const spinButton = $('#rouletteSpin', footEl);
    const hint = $('#rouletteHint', footEl);
    const modeButtons = $$('[data-roulette-mode]', body);

    const render = () => {
      const participants = rouletteParticipants(data, mode);
      $('#rouletteWheel', body).innerHTML = rouletteWheelSvg(participants);
      $('#rouletteList', body).innerHTML = rouletteListHtml(participants);
      $('#rouletteFormula', body).innerHTML = rouletteFormulaHtml(data, mode);
      hint.textContent = rouletteHint(mode, data);
      modeButtons.forEach((button) => {
        const active = button.dataset.rouletteMode === mode;
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-pressed', String(active));
      });
    };

    modeButtons.forEach((button) => {
      button.addEventListener('click', () => {
        if (spinning || finished) return;
        mode = button.dataset.rouletteMode;
        render();
      });
    });

    hint.textContent = rouletteHint(mode, data);

    spinButton.addEventListener('click', act(async () => {
      if (spinning || finished) return;
      const participants = rouletteParticipants(data, mode);
      if (!participants.length) return;
      spinning = true;
      spinButton.disabled = true;
      spinButton.textContent = 'Крутим…';
      modeButtons.forEach((button) => { button.disabled = true; });

      let result;
      try {
        result = await api('/api/draw', {
          method: 'POST',
          body: {
            date: data.date,
            candidate_ids: participants.map((participant) => participant.id),
            mode,
            relaxed: Boolean(data.relaxed),
            replace,
          },
        });
      } catch (error) {
        spinning = false;
        spinButton.disabled = false;
        spinButton.textContent = 'Крутить';
        modeButtons.forEach((button) => { button.disabled = false; });
        throw error;
      }

      await spinRouletteWheel(body, participants, result.winner.personId);

      const row = $(`[data-roulette-row="${result.winner.personId}"]`, body);
      if (row) {
        row.classList.add('is-winner');
        const pill = document.createElement('span');
        pill.className = 'pill pill--used';
        pill.textContent = 'выбран';
        row.appendChild(pill);
      }
      const hub = $('[data-hub-text]', body);
      if (hub) hub.textContent = initials(result.winner.personName);
      const resultEl = $('#rouletteResult', body);
      if (resultEl) resultEl.innerHTML = rouletteWinnerHtml(result, participants);
      const done = replace
        ? `Дежурство переназначено: ${result.winner.personName}.`
        : `Дежурство назначено: ${result.winner.personName}.`;
      hint.textContent = done;
      spinButton.textContent = replace ? 'Переназначено' : 'Назначено';
      spinning = false;
      finished = true;
      toast(done);
      await loadSchedule(S.month);
    }));
  }

  async function openRoulette(dateStr, options = {}) {
    let { replace = false, relaxed = false } = options;
    let data;
    try {
      const query = `date=${encodeURIComponent(dateStr)}${relaxed ? '&relaxed=1' : ''}`;
      data = await api(`/api/roulette?${query}`);
    } catch (error) {
      toast(error.message, 'error');
      return;
    }
    if (data.duty) {
      if (data.duty.status !== 'planned') {
        toast('Переиграть можно только запланированное дежурство', 'error');
        return;
      }
      if (!replace) {
        if (!confirm(`На ${fullDate(dateStr)} уже дежурит ${data.duty.personName}. Переиграть день?`)) return;
        replace = true;
      }
    }
    const hasEligible = data.candidates.some((candidate) => candidate.eligible);
    openModal({
      title: `Рулетка · ${fullDate(dateStr)}`,
      wide: true,
      body: buildRouletteBody(data),
      foot: hasEligible
        ? `
          <div class="foot-info small muted" id="rouletteHint"></div>
          <button class="btn btn--ghost" type="button" data-close>Закрыть</button>
          <button class="btn btn--primary" type="button" id="rouletteSpin">${replace ? 'Переиграть' : 'Крутить'}</button>
        `
        : '<button class="btn btn--primary" type="button" data-close>Закрыть</button>',
      bind: (body, footEl) => bindRoulette(data, body, footEl, replace),
    });
  }

  async function openRoulettePicker() {
    const defaultValue = S.today || new Date().toISOString().slice(0, 10);
    openModal({
      title: 'Рулетка',
      body: `
        <div class="form-row">
          <label class="check" style="flex-direction:column;align-items:flex-start">
            <span class="small muted">Дата дежурства</span>
            <input type="date" id="rouletteDate" value="${esc(defaultValue)}">
          </label>
        </div>
        <div class="small muted">
          Рулетка исключает сотрудников в отпуске и на отсыпном. Если день уже занят,
          дежурного можно переиграть.
        </div>
      `,
      foot: `
        <button class="btn btn--ghost" type="button" data-close>Отмена</button>
        <button class="btn btn--primary" type="button" id="roulettePickGo">Открыть рулетку</button>
      `,
      bind: (body, footEl) => {
        $('#roulettePickGo', footEl).addEventListener('click', act(async () => {
          const dateInput = $('#rouletteDate', body);
          const value = dateInput ? dateInput.value : '';
          if (!value) {
            toast('Выберите дату', 'error');
            return;
          }
          closeModal();
          await openRoulette(value);
        }));
      },
    });
  }

  /* ---------- init ---------- */

  async function init() {
    $$('#tabs .tab').forEach((button) => {
      button.addEventListener('click', () => switchTab(button.dataset.tab));
    });
    el('modal').addEventListener('click', (event) => {
      if (event.target.closest('[data-close]')) closeModal();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !el('modal').hidden) closeModal();
    });

    try {
      const me = await api('/api/auth/me');
      S.user = me.user;
      applyRoleChrome();
      el('logoutBtn').addEventListener('click', act(async () => {
        await api('/api/auth/logout', { method: 'POST' });
        window.location.href = '/login';
      }));
      await loadSchedule();
    } catch (error) {
      el('view').innerHTML = `
        <div class="empty-state">
          <strong>Не удалось загрузить данные</strong>
          ${esc(error.message || error)}
        </div>
      `;
      toast(error.message || 'Ошибка загрузки', 'error');
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
