"""Smoke tests for src/server.py against the placeholder fixture. Run: python -m pytest tests/test_server.py"""
import os
import shutil
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.server import create_app  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "data")


@pytest.fixture
def client(tmp_path):
    data = tmp_path / "data"  # copy so progress.db never lands in the fixture
    shutil.copytree(FIXTURE, data)
    app = create_app(str(data))
    app.config["TESTING"] = True
    return app.test_client()


def test_index_and_static(client):
    assert client.get("/").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.get("/lesson.html").status_code == 200


def test_lessons_list_and_totals(client):
    r = client.get("/api/lessons").get_json()
    nums = [x["lesson"] for x in r["lessons"]]
    assert nums == [900, 901]
    assert r["lessons"][1]["processed"] is False
    assert r["totals"]["lessons"] == 2 and r["totals"]["processed"] == 1


def test_lesson_detail_and_404(client):
    r = client.get("/api/lesson/900").get_json()
    assert r["lesson"] == 900 and r["chunks"][1]["lang"] == "zh"
    assert r["progress"]["status"] == "not started"
    assert client.get("/api/lesson/901").status_code == 404


def test_progress_union_and_last_lesson(client):
    client.post("/api/progress", json={"lesson": 900, "practiced": [1, 3], "last_chunk": 3,
                                       "status": "in progress"})
    r = client.post("/api/progress", json={"lesson": 900, "practiced": [3, 4]}).get_json()
    assert r["practiced"] == [1, 3, 4] and r["status"] == "in progress"
    assert client.get("/api/lessons").get_json()["last_lesson"] == 900
    assert client.post("/api/progress", json={"lesson": 900, "status": "bogus"}).status_code == 400


def test_saves_roundtrip(client):
    row = {"lesson": 900, "chunk_id": 3, "kind": "word", "text": "我", "pinyin": "wǒ",
           "english": "I", "pos": "pron", "clip": None}
    a = client.post("/api/saves", json=row).get_json()
    b = client.post("/api/saves", json=row).get_json()  # duplicate is ignored
    assert a["id"] == b["id"]
    assert len(client.get("/api/saves?lesson=900").get_json()) == 1
    assert client.delete("/api/saves", json={"id": a["id"]}).get_json()["deleted"] == 1
    assert client.get("/api/saves").get_json() == []


def test_data_range_request(client):
    full = client.get("/data/episodes/lesson_900.mp3")
    assert full.status_code == 200
    part = client.get("/data/episodes/lesson_900.mp3", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.data) == 100


def test_export_filters_and_file(client):
    client.post("/api/saves", json={"lesson": 900, "chunk_id": 3, "kind": "sentence",
                                    "text": "我很好。", "pinyin": "Wǒ hěn hǎo.", "english": "I am fine.",
                                    "clip": "lessons/900/clips/0003.mp3"})
    assert client.get("/api/export.apkg?kind=word").status_code == 400  # nothing matches
    r = client.get("/api/export.apkg?kind=sentence&lesson=900")
    if r.status_code == 501:  # anki_export not written yet: contract says 501
        pytest.skip("src/anki_export.py not available")
    assert r.status_code == 200
    assert "attachment" in r.headers["Content-Disposition"]
    assert r.data[:2] == b"PK"  # .apkg is a zip


def test_export_bad_params_are_400(client):
    assert client.get("/api/export.apkg?lesson=abc").status_code == 400
    assert client.get("/api/export.apkg?kind=foo").status_code == 400
    assert client.get("/api/export.apkg?pos=zzz").status_code == 400
    r = client.get("/api/export.apkg?kind=sentence&pos=noun")
    assert r.status_code == 400 and "words only" in r.get_json()["error"]


def test_practiced_count_counts_only_mandarin(client):
    # fixture lesson 900: chunk 0 and 2 are English, 1/3/4 Mandarin
    client.post("/api/progress", json={"lesson": 900, "practiced": [0, 1, 2, 3]})
    row = [x for x in client.get("/api/lessons").get_json()["lessons"] if x["lesson"] == 900][0]
    assert row["practiced_count"] == 2
    assert client.get("/api/lessons").get_json()["totals"]["practiced"] == 2


def test_favicon_is_inline(client):
    html = client.get("/").get_data(as_text=True)
    assert 'rel="icon"' in html and "data:" in html
