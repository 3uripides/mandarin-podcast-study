"""faster-whisper transcription with JSON cache (reruns are free)."""
import json
import os
import subprocess

import numpy as np

from .paths import ffmpeg, lesson_dir

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("small", device="cpu", compute_type="int8")
    return _model


def load_audio(mp3):
    """Decode to 16 kHz mono float32 with bundled ffmpeg (venv PyAV is too old for faster-whisper's decoder)."""
    out = subprocess.run(
        [ffmpeg(), "-v", "error", "-i", mp3, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(out, np.int16).astype(np.float32) / 32768.0


def transcribe(mp3, lesson_no, language=None, tag="auto"):
    """Return raw dict {duration, language, segments:[{start,end,text,words:[{start,end,word}]}]}.

    language=None -> Whisper auto-detect. Cached at data/lessons/NNN/raw_<tag>.json.
    """
    cache = os.path.join(lesson_dir(lesson_no), f"raw_{tag}.json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f)

    segs, info = _get_model().transcribe(
        load_audio(mp3),
        language=language,
        word_timestamps=True,
        vad_filter=True,
    )
    segments = []
    for s in segs:  # generator: consume fully
        segments.append({
            "start": s.start,
            "end": s.end,
            "text": s.text,
            "words": [{"start": w.start, "end": w.end, "word": w.word} for w in (s.words or [])],
        })
    raw = {"duration": info.duration, "language": info.language, "segments": segments}
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)
    return raw

