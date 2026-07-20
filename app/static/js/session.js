(function () {
  const params = new URLSearchParams(window.location.search);
  const startQ = parseInt(params.get('q') || '1', 10);

  const panels = document.querySelectorAll('.question-panel');
  const navBtns = document.querySelectorAll('.q-nav-btn');
  const timerEl = document.getElementById('timer');
  let remaining = parseInt(timerEl.dataset.remaining || '0', 10);

  function showQuestion(index) {
    panels.forEach((p) => {
      p.style.display = p.dataset.index === String(index) ? 'block' : 'none';
    });
    navBtns.forEach((b) => {
      b.classList.toggle('active', b.dataset.index === String(index));
    });
    const submitQid = document.getElementById('submitQid');
    const panel = document.querySelector(`.question-panel[data-index="${index}"]`);
    if (submitQid && panel) {
      const hid = panel.querySelector('input[name="question_id"]');
      if (hid) submitQid.value = hid.value;
    }
  }

  navBtns.forEach((btn) => {
    btn.addEventListener('click', () => showQuestion(parseInt(btn.dataset.index, 10)));
  });

  document.querySelectorAll('.option-item input').forEach((input) => {
    input.addEventListener('change', function () {
      const label = this.closest('.option-item');
      const list = label.closest('.options-list');
      if (this.type === 'radio') {
        list.querySelectorAll('.option-item').forEach((l) => l.classList.remove('selected'));
      }
      label.classList.toggle('selected', this.checked);
      const panel = this.closest('.question-panel');
      const idx = panel.dataset.index;
      document.querySelector(`.q-nav-btn[data-index="${idx}"]`)?.classList.add('answered');
    });
  });

  function formatTime(sec) {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  function tick() {
    if (remaining <= 0) {
      document.getElementById('submitForm')?.submit();
      return;
    }
    timerEl.textContent = formatTime(remaining);
    timerEl.classList.toggle('warning', remaining <= 600 && remaining > 60);
    timerEl.classList.toggle('danger', remaining <= 60);
    remaining -= 1;
    setTimeout(tick, 1000);
  }

  showQuestion(startQ);
  tick();
})();
