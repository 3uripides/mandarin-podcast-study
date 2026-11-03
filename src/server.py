"""Flask server for the study UI. Data contract: DECISIONS.md.

Run:  .venv\\Scripts\\python.exe -m src.server [--data DIR]
"""
import argparse
import json
import os
import re
import sqlite3
from datetime import datetime

from flask import Flask, g, jsonify, request, send_file, send_from_directory

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
DEFAULT_DATA = os.path.join(ROOT, "data")
STATUSES = {"not started", "in progress", "completed"}
POS_TAGS = {"noun", "verb", "adj", "adv", "pron", "num", "measure", "prep", "conj", "particle", "other"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS progress(lesson INTEGER PRIMARY KEY, status TEXT,
    last_chunk INTEGER, practiced TEXT);
CREATE TABLE IF NOT EXISTS saves(id INTEGER PRIMARY KEY, lesson INT, chunk_id INT,
    kind TEXT, text TEXT, pinyin TEXT, english TEXT, pos TEXT, clip TEXT,
    UNIQUE(lesson, chunk_id, kind, text));
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""
# ponytail: meta table holds only last_lesson; added beyond the contract for "Continue".


def create_app(data_dir=DEFAULT_DATA):
    data_dir = os.path.abspath(data_dir)
    db_path = os.path.join(data_dir, "progress.db")
    os.makedirs(data_dir, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.executescript(SCHEMA)

    app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")
    app.config["DATA_DIR"] = data_dir

    def db():
        if "db" not in g:
            g.db = sqlite3.connect(db_path, timeout=10)
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def _close(_exc):
        con = g.pop("db", None)
        if con is not None:
            con.close()

    def read_index():
        p = os.path.join(data_dir, "lessons", "index.json")
        if not os.path.isfile(p):
            return []
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def lesson_json_path(n):
        return os.path.join(data_dir, "lessons", f"{n:03d}", "lesson.json")

    def progress_row(lesson):
        r = db().execute("SELECT * FROM progress WHERE lesson=?", (lesson,)).fetchone()
        if r is None:
            return {"lesson": lesson, "status": "not started", "last_chunk": 0, "practiced": []}
        return {"lesson": lesson, "status": r["status"] or "not started",
                "last_chunk": r["last_chunk"] or 0,
                "practiced": json.loads(r["practiced"] or "[]")}

    def saves_for(lesson=None):
        if lesson is None:
            return [dict(r) for r in db().execute("SELECT * FROM saves ORDER BY id")]
        return [dict(r) for r in db().execute(
            "SELECT * FROM saves WHERE lesson=? ORDER BY id", (lesson,))]

    def error(msg, code=400):
        return jsonify({"error": msg}), code

    @app.errorhandler(ValueError)
    @app.errorhandler(TypeError)
    @app.errorhandler(KeyError)
    def _bad_input(exc):  # any malformed query/body value -> 400 JSON, never 500
        return error("bad parameter: %s" % exc)

    def zh_ids(n):
        p = lesson_json_path(n)
        if not os.path.isfile(p):
            return None
        with open(p, encoding="utf-8") as f:
            return {c["id"] for c in json.load(f)["chunks"] if c.get("lang") == "zh"}

    def practiced_zh_count(n, practiced):
        # only Mandarin lines count as practiced
        zh = zh_ids(n)
        return len(set(practiced) & zh) if zh is not None else len(practiced)

    # ---- pages and data -------------------------------------------------
    @app.get("/")
    def index_page():
        return send_from_directory(WEB_DIR, "index.html")

    @app.get("/data/<path:relpath>")
    def data_file(relpath):
        # conditional=True gives ETag/Last-Modified and HTTP Range (audio seeking).
        return send_from_directory(data_dir, relpath, conditional=True)

    # ---- lessons --------------------------------------------------------
    @app.get("/api/lessons")
    def api_lessons():
        counts = {}
        for r in db().execute(
                "SELECT lesson, kind, COUNT(*) AS n FROM saves GROUP BY lesson, kind"):
            counts.setdefault(r["lesson"], {})[r["kind"]] = r["n"]
        prog = {r["lesson"]: r for r in db().execute("SELECT * FROM progress")}
        lessons = []
        for e in read_index():
            n = int(e["lesson"])
            pr = prog.get(n)
            c = counts.get(n, {})
            lessons.append({
                "lesson": n,
                "title": e.get("title", ""),
                "processed": bool(e.get("processed")),
                "status": (pr["status"] if pr else None) or "not started",
                "last_chunk": (pr["last_chunk"] if pr else 0) or 0,
                "practiced_count": practiced_zh_count(n, json.loads(pr["practiced"] or "[]")) if pr else 0,
                "saved_words": c.get("word", 0),
                "saved_sentences": c.get("sentence", 0),
            })
        last = db().execute("SELECT value FROM meta WHERE key='last_lesson'").fetchone()
        totals = {
            "lessons": len(lessons),
            "processed": sum(1 for x in lessons if x["processed"]),
            "completed": sum(1 for x in lessons if x["status"] == "completed"),
            "practiced": sum(x["practiced_count"] for x in lessons),
            "saved_words": sum(x["saved_words"] for x in lessons),
            "saved_sentences": sum(x["saved_sentences"] for x in lessons),
        }
        return jsonify({"lessons": lessons, "totals": totals,
                        "last_lesson": int(last["value"]) if last else None})

    @app.get("/api/lesson/<int:n>")
    def api_lesson(n):
        p = lesson_json_path(n)
        if not os.path.isfile(p):
            return error("lesson not processed yet", 404)
        with open(p, encoding="utf-8") as f:
            lesson = json.load(f)
        lesson["progress"] = progress_row(n)
        lesson["saves"] = saves_for(n)
        return jsonify(lesson)

    # ---- progress -------------------------------------------------------
    @app.get("/api/progress")
    def api_progress_get():
        lesson = request.args.get("lesson", type=int)
        if lesson is not None:
            return jsonify(progress_row(lesson))
        rows = db().execute("SELECT lesson FROM progress ORDER BY lesson").fetchall()
        return jsonify([progress_row(r["lesson"]) for r in rows])

    @app.post("/api/progress")
    def api_progress_post():
        body = request.get_json(silent=True) or {}
        if "lesson" not in body:
            return error("lesson required")
        n = int(body["lesson"])
        cur = progress_row(n)
        status = body.get("status", cur["status"])
        if status not in STATUSES:
            return error("bad status")
        last_chunk = int(body.get("last_chunk", cur["last_chunk"]))
        # practiced is a union: the client sends chunk ids it has practiced.
        practiced = sorted(set(cur["practiced"]) | {int(x) for x in body.get("practiced", [])})
        db().execute(
            "INSERT INTO progress(lesson,status,last_chunk,practiced) VALUES(?,?,?,?) "
            "ON CONFLICT(lesson) DO UPDATE SET status=excluded.status, "
            "last_chunk=excluded.last_chunk, practiced=excluded.practiced",
            (n, status, last_chunk, json.dumps(practiced)))
        db().execute("INSERT INTO meta(key,value) VALUES('last_lesson',?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(n),))
        db().commit()
        return jsonify(progress_row(n))

    # ---- saves ----------------------------------------------------------
    @app.get("/api/saves")
    def api_saves_get():
        lesson = request.args.get("lesson", type=int)
        return jsonify(saves_for(lesson))

    @app.post("/api/saves")
    def api_saves_post():
        b = request.get_json(silent=True) or {}
        kind = b.get("kind")
        if kind not in ("word", "sentence") or not b.get("text") or "lesson" not in b:
            return error("lesson, kind (word|sentence) and text required")
        vals = (int(b["lesson"]), int(b.get("chunk_id") or 0), kind, b["text"],
                b.get("pinyin", ""), b.get("english", ""), b.get("pos", "") or "",
                b.get("clip"))
        db().execute("INSERT OR IGNORE INTO saves(lesson,chunk_id,kind,text,pinyin,english,pos,clip) "
                     "VALUES(?,?,?,?,?,?,?,?)", vals)
        db().commit()
        row = db().execute("SELECT * FROM saves WHERE lesson=? AND chunk_id=? AND kind=? AND text=?",
                           vals[:4]).fetchone()
        return jsonify(dict(row))

    @app.delete("/api/saves")
    def api_saves_delete():
        b = {**request.args.to_dict(), **(request.get_json(silent=True) or {})}
        if b.get("id") not in (None, ""):
            cur = db().execute("DELETE FROM saves WHERE id=?", (int(b["id"]),))
        elif {"lesson", "chunk_id", "kind", "text"} <= b.keys():
            cur = db().execute("DELETE FROM saves WHERE lesson=? AND chunk_id=? AND kind=? AND text=?",
                               (int(b["lesson"]), int(b["chunk_id"]), b["kind"], b["text"]))
        else:
            return error("id, or lesson+chunk_id+kind+text, required")
        db().commit()
        return jsonify({"deleted": cur.rowcount})

    # ---- Anki export ----------------------------------------------------
    @app.get("/api/export.apkg")
    def api_export():
        kind = request.args.get("kind", "all")
        pos = request.args.get("pos", "")
        lesson = request.args.get("lesson", "")
        characters = request.args.get("characters", "") in ("1", "true", "yes", "on")
        if kind not in ("all", "word", "sentence"):
            return error("kind must be word|sentence|all")
        if pos and pos not in POS_TAGS:
            return error("unknown pos: " + pos)
        if pos and kind == "sentence":
            return error("pos filter applies to words only; use kind=word or kind=all")
        lesson_no = None
        if lesson not in ("", "all"):
            try:
                lesson_no = int(lesson)
            except ValueError:
                return error("lesson must be an integer or all")
        where, params = [], []
        if pos:  # POS exists only on words, so this is words-only
            where.append("kind='word' AND pos=?")
            params.append(pos)
        elif kind != "all":
            where.append("kind=?")
            params.append(kind)
        if lesson_no is not None:
            where.append("lesson=?")
            params.append(lesson_no)
        sql = "SELECT * FROM saves" + (" WHERE " + " AND ".join(where) if where else "")
        items = [dict(r) for r in db().execute(sql + " ORDER BY lesson, chunk_id, id", params)]
        if not items:
            return error("no saves match these filters")
        try:
            from src import anki_export  # lazy: built by the Anki agent
            export_apkg = anki_export.export_apkg
        except (ImportError, AttributeError):
            return error("Anki export module not available yet", 501)
        out_dir = os.path.join(data_dir, "exports")
        os.makedirs(out_dir, exist_ok=True)
        name = "mandarin-{}-{}-{}.apkg".format(
            re.sub(r"\W+", "", pos or kind) or "all",
            lesson if lesson and lesson != "all" else "all",
            datetime.now().strftime("%Y%m%d-%H%M%S"))
        out_path = os.path.join(out_dir, name)
        export_apkg(items, out_path, data_dir, include_characters=characters)
        return send_file(out_path, as_attachment=True, download_name=name,
                         mimetype="application/octet-stream")

    return app


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mandarin study server")
    ap.add_argument("--data", default=DEFAULT_DATA, help="data dir (default: ./data)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)
    app = create_app(args.data)
    print(f"Serving {app.config['DATA_DIR']} at http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
