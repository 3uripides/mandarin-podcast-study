import json
import os
import sqlite3
import subprocess
import zipfile

import genanki
import imageio_ffmpeg
import pytest

from src.anki_export import (
    MASTER_DECK,
    export_apkg,
    lesson_deck_name,
    load_saves,
    main,
)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _make_mp3(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=0.2", str(path)],
        check=True,
    )


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    _make_mp3(d / "lessons/001/wordclips/0.mp3")
    _make_mp3(d / "lessons/001/clips/0004.mp3")
    return d


@pytest.fixture
def items():
    return [
        {"lesson": 1, "chunk_id": 4, "kind": "word", "text": "学习", "pinyin": "xuéxí",
         "english": "to study", "pos": "verb", "clip": "lessons/001/wordclips/0.mp3"},
        {"lesson": 1, "chunk_id": 4, "kind": "word", "text": "老师", "pinyin": "lǎoshī",
         "english": "teacher", "pos": "noun", "clip": None},
        {"lesson": 1, "chunk_id": 4, "kind": "sentence", "text": "你好", "pinyin": "nǐ hǎo",
         "english": "hello", "pos": None, "clip": "lessons/001/clips/0004.mp3"},
        {"lesson": 2, "chunk_id": 0, "kind": "sentence", "text": "谢谢", "pinyin": "xièxie",
         "english": "thanks", "pos": None, "clip": "lessons/002/clips/0000.mp3"},  # missing file
    ]


def _open(apkg, tmp_path):
    with zipfile.ZipFile(apkg) as z:
        names = z.namelist()
        assert "collection.anki2" in names and "media" in names
        z.extract("collection.anki2", tmp_path)
        media = json.loads(z.read("media"))
    con = sqlite3.connect(tmp_path / "collection.anki2")
    return con, media, names


def test_package_structure_and_media(tmp_path, data_dir, items):
    out = tmp_path / "out.apkg"
    assert export_apkg(items, str(out), str(data_dir)) == 4
    con, media, names = _open(out, tmp_path)
    con.close()
    assert "mm_L001_c0004_sentence.mp3" in media.values()
    assert any(v.startswith("mm_L001_c0004_word_") and v.endswith(".mp3") for v in media.values())
    assert len(media) == 2  # two clips exist; missing clips are skipped


def test_models_decks_tags_cards(tmp_path, data_dir, items):
    out = tmp_path / "out.apkg"
    export_apkg(items, str(out), str(data_dir))
    con, _, _ = _open(out, tmp_path)

    models_json, decks_json = con.execute("SELECT models, decks FROM col").fetchone()
    models = {m["name"]: m for m in json.loads(models_json).values()}
    assert set(models) == {"Mandarin Word", "Mandarin Sentence"}
    assert [t["name"] for t in models["Mandarin Word"]["tmpls"]] == ["Listen", "Speak"]
    assert [t["name"] for t in models["Mandarin Sentence"]["tmpls"]] == ["Listen", "Speak"]
    assert [f["name"] for f in models["Mandarin Word"]["flds"]][:6] == [
        "Chinese", "Pinyin", "English", "Audio", "Lesson", "POS"]

    decks = {d["name"] for d in json.loads(decks_json).values()}
    assert MASTER_DECK in decks
    assert lesson_deck_name(1) in decks and lesson_deck_name(2) in decks

    deck_names = {int(k): v["name"] for k, v in json.loads(decks_json).items()}
    cards = con.execute(
        "SELECT c.did, c.ord, n.tags FROM cards c JOIN notes n ON n.id = c.nid").fetchall()
    per_deck = {}
    for did, _, _ in cards:
        per_deck[deck_names[did]] = per_deck.get(deck_names[did], 0) + 1
    # 学习: Listen+Speak, 老师: Speak only (no audio), 你好: Listen+Speak, 谢谢: Speak only
    assert per_deck == {lesson_deck_name(1): 5, lesson_deck_name(2): 1}

    tags_all = " ".join(t for _, _, t in cards)
    assert " word " in tags_all and " sentence " in tags_all
    assert " pos::verb " in tags_all and " pos::noun " in tags_all
    assert " lesson::001 " in tags_all and " lesson::002 " in tags_all
    con.close()


def test_guid_stable_and_chinese_hidden(tmp_path, data_dir, items):
    out1, out2 = tmp_path / "a.apkg", tmp_path / "b.apkg"
    export_apkg(items, str(out1), str(data_dir))
    export_apkg(items, str(out2), str(data_dir), include_characters=True)

    def rows(path):
        scratch = tmp_path / path.stem
        scratch.mkdir()
        con, _, _ = _open(path, scratch)
        r = con.execute("SELECT guid, flds FROM notes ORDER BY guid").fetchall()
        con.close()
        return r

    r1, r2 = rows(out1), rows(out2)
    assert [g for g, _ in r1] == [g for g, _ in r2]  # same guids -> re-import updates
    expected = {genanki.guid_for(1, 4, "word", "学习"), genanki.guid_for(2, 0, "sentence", "谢谢")}
    assert expected <= {g for g, _ in r1}

    hidden = [f.split("\x1f") for _, f in r1]
    shown = [f.split("\x1f") for _, f in r2]
    assert all(f[0] == "" for f in hidden)            # Chinese hidden by default
    assert any(f[-1] == "学习" for f in hidden)       # ChineseStored keeps the text
    assert any(f[0] == "学习" for f in shown)         # shown when include_characters


def test_filters(tmp_path, data_dir, items):
    db = tmp_path / "progress.db"
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE saves(id INTEGER PRIMARY KEY, lesson INT, chunk_id INT,
                   kind TEXT, text TEXT, pinyin TEXT, english TEXT, pos TEXT, clip TEXT,
                   UNIQUE(lesson, chunk_id, kind, text))""")
    for it in items:
        con.execute("INSERT INTO saves(lesson, chunk_id, kind, text, pinyin, english, pos, clip)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (it["lesson"], it["chunk_id"], it["kind"], it["text"], it["pinyin"],
                     it["english"], it["pos"], it["clip"]))
    con.commit()
    con.close()

    assert len(load_saves(str(db))) == 4
    assert [r["text"] for r in load_saves(str(db), kind="word")] == ["学习", "老师"]
    assert [r["text"] for r in load_saves(str(db), pos="verb")] == ["学习"]
    assert [r["text"] for r in load_saves(str(db), lesson=2)] == ["谢谢"]
    assert load_saves(str(db), kind="word", lesson=2) == []

    out = tmp_path / "cli.apkg"
    assert main(["--db", str(db), "--data", str(data_dir), "--out", str(out),
                 "--kind", "word", "--pos", "verb", "--lesson", "1", "--characters"]) == 0
    con2, _, _ = _open(out, tmp_path / "cli")
    assert con2.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
    con2.close()


def test_empty_items_still_valid(tmp_path, data_dir):
    out = tmp_path / "empty.apkg"
    assert export_apkg([], str(out), str(data_dir)) == 0
    con, media, _ = _open(out, tmp_path)
    assert con.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    assert media == {}
    con.close()
