# DECISIONS & CONTRACT

Project root: the repository root. Python: `.venv\Scripts\python.exe` (never system python). ffmpeg: `imageio_ffmpeg.get_ffmpeg_exe()`.
Sub-agents NEVER ask the user questions. Report to PM; log decisions here.

## User decisions (interview)
- Beginner, speaking-focused. Simplified characters; master toggle hides ALL Chinese characters (default: hidden; pinyin+English shown).
- Lesson 1 first (feed has ~100 lessons; Lesson 001 has 2 entries: "PDF Lesson Transcript (Read First)" and "Basic Greetings" - use the one with an MP3 of the real lesson). Scale to all later.
- Whisper `small`, CPU, int8. Translation: Argos Translate zh->en (local). Dark mode follows system + toggle.
- Playback freedom: play whole episode straight through w/ highlight; play a section / selected range; practice one sentence. Auto-pause-after-sentence and auto-advance are both toggles (default off).
- Layout: one scrolling transcript; Mandarin lines = clickable cards; English = plain text still playable; "Mandarin lines only" filter.
- Shortcuts: Space play/pause, R replay, L loop, S slow(0.75x), Left/Right prev/next, M record, 1/2/3 toggle Chinese/pinyin/English, W save word, T save sentence.
- Words: jieba-split, each clickable -> pinyin, meaning, POS, one-click save; separate save-sentence button; "both" possible.
- Anki: ONE master deck "Mandarin Melnyks" with subdeck per lesson ("Mandarin Melnyks::Lesson 001"), single .apkg. Two note types (Word, Sentence), each 2 card templates: (1) audio->meaning, (2) English->speak (back has audio+pinyin). Characters optional on back, off by default. Tags: `word`|`sentence`, `pos::noun` etc, `lesson::001`. Export subset filters: kind, pos, lesson.
- Progress in SQLite `data/progress.db`.
- Publishing: public GitHub repo under account `3uripides` (gh already logged in), name `mandarin-podcast-study`. GitHub Pages demo w/ placeholder content only. .gitignore: data/, .venv/, *.mp3, *.apkg, progress.db.

## Data contract (all agents obey)
```
data/episodes/lesson_001.mp3
data/lessons/001/lesson.json
data/lessons/001/clips/0000.mp3 ...   (sentence clips)
data/lessons/001/wordclips/<n>.mp3     (optional word clips; fall back to sentence clip)
data/lessons/index.json  -> [{"lesson":1,"title":"...","processed":true}, ... all feed lessons; processed false if not built]
```
lesson.json:
```
{"lesson":1,"title":str,"audio":"episodes/lesson_001.mp3" (relative to data/),"duration":float,
 "sections":[{"id":"s1","label":str,"start":chunk_idx,"end":chunk_idx}],   // heuristic
 "chunks":[{"id":0,"start":sec,"end":sec,"lang":"zh"|"en","text":str,
            "pinyin":str|"" (zh only),"english":str|"" (zh only, machine translation),
            "clip":"lessons/001/clips/0000.mp3" (relative to data/),
            "words":[{"text":str,"pinyin":str,"pos":"noun|verb|adj|adv|pron|num|measure|prep|conj|particle|other",
                      "english":str,"clip":str|null}]}]}   // words only for zh chunks
```
progress.db (owned by frontend/server): tables `progress(lesson INTEGER PRIMARY KEY,status TEXT,last_chunk INTEGER,practiced TEXT /*json list of chunk ids*/)`, `saves(id INTEGER PRIMARY KEY,lesson INT,chunk_id INT,kind TEXT /*word|sentence*/,text TEXT,pinyin TEXT,english TEXT,pos TEXT,clip TEXT, UNIQUE(lesson,chunk_id,kind,text))`.

Module owners:
- `src/pipeline/` (download.py, transcribe.py, chunk.py, clips.py, enrich.py, run.py `python -m src.pipeline.run --lesson 1`) - pipeline builder.
- `src/anki_export.py`: `export_apkg(items:list[dict], out_path:str, data_dir:str, include_characters:bool=False)`; items = rows of `saves`. - anki builder.
- `src/server.py` (Flask, `python -m src.server`, port 8765) + `src/web/` (index.html lesson list, lesson.html, app.js, style.css) - frontend builder. Endpoints: `GET /api/lessons`, `GET /api/lesson/<n>`, `/data/<path>` static (supports Range), `GET/POST /api/progress`, `GET/POST/DELETE /api/saves`, `GET /api/export.apkg?kind=&pos=&lesson=`.
- `demo/` = static GitHub Pages build with placeholder content (frontend builder, later).
- `tests/` - tester.

## Log
(append below: tool choices, agent upgrades, auto-decisions)
- Tooling: uv (user-level), Python 3.12 venv, imageio-ffmpeg for ffmpeg (no admin), Flask, Argos Translate, jieba (POS via jieba.posseg).
- [pipeline] Feed: only entries with an audio enclosure are used (Lesson 001 -> "Basic Greetings", MP3 https://www.melnyks.com/audio/L1.mp3). `title` = feed title minus "Lesson NNN. " and trailing period.
- [pipeline] Whisper ASR: the auto-language pass gave Mandarin as romanised pinyin with no Chinese characters, so every chunk would be "en". Lesson 1 uses a single forced `language="zh"` pass (cache `data/lessons/NNN/raw_zh.json`). It gives Chinese for Mandarin and clean English for the English explanation. No merge needed. Re-check per lesson if the English is garbled.
- [pipeline] venv PyAV (av) is too old for faster-whisper's file decoder (`metadata_errors` TypeError). Audio is decoded with the bundled ffmpeg to 16 kHz float32 and passed as an array.
- [pipeline] zhconv installed (uv) for Traditional->Simplified, applied per Whisper token so word timings stay aligned. Argos zh->en package installed (local; works offline after install).
- [pipeline] Chunk `lang`: "zh" if any CJK char is present, else "en". Mixed chunks are zh. Chunk `end` in sections is inclusive.
- [pipeline] Intermediate files: `data/lessons/NNN/chunks.json` (word timings), `raw_zh.json` (Whisper cache). Clip names are zero-padded: `clips/NNNN.mp3`, `wordclips/NNNN.mp3` (100 ms word pad, 150 ms chunk pad).
- [pipeline] English chunks have `pinyin:""`, `english:""`, `words:[]`. zh chunks get words from jieba posseg (punctuation skipped), with pinyin, POS (mapped from jieba flags), and per-word Argos English.
- [pipeline] Sections: heuristic. Break before an English chunk containing a keyword (vocabulary, repeat after, listen, dialogue, practice, review, summary), merge breaks closer than 3 chunks. Label = first 40 chars of that chunk.
- Frontend builder (server + UI + demo):
  - Server: `create_app(data_dir)`; default data dir = project `data/`. Extra table `meta(key,value)` stores `last_lesson` for the "Continue" link (beyond contract tables, nothing else changed).
  - `/api/export.apkg`: a `pos` filter implies words only (sentences have no POS). `characters=1` maps to include_characters. Empty match -> 400. Output written to `<data>/exports/`.
  - `/api/progress` POST: `practiced` is a union of ids; `status` replaces. Client marks a line practiced when its clip ends, loops, or the episode/section passes its end.
  - `/api/saves` POST uses INSERT OR IGNORE on the contract UNIQUE key; word saves store the word clip, falling back to the sentence clip.
  - UI semantics: "Save both" = sentence + all its words (unsaves all if all already saved). W and T only save (never unsave); buttons toggle. Auto-pause pauses at each sentence boundary; auto-advance = next clip in clip mode, and a 1.2s auto-resume after a pause in episode/section mode.
  - URLs in the UI are relative so the same files run on Flask and GitHub Pages. Demo = `python -m src.build_demo` (copies src/web, adds `src/demo_shim.js` as localStorage fake API, placeholder lesson with sine tones). Test fixture = `python tests/fixtures/make_fixture.py` (lesson 900, unprocessed 901).
  - .gitignore: added `!tests/fixtures/**/*.mp3` and `!demo/**/*.mp3` so the placeholder audio is committed (demo must be published with its clips).
- Anki builder (src/anki_export.py): text field = Chinese in both kinds. Chinese field filled only with include_characters; always stored in ChineseStored. Sentence note type has no POS field. Note GUID = genanki.guid_for(lesson, chunk, kind, text). Deck IDs = sha1(name). Model IDs 1718400101/1718400102. Word clip filenames get a 6-char text hash suffix (several words share a chunk). Missing clip -> empty Audio; Listen card then not generated (Anki skips empty fronts). Filters (kind/pos/lesson) live in load_saves(), used by CLI. Empty export writes a valid apkg with only the master deck.
- [pipeline v2] Word glosses: CC-CEDICT (https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz, CC BY-SA 4.0) downloaded once to data/cedict_ts.u8 (gitignored). Gloss = shortest of the first 3 usable glosses for the entry whose pinyin matches; Argos is the fallback. Attribution needed in README.
- [pipeline v2] POS: full jieba flag map. Idioms (flag l/i) take the head word, the last sub-word from search-mode split, or the final character. Result: 0% "other" on lesson 1.
- [pipeline v2] English-only tokens inside zh chunks are dropped from word lists (they are not study words). Chunk text keeps them.
- [pipeline v2] English fragments under 1.0s merge into an adjacent English chunk. Hallucinated repeats (3+ copies of a 1-2 char unit) collapse to 2 copies.
- [pipeline v2] Sections: new section at an English run lasting >= 12s that starts after a zh line (threshold lowered from 20s to get 4+ sections on lesson 1), or at keyword chunks. Labels: superseded by pipeline v3 (see below).
- [pipeline v2] zh chunk `english` = Argos translation of the Chinese characters only (English words stripped first). `pinyin` still covers the whole chunk text.
- PM: .claude/agents definitions are kept in the public repo (no secrets; useful to others). DECISIONS.md is kept as the project log; personal paths scrubbed.
- PM: English toggle (key 3) hides English TRANSLATIONS of Mandarin lines only; the teacher's English explanation stays visible (use "Mandarin lines only" to hide it).
- PM: Feed has 100 real lessons (104 was an early over-count including non-audio entries).
- [pipeline v3] Chunks split on . ? ! so each English chunk is one sentence. An English fragment under 1.0s with no terminal punctuation merges forward (else backward).
- [pipeline v3] lang: 'zh' only if CJK characters are at least 50% of letters (spaces and punctuation excluded). Otherwise 'en' with pinyin '' and english '' (teacher explanation).
- [pipeline v3] Whisper corrections map (chunk.py WHISPER_FIXES): 麻 -> 吗 when the chunk is a bare 麻 or mentions 'question particle'. Applied per token.
- [pipeline v3] WORD_POS_OVERRIDE (enrich.py): 谢谢/再见/不客气/对不起 -> verb, 你好 -> other, 好久 -> adv. Applied after jieba.
- [pipeline v3] Section labels (code is the truth): 'Section N - <first 5 English words> (m:ss)', or 'Section N - Mandarin practice (m:ss)' when the section has no English. Start time is the first chunk's start.
- [pipeline v3] clips: each clip folder has clips.sig (hash of the clip plan). A changed plan clears clips/ and wordclips/ before cutting.
- [pipeline v3] pytest moved from requirements.txt to requirements-dev.txt.
- PM (final): Pages demo deployed from the `gh-pages` branch (a subtree of `demo/`). To update: `python -m src.build_demo`, commit, then `git subtree split --prefix demo -b t && git push -f origin t:gh-pages`.
- PM (final): Anki export de-duplicates the same word/sentence saved on several lines (one card per lesson+kind+text). Popover height measured after Save label fill.
- Agents: all ran on Haiku; no Sonnet upgrades were needed (no agent failed the same task twice).
