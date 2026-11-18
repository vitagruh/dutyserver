import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const i18n = require('../app/static/i18n.js');

const CYRILLIC = /[А-Яа-яЁё]/;

test('dictionary entries are complete English strings', () => {
  const entries = Object.entries(i18n.dictionary);
  assert.ok(entries.length > 400, `expected a large dictionary, got ${entries.length}`);
  for (const [source, target] of entries) {
    assert.ok(source.trim().length > 0, 'empty source key');
    assert.ok(typeof target === 'string' && target.trim().length > 0, `empty translation for ${source}`);
    assert.ok(!CYRILLIC.test(target), `translation still contains Cyrillic: ${source} -> ${target}`);
    assert.ok(!/\{\d+\}/.test(source), `unresolved placeholder in key: ${source}`);
    assert.ok(!/\{\d+\}/.test(target), `unresolved placeholder in value: ${target}`);
  }
});

test('static labels are translated', () => {
  assert.equal(i18n.translate('График', 'en'), 'Schedule');
  assert.equal(i18n.translate('Требуют решения', 'en'), 'Needs decision');
  assert.equal(i18n.translate('Пн', 'en'), 'Mon');
  assert.equal(i18n.translate('ПОДТВЕРЖДЕНО', 'en'), 'VERIFIED');
  assert.equal(i18n.translate('Пруф жеребьёвки', 'en'), 'Draw proof');
  assert.equal(i18n.translate('Войти', 'en'), 'Sign in');
});

test('dynamic phrases are translated without touching names', () => {
  assert.equal(i18n.translate('ноябрь 2026', 'en'), 'November 2026');
  assert.equal(i18n.translate('из 30 дней', 'en'), 'of 30 days');
  assert.equal(i18n.translate('1 праздник в месяце', 'en'), '1 holiday this month');
  assert.equal(i18n.translate('13 активных', 'en'), '13 active');
  assert.equal(
    i18n.translate('Николай Фёдоров: 5 из 9', 'en'),
    'Николай Фёдоров: 5 of 9',
  );
  assert.equal(
    i18n.translate('Отсыпной после дежурства 25.10', 'en'),
    'Rest day after duty on 25.10',
  );
  assert.equal(
    i18n.translate('Сергей Лебедев — мои дежурства', 'en'),
    'Сергей Лебедев — my duties',
  );
  assert.equal(
    i18n.translate('Пруф жеребьёвки №4 — дежурства', 'en'),
    'Draw proof #4 — duties',
  );
  assert.equal(i18n.translate('Провести жеребьёвку ( 3 )', 'en'), 'Run the draw (3)');
  assert.equal(i18n.translate('сегодня 18.11.2026', 'en'), 'today 18.11.2026');
  assert.equal(
    i18n.translate(
      'Заявки подаются на 90 дней вперёд и не более 10 дней в месяц. Планировщик согласует или отклонит их; ' +
        'при согласовании дни «не могу» исключаются из распределения. Отозвать можно только заявку, ожидающую согласования.',
      'en',
    ),
    'Requests can be submitted up to 90 days ahead and no more than 10 days per month. ' +
      'The planner approves or declines them; once approved, “can’t” days are excluded from scheduling. ' +
      'Only a request awaiting approval can be withdrawn.',
  );
});

test('unknown data and russian mode stay unchanged', () => {
  assert.equal(i18n.translate('Александр Ковалёв', 'en'), 'Александр Ковалёв');
  assert.equal(i18n.translate('График', 'ru'), 'График');
  assert.equal(i18n.translate('  График  ', 'en'), '  Schedule  ');
  assert.equal(i18n.translate('', 'en'), '');
  assert.equal(i18n.translate(undefined, 'en'), undefined);
});
