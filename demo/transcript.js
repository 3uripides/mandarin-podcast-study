/* Full-lesson transcript page (transcript.html). Reads api/lesson/<n>; works on the server and in the demo. */
(function () {
  'use strict';

  const $ = (sel) => document.querySelector(sel);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const fmt = (s) => {
    s = Math.max(0, Math.floor(s || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : String(m)) + ':' + String(x).padStart(2, '0');
  };

  function render(L) {
    document.title = `Transcript: Lesson ${L.lesson} - Mandarin Study`;
    $('#title').textContent = `Lesson ${L.lesson}: ${L.title}`;
    $('#sub').textContent = `Full transcript · ${fmt(L.duration)} · ${L.chunks.length} lines`;
    $('#back').href = 'lesson.html?n=' + L.lesson;
    const secAt = new Map(L.sections.map((s) => [s.start, s]));
    const out = [];
    L.chunks.forEach((c, i) => {
      if (secAt.has(i)) out.push(`<h2 class="sec">${esc(secAt.get(i).label)}</h2>`);
      const ts = `<span class="ts">${fmt(c.start)}</span>`;
      if (c.lang === 'zh') {
        out.push(`<div class="line zh">${ts}<div class="body">
          <div class="hanzi">${esc(c.text)}</div>
          <div class="py">${esc(c.pinyin)}</div>
          <div class="en">${esc(c.english)}</div></div></div>`);
      } else {
        out.push(`<div class="line en-line">${ts}<div class="body"><div class="en-text">${esc(c.text)}</div></div></div>`);
      }
    });
    $('#tx').innerHTML = out.join('') || '<p class="empty">This lesson has no lines.</p>';
  }

  // the four checkboxes only add/remove classes; print always shows what is checked on screen
  function bindToggles() {
    [['#c-chars', 'hide-chars'], ['#c-py', 'hide-py'], ['#c-en', 'hide-en'], ['#c-ts', 'hide-ts']].forEach(([sel, cls]) => {
      const box = $(sel);
      const apply = () => document.body.classList.toggle(cls, !box.checked);
      box.addEventListener('change', apply);
      apply();
    });
    $('#pdf-btn').addEventListener('click', () => window.print());
  }

  async function init() {
    bindToggles();
    const n = parseInt(new URLSearchParams(location.search).get('n'), 10);
    if (!n) { $('#title').textContent = 'No lesson selected'; return; }
    try {
      const r = await fetch('api/lesson/' + n);
      if (!r.ok) throw new Error(r.status === 404 ? 'lesson not processed yet' : 'HTTP ' + r.status);
      render(await r.json());
    } catch (e) {
      $('#title').textContent = 'Transcript not available: ' + e.message;
    }
    document.body.dataset.ready = '1';  // used by the PDF exporter to wait for the page
  }

  document.addEventListener('DOMContentLoaded', init);
})();
