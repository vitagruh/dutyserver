(() => {
  'use strict';

  let stored = null;
  try { stored = localStorage.getItem('duty-theme'); } catch (error) { stored = null; }
  const preferred = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
  const initial = stored === 'dark' || stored === 'light' ? stored : preferred;

  function current() {
    return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
  }

  function sync() {
    const theme = current();
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      button.textContent = theme === 'dark' ? 'Светлая' : 'Тёмная';
      button.setAttribute('aria-pressed', String(theme === 'dark'));
      button.setAttribute('title', theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему');
    });
  }

  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('duty-theme', theme); } catch (error) { /* приватный режим */ }
    sync();
  }

  function toggle() {
    apply(current() === 'dark' ? 'light' : 'dark');
  }

  apply(initial);
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-theme-toggle]');
    if (!button) return;
    event.preventDefault();
    toggle();
  });
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', sync);
  } else {
    sync();
  }

  window.DutyTheme = { toggle, apply, sync, current };
})();
