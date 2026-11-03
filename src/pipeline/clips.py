"""ffmpeg clips: one per chunk (150ms padding) plus one per zh word (100ms padding, fallback null)."""
import hashlib
import json
import os
import shutil
import subprocess

from .chunk import split_words
from .paths import DATA, ffmpeg, episode_mp3, lesson_dir

CHUNK_PAD = 0.15
WORD_PAD = 0.10


def _cut(src, start, end, out):
    if os.path.exists(out):
        return True
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cmd = [ffmpeg(), "-v", "error", "-y", "-i", src,
           "-ss", f"{max(0.0, start):.3f}", "-to", f"{end:.3f}",
           "-vn", "-codec:a", "libmp3lame", "-q:a", "4", out]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not os.path.exists(out):
        return False
    return True


def run(n, chunks):
    """Mutates chunks: adds "clip" (relative to data/) and "zhwords" (with "clip" per word).

    Clip files are keyed by a plan signature (every clip's name, start and end). When the chunks change,
    the signature changes and all clip folders are cleared before cutting.
    """
    src = episode_mp3(n)
    ld = lesson_dir(n)
    plan = []  # (rel, start, end) for every clip this lesson needs
    for c in chunks:
        c["clip"] = f"lessons/{n:03d}/clips/{c['id']:04d}.mp3"
        plan.append((c["clip"], c["start"] - CHUNK_PAD, c["end"] + CHUNK_PAD))
    wn = 0
    for c in chunks:
        c["zhwords"] = []
        if c["lang"] != "zh":
            continue
        for w in split_words(c):
            rel = f"lessons/{n:03d}/wordclips/{wn:04d}.mp3"
            w["clip"] = rel
            plan.append((rel, w["start"] - WORD_PAD, w["end"] + WORD_PAD))
            wn += 1
            c["zhwords"].append(w)
    sig = hashlib.sha1(json.dumps(plan).encode("utf-8")).hexdigest()
    sigpath = os.path.join(ld, "clips.sig")
    if not (os.path.exists(sigpath) and open(sigpath).read() == sig):
        for sub in ("clips", "wordclips"):
            shutil.rmtree(os.path.join(ld, sub), ignore_errors=True)
        os.makedirs(ld, exist_ok=True)
        with open(sigpath, "w") as f:
            f.write(sig)
    for rel, st, en in plan:
        if not _cut(src, st, en, os.path.join(DATA, rel)):
            print(f"[clips] failed: {rel}")
    for c in chunks:
        for w in c["zhwords"]:
            w["clip"] = w["clip"] if os.path.exists(os.path.join(DATA, w["clip"])) else None
    return chunks
