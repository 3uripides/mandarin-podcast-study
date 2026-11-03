"""Fetch the podcast feed, pick the real audio entry per lesson, download MP3s, write index.json."""
import json
import os
import re
import sys

import feedparser
import requests

from .paths import DATA, FEED_URL, episode_mp3, lesson_dir

TITLE_RE = re.compile(r"^Lesson (\d+)\.\s*(.*?)\.?\s*$")


def parse_feed():
    """Return {lesson_no: {"lesson", "title", "mp3"}} using only entries with an audio enclosure."""
    feed = feedparser.parse(FEED_URL)
    lessons = {}
    for e in feed.entries:
        m = TITLE_RE.match(e.get("title", "").strip())
        if not m:
            continue
        audio = [x for x in e.get("enclosures", []) if x.get("type", "").startswith("audio/")]
        if not audio:  # e.g. the "PDF Lesson Transcript" entry for lesson 1
            continue
        n = int(m.group(1))
        if n in lessons:  # keep first audio entry
            continue
        lessons[n] = {"lesson": n, "title": m.group(2), "mp3": audio[0]["href"]}
    return lessons


def download_lesson(info):
    """Download the lesson MP3 if missing. Returns local path."""
    path = episode_mp3(info["lesson"])
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with requests.get(info["mp3"], stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for block in r.iter_content(1 << 16):
                f.write(block)
    os.replace(tmp, path)
    return path


def write_index(lessons):
    """Write data/lessons/index.json listing all feed lessons. processed = lesson.json exists."""
    rows = []
    for n in sorted(lessons):
        info = lessons[n]
        processed = os.path.exists(os.path.join(lesson_dir(n), "lesson.json"))
        rows.append({"lesson": n, "title": info["title"], "processed": processed})
    os.makedirs(os.path.join(DATA, "lessons"), exist_ok=True)
    with open(os.path.join(DATA, "lessons", "index.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    return rows


def run(n):
    lessons = parse_feed()
    if n not in lessons:
        sys.exit(f"Lesson {n} not found with audio in feed")
    path = download_lesson(lessons[n])
    write_index(lessons)
    return path, lessons[n]


if __name__ == "__main__":
    print(run(int(sys.argv[1]) if len(sys.argv) > 1 else 1))
