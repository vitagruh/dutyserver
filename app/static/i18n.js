(() => {
  'use strict';

  const LANGS = ['ru', 'en'];
  const STORAGE_KEY = 'duty-lang';
  const ATTRS = ['title', 'aria-label', 'placeholder', 'alt'];

  let lang = 'ru';
  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (LANGS.includes(saved)) lang = saved;
    } catch (error) { /* приватный режим */ }
  }

  const EXACT = {
    // ===== Каркас и навигация =====
    "Дежурная служба": "Duty Service",
    "Учёт и распределение суточных дежурств": "Scheduling and distribution of 24-hour duties",
    "Личная страница сотрудника": "Employee self-service",
    "Личный кабинет": "Employee account",
    "Суточные дежурства": "24-hour Duties",
    "Вход в систему": "Sign in to the system",
    "Вход — Суточные дежурства": "Sign in — 24-hour Duties",
    "График": "Schedule",
    "Сотрудники": "Staff",
    "Заявки": "Requests",
    "Требуют решения": "Needs decision",
    "Отгулы": "Comp days",
    "Отсутствия": "Absences",
    "Статистика": "Statistics",
    "Аккаунты": "Accounts",
    "Настройки": "Settings",
    "Разделы": "Sections",
    "Сегодня": "Today",
    "Выйти": "Sign out",
    "Тёмная": "Dark",
    "Светлая": "Light",
    "Включить тёмную тему": "Switch to dark theme",
    "Включить светлую тему": "Switch to light theme",
    "Закрыть": "Close",
    "Отмена": "Cancel",
    "Сохранить": "Save",
    "Удалить": "Delete",
    "Добавить": "Add",
    "Готово": "Done",
    "Обновить": "Refresh",
    "Изменить": "Edit",
    "Загрузка…": "Loading…",
    "Требуется вход": "Sign-in required",
    "Ошибка запроса": "Request error",
    "Ошибка загрузки": "Load error",
    "Не удалось загрузить раздел": "Failed to load the section",

    // ===== Динамические подписи =====
    "Выходные и праздники учитываются с весом 1.5.": "Weekends and holidays are counted with weight 1.5.",
    "Выходные и праздничные дни учитываются с весом 1.5; отгулы: ожидает / запланирован / использован.": "Weekend and holiday duties are counted with weight 1.5; comp days: pending / scheduled / used.",

    // ===== Расписание =====
    "Автораспределение": "Auto-plan",
    "Excel для печати": "Print Excel",
    "Экспорт CSV": "Export CSV",
    "Дежурств в месяце": "Duties this month",
    "Выходных дежурств": "Weekend duties",
    "Активных сотрудников": "Active staff",
    "участвуют в распределении": "participate in scheduling",
    "Отгулов к оформлению": "Comp days to arrange",
    "за выходные дежурства": "for weekend duties",
    "дежурство": "duty",
    "отсыпной": "rest day",
    "отгул": "comp day",
    "отпуск / болезнь": "vacation / sick leave",
    "заявка «не могу»": "“can’t” request",
    "просит не назначать": "prefers not to be scheduled",
    "выходной": "day off",
    "нажмите на день, чтобы назначить или разыграть": "click a day to assign or draw",
    "сегодня": "today",
    "жребий": "draw",
    "автораспределение": "auto-plan",
    "праздник": "holiday",
    "Журнал розыгрышей и пруфы": "Draw log and proofs",
    "каждый розыгрыш запечатан SHA-256 и воспроизводится": "every draw is sealed with SHA-256 and can be replayed",
    "Дежурства за месяц": "Duties this month",
    "Кандидат": "Candidate",
    "Дежурств": "Duties",
    "Выходных": "Weekends",
    "Нагрузка": "Load",
    "Вероятность": "Probability",
    "выбран": "selected",
    "открыть пруф": "open proof",
    "Правила:": "Rules:",
    "после суточного дежурства — обязательный отсыпной (1 день); минимальный интервал между дежурствами — 2 дня. Выходное или праздничное дежурство даёт право на отгул в рабочий день (60 дней после дежурства).": "after a 24-hour duty a rest day is mandatory (1 day); the minimum interval between duties is 2 days. A weekend or holiday duty entitles the employee to a comp day on a working day (within 60 days after the duty).",
    "Предыдущий месяц": "Previous month",
    "Следующий месяц": "Next month",

    // ===== Статусы и типы =====
    "Плановое": "Planned",
    "Выполнено": "Completed",
    "Неявка": "No-show",
    "Отменено": "Cancelled",
    "Вручную": "Manual",
    "Жребий": "Draw",
    "Не оформлен": "Not arranged",
    "Запланирован": "Scheduled",
    "Запланированы": "Scheduled",
    "Запланировано": "Scheduled",
    "Использован": "Used",
    "Использовано": "Used",
    "Использованы": "Used",
    "Отказ": "Declined",
    "Отпуск": "Vacation",
    "Болезнь": "Sick leave",
    "Командировка": "Business trip",
    "Другое": "Other",
    "отпуск": "vacation",
    "болезнь": "sick leave",
    "командировка": "business trip",
    "отсутствие": "absence",
    "Не может дежурить": "Cannot be on duty",
    "Предпочитает не дежурить": "Prefers not to be on duty",
    "просит не назначать": "asks not to be scheduled",
    "Ожидает согласования": "Awaiting approval",
    "Согласована": "Approved",
    "Согласованы": "Approved",
    "Отклонена": "Declined",
    "Отклонены": "Declined",
    "Администратор": "Administrator",
    "Тимлид": "Team lead",
    "Сотрудник": "Employee",
    "В очереди": "Queued",
    "Отправлено": "Sent",
    "Ошибка": "Error",
    "Пропущено": "Skipped",
    "По нагрузке": "By load",
    "По накопленной нагрузке": "By accumulated load",
    "По дежурствам за месяц": "By monthly duties",
    "Равные шансы": "Equal chances",
    "пруф": "proof",
    "архив": "archive",
    "проверен": "verified",
    "активен": "active",
    "неактивен": "inactive",
    "резерв": "reserve",
    "1 смена": "Shift 1",
    "2 смена": "Shift 2",
    "3 смена": "Shift 3",
    "не привязан": "not linked",
    "это вы": "this is you",
    "Все": "All",

    // ===== Заявки =====
    "Заявки сотрудников": "Employee requests",
    "Сотрудник отмечает дни в личном кабинете. «Не могу» после согласования жёстко исключает из назначений; «предпочитаю» — мягкий приоритет, автораспределение обходит его, если есть альтернатива.": "An employee marks days in the self-service account. An approved “can’t” request strictly excludes them from assignments; “prefer not” is a soft priority that auto-plan avoids when an alternative exists.",
    "Учётные записи": "User accounts",
    "Ждут согласования": "Awaiting approval",
    "проверьте дни и конфликты": "review days and conflicts",
    "учитываются в распределении": "included in scheduling",
    "на график не влияют": "do not affect the schedule",
    "Правила приёма": "Acceptance rules",
    "В этом статусе заявок нет": "No requests with this status",
    "Сотрудник подаёт заявки из личного кабинета. Учётные записи создаются в разделе «Аккаунты».": "Employees submit requests from the self-service account. User accounts are created under “Accounts”.",
    "Как это работает.": "How it works.",
    "Заявка «не могу» после согласования исключает сотрудника из назначений на выбранные дни — как отпуск. Заявка «предпочитаю» не запрещает назначение, но автораспределение выбирает других сотрудников, если это не увеличивает нагрузку. Согласовать заявку нельзя, пока на эти дни у сотрудника есть действующее дежурство: сначала переназначьте его.": "An approved “can’t” request excludes the employee from assignments on the selected days, just like vacation. A “prefer not” request does not forbid assignment, but auto-plan picks other employees when that does not increase the load. A request cannot be approved while the employee has an active duty on those days: reassign it first.",
    "Согласовать": "Approve",
    "Заявок пока нет": "No requests yet",
    "Отклонить заявку сотрудника?": "Decline the employee’s request?",
    "Заявка согласована": "Request approved",
    "Заявка отклонена": "Request declined",
    "Удалить заявку без возможности восстановления?": "Delete the request permanently?",
    "Заявка удалена": "Request deleted",

    // ===== Дни без покрытия =====
    "Дни без доступных сотрудников": "Days without available staff",
    "Дни горизонта, где ни один активный сотрудник не может дежурить по правилам. Для решения показываются кандидаты с коэффициентом: отсыпной, отпуска, интервалы и согласованные заявки не блокируют назначение, а фиксируются как отступления.": "Days in the horizon where no active employee can be on duty under the rules. Candidates are shown with a coefficient: rest days, vacations, intervals and approved requests do not block the assignment but are recorded as exceptions.",
    "Снято с контроля": "Dismissed",
    "осознанно оставлены без дежурства": "intentionally left without duty",
    "Решений тимлида": "Team lead decisions",
    "назначения поверх правил": "assignments overriding rules",
    "Горизонт проверки": "Check horizon",
    "На горизонте все дни покрыты": "All days in the horizon are covered",
    "На каждый будущий день есть хотя бы один доступный сотрудник, либо день снят с контроля.": "Every future day has at least one available employee, or the day is dismissed.",
    "Назначения поверх правил": "Assignments overriding rules",
    "Дата": "Date",
    "Причина": "Reason",
    "Кто": "Who",
    "Вернуть в контроль": "Restore to review",
    "День возвращён в контроль": "Day restored to review",
    "День снят с контроля": "Day dismissed",
    "День останется без дежурства. Он исчезнет из списка «Требуют решения»; вернуть его можно кнопкой «Вернуть в контроль».": "The day will stay without a duty. It disappears from “Needs decision”; you can bring it back with “Restore to review”.",
    "Комментарий": "Comment",
    "Назначить": "Assign",
    "Снять с контроля": "Dismiss",

    // ===== Сотрудники =====
    "Активные участвуют в автораспределении и жеребьёвке. Личный кабинет сотрудник получает через учётную запись — вкладка «Аккаунты».": "Active employees take part in auto-plan and draws. Employees get a self-service account via a user account on the “Accounts” tab.",
    "Добавить сотрудника": "Add employee",
    "Статус": "Status",
    "Последнее": "Last",
    "Деактивировать": "Deactivate",
    "Деактивировать сотрудника? Он перестанет участвовать в новых распределениях, существующие дежурства останутся.": "Deactivate the employee? They will stop taking part in new scheduling, while existing duties remain.",
    "Сотрудник деактивирован": "Employee deactivated",
    "Сотрудник активирован": "Employee activated",
    "Данные сотрудника": "Employee details",
    "Новый сотрудник": "New employee",
    "ФИО или позывной": "Full name or callsign",
    "Email для уведомлений": "Notification email",
    "Используется, если у учётной записи не заполнен свой контакт.": "Used when the user account has no contact of its own.",
    "Данные обновлены": "Data updated",
    "Сотрудник добавлен": "Employee added",
    "подразделение, должность — необязательно": "unit, position — optional",
    "@username или #канал": "@username or #channel",
    "Название": "Name",
    "не задан": "not set",
    "Примечание": "Note",

    // ===== Отгулы =====
    "Отгулы за выходные дежурства": "Comp days for weekend duties",
    "Один отгул за каждое дежурство в выходной или праздничный день. Дата — на выбор сотрудника, в пределах 60 дней после дежурства.": "One comp day for each duty on a weekend or holiday. The employee chooses the date within 60 days after the duty.",
    "К оформлению": "To arrange",
    "ещё не выбрана дата": "date not chosen yet",
    "дата уже назначена": "date already set",
    "отгул предоставлен": "comp day granted",
    "отгул не требуется": "comp day not needed",
    "Дежурство": "Duty",
    "Срок выбора": "Choose by",
    "Дата отгула": "Comp day date",
    "впереди": "upcoming",
    "Оформить": "Arrange",
    "Сброс": "Reset",
    "Отказаться от отгула за это дежурство?": "Decline the comp day for this duty?",
    "Отметить отгул использованным": "Mark the comp day as used",
    "Оформление отгула": "Comp day arrangement",
    "Отгул обновлён": "Comp day updated",
    "Отгул": "Comp day",
    "Отгулы отключены в настройках.": "Comp days are disabled in settings.",
    "Вернуть в ожидание": "Return to pending",
    "Сбросить отметку": "Clear mark",
    "Вернуть в план": "Return to plan",
    "Снять дежурство": "Remove duty",
    "Статус дежурства обновлён": "Duty status updated",
    "Снять дежурство с этого дня?": "Remove the duty from this day?",
    "Дежурство снято": "Duty removed",
    "Укажите дату отгула": "Choose a comp day date",
    "Укажите причину решения (не короче 5 символов)": "Describe the decision reason (at least 5 characters)",

    // ===== Отсутствия =====
    "Отпуск, болезнь и командировка исключают сотрудника из распределения на выбранные дни.": "Vacation, sick leave and business trips exclude the employee from scheduling on the selected days.",
    "Добавить отсутствие": "Add absence",
    "С": "From",
    "По": "To",
    "Тип": "Type",
    "Все отсутствия": "All absences",
    "Период": "Period",
    "Дней": "Days",
    "Плановый отпуск": "Planned vacation",
    "Больничный": "Sick leave",
    "сейчас": "now",
    "необязательно": "optional",
    "Отсутствие добавлено": "Absence added",
    "Удалить отсутствие?": "Delete the absence?",
    "Отсутствие удалено": "Absence deleted",

    // ===== Статистика =====
    "Статистика и равномерность": "Statistics and fairness",
    "Нагрузка: будни — 1, выходные и праздники — 1.5. Дашборды показывают перекос, покрытие и проверяемость жеребьёвок.": "Load: weekdays — 1, weekends and holidays — 1.5. The dashboards show imbalance, coverage and draw verifiability.",
    "в распределении": "in scheduling",
    "Дежурств всего": "Total duties",
    "Средняя нагрузка": "Average load",
    "Коэффициент вариации": "Coefficient of variation",
    "равномерно": "even",
    "умеренный разброс": "moderate spread",
    "есть перекос": "imbalanced",
    "Дни без покрытия": "Uncovered days",
    "Справедливость нагрузки": "Load fairness",
    "недогрузка": "underload",
    "средняя": "average",
    "перегрузка": "overload",
    "Красный — нагрузка выше средней более чем на 0.5; зелёный — ниже более чем на 0.5.": "Red — load is more than 0.5 above the mean; green — more than 0.5 below.",
    "Тепловая карта: сотрудник × месяц": "Heatmap: employee × month",
    "Итого": "Total",
    "Всего": "Total",
    "Дежурства по дням недели": "Duties by weekday",
    "все активные дежурства": "all active duties",
    "будни": "weekdays",
    "Понедельник": "Monday",
    "Вторник": "Tuesday",
    "Среда": "Wednesday",
    "Четверг": "Thursday",
    "Пятница": "Friday",
    "Суббота": "Saturday",
    "Воскресенье": "Sunday",
    "Пн": "Mon",
    "Вт": "Tue",
    "Ср": "Wed",
    "Чт": "Thu",
    "Пт": "Fri",
    "Сб": "Sat",
    "Вс": "Sun",
    "Покрытие горизонта": "Horizon coverage",
    "Ручных решений": "Manual decisions",
    "Заявки в работе": "Requests in progress",
    "Открыть дни без покрытия": "Open uncovered days",
    "Доля выходных и праздничных дежурств": "Share of weekend and holiday duties",
    "кто чаще дежурит в нерабочие дни · шкала 0–100%": "who is on duty more often on non-working days · scale 0–100%",
    "Матрица: сотрудник × день недели": "Matrix: employee × weekday",
    "в ячейке — количество дежурств": "each cell shows the number of duties",
    "Взвеш.": "Weighted",
    "Нагрузка по сотрудникам": "Load by employee",
    "Δ — отклонение от средней; отгулы: ожидает / запланирован / использован": "Δ — deviation from the mean; comp days: pending / scheduled / used",
    "Будни": "Weekdays",
    "Выходные": "Weekends",
    "Взвешенная нагрузка": "Weighted load",
    "План / вып. / неявка": "Planned / done / no-show",
    "Следующее": "Next",
    "Аудит жеребьёвок": "Draw audit",
    "Режим": "Mode",
    "Победитель": "Winner",
    "Пруф": "Proof",
    "Взвешенная нагрузка = число будних дежурств × 1 + число выходных/праздничных × 1.5. При жеребьёвке вес кандидата равен": "Weighted load = weekday duties × 1 + weekend/holiday duties × 1.5. In a draw, a candidate’s weight is",
    "= число будних дежурств × 1 + число выходных/праздничных × 1.5. При жеребьёвке вес кандидата равен": "= weekday duties × 1 + weekend/holiday duties × 1.5. In a draw, a candidate’s weight is",
    ", вероятность — вес / сумма весов отмеченных кандидатов. Каждый розыгрыш запечатан SHA-256; ссылка «пруф» открывает пакет с seed, случайным числом и весами для независимой проверки.": ", the probability is weight / sum of weights of the selected candidates. Every draw is sealed with SHA-256; the “proof” link opens a package with the seed, random number and weights for independent verification.",

    // ===== Аккаунты =====
    "Роли: администратор настраивает систему и уведомления, тимлид планирует дежурства и разбирает заявки, сотрудник видит личный кабинет и подаёт заявки.": "Roles: the administrator configures the system and notifications, the team lead plans duties and handles requests, and the employee uses the self-service account to submit requests.",
    "Добавить аккаунт": "Add account",
    "Всего аккаунтов": "Total accounts",
    "Администраторы": "Administrators",
    "минимум один обязателен": "at least one is required",
    "Привязаны к сотрудникам": "Linked to employees",
    "получают личный кабинет": "get a self-service account",
    "Без привязки": "Unlinked",
    "тимлиды и администраторы": "team leads and administrators",
    "Логин": "Login",
    "Роль": "Role",
    "Контакты": "Contacts",
    "Вход": "Sign-in",
    "Заблокировать": "Block",
    "Пароли.": "Passwords.",
    "Хранятся в виде PBKDF2-SHA256 с солью. Смена пароля завершает прежние сессии. Сессия — подписанная HttpOnly cookie на 12 часов.": "Stored as salted PBKDF2-SHA256. Changing the password ends previous sessions. A session is a signed HttpOnly cookie valid for 12 hours.",
    "Заблокировать аккаунт? Пользователь потеряет доступ к системе.": "Block the account? The user will lose access to the system.",
    "Аккаунт заблокирован": "Account blocked",
    "Аккаунт разблокирован": "Account unblocked",
    "Удалить аккаунт? Сотрудник и его история сохранятся.": "Delete the account? The employee and their history will be kept.",
    "Аккаунт удалён": "Account deleted",
    "Текущий сотрудник": "Current employee",
    "Новый аккаунт": "New account",
    "Сотруднику нужна привязка для личного кабинета.": "The employee needs a link to use the self-service account.",
    "Аккаунт активен": "Account active",
    "Аккаунт обновлён": "Account updated",
    "Аккаунт создан": "Account created",
    "Доступно только администратору": "Administrators only",

    // ===== Настройки =====
    "Правила распределения, сроки отгулов и календарь праздников.": "Scheduling rules, comp day windows and the holiday calendar.",
    "Правила дежурств": "Duty rules",
    "Название подразделения": "Unit name",
    "Отсыпной после дежурства, дней": "Rest days after duty",
    "1 — следующий день недоступен для назначений.": "1 — the next day is unavailable for assignments.",
    "Минимальный интервал, дней": "Minimum interval, days",
    "Не меньше отсыпного + 1.": "At least rest days + 1.",
    "Вес выходного дежурства": "Weekend duty weight",
    "Насколько выходное дежурство «тяжелее» буднего при расчёте нагрузки.": "How much heavier a weekend duty is than a weekday one when calculating load.",
    "Степень справедливости": "Fairness strength",
    "1 — мягко, 3–4 — сильный приоритет менее загруженным.": "1 — mild, 3–4 — strong priority for less loaded employees.",
    "Срок выбора отгула, дней": "Comp day window, days",
    "Сколько дней после выходного дежурства доступен отгул.": "How many days after a weekend duty the comp day is available.",
    "История для нагрузки, дней": "Load history, days",
    "0 — учитывать всю историю.": "0 — use the whole history.",
    "Лимит заявок, дней в месяц": "Request limit, days per month",
    "Сколько дней в месяц сотрудник может отметить. 0 — без лимита.": "How many days per month an employee can mark. 0 — no limit.",
    "Горизонт заявок, дней": "Request horizon, days",
    "На сколько дней вперёд принимаются заявки.": "How many days ahead requests are accepted.",
    "Давать отгул за дежурство в выходные и праздники": "Grant a comp day for weekend and holiday duties",
    "Сохранить настройки": "Save settings",
    "Настройки сохранены": "Settings saved",
    "Праздники": "Holidays",
    "Заполнить праздники РБ": "Fill Belarusian holidays",
    "Государственные праздники РБ (10 нерабочих дней) подгружаются автоматически при запуске для прошлого, текущего и следующего года. Удалённые вручную даты повторно не добавляются.": "Belarusian public holidays (10 non-working days) are loaded automatically at startup for the previous, current and next year. Dates deleted manually are not added again.",
    "Праздник добавлен": "Holiday added",
    "Праздник удалён": "Holiday deleted",
    "Удалить праздник?": "Delete the holiday?",
    "Уведомления": "Notifications",
    "email и Rocket.Chat": "email and Rocket.Chat",
    "Включить уведомления": "Enable notifications",
    "Новые заявки": "New requests",
    "Решения по заявкам": "Request decisions",
    "SMTP-сервер": "SMTP server",
    "Порт": "Port",
    "Пользователь SMTP": "SMTP user",
    "Пароль SMTP": "SMTP password",
    "Адрес отправителя": "Sender address",
    "Адрес системы": "System URL",
    "Добавляется в письма как ссылка на систему.": "Added to emails as a link to the system.",
    "STARTTLS при отправке email": "STARTTLS for email",
    "Сохранить уведомления": "Save notifications",
    "Настройки уведомлений сохранены": "Notification settings saved",
    "Проверка каналов": "Channel test",
    "сообщение уйдёт на контакты вашей учётной записи": "the message goes to your account contacts",
    "Тест email": "Test email",
    "Тест Rocket.Chat": "Test Rocket.Chat",
    "Повторить ошибки": "Retry failed",
    "Журнал отправки": "Delivery log",
    "Сообщений пока не было. Уведомления ставятся в очередь при событиях заявок и покрытия.": "No messages yet. Notifications are queued on request and coverage events.",
    "Тестовое письмо отправлено": "Test email sent",
    "Не удалось отправить письмо": "Failed to send the email",
    "Сообщение в Rocket.Chat отправлено": "Rocket.Chat message sent",
    "Не удалось отправить сообщение": "Failed to send the message",
    "Как работает распределение": "How scheduling works",
    "1. Доступность.": "1. Availability.",
    "Кандидат исключается, если он в отпуске/на больничном, уже дежурит в этот день, находится на отсыпном, нарушает минимальный интервал или у него оформлен отгул.": "A candidate is excluded if they are on vacation/sick leave, already on duty that day, on a rest day, violate the minimum interval, or have an arranged comp day.",
    "2. Нагрузка.": "2. Load.",
    "Буднее дежурство = 1, выходное или праздничное = 1.5. Отгулы не уменьшают нагрузку — дополнительная тяжесть выходного уже учтена коэффициентом.": "A weekday duty = 1, a weekend or holiday duty = 1.5. Comp days do not reduce load — the extra weight of a weekend duty is already reflected in the coefficient.",
    "3. Вероятность.": "3. Probability.",
    "Среди отмеченных доступных кандидатов вес =": "Among the selected available candidates, weight =",
    ". Меньшая нагрузка даёт больший вес; при равной нагрузке шансы равны.": ". A lower load gives more weight; with equal load the chances are equal.",
    "4. Аудит.": "4. Audit.",
    "Каждая жеребьёвка сохраняется с seed и таблицей вероятностей. Один и тот же seed воспроизводит результат.": "Every draw is stored with its seed and probability table. The same seed reproduces the result.",
    "5. Автораспределение.": "5. Auto-plan.",
    "Заполняет только пустые дни, выбирая сотрудников с минимальной нагрузкой; при равенстве — случайно.": "Fills only empty days, choosing employees with the lowest load; ties are broken randomly.",
    "6. Заявки сотрудников.": "6. Employee requests.",
    "«Не могу» после согласования исключает из назначений на выбранные дни; «предпочитаю» — мягкий приоритет: автораспределение обходит такого сотрудника, если есть альтернатива без роста нагрузки. Жёсткие правила (отсыпной, интервал, отсутствия) остаются в силе.": "An approved “can’t” request excludes the employee from assignments on the selected days; “prefer not” is a soft priority: auto-plan skips such an employee when an alternative exists without increasing the load. Hard rules (rest days, interval, absences) still apply.",

    // ===== Автораспределение и рулетка =====
    "Заполняются только пустые дни. Выбирается сотрудник с минимальной взвешенной нагрузкой; при равенстве — жребий. Отсыпной, минимальный интервал, отгулы, отсутствия и согласованные заявки «не могу» учитываются автоматически; «предпочитаю» — мягкий приоритет.": "Only empty days are filled. The employee with the lowest weighted load is chosen; ties are decided by a draw. Rest days, the minimum interval, comp days, absences and approved “can’t” requests are applied automatically; “prefer not” is a soft priority.",
    "Seed (необязательно)": "Seed (optional)",
    "Одинаковый seed и одинаковые данные дают одинаковый график.": "The same seed and the same data produce the same schedule.",
    "Распределить": "Auto-plan",
    "Распределяю…": "Planning…",
    "день уже занят": "day already assigned",
    "Автораспределение завершено": "Auto-plan finished",
    "Свободных дней для распределения нет.": "No free days to plan.",
    "Отметьте претендентов. Жеребьёвка пройдёт только среди них.": "Select the candidates. The draw will run only among them.",
    "Рулетка": "Roulette",
    "Провести жеребьёвку": "Run the draw",
    "Выходной день. За дежурство положен отгул на выбор.": "Day off. The duty earns a comp day of the employee’s choice.",
    "Рабочий день. После дежурства на следующий день — отсыпной.": "Working day. The next day after the duty is a rest day.",
    "Нет активных сотрудников.": "No active employees.",
    "Кандидаты на дежурство": "Duty candidates",
    "Участвует в жеребьёвке": "Participates in the draw",
    "Жеребьёвка…": "Drawing…",
    "Розыгрыш проведён": "Draw completed",
    "У всех участников одинаковый шанс — дежурства не учитываются.": "All participants have an equal chance — duties are not counted.",
    "Выходной день": "Day off",
    "Рабочий день": "Working day",
    "в этом месяце": "this month",
    "Крутим…": "Spinning…",
    "Крутить": "Spin",
    "Назначено": "Assigned",
    "На этот день уже назначено дежурство": "A duty is already assigned to this day",

    // ===== Личный кабинет =====
    "Сессия истекла — войдите заново": "The session expired — sign in again",
    "Не удалось загрузить данные": "Failed to load data",
    "Рулетка ·": "Roulette ·",
    "выполнено": "completed",
    "неявка": "no-show",
    "план": "planned",
    "заявка · не могу": "request · can’t",
    "не могу · согласовано": "can’t · approved",
    "выбрано": "selected",
    "Лимит заявок": "Request limit",
    "дней в месяц на сотрудника": "days per month per employee",
    "Горизонт планирования": "Planning horizon",
    "Выбрано сейчас": "Selected now",
    "дней в новой заявке": "days in the new request",
    "нажмите на день, чтобы выбрать или снять": "click a day to select or unselect",
    "заявка ожидает": "request pending",
    "«не могу» согласовано": "“can’t” approved",
    "просьба не назначать": "prefers not to be scheduled",
    "Новая заявка": "New request",
    "Не могу дежурить": "I can’t be on duty",
    "После согласования дни исключаются из графика.": "Once approved, the days are excluded from the schedule.",
    "Предпочитаю не дежурить": "I prefer not to be on duty",
    "Мягкая просьба: по возможности выберут другого.": "A soft request: another employee will be chosen when possible.",
    "Причина (необязательно)": "Reason (optional)",
    "Дни не выбраны. Отметьте их в календаре.": "No days selected. Mark them in the calendar.",
    "Отправить на согласование": "Submit for approval",
    "Очистить": "Clear",
    "Мои заявки": "My requests",
    "Согласованные «не могу» блокируют назначение. Ожидающие заявки планировщик видит, но они не исключают из графика до согласования.": "Approved “can’t” requests block assignments. The planner sees pending requests, but they do not exclude days from the schedule until approved.",
    "Аккаунт": "Account",
    "Текущий пароль": "Current password",
    "Новый пароль": "New password",
    "Сменить пароль": "Change password",
    "Выберите дни в календаре": "Select days in the calendar",
    "Пароль должен быть не короче 6 символов": "The password must be at least 6 characters",
    "Пароль изменён": "Password changed",
    "Отозвать заявку?": "Withdraw the request?",
    "Заявка отозвана": "Request withdrawn",
    "Равные шансы. Дежурства не учитываются: у каждого участника вес 1, вероятность = 1 / число участников.": "Equal chances. Duties are not counted: each participant has weight 1, probability = 1 / number of participants.",

    // ===== Вход =====
    "Пароль": "Password",
    "Войти": "Sign in",
    "Вход…": "Signing in…",
    "Не удалось войти": "Sign-in failed",
    "Сотрудник видит личный кабинет с календарём и заявками. Тимлид и администратор работают с графиком, заявками и днями без покрытия.": "Employees see a self-service account with a calendar and requests. Team leads and administrators work with the schedule, requests and uncovered days.",
    "например, учёба, семейные обстоятельства": "e.g. studies, family matters",

    // ===== Пруф =====
    "Пруф жеребьёвки": "Draw proof",
    "Пруф не найден": "Proof not found",
    "Розыгрыш не найден": "Draw not found",
    "Вернуться к графику": "Back to schedule",
    "К графику": "Back to schedule",
    "Канонический JSON, SHA-256 и повторный пересчёт выбора. Данные не зависят от текущего состояния графика.": "Canonical JSON, SHA-256 and an independent replay of the selection. The data does not depend on the current state of the schedule.",
    "ПОДТВЕРЖДЕНО": "VERIFIED",
    "НЕ СОВПАЛО": "MISMATCH",
    "АРХИВНАЯ ЗАПИСЬ": "ARCHIVED RECORD",
    "Печать совпадает, повторный пересчёт даёт того же победителя.": "The seal matches and the replay yields the same winner.",
    "Хэш или пересчёт не совпали. Результат нельзя считать доказуемым.": "The hash or the replay did not match. The result cannot be considered provable.",
    "Случайное число (roll)": "Random number (roll)",
    "Сумма весов": "Total weight",
    "Порог roll × Σвесов": "Threshold roll × Σweights",
    "Алгоритм": "Algorithm",
    "Пакет жеребьёвки": "Draw package",
    "победитель — первый интервал, накрывающий порог": "the winner is the first interval covering the threshold",
    "Дежурств в месяце": "Duties in month",
    "Вес": "Weight",
    "Интервал": "Interval",
    "Кандидаты из архива": "Candidates from the archive",
    "Нет данных": "No data",
    "Проверка": "Verification",
    "✓ SHA-256 пакета совпадает с печатью": "✓ The package SHA-256 matches the seal",
    "✓ Сумма весов положительна": "✓ The total weight is positive",
    "✓ Сумма вероятностей равна 1": "✓ The probabilities sum to 1",
    "✓ Пересчёт даёт указанного победителя": "✓ The replay yields the stated winner",
    "SHA-256 печать": "SHA-256 seal",
    "Канонический пакет": "Canonical package",
    "Как проверить самому": "How to verify it yourself",
    "Сохраните JSON пакета как": "Save the package JSON as",
    "и выполните код. Хэш должен совпасть с печатью, а победитель — с записью.": "and run the code. The hash must match the seal and the winner must match the record.",
    "Что это доказывает.": "What this proves.",
    "Сервер заранее фиксирует seed, случайное число, веса и вероятности всех участников.": "The server fixes the seed, the random number, the weights and the probabilities of all participants in advance.",
    "Любой может пересчитать SHA-256 канонического JSON и убедиться, что победитель выбран именно этим случайным числом.": "Anyone can recompute the SHA-256 of the canonical JSON and confirm that the winner was chosen by this particular random number.",
    "Сервер заранее фиксирует seed, случайное число, веса и вероятности всех участников. Любой может пересчитать SHA-256 канонического JSON и убедиться, что победитель выбран именно этим случайным числом.": "The server fixes the seed, the random number, the weights and the probabilities of all participants in advance. Anyone can recompute the SHA-256 of the canonical JSON and confirm that the winner was chosen by this particular random number.",

    // ===== Праздники РБ =====
    "Новый год": "New Year’s Day",
    "Новый год (2-й день)": "New Year’s Day (2nd day)",
    "Рождество Христово (православное)": "Orthodox Christmas",
    "День женщин": "Women’s Day",
    "Радуница": "Radunitsa",
    "Праздник труда": "Labour Day",
    "День Победы": "Victory Day",
    "День Независимости Республики Беларусь": "Independence Day of Belarus",
    "Рождество Христово (католическое)": "Catholic Christmas",
    "День Октябрьской революции": "October Revolution Day",

    // ===== Ошибки сервера =====
    "Неверный логин или пароль": "Wrong login or password",
    "Укажите логин и пароль": "Enter login and password",
    "Текущий пароль указан неверно": "The current password is incorrect",
    "Такой логин уже занят": "This login is already taken",
    "Сотрудник не найден": "Employee not found",
    "Сотрудник неактивен": "The employee is inactive",
    "Учётная запись не найдена": "User account not found",
    "Заявка не найдена": "Request not found",
    "Отсутствие не найдено": "Absence not found",
    "Дежурство не найдено": "Duty not found",
    "Розыгрыш не найден": "Draw not found",
    "День не снят с контроля": "The day is not dismissed",
    "День уже занят": "The day is already assigned",
    "День уже занят. Сначала снимите текущее дежурство.": "The day is already assigned. Remove the current duty first.",
    "На этот день уже назначено дежурство. Сначала снимите его.": "A duty is already assigned to this day. Remove it first.",
    "На этот день уже есть другое активное дежурство": "Another active duty already exists on this day",
    "Нет доступных кандидатов для розыгрыша": "No available candidates for the draw",
    "Не удалось выбрать победителя": "Failed to select a winner",
    "Некорректный список кандидатов": "Invalid candidate list",
    "Некорректный seed": "Invalid seed",
    "Неизвестный режим розыгрыша": "Unknown draw mode",
    "Неизвестные сотрудники": "Unknown employees",
    "Некорректный статус дежурства": "Invalid duty status",
    "Некорректный статус заявки": "Invalid request status",
    "Некорректный тип заявки": "Invalid request type",
    "Некорректный тип отсутствия": "Invalid absence type",
    "Некорректная роль": "Invalid role",
    "Прошедший день нельзя снять с контроля": "A past day cannot be dismissed",
    "Нельзя назначать дежурство в прошлое": "A duty cannot be assigned in the past",
    "Нельзя отмечать прошедшие дни": "Past days cannot be marked",
    "Выберите хотя бы один день": "Select at least one day",
    "Дата окончания раньше даты начала": "The end date is before the start date",
    "Дата начала позже даты окончания": "The start date is after the end date",
    "Нельзя удалить собственную запись": "You cannot delete your own account",
    "Нельзя оставить систему без активного администратора": "The system must keep at least one active administrator",
    "Этот сотрудник уже привязан к другой учётной записи": "This employee is already linked to another account",
    "К учётной записи не привязан сотрудник. Обратитесь к администратору.": "No employee is linked to this account. Contact the administrator.",
    "Логин: от 3 до 40 символов": "Login: 3 to 40 characters",
    "Логин может содержать буквы, цифры, точку, дефис, подчёркивание и @": "The login may contain letters, digits, dot, hyphen, underscore and @",
    "Сначала снимите дежурства на эти даты": "Remove the duties on these dates first",
    "Месяц должен быть в формате ГГГГ-ММ": "The month must be in YYYY-MM format",
    "Укажите имя сотрудника": "Enter the employee name",
    "Слишком длинное имя": "The name is too long",
    "Имя не может быть пустым": "The name cannot be empty"
  };

  const MONTHS = {
    'январь': 'January', 'февраль': 'February', 'март': 'March', 'апрель': 'April',
    'май': 'May', 'июнь': 'June', 'июль': 'July', 'август': 'August',
    'сентябрь': 'September', 'октябрь': 'October', 'ноябрь': 'November', 'декабрь': 'December',
    'января': 'January', 'февраля': 'February', 'марта': 'March', 'апреля': 'April',
    'мая': 'May', 'июня': 'June', 'июля': 'July', 'августа': 'August',
    'сентября': 'September', 'октября': 'October', 'ноября': 'November', 'декабря': 'December'
  };

  const RULES = [
    [/^Пруф жеребьёвки №(\d+) — дежурства$/, 'Draw proof #$1 — duties'],
    [/^Проверяемый жребий · пакет №(\d+)$/, 'Verifiable draw · package #$1'],
    [/^(.+) — мои дежурства$/, '$1 — my duties'],
    [/^(.+) — суточные дежурства$/, (match, unit) => ((EXACT[unit.trim()] || unit) + ' — 24-hour duties')],
    [/^([а-яё]+)\s+(\d{4})$/i, (match, month, year) => (MONTHS[month.toLowerCase()] ? MONTHS[month.toLowerCase()] + ' ' + year : match)],
    [/^(\d+) (?:праздник|праздника|праздников) в месяце$/, (match, n) => n + (n === '1' ? ' holiday' : ' holidays') + ' this month'],
    [/^из (\d+) (?:день|дня|дней)$/, 'of $1 days'],
    [/^(\d+) (?:активных|активен)$/, '$1 active'],
    [/^(\d+) выходных и праздничных$/, '$1 weekend/holiday'],
    [/^разброс ([\d.,]+)$/, 'spread $1'],
    [/^горизонт (\d+) дн\. · без дежурного (\d+)$/, 'horizon $1 d · unassigned $2'],
    [/^отклонение от средней ([\d.,]+) · перегружены (\d+) · недогружены (\d+)$/, 'deviation from mean $1 · overloaded $2 · underloaded $3'],
    [/^из них (\d+) вых\.$/, '$1 weekend'],
    [/^(\d+) (?:день|дня|дней) вперёд$/, '$1 days ahead'],
    [/^из (\d+) (?:день|дня|дней) закрыты дежурным$/, (match, n) => n + ' of ' + n + ' days covered'],
    [/^(\d+) (?:день|дня|дней) без назначения$/, '$1 days unassigned'],
    [/^горизонт (\d+) дн\.$/, 'horizon $1 days'],
    [/^последние (\d+) · пруф пересчитывается при открытии$/, 'last $1 · proof recalculated on open'],
    [/^последние (\d+)$/, 'last $1'],
    [/^пруф · (.+)$/, 'proof · $1'],
    [/^открыть · (.+)$/, 'open · $1'],
    [/^до (\d{2}\.\d{2}(?:\.\d{4})?)$/, 'until $1'],
    [/^Отсыпной после дежурства (\d{2}\.\d{2})$/, 'Rest day after duty on $1'],
    [/^Предпочитает не дежурить · (\d{2}\.\d{2}–\d{2}\.\d{2})$/, 'Prefers off · $1'],
    [/^отсыпной · (.+)$/, 'rest day · $1'],
    [/^отгул · (.+)$/, 'comp day · $1'],
    [/^отпуск · (.+)$/, 'vacation · $1'],
    [/^болезнь · (.+)$/, 'sick leave · $1'],
    [/^командировка · (.+)$/, 'business trip · $1'],
    [/^просит · (.+)$/, 'prefers off · $1'],
    [/^автораспределение · выполнено$/, 'auto-plan · completed'],
    [/^(.+): (\d+) из (\d+)$/, '$1: $2 of $3'],
    [/^(\d+) из (\d+)$/, '$1 of $2'],
    [/^сегодня (\d{2}\.\d{2}\.\d{4})$/, 'today $1'],
    [/^дежурство · выполнено$/, 'duty · completed'],
    [/^дежурство · план$/, 'duty · planned'],
    [/^дежурство · (.+)$/, 'duty · $1'],
    [/^просьба · (.+)$/, 'preference · $1'],
    [/^просьба (.+)$/, 'preference: $1'],
    [/^ожидают: (\d+)$/, 'pending: $1'],
    [/^согласовано: (\d+)$/, 'approved: $1'],
    [/^ожидают \/ запланированы · использовано (\d+)$/, 'pending / scheduled · used $1'],
    [/^(.+): ([\d.,]+)$/, '$1: $2'],
    [/^дней в месяц · горизонт (\d+) дн\.$/, 'days per month · horizon $1 days'],
    [/^дней вперёд, до (\d{2}\.\d{2}\.\d{4})$/, 'days ahead, until $1'],
    [/^(\d+) (день|дня|дней) · (.+)$/, (match, n, word, rest) => n + (n === '1' ? ' day' : ' days') + ' · ' + rest],
    [/^(\d+) (день|дня|дней)$/, (match, n) => n + (n === '1' ? ' day' : ' days')],
    [/^(\d+) дн\.$/, '$1 d'],
    [/^(\d+) %$/, '$1 %'],
    [/^(\d+) коэф\.$/, '$1 coeff.'],
    [/^Отгул можно выбрать с (\d{2}\.\d{2}\.\d{4}) по (\d{2}\.\d{2}\.\d{4}), только на рабочий день, свободный от дежурств и отсутствий\.$/, 'A comp day can be chosen from $1 to $2, only on a working day free from duties and absences.'],
    [/^Срок выбора — до (\d{2}\.\d{2}\.\d{4})\. Только рабочий день, свободный от дежурств, отсыпных и отсутствий\.$/, 'Choose by $1. Only a working day free from duties, rest days and absences.'],
    [/^Отгул за выходное дежурство (\d{2}\.\d{2})$/, 'Comp day for the weekend duty on $1'],
    [/^Праздничный день: (.+)\. Дежурство учитывается как выходное\.$/, 'Holiday: $1. The duty counts as a weekend duty.'],
    [/^Праздник: (.+)$/, 'Holiday: $1'],
    [/^Дежурный (.+)$/, 'On duty: $1'],
    [/^Доступно: (\d+) из (\d+)\. Отметьте участников жеребьёвки\.$/, 'Available: $1 of $2. Select the draw participants.'],
    [/^Добавлено (\d+) (?:праздник|праздника|праздников) за (\d{4}) год$/, (match, n, year) => 'Added ' + n + (n === '1' ? ' holiday' : ' holidays') + ' for ' + year],
    [/^Повторно отправлено: (\d+)$/, 'Retried: $1'],
    [/^Назначено (\d+) (?:дежурство|дежурства|дежурств) · seed (.+)$/, 'Assigned $1 duties · seed $2'],
    [/^Дежурство назначено: (.+)\.$/, 'Duty assigned: $1.'],
    [/^Дежурство назначено: (.+)$/, 'Duty assigned: $1'],
    [/^Рулетка · (.+)$/, 'Roulette · $1'],
    [/^Не удалось загрузить данные (.+)$/, 'Failed to load data: $1'],
    [/^Кабинет недоступен (.+)$/, 'Account unavailable: $1'],
    [/^Заявки принимаются не дальше чем на (\d+) (?:день|дня|дней) вперёд$/, 'Requests are accepted at most $1 days ahead'],
    [/^Заявки подаются на (\d+) (?:день|дня|дней) вперёд и не более (\d+) (?:день|дня|дней) в месяц\. Планировщик согласует или отклонит их; при согласовании дни «не могу» исключаются из распределения\. Отозвать можно только заявку, ожидающую согласования\.$/, 'Requests can be submitted up to $1 days ahead and no more than $2 days per month. The planner approves or declines them; once approved, “can’t” days are excluded from scheduling. Only a request awaiting approval can be withdrawn.'],
    [/^Максимальный период — (\d+) (?:день|дня|дней)$/, 'The maximum period is $1 days'],
    [/^Назначено с отступлениями: (.+)$/, 'Assigned with exceptions: $1'],
    [/^Снять с контроля: (.+)$/, 'Dismiss: $1'],
    [/^Назначение на (.+)$/, 'Assignment for $1'],
    [/^Шанс выше у тех, кто меньше дежурил в (.+)$/, 'Those who were on duty less in $1 have a higher chance.'],
    [/^Отсыпной: (\d+) дн\.; минимальный интервал: (\d+) дн\.$/, 'Rest days: $1; minimum interval: $2 days.'],
    [/^Вес = \(Lmax − L \+ 1\) × ([\d.,]+), где L — взвешенная нагрузка \(выходное дежурство = ([\d.,]+)\)\. Вероятность = вес \/ сумма весов отмеченных доступных кандидатов\.$/, 'Weight = (Lmax − L + 1) × $1, where L is the weighted load (a weekend duty = $2). Probability = weight / sum of weights of the selected available candidates.'],
    [/^Взвешенная нагрузка = число будних дежурств × 1 \+ число выходных\/праздничных × ([\d.,]+)\. При жеребьёвке вес кандидата равен$/, 'Weighted load = weekday duties × 1 + weekend/holiday duties × $1. In a draw, a candidate’s weight is'],
    [/^= число будних дежурств × 1 \+ число выходных\/праздничных × ([\d.,]+)\. При жеребьёвке вес кандидата равен$/, '= weekday duties × 1 + weekend/holiday duties × $1. In a draw, a candidate’s weight is'],
    [/^Выходные и праздники учитываются с весом ([\d.,]+)\.$/, 'Weekends and holidays are counted with weight $1.'],
    [/^Выходные и праздничные дни учитываются с весом ([\d.,]+); отгулы: ожидает \/ запланирован \/ использован\.$/, 'Weekend and holiday duties are counted with weight $1; comp days: pending / scheduled / used.'],
    [/^С учётом дежурств за месяц\. Вес = \(M max − M \+ 1\) × ([\d.,]+), где M — число дежурств в (.+)\. Чем меньше дежурств, тем выше шанс\.$/, 'Duties this month are counted. Weight = (M max − M + 1) × $1, where M is the number of duties in $2. Fewer duties mean a higher chance.'],
    [/^Провести жеребьёвку \(\s*(\d+)\s*\)$/, 'Run the draw ($1)'],
    [/^(\d+) (?:дежурство|дежурства|дежурств)$/, (match, n) => n + (n === '1' ? ' duty' : ' duties')],
    [/^(\d+) (?:день|дня|дней)$/, (match, n) => n + (n === '1' ? ' day' : ' days')],
    [/^(.+) коэф\. (.+)$/, '$1 coeff. $2']
  ];

  function withSpacing(original, core) {
    const lead = original.match(/^\s*/)[0];
    const trail = original.match(/\s*$/)[0];
    return lead + core + trail;
  }

  function translate(text, target = lang) {
    if (target !== 'en' || typeof text !== 'string' || !text) return text;
    const trimmed = text.trim();
    if (!trimmed) return text;
    const core = trimmed.replace(/\s+/g, ' ');
    const exact = EXACT[core];
    if (exact !== undefined) return withSpacing(text, exact);
    for (const [pattern, replacement] of RULES) {
      const match = core.match(pattern);
      if (!match) continue;
      const output = typeof replacement === 'function'
        ? replacement.apply(null, match)
        : core.replace(pattern, replacement);
      return withSpacing(text, output);
    }
    return text;
  }

  function t(text) {
    return translate(text, lang);
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { translate, dictionary: EXACT, rules: RULES, get lang() { return lang; } };
  }
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  const textSources = new WeakMap();
  const textTranslated = new WeakMap();
  const attrSources = new WeakMap();
  const attrTranslated = new WeakMap();
  let observer = null;
  let applying = false;

  function shouldSkip(node) {
    const parent = node.parentElement;
    return parent && (parent.tagName === 'SCRIPT' || parent.tagName === 'STYLE');
  }

  function translateTextNode(node) {
    if (shouldSkip(node)) return;
    const current = node.nodeValue;
    if (current == null) return;
    let source = textSources.get(node);
    const last = textTranslated.get(node);
    if (source === undefined || (last !== undefined && current !== last)) {
      source = current;
      textSources.set(node, source);
    }
    if (lang === 'en' && !/[А-Яа-яЁё]/.test(source)) return;
    const next = translate(source, lang);
    if (next !== current) {
      applying = true;
      node.nodeValue = next;
      applying = false;
      textTranslated.set(node, next);
    }
  }

  function translateAttr(el, name) {
    if (!el.getAttribute || !el.hasAttribute(name)) return;
    const current = el.getAttribute(name);
    let sources = attrSources.get(el);
    if (!sources) { sources = {}; attrSources.set(el, sources); }
    let translated = attrTranslated.get(el);
    if (!translated) { translated = {}; attrTranslated.set(el, translated); }
    if (sources[name] === undefined || (translated[name] !== undefined && current !== translated[name])) {
      sources[name] = current;
    }
    if (lang === 'en' && !/[А-Яа-яЁё]/.test(sources[name])) return;
    const next = translate(sources[name], lang);
    if (next !== current) {
      applying = true;
      el.setAttribute(name, next);
      applying = false;
      translated[name] = next;
    }
  }

  function translateElement(el) {
    ATTRS.forEach((name) => translateAttr(el, name));
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) translateTextNode(node);
  }

  function apply(root = document.documentElement) {
    if (!root) return;
    if (root.nodeType === 3) {
      translateTextNode(root);
      return;
    }
    if (root.nodeType !== 1) return;
    translateElement(root);
    root.querySelectorAll(ATTRS.map((name) => '[' + name + ']').join(',')).forEach((el) => {
      if (el !== root) ATTRS.forEach((name) => translateAttr(el, name));
    });
  }

  function observe() {
    if (!observer) {
      observer = new MutationObserver((mutations) => {
        if (applying) return;
        for (const mutation of mutations) {
          if (mutation.type === 'characterData') {
            translateTextNode(mutation.target);
          } else if (mutation.type === 'childList') {
            mutation.addedNodes.forEach((node) => {
              if (node.nodeType === 3) translateTextNode(node);
              else if (node.nodeType === 1) apply(node);
            });
          } else if (mutation.type === 'attributes') {
            translateAttr(mutation.target, mutation.attributeName);
          }
        }
      });
    }
    observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ATTRS
    });
  }

  function refresh() {
    if (observer) observer.disconnect();
    document.documentElement.lang = lang;
    apply(document.documentElement);
    observe();
  }

  function setLiteralAttr(el, name, value) {
    let sources = attrSources.get(el);
    if (!sources) { sources = {}; attrSources.set(el, sources); }
    let translated = attrTranslated.get(el);
    if (!translated) { translated = {}; attrTranslated.set(el, translated); }
    sources[name] = value;
    translated[name] = value;
    el.setAttribute(name, value);
  }

  function syncButtons() {
    document.querySelectorAll('[data-lang-toggle]').forEach((button) => {
      button.textContent = lang === 'en' ? 'RU' : 'EN';
      const label = lang === 'en' ? 'Switch to Russian' : 'Переключить на английский';
      setLiteralAttr(button, 'aria-label', label);
      setLiteralAttr(button, 'title', label);
      setLiteralAttr(button, 'aria-pressed', String(lang === 'en'));
    });
  }

  function setLang(next) {
    if (!LANGS.includes(next) || next === lang) return;
    lang = next;
    try { localStorage.setItem(STORAGE_KEY, next); } catch (error) { /* приватный режим */ }
    refresh();
    syncButtons();
  }

  function toggle() {
    setLang(lang === 'en' ? 'ru' : 'en');
  }

  document.documentElement.lang = lang;
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-lang-toggle]');
    if (!button) return;
    event.preventDefault();
    toggle();
  });
  ['confirm', 'alert', 'prompt'].forEach((name) => {
    const original = window[name];
    if (typeof original !== 'function') return;
    window[name] = function (message, ...rest) {
      return original.call(window, translate(String(message), lang), ...rest);
    };
  });
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { refresh(); syncButtons(); });
  } else {
    refresh();
    syncButtons();
  }

  window.DutyI18n = { t, translate, apply, setLang, toggle, refresh, syncButtons, get lang() { return lang; }, dictionary: EXACT };
})();
