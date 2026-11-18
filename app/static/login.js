(() => {
  'use strict';

  const form = document.getElementById('loginForm');
  const errorBox = document.getElementById('loginError');
  const submit = document.getElementById('loginSubmit');

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    errorBox.hidden = true;
    submit.disabled = true;
    submit.textContent = 'Вход…';
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: form.username.value.trim(),
          password: form.password.value,
        }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error((data && data.detail) || 'Не удалось войти');
      }
      window.location.href = data.user.role === 'employee' ? '/me' : '/';
    } catch (error) {
      showError(error.message || 'Не удалось войти');
      submit.disabled = false;
      submit.textContent = 'Войти';
    }
  });
})();
