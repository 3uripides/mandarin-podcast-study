"""Server tests for auto vocab decks: /api/lesson/<n>/vocab and /api/export.apkg?auto=1.

Run: python -m pytest tests/test_vocab_server.py
"""
import json
import os
import shutil
import sys
import zipfile

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.server import create_app  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "data")
VOCAB_900 = {
    "lesson": 900, "generated_by": "auto",
    "words": [
        {"text": "你好", "pinyin": "nǐ hǎo", "english": "hello", "pos": "other",
         "chunk_id": 1, "clip": None},
        {"text": "学习", "pinyin": "xuéxí", "english": "to study", "pos": "verb",
         "chunk_id": 2, "clip": None},
    ],
    "sentences": [
        {"text": "你好", "pinyin": "nǐ hǎo", "english": "hello", "chunk_id": 1, "clip": None},
    ],
}


@pytest.fixture
def data(tmp_path):
    d = tmp_path / "data"
    shutil.copytree(FIXTURE, d)  # lesson 900 processed, 901 not
    (d / "lessons" / "900" / "vocab.json").write_text(json.dumps(VOCAB_900, ensure_ascii=False),
                                                      encoding="utf-8")
    return d


@pytest.fixture
def client(data):
    app = create_app(str(data))
    app.config["TESTING"] = True
    return app.test_client()


def _names(resp):
    import io
    with zipfile.ZipFile(io.BytesIO(resp.data)) as z:
        return z.namelist()


def test_vocab_endpoint(client):
    r = client.get("/api/lesson/900/vocab")
    assert r.status_code == 200
    assert [w["text"] for w in r.get_json()["words"]] == ["你好", "学习"]
    assert client.get("/api/lesson/901/vocab").status_code == 404


def test_auto_export_single_lesson_builds_from_vocab(client):
    r = client.get("/api/export.apkg?auto=1&lesson=900")
    assert r.status_code == 200
    assert "attachment" in r.headers["Content-Disposition"]
    assert "collection.anki2" in _names(r)


def test_auto_export_filters_and_errors(client):
    # pos filter is words-only; sentence kind + pos is rejected as before
    assert client.get("/api/export.apkg?auto=1&lesson=900&pos=verb").status_code == 200
    assert client.get("/api/export.apkg?auto=1&lesson=900&kind=sentence&pos=verb").status_code == 400
    assert client.get("/api/export.apkg?auto=1&lesson=901").status_code == 404  # no vocab
    assert client.get("/api/export.apkg?auto=1&lesson=900&pos=noun").status_code == 400


def test_auto_export_all_lessons_merges_vocab(client, data):
    # add a second lesson's vocab; lesson=all must include both
    d = data / "lessons" / "901"
    d.mkdir(parents=True, exist_ok=True)
    (d / "vocab.json").write_text(json.dumps({
        "lesson": 901, "generated_by": "auto",
        "words": [{"text": "谢谢", "pinyin": "xièxie", "english": "thanks", "pos": "verb",
                   "chunk_id": 3, "clip": None}],
        "sentences": []}, ensure_ascii=False), encoding="utf-8")
    seen = {}
    import src.anki_export as ae
    real = ae.export_apkg

    def spy(items, out_path, data_dir, include_characters=False):
        seen["items"] = items
        seen["chars"] = include_characters
        return real(items, out_path, data_dir, include_characters)

    ae.export_apkg = spy
    try:
        r = client.get("/api/export.apkg?auto=1&lesson=all&characters=1")
    finally:
        ae.export_apkg = real
    assert r.status_code == 200
    texts = sorted(i["text"] for i in seen["items"])
    assert texts == ["你好", "你好", "学习", "谢谢"]  # sentence 你好 + word 你好 + 学习 + 谢谢
    assert {i["lesson"] for i in seen["items"]} == {900, 901}
    assert seen["chars"] is True


def test_manual_saves_export_still_works(client):
    client.post("/api/saves", json={"lesson": 900, "chunk_id": 5, "kind": "word",
                                    "text": "再见", "pinyin": "zàijiàn", "english": "bye",
                                    "pos": "other", "clip": None})
    r = client.get("/api/export.apkg?lesson=900")
    assert r.status_code == 200
    assert "collection.anki2" in _names(r)
    # auto=0 is the manual path; with no saves for lesson 901 it stays a 400
    assert client.get("/api/export.apkg?lesson=901").status_code == 400
