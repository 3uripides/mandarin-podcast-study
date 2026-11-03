"""Build an Anki .apkg from saved words/sentences (the `saves` table).

Library: export_apkg(items, out_path, data_dir, include_characters=False)
CLI:     python -m src.anki_export --db data/progress.db --data data --out out.apkg
         [--kind word|sentence] [--pos verb] [--lesson 1] [--characters]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile

import genanki

MASTER_DECK = "Mandarin Melnyks"
# Hard-coded so re-imports update the existing note types instead of creating new ones.
WORD_MODEL_ID = 1718400101
SENTENCE_MODEL_ID = 1718400102

# ponytail: one stylesheet for both note types, no per-type CSS.
CSS = """
.card { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 22px;
        text-align: center; color: #1d1d1f; background: #ffffff; }
.pinyin { color: #0b6e4f; font-size: 26px; margin: 6px 0; }
.english { font-size: 22px; }
.hanzi { font-size: 30px; font-family: "Microsoft YaHei", SimSun, serif; margin-top: 8px; }
.meta { font-size: 14px; color: #6b6b6b; text-transform: uppercase; letter-spacing: .05em; }
hr { border: 0; border-top: 1px solid #ccc; margin: 14px 0; }
@media (prefers-color-scheme: dark) {
  .card { color: #e6e6e6; background: #1e1f22; }
  .pinyin { color: #5fd4a8; }
  .meta { color: #9aa0a6; }
  hr { border-top-color: #444; }
}
.nightMode .card { color: #e6e6e6; background: #1e1f22; }
.nightMode .pinyin { color: #5fd4a8; }
.nightMode .meta { color: #9aa0a6; }
.nightMode hr { border-top-color: #444; }
"""

WORD_FIELDS = ["Chinese", "Pinyin", "English", "Audio", "Lesson", "POS", "ChineseStored"]
SENTENCE_FIELDS = ["Chinese", "Pinyin", "English", "Audio", "Lesson", "ChineseStored"]


def _templates(with_pos: bool) -> list[dict]:
    pos_html = "{{#POS}}<div class=meta>{{POS}}</div>{{/POS}}" if with_pos else ""
    listen_back = (
        "{{FrontSide}}<hr id=answer>"
        f"<div class=pinyin>{{{{Pinyin}}}}</div><div class=english>{{{{English}}}}</div>"
        f"{pos_html}"
        "{{#Chinese}}<div class=hanzi>{{Chinese}}</div>{{/Chinese}}"
    )
    speak_back = (
        "{{FrontSide}}<hr id=answer>{{Audio}}"
        "<div class=pinyin>{{Pinyin}}</div>"
        "{{#Chinese}}<div class=hanzi>{{Chinese}}</div>{{/Chinese}}"
    )
    return [
        # Listen: audio only on the front, meaning on the back.
        {"name": "Listen", "qfmt": "{{Audio}}", "afmt": listen_back},
        # Speak: English on the front, say it, then audio + pinyin on the back.
        {"name": "Speak", "qfmt": "{{English}}", "afmt": speak_back},
    ]


WORD_MODEL = genanki.Model(
    WORD_MODEL_ID, "Mandarin Word",
    fields=[{"name": f} for f in WORD_FIELDS],
    templates=_templates(with_pos=True), css=CSS, sort_field_index=2,
)
SENTENCE_MODEL = genanki.Model(
    SENTENCE_MODEL_ID, "Mandarin Sentence",
    fields=[{"name": f} for f in SENTENCE_FIELDS],
    templates=_templates(with_pos=False), css=CSS, sort_field_index=2,
)


def deck_id(name: str) -> int:
    """Stable deck id derived from the deck name."""
    return int(hashlib.sha1(name.encode("utf-8")).hexdigest()[:10], 16)


def lesson_deck_name(lesson: int) -> str:
    return f"{MASTER_DECK}::Lesson {int(lesson):03d}"


def _clip_path(clip, data_dir):
    if not clip:
        return None
    path = os.path.join(data_dir, clip)
    return path if os.path.isfile(path) else None


def export_apkg(items: list[dict], out_path: str, data_dir: str,
                include_characters: bool = False) -> int:
    """Write a .apkg with one note per item. Returns the number of notes written."""
    decks = {MASTER_DECK: genanki.Deck(deck_id(MASTER_DECK), MASTER_DECK)}
    media: dict[str, str] = {}  # unique media filename -> source path
    notes = 0

    seen: set = set()  # same word/sentence saved on several lines -> one card
    for item in items:
        kind = item["kind"]
        if kind not in ("word", "sentence"):
            raise ValueError(f"unknown kind: {kind!r}")
        key = (int(item["lesson"]), kind, item["text"])
        if key in seen:
            continue
        seen.add(key)
        lesson = int(item["lesson"])
        chunk = int(item["chunk_id"])
        text = item["text"] or ""
        pinyin = item.get("pinyin") or ""
        english = item.get("english") or ""
        pos = (item.get("pos") or "").strip()

        audio = ""
        src = _clip_path(item.get("clip"), data_dir)
        if src:
            name = f"mm_L{lesson:03d}_c{chunk:04d}_{kind}"
            if kind == "word":  # several words can share one chunk
                name += "_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]
            name += os.path.splitext(src)[1] or ".mp3"
            media.setdefault(name, src)
            audio = f"[sound:{name}]"

        lesson_field = f"{lesson:03d}"
        shown_chinese = text if include_characters else ""
        if kind == "word":
            fields = [shown_chinese, pinyin, english, audio, lesson_field, pos, text]
            model = WORD_MODEL
            tags = ["word"] + ([f"pos::{pos.replace(' ', '_')}"] if pos else [])
        else:
            fields = [shown_chinese, pinyin, english, audio, lesson_field, text]
            model = SENTENCE_MODEL
            tags = ["sentence"]
        tags.append(f"lesson::{lesson_field}")

        note = genanki.Note(
            model=model, fields=fields, tags=tags,
            guid=genanki.guid_for(lesson, chunk, kind, text),
        )
        lname = lesson_deck_name(lesson)
        if lname not in decks:
            decks[lname] = genanki.Deck(deck_id(lname), lname)
        decks[lname].add_note(note)
        notes += 1

    # genanki names media by basename, so copy each clip to its unique name first.
    with tempfile.TemporaryDirectory() as tmp:
        media_paths = []
        for name, src in media.items():
            dst = os.path.join(tmp, name)
            shutil.copyfile(src, dst)
            media_paths.append(dst)

        pkg = genanki.Package(list(decks.values()))
        pkg.media_files = media_paths
        out_dir = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(out_dir, exist_ok=True)
        pkg.write_to_file(out_path)

    return notes


def load_saves(db_path: str, kind=None, pos=None, lesson=None) -> list[dict]:
    """Read rows from the `saves` table, optionally filtered."""
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"progress db not found: {db_path}")
    clauses, params = [], []
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    if pos:
        clauses.append("pos = ?")
        params.append(pos)
    if lesson is not None:
        clauses.append("lesson = ?")
        params.append(int(lesson))
    sql = "SELECT lesson, chunk_id, kind, text, pinyin, english, pos, clip FROM saves"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY lesson, chunk_id, id"
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Export saved items to an Anki .apkg")
    p.add_argument("--db", default="data/progress.db")
    p.add_argument("--data", default="data")
    p.add_argument("--out", default="out.apkg")
    p.add_argument("--kind", choices=["word", "sentence"])
    p.add_argument("--pos")
    p.add_argument("--lesson", type=int)
    p.add_argument("--characters", action="store_true", help="show Chinese on card backs")
    a = p.parse_args(argv)

    items = load_saves(a.db, a.kind, a.pos, a.lesson)
    if not items:
        print("No saved items matched; writing an empty deck.", file=sys.stderr)
    n = export_apkg(items, a.out, a.data, include_characters=a.characters)
    print(f"Wrote {n} notes to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
