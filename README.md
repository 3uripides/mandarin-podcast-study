# Mandarin Podcast Study Tool

A free, local, open-source tool that turns a Mandarin podcast RSS feed into a sentence-by-sentence
listen-and-repeat study site: transcripts, pinyin, local machine translation, loop / slow-down /
record-and-compare, and Anki flashcard export. Built for speaking practice (Chinese characters can be hidden).

**Demo (placeholder content only):** https://3uripides.github.io/mandarin-podcast-study/

## Copyright - read this
This repo contains **no podcast audio, clips or transcripts**. You point the tool at the public RSS feed
of a podcast (default: Melnyks Chinese, `https://www.melnyks.com/feed/podcast/`) and it builds a
**private, local** library on your own computer for personal study. `data/` is git-ignored: never publish
what it generates. Only download from feeds you are entitled to use; never rip copy-protected audio.

## Setup (Windows / macOS / Linux, CPU is fine, no accounts or paid APIs)
```
pip install uv            # or: https://docs.astral.sh/uv/
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt   # on macOS/Linux: .venv/bin/python
```
ffmpeg is bundled via `imageio-ffmpeg` (no system install needed).

## Build a lesson, then study
```
.venv\Scripts\python.exe -m src.pipeline.run --lesson 1     # download, transcribe (Whisper small), clip, pinyin, translate
.venv\Scripts\python.exe -m src.server                       # open http://127.0.0.1:8765
```
First run downloads the Whisper `small` model and the Argos zh->en package, and a CC-CEDICT dictionary.
Transcribing on CPU takes a while per lesson; results are cached. Run other lessons with `--lesson N`.

## Using the study page
- Lesson list with progress (not started / in progress / completed), practiced sentences, saved words, "continue where you left off".
- Transcript: Mandarin lines are clickable cards; English explanation is plain text (playable). "Mandarin lines only" filter.
- Play the whole episode with highlighting, a section, a selected range (click, shift-click), or one sentence.
- Loop, slow 0.75x, auto-pause after sentence, auto-advance (both off by default), record yourself and compare.
- Toggles: Chinese characters (hidden by default), pinyin, English. Dark mode follows your system.
- Click any word for pinyin / meaning / part of speech and save it. Save word, sentence, or both.

Shortcuts: Space play/pause, R replay, L loop, S slow, Left/Right prev/next, M record, 1/2/3 toggle characters/pinyin/English, W save word, T save sentence.

## Anki export
Free Anki (https://apps.ankiweb.net) imports the `.apkg`. One master deck `Mandarin Melnyks` with a subdeck per lesson,
note types *Mandarin Word* and *Mandarin Sentence*, each with a Listen card (audio -> meaning) and a Speak card (English -> say it).
Tags: `word`/`sentence`, `pos::verb` etc., `lesson::001`. Export everything saved or a subset (kind / part of speech / lesson)
from the lesson list page, or via CLI: `python -m src.anki_export --db data/progress.db --data data --out out.apkg --kind word --pos verb`.

## Known limits
Whisper `small` misses some Mandarin words (use a bigger model for better accuracy); machine translations of short phrases can be rough;
sections are a best-effort heuristic. Recording needs microphone permission in the browser.

## Credits / licenses
faster-whisper, pypinyin, jieba, genanki, Argos Translate, Flask (open source). Word glosses from
[CC-CEDICT](https://cc-cedict.org) (CC BY-SA 4.0). Code: MIT.
