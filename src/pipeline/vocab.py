"""Auto vocab/flashcard set for one lesson: data/lessons/NNN/vocab.json.

Heuristic, built from lesson.json zh chunks. A vocab.json with generated_by == "curated"
is never overwritten (the PM curates those by hand).

CLI: python -m src.pipeline.vocab --lesson 1
"""
import argparse
import json
import os
from collections import Counter

from . import enrich
from .paths import DATA

FUNCTION_MIN_COUNT = 3  # single-char particles only dropped when at least this frequent


def _has_cedict(text):
    return enrich.cedict_gloss(text) is not None


def build_words(zh_chunks):
    counts = Counter(w["text"] for c in zh_chunks for w in c.get("words", []))
    seen = {}  # text -> (first index, entry)
    idx = 0
    for c in zh_chunks:
        for w in c.get("words", []):
            text = w["text"]
            idx += 1
            if text in seen or not text:
                continue
            if len(text) == 1 and w.get("pos") == "particle" and counts[text] >= FUNCTION_MIN_COUNT:
                continue
            clip = w.get("clip") or c.get("clip")  # fall back to the sentence clip
            seen[text] = (idx, {
                "text": text,
                "pinyin": w.get("pinyin", ""),
                "english": w.get("english", ""),
                "pos": w.get("pos", "other"),
                "chunk_id": c["id"],
                "clip": clip,
                "_cedict": _has_cedict(text),
            })
    # CC-CEDICT-glossed words first, each group in order of first appearance
    ordered = sorted(seen.values(), key=lambda t: (not t[1]["_cedict"], t[0]))
    out = []
    for _, e in ordered:
        e.pop("_cedict")
        out.append(e)
    return out


def build_sentences(zh_chunks):
    out, seen = [], set()
    for c in zh_chunks:
        text = c["text"]
        if len(text) < 2 or text in seen:
            continue
        seen.add(text)
        out.append({
            "text": text,
            "pinyin": c.get("pinyin", ""),
            "english": c.get("english", ""),
            "chunk_id": c["id"],
            "clip": c.get("clip"),
        })
    return out


def build_vocab(n, data_dir=DATA):
    """Write vocab.json for lesson n. Returns the path, or None when a curated file is kept."""
    d = os.path.join(data_dir, "lessons", f"{n:03d}")
    path = os.path.join(d, "vocab.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            if json.load(f).get("generated_by") == "curated":
                print(f"[vocab] kept curated {path}")
                return None
    with open(os.path.join(d, "lesson.json"), encoding="utf-8") as f:
        lesson = json.load(f)
    zh = [c for c in lesson["chunks"] if c.get("lang") == "zh"]
    vocab = {
        "lesson": n,
        "generated_by": "auto",
        "words": build_words(zh),
        "sentences": build_sentences(zh),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False, indent=1)
    print(f"[vocab] wrote {path}: {len(vocab['words'])} words, {len(vocab['sentences'])} sentences")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lesson", type=int, required=True)
    build_vocab(ap.parse_args().lesson)
