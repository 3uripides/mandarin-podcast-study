"""Tests for src/pipeline/vocab.py (auto vocab.json). Run: python -m pytest tests/test_vocab.py"""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.pipeline import enrich, vocab  # noqa: E402

GLOSSED = {"学习", "你好", "谢谢"}  # stand-in for CC-CEDICT hits


@pytest.fixture(autouse=True)
def fake_cedict(monkeypatch):
    monkeypatch.setattr(enrich, "cedict_gloss", lambda w: "gloss" if w in GLOSSED else None)


def _w(text, pos="verb", clip="lessons/001/wordclips/x.mp3"):
    return {"text": text, "pinyin": "py", "english": "en", "pos": pos, "clip": clip}


def _lesson(root, n, chunks):
    d = root / "lessons" / f"{n:03d}"
    d.mkdir(parents=True)
    (d / "lesson.json").write_text(json.dumps({"lesson": n, "chunks": chunks}, ensure_ascii=False),
                                   encoding="utf-8")
    return d


CHUNKS = [
    {"id": 0, "lang": "en", "text": "Listen.", "english": "", "pinyin": "", "words": []},
    {"id": 1, "lang": "zh", "text": "你好", "pinyin": "nǐ hǎo", "english": "hello",
     "clip": "lessons/001/clips/0001.mp3",
     "words": [_w("你好", "other"), _w("的", "particle", None)]},
    {"id": 2, "lang": "zh", "text": "学习", "pinyin": "xuéxí", "english": "study",
     "clip": "lessons/001/clips/0002.mp3",
     "words": [_w("学习"), _w("的", "particle", None)]},
    {"id": 3, "lang": "zh", "text": "你好", "pinyin": "nǐ hǎo", "english": "hello",  # repeat
     "clip": "lessons/001/clips/0003.mp3", "words": [_w("你好", "other")]},
    {"id": 4, "lang": "zh", "text": "的", "pinyin": "de", "english": "of",  # 1 char: not a sentence
     "clip": "lessons/001/clips/0004.mp3", "words": [_w("的", "particle", None)]},
    {"id": 5, "lang": "zh", "text": "吗", "pinyin": "ma", "english": "",
     "clip": "lessons/001/clips/0005.mp3", "words": [_w("吗", "particle", None)]},
    {"id": 6, "lang": "zh", "text": "谢谢", "pinyin": "xièxie", "english": "thanks",
     "clip": "lessons/001/clips/0006.mp3", "words": [_w("谢谢", "verb", None)]},
]


def test_words_dedupe_drop_particles_and_prefer_cedict(tmp_path):
    _lesson(tmp_path, 1, CHUNKS)
    path = vocab.build_vocab(1, data_dir=str(tmp_path))
    d = json.load(open(path, encoding="utf-8"))
    assert d["generated_by"] == "auto" and d["lesson"] == 1
    texts = [w["text"] for w in d["words"]]
    # 的 is a frequent single-char particle -> dropped; 吗 appears once -> kept.
    assert "的" not in texts
    assert texts.count("你好") == 1 and texts.count("学习") == 1
    # CEDICT-glossed words first (学习, 你好, 谢谢 in first-appearance order), then the rest.
    assert texts == ["你好", "学习", "谢谢", "吗"]
    first = d["words"][0]
    assert first["chunk_id"] == 1 and first["clip"] == "lessons/001/wordclips/x.mp3"


def test_sentences_unique_and_min_length(tmp_path):
    _lesson(tmp_path, 1, CHUNKS)
    d = json.load(open(vocab.build_vocab(1, data_dir=str(tmp_path)), encoding="utf-8"))
    sents = [s["text"] for s in d["sentences"]]
    assert sents == ["你好", "学习", "谢谢"]  # 的 and 吗 are single chars; repeat 你好 dropped
    assert d["sentences"][0]["chunk_id"] == 1
    assert d["sentences"][0]["clip"] == "lessons/001/clips/0001.mp3"


def test_curated_file_is_never_overwritten(tmp_path):
    d = _lesson(tmp_path, 1, CHUNKS)
    curated = {"lesson": 1, "generated_by": "curated", "words": [], "sentences": []}
    (d / "vocab.json").write_text(json.dumps(curated), encoding="utf-8")
    assert vocab.build_vocab(1, data_dir=str(tmp_path)) is None
    assert json.loads((d / "vocab.json").read_text(encoding="utf-8")) == curated


def test_auto_file_is_regenerated(tmp_path):
    d = _lesson(tmp_path, 1, CHUNKS)
    (d / "vocab.json").write_text(json.dumps({"lesson": 1, "generated_by": "auto",
                                              "words": [], "sentences": []}), encoding="utf-8")
    path = vocab.build_vocab(1, data_dir=str(tmp_path))
    assert len(json.load(open(path, encoding="utf-8"))["words"]) == 4
