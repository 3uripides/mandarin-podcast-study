/* Demo-only shim: answers the /api/* calls from localStorage so the static demo works
   on GitHub Pages. Loaded before app.js by src/build_demo.py. Placeholder content only. */
(function () {
  'use strict';
  const realFetch = window.fetch.bind(window);
  const KEY = 'demo.state';

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; }
  }
  function save(s) {
    try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* ignore */ }
  }
  function reply(obj, status) {
    return new Response(JSON.stringify(obj), { status: status || 200, headers: { 'Content-Type': 'application/json' } });
  }
  async function readIndex() {
    const r = await realFetch('data/lessons/index.json');
    return r.json();
  }

  function progressOf(st, n) {
    const p = st.progress[n];
    return p ? { lesson: n, status: p.status, last_chunk: p.last_chunk, practiced: p.practiced }
      : { lesson: n, status: 'not started', last_chunk: 0, practiced: [] };
  }

  window.fetch = async function (input, init) {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (!url.pathname.includes('/api/')) return realFetch(input, init);
    const path = url.pathname.slice(url.pathname.indexOf('/api/') + 5);
    const method = ((init && init.method) || 'GET').toUpperCase();
    const body = init && init.body ? JSON.parse(init.body) : {};
    const st = load();
    st.progress = st.progress || {};
    st.saves = st.saves || [];
    st.nextId = st.nextId || 1;

    if (path === 'lessons') {
      const idx = await readIndex();
      // Only Mandarin (zh) lines count as practiced, same as the server.
      const zhSets = await Promise.all(idx.map(async (e) => {
        if (!e.processed) return new Set();
        const j = await (await realFetch('data/lessons/' + String(e.lesson).padStart(3, '0') + '/lesson.json')).json();
        return new Set(j.chunks.filter((c) => c.lang === 'zh').map((c) => c.id));
      }));
      const lessons = idx.map((e, k) => {
        const p = progressOf(st, e.lesson);
        const mine = st.saves.filter((s) => s.lesson === e.lesson);
        return {
          lesson: e.lesson, title: e.title, processed: !!e.processed, status: p.status,
          last_chunk: p.last_chunk, practiced_count: p.practiced.filter((id) => zhSets[k].has(id)).length,
          saved_words: mine.filter((s) => s.kind === 'word').length,
          saved_sentences: mine.filter((s) => s.kind === 'sentence').length,
        };
      });
      const sum = (f) => lessons.reduce((a, x) => a + f(x), 0);
      return reply({
        lessons,
        totals: {
          lessons: lessons.length, processed: sum((x) => (x.processed ? 1 : 0)),
          completed: sum((x) => (x.status === 'completed' ? 1 : 0)), practiced: sum((x) => x.practiced_count),
          saved_words: sum((x) => x.saved_words), saved_sentences: sum((x) => x.saved_sentences),
        },
        last_lesson: st.last_lesson == null ? null : st.last_lesson,
      });
    }

    const lm = /^lesson\/(\d+)$/.exec(path);
    if (lm && method === 'GET') {
      const n = parseInt(lm[1], 10);
      const r = await realFetch('data/lessons/' + String(n).padStart(3, '0') + '/lesson.json');
      if (!r.ok) return reply({ error: 'lesson not processed yet' }, 404);
      const lesson = await r.json();
      lesson.progress = progressOf(st, n);
      lesson.saves = st.saves.filter((s) => s.lesson === n);
      return reply(lesson);
    }

    if (path === 'progress') {
      if (method === 'GET') {
        const n = url.searchParams.get('lesson');
        if (n) return reply(progressOf(st, parseInt(n, 10)));
        return reply(Object.keys(st.progress).map((k) => progressOf(st, +k)));
      }
      const n = parseInt(body.lesson, 10);
      const cur = progressOf(st, n);
      const practiced = Array.from(new Set(cur.practiced.concat((body.practiced || []).map(Number)))).sort((a, b) => a - b);
      st.progress[n] = {
        status: body.status || cur.status,
        last_chunk: body.last_chunk != null ? body.last_chunk : cur.last_chunk,
        practiced: practiced,
      };
      st.last_lesson = n;
      save(st);
      return reply(progressOf(st, n));
    }

    if (path === 'saves') {
      if (method === 'GET') {
        const n = url.searchParams.get('lesson');
        return reply(n ? st.saves.filter((s) => s.lesson === +n) : st.saves);
      }
      if (method === 'POST') {
        const dup = st.saves.find((s) => s.lesson === body.lesson && s.chunk_id === body.chunk_id &&
          s.kind === body.kind && s.text === body.text);
        if (dup) return reply(dup);
        const row = Object.assign({ id: st.nextId++, chunk_id: 0, pos: '', pinyin: '', english: '', clip: null }, body);
        st.saves.push(row);
        save(st);
        return reply(row);
      }
      if (method === 'DELETE') {
        const before = st.saves.length;
        st.saves = st.saves.filter((s) => !(body.id != null ? s.id === body.id :
          (s.lesson === body.lesson && s.chunk_id === body.chunk_id && s.kind === body.kind && s.text === body.text)));
        save(st);
        return reply({ deleted: before - st.saves.length });
      }
    }

    if (path === 'export.apkg') {
      return reply({ error: 'Anki export needs the local tool (python -m src.server). Not available in the demo.' }, 501);
    }
    return reply({ error: 'not found in demo' }, 404);
  };

  document.addEventListener('DOMContentLoaded', function () {
    const bar = document.createElement('div');
    bar.className = 'demo-banner';
    bar.textContent = 'Demo with placeholder content - build your own library with the open-source tool';
    document.body.insertBefore(bar, document.body.firstChild);
    const ex = document.getElementById('ex-go');
    if (ex) { ex.disabled = true; ex.title = 'Available in the local tool'; }
  });
})();
