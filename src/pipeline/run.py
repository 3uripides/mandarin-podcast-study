"""Run the whole pipeline for one lesson: python -m src.pipeline.run --lesson 1

Idempotent: episode MP3, Whisper raw JSON, chunks.json and clip files are cached; lesson.json and index.json are rebuilt.
"""
import argparse
import json
import os

from . import clips, chunk, download, enrich, transcribe
from .paths import DATA, episode_mp3, lesson_dir


def main(n):
    path, info = download.run(n)
    print(f"[run] episode: {path}")

    # forced language=zh: gives Chinese characters for Mandarin and English for English (auto pass only gave romanised Mandarin)
    raw = transcribe.transcribe(path, n, language="zh", tag="zh")
    print(f"[run] whisper zh-pass duration={raw['duration']:.1f}s segments={len(raw['segments'])}")

    cpath = os.path.join(lesson_dir(n), "chunks.json")
    if os.path.exists(cpath):
        with open(cpath, encoding="utf-8") as f:
            chunks = json.load(f)
    else:
        chunks = chunk.run(n, raw)
    print(f"[run] chunks: {len(chunks)}")

    clips.run(n, chunks)
    print("[run] clips done")

    lesson = enrich.run(n, chunks, info["title"], raw["duration"])
    print(f"[run] wrote {os.path.join(lesson_dir(n), 'lesson.json')}")

    lessons = download.parse_feed()
    download.write_index(lessons)
    print("[run] index.json updated")
    return lesson


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", type=int, required=True)
    main(ap.parse_args().lesson)
