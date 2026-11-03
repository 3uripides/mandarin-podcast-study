/* Study UI. One file for both pages: index.html (#lesson-list) and lesson.html (#lesson-root).
   All URLs are relative so the same files work on the Flask server and on GitHub Pages. */
(function () {
  'use strict';

  const $ = (sel) => document.querySelector(sel);
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : many);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // Per-viewer conveniences only; never fatal.
  const store = {
    get(k, d) { try { const v = localStorage.getItem('mq.' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('mq.' + k, JSON.stringify(v)); } catch (e) { /* ignore */ } },
  };

  async function api(path, opts) {
    const r = await fetch(path, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts || {}));
    let body = null;
    try { body = await r.json(); } catch (e) { /* not JSON */ }
    if (!r.ok) throw new Error((body && body.error) || ('HTTP ' + r.status));
    return body;
  }
  const post = (path, data) => api(path, { method: 'POST', body: JSON.stringify(data) });
  const del = (path, data) => api(path, { method: 'DELETE', body: JSON.stringify(data) });

  // ---------- theme ----------
  function applyTheme() {
    const t = store.get('theme', null);
    if (t) document.documentElement.dataset.theme = t;
    else delete document.documentElement.dataset.theme;
  }
  function toggleTheme() {
    const cur = document.documentElement.dataset.theme ||
      (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    store.set('theme', cur === 'dark' ? 'light' : 'dark');
    applyTheme();
  }

  // ---------- index page ----------
  async function initIndex() {
    const data = await api('api/lessons');
    const t = data.totals;
    $('#overall-bar').style.width = (t.lessons ? Math.round(100 * t.completed / t.lessons) : 0) + '%';
    $('#overall-stats').innerHTML = [
      ['Completed', t.completed, `of ${t.lessons}`],
      ['Processed', t.processed, `of ${t.lessons}`],
      ['Lines practiced', t.practiced, ''],
      ['Words saved', t.saved_words, ''],
      ['Sentences saved', t.saved_sentences, ''],
    ].map(([k, v, s]) => `<div class="kpi"><span class="k">${k}</span><span class="v">${v}</span>${s ? `<span class="s">${s}</span>` : ''}</div>`).join('');
    const last = data.lessons.find((x) => x.lesson === data.last_lesson);
    $('#overall-sub').textContent = last ? `Last studied: Lesson ${last.lesson}, ${last.title}` : 'Nothing studied yet.';
    if (last) {
      $('#continue-slot').innerHTML = `<a href="lesson.html?n=${last.lesson}">Continue Lesson ${last.lesson} &rarr;</a>`;
    }
    const ul = $('#lesson-list');
    if (!data.lessons.length) {
      ul.innerHTML = '<li class="muted">No lessons yet. Run the pipeline to add some.</li>';
      return;
    }
    ul.innerHTML = data.lessons.map((x) => {
      const cls = x.status.replace(/ /g, '-');
      if (!x.processed) {
        return `<li class="lesson-card off"><div><div class="title">Lesson ${x.lesson}: ${esc(x.title)}</div>
          <div class="meta">not processed yet</div></div><div></div></li>`;
      }
      return `<li class="lesson-card"><div><div class="title"><a href="lesson.html?n=${x.lesson}">Lesson ${x.lesson}: ${esc(x.title)}</a></div>
        <div class="meta">${plural(x.practiced_count, 'line', 'lines')} practiced · ${plural(x.saved_words, 'word', 'words')} · ${plural(x.saved_sentences, 'sentence', 'sentences')} saved</div></div>
        <div class="row-links"><span class="badge ${cls}">${x.status}</span>
          <a href="transcript.html?n=${x.lesson}">Transcript</a>
          ${window.MQ_DEMO ? '' : `<a href="api/export.apkg?auto=1&amp;lesson=${x.lesson}" download>Deck</a>`}
        </div></li>`;
    }).join('');
    const exLesson = $('#ex-lesson');
    data.lessons.filter((x) => x.processed).forEach((x) => {
      exLesson.insertAdjacentHTML('beforeend', `<option value="${x.lesson}">Lesson ${x.lesson}</option>`);
    });
    // POS applies to words only: disable the POS picker for Sentences.
    const syncPos = () => {
      const sent = $('#ex-kind').value === 'sentence';
      $('#ex-pos').disabled = sent;
      if (sent) $('#ex-pos').value = '';
      $('#ex-pos-hint').textContent = sent ? 'Part of speech applies to words only.' : '';
    };
    $('#ex-kind').addEventListener('change', syncPos);
    syncPos();
    $('#ex-go').addEventListener('click', exportDeck);
  }

  async function exportDeck() {
    const msg = $('#ex-msg');
    msg.className = 'msg';
    msg.textContent = 'Building deck...';
    const q = new URLSearchParams({
      kind: $('#ex-kind').value, pos: $('#ex-pos').value, lesson: $('#ex-lesson').value,
      characters: $('#ex-chars').checked ? '1' : '0',
    });
    try {
      const r = await fetch('api/export.apkg?' + q);
      if (!r.ok) {
        let m = 'HTTP ' + r.status;
        try { m = (await r.json()).error || m; } catch (e) { /* not JSON */ }
        throw new Error(m);
      }
      const fm = /filename="?([^";]+)"?/.exec(r.headers.get('Content-Disposition') || '');
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement('a');
      a.href = url;
      a.download = fm ? fm[1] : 'mandarin.apkg';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      msg.textContent = 'Downloaded ' + a.download + '. Import it into Anki.';
    } catch (e) {
      msg.className = 'msg err';
      msg.textContent = 'Export failed: ' + e.message;
    }
  }

  // ---------- lesson page ----------
  const P = { chars: false, pinyin: true, english: true, zhOnly: false, loop: false, slow: false, autoPause: false, autoAdv: false };
  // whole episode and one sentence / word / recording; real <audio> elements on lesson.html
  const full = document.getElementById('ep') || new Audio();
  const clip = document.getElementById('clipaudio') || new Audio();
  full.preload = 'auto';
  clip.preload = 'auto';
  [full, clip].forEach((a) => { a.preservesPitch = true; a.mozPreservesPitch = true; a.webkitPreservesPitch = true; });
  // Slow mode must survive every src change: re-apply the rate when media loads.
  full.addEventListener('loadedmetadata', () => applyRate());
  clip.addEventListener('loadedmetadata', () => applyRate());

  let L = null;  // lesson.json + progress + saves from the server
  let S = null;  // playback and UI state
  const cs = () => L.chunks;

  const skey = (cid, kind, text) => cid + '|' + kind + '|' + text;
  const isSaved = (c, kind, text) => S.saves.has(skey(c.id, kind, text));
  const rate = () => (P.slow ? 0.75 : 1);

  let sayTimer = null;
  function say(msg) {
    $('#now-line').textContent = msg;
    clearTimeout(sayTimer);
    sayTimer = setTimeout(updateNow, 3000);
  }
  function fail(e) {
    if (e && e.name === 'AbortError') return;  // src changed mid-play; harmless
    say('Playback problem: ' + (e && e.message ? e.message : e));
  }

  function updateNow() {
    if (!S || !L) return;
    const c = cs()[S.active];
    if (!c) return;
    const mode = { idle: 'stopped', episode: 'playing episode', range: 'playing selection', clip: 'practicing' }[S.mode];
    $('#now-line').textContent = `Line ${S.active + 1}/${cs().length} (${c.lang === 'zh' ? c.pinyin : c.text}) · ${mode}` +
      (P.loop ? ' · loop' : '') + (P.slow ? ' · 0.75x' : '');
  }

  function updatePlayBtn() {
    const playing = (S.mode === 'clip' && !clip.paused) ||
      ((S.mode === 'episode' || S.mode === 'range') && !full.paused);
    const b = $('#play-btn');
    b.innerHTML = playing ? '&#10074;&#10074; Pause' : '&#9654; Play episode';
    b.classList.toggle('on', playing);
    const bp = $('#bar-play');
    if (bp) {
      bp.innerHTML = playing ? '&#10074;&#10074;' : '&#9654;';
      bp.setAttribute('aria-label', playing ? 'Pause' : 'Play');
    }
    updateBar();
  }

  function updateCompare() {
    $('#cmp-btn').disabled = !S.recUrls.has(S.active);
  }

  function updateRecButtons() {
    const b = $('#rec-btn');
    b.textContent = S.recording ? 'Stop' : 'Record';
    b.classList.toggle('on', S.recording);
    updateCompare();
  }

  function setActive(i, scroll) {
    if (i < 0 || i >= cs().length) return;
    if (S.els[S.active]) S.els[S.active].classList.remove('active');
    S.active = i;
    const el = S.els[i];
    el.classList.add('active');
    if (scroll) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    updateNow();
    updateCompare();
    if (S.ready) scheduleSave();
  }

  function renderSel() {
    cs().forEach((_, i) => {
      const on = !!S.range && i >= S.range[0] && i <= S.range[1];
      S.els[i].classList.toggle('sel', on);
    });
    $('#range-btn').disabled = !S.range;
    $('#clear-sel-btn').disabled = !S.range;
  }

  function selectChunk(i, extend) {
    if (extend && S.anchor != null) S.range = [Math.min(S.anchor, i), Math.max(S.anchor, i)];
    else { S.anchor = i; S.range = [i, i]; }
    setActive(i, false);
    renderSel();
  }

  // ---------- progress ----------
  function markPracticed(i) {
    const c = cs()[i];
    if (!c) return;  // word clips pass -1
    // only Mandarin lines count as practiced; English lines just move status to in progress
    if (c.lang === 'zh' && !S.practiced.has(c.id)) {
      S.practiced.add(c.id);
      if (S.els[i]) S.els[i].classList.add('practiced');
    }
    if (S.status === 'not started') S.status = 'in progress';
    const zh = cs().filter((x) => x.lang === 'zh');
    if (S.status !== 'completed' && zh.length && zh.every((x) => S.practiced.has(x.id))) S.status = 'completed';
    syncCompleteBtn();
    updateStats();
    scheduleSave();
  }

  function syncCompleteBtn() {
    const done = S.status === 'completed';
    const b = $('#complete-btn');
    b.textContent = done ? 'Completed (click to undo)' : 'Mark lesson complete';
    b.classList.toggle('on', done);
  }

  function updateStats() {
    const zh = cs().filter((c) => c.lang === 'zh');
    const prac = zh.filter((c) => S.practiced.has(c.id)).length;
    let words = 0, sents = 0;
    S.saves.forEach((v) => (v.kind === 'word' ? words++ : sents++));
    $('#lesson-stats').textContent = `${S.status} · practiced ${prac}/${zh.length} Mandarin lines · saved ${plural(words, 'word', 'words')}, ${plural(sents, 'sentence', 'sentences')}`;
  }

  function scheduleSave() {
    clearTimeout(S.saveTimer);
    S.saveTimer = setTimeout(flushProgress, 600);
  }

  function flushProgress() {
    if (!S || !S.ready) return;
    clearTimeout(S.saveTimer);
    const c = cs()[S.active];
    const body = JSON.stringify({ lesson: S.n, status: S.status, last_chunk: c ? c.id : 0, practiced: [...S.practiced] });
    // keepalive lets the last write survive page unload
    fetch('api/progress', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true })
      .catch(() => { /* offline or server down: progress is best-effort */ });
  }

  function setStatusManual() {
    S.status = S.status === 'completed' ? 'in progress' : 'completed';
    syncCompleteBtn();
    updateStats();
    scheduleSave();
  }

  // ---------- playback ----------
  function idxAtTime(t) {
    let best = 0;
    const list = cs();
    for (let i = 0; i < list.length; i++) {
      if (list[i].start <= t + 0.05) best = i;
      else break;
    }
    return best;
  }

  function nextIdx(i, dir) {
    const list = cs();
    for (let j = i + dir; j >= 0 && j < list.length; j += dir) {
      if (!P.zhOnly || list[j].lang === 'zh') return j;
    }
    return -1;
  }

  function stopAll() {
    full.pause();
    clip.pause();
    clearTimeout(S.resumeTimer);
    S.pausedAuto = false;
    S.clipDone = null;
    S.mode = 'idle';
    updatePlayBtn();
    updateNow();
  }

  // Episode (a == 0 .. last) or range/section (a..b) through the full audio file.
  function playSegment(a, b, mode) {
    clip.pause();
    clearTimeout(S.resumeTimer);
    S.pausedAuto = false;
    S.clipDone = null;
    S.mode = mode;
    S.segFrom = a;
    S.segTo = b;
    full.currentTime = cs()[a].start;
    setActive(a, true);
    full.play().catch(fail);
    updatePlayBtn();
  }

  function playEpisodeFrom(i) {
    playSegment(i, cs().length - 1, 'episode');
  }

  // One sentence / word / recording through the clip element. done() runs instead of loop/advance.
  function playClip(i, done) {
    const c = cs()[i];
    if (!c.clip) { playSegment(i, i, 'range'); return; }  // ponytail: no clip -> play its span of the episode
    full.pause();
    clearTimeout(S.resumeTimer);
    S.pausedAuto = false;
    S.mode = 'clip';
    S.clipIdx = i;
    S.clipDone = done || null;
    setActive(i, true);
    clip.src = 'data/' + c.clip;
    clip.currentTime = 0;
    applyRate();
    clip.play().catch(fail);
    updatePlayBtn();
  }

  // Plays a list of audio URLs back to back (original then recording, etc.).
  function playSeq(srcs, done) {
    full.pause();
    clearTimeout(S.resumeTimer);
    S.mode = 'clip';
    const steps = srcs.slice();
    const go = () => {
      if (!steps.length) {
        S.clipDone = null;
        S.mode = 'idle';
        updatePlayBtn();
        updateNow();
        if (done) done();
        return;
      }
      S.clipDone = go;
      clip.src = steps.shift();
      clip.currentTime = 0;
      applyRate();
      clip.play().catch(fail);
    };
    go();
  }

  function playWordAudio(i, wi) {
    const c = cs()[i];
    const src = c.words[wi].clip || c.clip;
    if (!src) return;
    S.clipIdx = -1;  // listening to a word does not count as practicing the line
    playSeq(['data/' + src]);
  }

  // Playing -> pause. Paused -> resume only if the active line is the one that was paused;
  // otherwise play the episode from the active line.
  function togglePlay() {
    clearTimeout(S.resumeTimer);
    S.pausedAuto = false;
    const playingNow = (S.mode === 'clip' && !clip.paused) ||
      ((S.mode === 'episode' || S.mode === 'range') && !full.paused);
    const inSeg = S.active >= S.segFrom && S.active <= S.segTo;
    if (playingNow) {
      if (S.mode === 'clip') clip.pause(); else full.pause();
    } else if (S.mode === 'clip' && clip.paused && S.clipIdx === S.active && !clip.ended) {
      clip.play().catch(fail);
    } else if ((S.mode === 'episode' || S.mode === 'range') && full.paused && inSeg) {
      full.play().catch(fail);
    } else {
      playEpisodeFrom(S.active);
    }
    updatePlayBtn();
  }

  function pauseAfterSentence(ci) {
    full.pause();
    full.currentTime = cs()[ci].start;  // resume exactly at the next sentence
    S.pausedAuto = true;
    updatePlayBtn();
    updateNow();
    clearTimeout(S.resumeTimer);
    if (P.autoAdv) {
      S.resumeTimer = setTimeout(() => {
        if (S.pausedAuto && (S.mode === 'episode' || S.mode === 'range')) {
          S.pausedAuto = false;
          full.play().catch(fail);
        }
      }, 1200);
    }
  }

  function onFullTime() {
    if (!S || (S.mode !== 'episode' && S.mode !== 'range')) return;
    const list = cs();
    const t = full.currentTime;
    if (t >= list[S.segTo].end) {
      markPracticed(S.segTo);
      if (P.loop) { full.currentTime = list[S.segFrom].start; return; }
      full.pause();
      S.mode = 'idle';
      updatePlayBtn();
      updateNow();
      return;
    }
    const ci = Math.min(Math.max(idxAtTime(t), S.segFrom), S.segTo);
    if (ci !== S.active) {
      const prev = S.active;
      markPracticed(prev);
      if (P.loop && S.mode === 'episode') { full.currentTime = list[prev].start; return; }
      setActive(ci, true);
      if (P.autoPause) pauseAfterSentence(ci);
    }
  }

  function onFullEnded() {
    if (!S || (S.mode !== 'episode' && S.mode !== 'range')) return;
    markPracticed(S.segTo);
    if (P.loop) { full.currentTime = cs()[S.segFrom].start; full.play().catch(fail); return; }
    S.mode = 'idle';
    updatePlayBtn();
    updateNow();
  }

  function onClipEnded() {
    if (!S || S.mode !== 'clip') return;
    markPracticed(S.clipIdx);
    if (S.clipDone) { const f = S.clipDone; S.clipDone = null; f(); return; }
    if (P.loop) { clip.currentTime = 0; clip.play().catch(fail); return; }
    if (P.autoAdv) {
      const nx = nextIdx(S.clipIdx, 1);
      if (nx >= 0) { playClip(nx); return; }
    }
    S.mode = 'idle';
    updatePlayBtn();
    updateNow();
  }

  function step(dir) {
    const nx = nextIdx(S.active, dir);
    if (nx < 0) return;
    if (S.mode === 'clip') playClip(nx);
    else seekTo(cs()[nx].start);  // episode position moves with the line, same as the play bar
  }

  // ---------- play bar: whole-episode position ----------
  const fmt = (s) => {
    s = Math.max(0, Math.floor(s || 0));  // floor, same as transcript.js, so both pages agree
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : String(m)) + ':' + String(x).padStart(2, '0');
  };
  const episodeDur = () => (L && L.duration) || (Number.isFinite(full.duration) ? full.duration : 0);

  // While a sentence clip plays, the bar shows chunk.start + clip time: "how far through the lesson".
  function episodePos() {
    if (S.mode === 'clip') {
      const i = S.clipIdx >= 0 ? S.clipIdx : S.active;
      return cs()[i].start + (clip.currentTime || 0);
    }
    return full.currentTime || 0;
  }

  let dragging = false, dragPos = 0;

  function updateBar() {
    if (!S || !L) return;
    const dur = episodeDur();
    const pos = Math.min(dragging ? dragPos : episodePos(), dur || Infinity);
    $('#bar-time').textContent = fmt(pos) + ' / ' + fmt(dur);
    $('#bar-rem').textContent = '-' + fmt(Math.max(0, dur - pos));
    const pct = dur ? (pos / dur) * 100 : 0;
    $('#seek-fill').style.width = pct + '%';
    $('#seek-thumb').style.left = pct + '%';
    const seek = $('#seek');
    seek.setAttribute('aria-valuemax', String(Math.floor(dur)));
    seek.setAttribute('aria-valuenow', String(Math.floor(pos)));
    seek.setAttribute('aria-valuetext', fmt(pos) + ' of ' + fmt(dur));
  }

  function renderTicks() {
    const dur = episodeDur();
    if (!dur) return;
    let html = '';
    L.sections.forEach((sec) => {
      html += `<i class="tick sec" style="left:${(cs()[sec.start].start / dur) * 100}%" title="${esc(sec.label)}"></i>`;
    });
    cs().forEach((c) => {
      if (c.lang === 'zh') html += `<i class="tick zh" style="left:${(c.start / dur) * 100}%"></i>`;
    });
    $('#seek-ticks').innerHTML = html;
  }

  // Jump the whole-episode position. Keeps playing if it was playing; a clip is stopped.
  function seekTo(t) {
    const list = cs();
    const dur = episodeDur();
    const wasPlaying = (S.mode === 'clip' && !clip.paused) ||
      ((S.mode === 'episode' || S.mode === 'range') && !full.paused);
    clip.pause();
    clearTimeout(S.resumeTimer);
    S.pausedAuto = false;
    S.clipDone = null;
    S.mode = 'episode';
    S.segFrom = 0;
    S.segTo = list.length - 1;
    t = Math.max(0, Math.min(t, dur || t));
    setActive(idxAtTime(t), true);  // set the line first so the seek does not mark lines as played
    full.currentTime = t;
    if (wasPlaying) full.play().catch(fail);
    updatePlayBtn();
    updateNow();
  }

  function wireBar() {
    const seekEl = $('#seek');
    const fracOf = (e) => {
      const r = seekEl.getBoundingClientRect();
      return Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    };
    seekEl.addEventListener('pointerdown', (e) => {
      dragging = true;
      seekEl.setPointerCapture(e.pointerId);
      dragPos = fracOf(e) * episodeDur();
      updateBar();
    });
    seekEl.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      dragPos = fracOf(e) * episodeDur();
      updateBar();
    });
    const finish = (e) => {
      if (!dragging) return;
      dragging = false;
      if (e.type === 'pointerup') seekTo(dragPos);
      else updateBar();
    };
    seekEl.addEventListener('pointerup', finish);
    seekEl.addEventListener('pointercancel', finish);
    seekEl.addEventListener('keydown', (e) => {
      const dur = episodeDur();
      if (!dur) return;
      const cur = episodePos();
      let t = null;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') t = cur - 5;
      else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') t = cur + 5;
      else if (e.key === 'Home') t = 0;
      else if (e.key === 'End') t = dur;
      if (t === null) return;
      e.preventDefault();
      e.stopPropagation();  // keep Left/Right from also moving line
      seekTo(Math.max(0, Math.min(dur, t)));
    });
    $('#bar-play').addEventListener('click', togglePlay);
    $('#bar-prev').addEventListener('click', () => step(-1));
    $('#bar-next').addEventListener('click', () => step(1));
    [full, clip].forEach((a) => {
      a.addEventListener('timeupdate', updateBar);
      a.addEventListener('seeked', updateBar);
      a.addEventListener('loadedmetadata', updateBar);
    });
  }

  function applyRate() {
    full.playbackRate = rate();
    clip.playbackRate = rate();
  }

  // ---------- recording ----------
  async function toggleRecord() {
    if (S.recording) {
      if (S.mr && S.mr.state !== 'inactive') S.mr.stop();
      return;
    }
    const i = S.active;
    if (!cs()[i].clip) { say('This line has no clip to record against.'); return; }
    if (!navigator.mediaDevices || !window.MediaRecorder) { say('Recording is not supported in this browser.'); return; }
    try {
      if (!S.stream) S.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      say('Microphone not available: ' + e.message);
      return;
    }
    // original plays first, then recording starts
    playClip(i, () => startRec(i));
  }

  function startRec(i) {
    const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
      .find((t) => MediaRecorder.isTypeSupported(t)) || '';
    const parts = [];
    const mr = new MediaRecorder(S.stream, type ? { mimeType: type } : undefined);
    mr.ondataavailable = (e) => { if (e.data && e.data.size) parts.push(e.data); };
    mr.onstop = () => {
      const blob = new Blob(parts, { type: mr.mimeType || 'audio/webm' });
      const old = S.recUrls.get(i);
      if (old) URL.revokeObjectURL(old);
      S.recUrls.set(i, URL.createObjectURL(blob));
      S.recording = false;
      updateRecButtons();
      playSeq([S.recUrls.get(i)]);  // play your take back
    };
    S.mr = mr;
    mr.start();
    S.recording = true;
    updateRecButtons();
    say('Recording... press Stop (M) when done');
  }

  function compare() {
    const i = S.active;
    const url = S.recUrls.get(i);
    if (!url) return;
    S.clipIdx = i;
    playSeq(['data/' + cs()[i].clip, url]);
  }

  // ---------- saves ----------
  function itemText(c, kind, wi) {
    return kind === 'word' ? c.words[wi].text : c.text;
  }

  async function toggleSave(i, kind, wi) {
    const c = cs()[i];
    const text = itemText(c, kind, wi);
    const k = skey(c.id, kind, text);
    try {
      if (S.saves.has(k)) {
        await del('api/saves', { id: S.saves.get(k).id });
        S.saves.delete(k);
      } else {
        let body;
        if (kind === 'word') {
          const w = c.words[wi];
          body = { text, pinyin: w.pinyin, english: w.english, pos: w.pos, clip: w.clip || c.clip || null };
        } else {
          body = { text, pinyin: c.pinyin, english: c.english, pos: '', clip: c.clip || null };
        }
        const row = await post('api/saves', Object.assign({ lesson: S.n, chunk_id: c.id, kind }, body));
        S.saves.set(k, { id: row.id, kind });
      }
    } catch (e) {
      say('Save failed: ' + e.message);
      return;
    }
    refreshSaves();
    updateStats();
  }

  // "Save both": if everything is saved, unsave all; otherwise save what is missing.
  async function saveBoth(i) {
    const c = cs()[i];
    const items = [['sentence', 0]].concat(c.words.map((_, wi) => ['word', wi]));
    const allSaved = items.every(([k, wi]) => isSaved(c, k, itemText(c, k, wi)));
    for (const [k, wi] of items) {
      if (isSaved(c, k, itemText(c, k, wi)) === allSaved) await toggleSave(i, k, wi);
    }
  }

  function refreshSaves() {
    cs().forEach((c, i) => {
      const el = S.els[i];
      if (!el || c.lang !== 'zh') return;
      const sent = isSaved(c, 'sentence', c.text);
      const sb = el.querySelector('.save-sent');
      if (sb) { sb.textContent = sent ? 'Saved' : 'Save sentence'; sb.classList.toggle('saved', sent); }
      const all = sent && c.words.every((w) => isSaved(c, 'word', w.text));
      const bb = el.querySelector('.save-both');
      if (bb) { bb.textContent = all ? 'Saved both' : 'Save both'; bb.classList.toggle('saved', all); }
      el.querySelectorAll('.chip').forEach((chip, wi) => {
        chip.classList.toggle('saved', isSaved(c, 'word', c.words[wi].text));
      });
    });
    if (S.pop) refreshPopSave();
  }

  // W: the open popover's word if one is open, otherwise the first word of the active line.
  function saveFocusedWord() {
    const f = S.pop && S.focus ? S.focus : { i: S.active, wi: 0 };
    const c = cs()[f.i];
    if (c.lang !== 'zh' || !c.words.length) { say('No word on this line. Click a word first.'); return; }
    const text = c.words[f.wi].text;
    if (isSaved(c, 'word', text)) { say(`"${text}" is already saved`); return; }
    toggleSave(f.i, 'word', f.wi).then(() => say(`Saved word ${text}`));
  }

  function saveActiveSentence() {
    const c = cs()[S.active];
    if (c.lang !== 'zh') { say('Only Mandarin lines can be saved as sentences'); return; }
    if (isSaved(c, 'sentence', c.text)) { say('Sentence already saved'); return; }
    toggleSave(S.active, 'sentence', 0).then(() => say('Saved sentence'));
  }

  // ---------- word popover ----------
  const POS = { noun: 'noun', verb: 'verb', adj: 'adjective', adv: 'adverb', pron: 'pronoun', num: 'number',
    measure: 'measure word', prep: 'preposition', conj: 'conjunction', particle: 'particle', other: 'other' };

  function openPop(i, wi, chipEl) {
    closePop();
    const c = cs()[i];
    const w = c.words[wi];
    S.focus = { i, wi };
    document.querySelectorAll('.chip.focus').forEach((x) => x.classList.remove('focus'));
    chipEl.classList.add('focus');
    setActive(i, false);
    const pop = document.createElement('div');
    pop.className = 'popover';
    pop.setAttribute('role', 'dialog');
    pop.innerHTML = `<div class="big cn-p">${esc(w.text)}</div>
      <div class="py">${esc(w.pinyin)}</div>
      <div>${esc(w.english)}</div>
      <div class="muted">${esc(POS[w.pos] || w.pos || 'other')}</div>
      <div class="actions">
        <button type="button" data-a="play">Play word</button>
        <button type="button" data-a="save"></button>
        <button type="button" data-a="close">Close</button>
      </div>`;
    document.body.appendChild(pop);
    S.pop = pop;
    refreshPopSave(); // fill the Save label first so offsetHeight below is final
    // bring the chip on screen first, then place the popover below it, or above if no room
    chipEl.scrollIntoView({ block: 'center', behavior: 'auto' });
    const r = chipEl.getBoundingClientRect();
    const h = pop.offsetHeight;
    const below = r.bottom + 6 + h <= window.innerHeight;
    const top = below ? r.bottom + 6 : Math.max(6, r.top - 6 - h);
    const left = Math.max(8, Math.min(r.left + window.scrollX, window.scrollX + window.innerWidth - 300));
    pop.style.left = left + 'px';
    pop.style.top = (top + window.scrollY) + 'px';
    pop.querySelector('[data-a=play]').onclick = () => playWordAudio(i, wi);
    pop.querySelector('[data-a=save]').onclick = () => toggleSave(i, 'word', wi);
    pop.querySelector('[data-a=close]').onclick = closePop;
    S.pop = pop;
    refreshPopSave();
  }

  function refreshPopSave() {
    const f = S.focus;
    const btn = S.pop && S.pop.querySelector('[data-a=save]');
    if (!btn || !f) return;
    const on = isSaved(cs()[f.i], 'word', cs()[f.i].words[f.wi].text);
    btn.textContent = on ? 'Saved (click to remove)' : 'Save word';
    btn.classList.toggle('saved', on);
  }

  function closePop() {
    if (S) { if (S.pop) S.pop.remove(); S.pop = null; S.focus = null; }
    document.querySelectorAll('.chip.focus').forEach((x) => x.classList.remove('focus'));
  }

  // ---------- rendering ----------
  function zhCardHTML(c) {
    const words = c.words.map((w, wi) =>
      `<button type="button" class="chip" data-w="${wi}"><span class="cn">${esc(w.text)}</span><span class="py">${esc(w.pinyin)}</span></button>`).join('');
    return `<div class="head"><span class="time">${fmt(c.start)}</span><div class="body">
      <div class="pinyin">${esc(c.pinyin)}</div>
      <div class="hanzi">${esc(c.text)}</div>
      <div class="english">${esc(c.english)}</div>
      <div class="words">${words}</div>
      <div class="actions">
        <button type="button" class="play-card">&#9654; Clip</button>
        <button type="button" class="save-sent">Save sentence</button>
        <button type="button" class="save-both">Save both</button>
      </div></div></div>`;
  }

  function enCardHTML(c) {
    return `<div class="head"><span class="time">${fmt(c.start)}</span><div class="body">
      <div class="en-text">${esc(c.text)}</div>
      <div class="actions"><button type="button" class="play-card">&#9654; Clip</button></div>
      </div></div>`;
  }

  function renderTranscript() {
    const secAt = new Map(L.sections.map((s) => [s.start, s]));
    const frag = document.createDocumentFragment();
    cs().forEach((c, i) => {
      if (secAt.has(i)) {
        const h = document.createElement('h2');
        h.className = 'section-h';
        h.dataset.full = secAt.get(i).label;  // syncToggles() strips CJK when chars are hidden
        frag.appendChild(h);
      }
      const el = document.createElement('div');
      el.className = 'chunk ' + c.lang + (S.practiced.has(c.id) ? ' practiced' : '');
      el.dataset.i = i;
      el.innerHTML = c.lang === 'zh' ? zhCardHTML(c) : enCardHTML(c);
      S.els[i] = el;
      frag.appendChild(el);
    });
    $('#transcript').appendChild(frag);
  }

  function syncToggles() {
    const body = document.body;
    body.classList.toggle('hide-chars', !P.chars);
    body.classList.toggle('hide-pinyin', !P.pinyin);
    body.classList.toggle('hide-english', !P.english);
    $('#transcript').classList.toggle('zh-only', P.zhOnly);
    // section labels: no Chinese characters while the chars toggle is off
    const cjk = /[㐀-鿿　-〿＀-￯]+/g;
    const label = (full) => (P.chars ? full : (full.replace(cjk, '').replace(/\s+/g, ' ').trim() || 'Section'));
    document.querySelectorAll('.section-h').forEach((h) => { h.textContent = label(h.dataset.full); });
    $('#section-sel').querySelectorAll('option').forEach((o, k) => {
      o.textContent = label(o.dataset.full) + ` (${L.sections[k].start + 1}-${L.sections[k].end + 1})`;
    });
    const map = { '#chars-btn': P.chars, '#pinyin-btn': P.pinyin, '#english-btn': P.english, '#zhonly-btn': P.zhOnly,
      '#loop-btn': P.loop, '#slow-btn': P.slow, '#autopause-btn': P.autoPause, '#autoadv-btn': P.autoAdv };
    Object.keys(map).forEach((sel) => $(sel).classList.toggle('on', !!map[sel]));
    applyRate();
    updateNow();
  }

  function setPref(k, v) {
    P[k] = v;
    store.set(k, v);
    syncToggles();
  }

  function wireLesson() {
    $('#play-btn').addEventListener('click', togglePlay);
    $('#prev-btn').addEventListener('click', () => step(-1));
    $('#next-btn').addEventListener('click', () => step(1));
    $('#replay-btn').addEventListener('click', () => playClip(S.active));
    $('#loop-btn').addEventListener('click', () => setPref('loop', !P.loop));
    $('#slow-btn').addEventListener('click', () => setPref('slow', !P.slow));
    $('#rec-btn').addEventListener('click', toggleRecord);
    $('#cmp-btn').addEventListener('click', compare);
    $('#autopause-btn').addEventListener('click', () => setPref('autoPause', !P.autoPause));
    $('#autoadv-btn').addEventListener('click', () => setPref('autoAdv', !P.autoAdv));
    $('#zhonly-btn').addEventListener('click', () => setPref('zhOnly', !P.zhOnly));
    $('#chars-btn').addEventListener('click', () => setPref('chars', !P.chars));
    $('#pinyin-btn').addEventListener('click', () => setPref('pinyin', !P.pinyin));
    $('#english-btn').addEventListener('click', () => setPref('english', !P.english));
    $('#section-btn').addEventListener('click', () => {
      const sec = L.sections[+$('#section-sel').value];
      if (sec) playSegment(sec.start, sec.end, 'range');
    });
    $('#range-btn').addEventListener('click', () => {
      if (S.range) playSegment(S.range[0], S.range[1], 'range');
    });
    $('#clear-sel-btn').addEventListener('click', () => {
      S.range = null;
      S.anchor = null;
      renderSel();
    });
    $('#complete-btn').addEventListener('click', setStatusManual);
    $('#more-btn').addEventListener('click', () => {
      const tb = document.querySelector('.toolbar');
      const open = tb.classList.toggle('more-open');
      $('#more-btn').setAttribute('aria-expanded', String(open));
    });
    $('#start-btn').addEventListener('click', () => playEpisodeFrom(0));

    const tr = $('#transcript');
    // shift-click selects a range; stop the browser from text-selecting over it
    tr.addEventListener('mousedown', (e) => { if (e.shiftKey) e.preventDefault(); });
    tr.addEventListener('click', (e) => {
      const card = e.target.closest('.chunk');
      if (!card) return;
      const i = +card.dataset.i;
      const chip = e.target.closest('.chip');
      if (chip) { e.stopPropagation(); openPop(i, +chip.dataset.w, chip); return; }
      if (e.target.closest('.play-card')) { playClip(i); return; }
      if (e.target.closest('.save-sent')) { toggleSave(i, 'sentence', 0); return; }
      if (e.target.closest('.save-both')) { saveBoth(i); return; }
      if (e.target.closest('button')) return;
      selectChunk(i, e.shiftKey);
    });
    document.addEventListener('click', (e) => {
      if (S.pop && !S.pop.contains(e.target) && !e.target.closest('.chip')) closePop();
    });

    full.addEventListener('timeupdate', onFullTime);
    full.addEventListener('ended', onFullEnded);
    clip.addEventListener('ended', onClipEnded);
    [full, clip].forEach((a) => {
      a.addEventListener('play', updatePlayBtn);
      a.addEventListener('pause', updatePlayBtn);
    });

    document.addEventListener('keydown', (e) => {
      if (!S || e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target;
      if (t && (/^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName) || t.isContentEditable)) return;
      const k = e.key;
      if (k === ' ') {
        e.preventDefault();
        if (t && t.tagName === 'BUTTON') t.blur();  // stop Space from also clicking the button
        togglePlay();
      } else if (k === 'ArrowLeft') { e.preventDefault(); step(-1); }
      else if (k === 'ArrowRight') { e.preventDefault(); step(1); }
      else if (k === 'Escape') closePop();
      else {
        switch (k.toLowerCase()) {
          case 'r': playClip(S.active); break;
          case 'l': setPref('loop', !P.loop); break;
          case 's': setPref('slow', !P.slow); break;
          case 'm': toggleRecord(); break;
          case '1': setPref('chars', !P.chars); break;
          case '2': setPref('pinyin', !P.pinyin); break;
          case '3': setPref('english', !P.english); break;
          case 'w': saveFocusedWord(); break;
          case 't': saveActiveSentence(); break;
        }
      }
    });

    wireBar();
    window.addEventListener('pagehide', flushProgress);
    document.addEventListener('visibilitychange', () => { if (document.hidden) flushProgress(); });
  }

  async function initLesson() {
    const n = parseInt(new URLSearchParams(location.search).get('n'), 10);
    if (!n) { $('#lesson-title').textContent = 'No lesson selected'; return; }
    try {
      L = await api('api/lesson/' + n);
    } catch (e) {
      $('#lesson-title').textContent = 'Lesson not available: ' + e.message;
      return;
    }
    S = {
      n, ready: false, active: 0, anchor: null, range: null, mode: 'idle',
      segFrom: 0, segTo: 0, clipIdx: -1, clipDone: null, focus: null, pop: null,
      status: L.progress.status, practiced: new Set(L.progress.practiced),
      saves: new Map(), els: [], recUrls: new Map(), recording: false, mr: null, stream: null,
      resumeTimer: null, pausedAuto: false, saveTimer: null,
    };
    L.saves.forEach((r) => S.saves.set(skey(r.chunk_id, r.kind, r.text), { id: r.id, kind: r.kind }));
    document.title = `Lesson ${n} - Mandarin Study`;
    $('#lesson-title').textContent = `Lesson ${n}: ${L.title}`;
    $('#crumb-now').textContent = `Lesson ${n}`;
    full.src = 'data/' + L.audio;
    $('#section-sel').innerHTML = L.sections.map((s, k) =>
      `<option value="${k}" data-full="${esc(s.label)}">${esc(s.label)} (${s.start + 1}-${s.end + 1})</option>`).join('');
    if (!L.sections.length) {
      $('#section-sel').disabled = true;
      $('#section-btn').disabled = true;
    }
    renderTranscript();
    const resume = cs().findIndex((c) => c.id === L.progress.last_chunk);
    setActive(resume >= 0 ? resume : 0, false);
    S.els[S.active].scrollIntoView({ block: 'center' });
    S.ready = true;
    syncCompleteBtn();
    refreshSaves();
    updateStats();
    updatePlayBtn();
    renderSel();
    syncToggles();
    $('#transcript-link').href = 'transcript.html?n=' + n;
    renderTicks();
    wireLesson();
    updateBar();
  }

  // ---------- boot ----------
  document.addEventListener('DOMContentLoaded', () => {
    Object.keys(P).forEach((k) => { P[k] = store.get(k, P[k]); });
    applyTheme();
    const tb = $('#theme-toggle');
    if (tb) tb.addEventListener('click', () => { toggleTheme(); });
    if ($('#lesson-root')) {
      initLesson().catch((e) => { $('#lesson-title').textContent = 'Error: ' + e.message; });
    } else if ($('#lesson-list')) {
      initIndex().catch((e) => { $('#overall-stats').textContent = 'Could not load lessons: ' + e.message; });
    }
  });
})();
