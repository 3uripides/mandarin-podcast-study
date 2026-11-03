"""Add pinyin, POS, English (CC-CEDICT for words, Argos zh->en fallback) and heuristic sections;
write lesson.json per contract."""
import json
import os
import re
import urllib.request

from pypinyin import Style, pinyin

from .paths import DATA, lesson_dir

CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
CEDICT_PATH = os.path.join(DATA, "cedict_ts.u8")

# jieba.posseg flag -> contract POS. Exact flags first, then prefixes (order matters).
POS_EXACT = {
    "vn": "noun", "ud": "particle", "uz": "particle", "ug": "particle", "uv": "particle",
    "dg": "adv", "mq": "measure", "qv": "measure", "qt": "measure", "pba": "prep", "pbei": "prep",
    "rz": "pron", "rr": "pron", "ry": "pron", "rg": "pron", "rzs": "pron", "rzv": "pron",
    "ul": "particle", "uj": "particle", "ule": "particle", "uguo": "particle", "ugl": "particle",
    "uzhe": "particle", "usuo": "particle", "eng": "other",
}
POS_PREFIX = [
    ("nr", "noun"), ("ns", "noun"), ("nt", "noun"), ("nz", "noun"), ("ng", "noun"), ("n", "noun"),
    ("s", "noun"), ("f", "noun"), ("t", "noun"), ("j", "noun"),
    ("v", "verb"), ("an", "adj"), ("ag", "adj"), ("al", "adj"), ("a", "adj"), ("b", "adj"), ("z", "adj"),
    ("ad", "adv"), ("d", "adv"), ("r", "pron"), ("m", "num"), ("q", "measure"),
    ("p", "prep"), ("cc", "conj"), ("c", "conj"), ("u", "particle"), ("y", "particle"),
]
WORD_POS_OVERRIDE = {  # common words jieba gets wrong
    "谢谢": "verb", "你好": "other", "再见": "verb", "不客气": "verb", "对不起": "verb", "好久": "adv",
}
HEAD_FLAGS = ("l", "i")  # idioms: tag by the head (last) piece from jieba
KEYWORDS = ("vocabulary", "repeat after", "listen", "dialogue", "practice", "review", "summary")
PRACTICE_WORDS = ("practice", "repeat", "listen")
PUNCT_SPACE = re.compile(r"\s+([，。！？、,.!?])")
LATIN = re.compile(r"[A-Za-zÀ-ɏ]+(?:['’][A-Za-z]+)*")
CJK = re.compile(r"[一-鿿]")


def pos_of(word, flag):
    if flag in POS_EXACT:
        return POS_EXACT[flag]
    if flag in HEAD_FLAGS:  # idiom: tag by head word = last sub-word from search-mode split (你好 -> 好)
        import jieba
        import jieba.posseg as pseg
        subs = [p for p in jieba.lcut_for_search(word) if p != word and CJK.search(p)] or [word[-1]]
        if subs:
            sub = subs[-1]
            flags = [x.flag for x in pseg.cut(sub)]
            if flags and flags[-1] not in HEAD_FLAGS:
                return pos_of(sub, flags[-1])
        return "other"
    for pref, pos in POS_PREFIX:
        if flag.startswith(pref):
            return pos
    return "other"


def pinyin_of(text):
    parts = pinyin(text, style=Style.TONE, heteronym=False)
    return PUNCT_SPACE.sub(r"\1", " ".join(p[0] for p in parts)).strip()


# ---- CC-CEDICT word glosses ----
_cedict = None


def _load_cedict():
    """Load CC-CEDICT (downloaded once to data/, gitignored). Returns {simplified: [(pinyin, [glosses])]}."""
    global _cedict
    if _cedict is not None:
        return _cedict
    _cedict = {}
    try:
        if not os.path.exists(CEDICT_PATH):
            import gzip
            with urllib.request.urlopen(CEDICT_URL, timeout=120) as r:
                data = gzip.decompress(r.read())
            with open(CEDICT_PATH, "wb") as f:
                f.write(data)
        line_re = re.compile(r"^(\S+) (\S+) \[([^\]]+)\] /(.+)/$")
        with open(CEDICT_PATH, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                m = line_re.match(line.rstrip("\n"))
                if not m:
                    continue
                _, simp, py, gl = m.groups()
                _cedict.setdefault(simp, []).append((py.lower(), gl.split("/")))
    except Exception as e:
        print(f"[enrich] CC-CEDICT unavailable: {e}")
    return _cedict


SKIP_GLOSS = ("variant of", "old variant", "see ", "surname", "abbr.", "cl:", "also pr.", "taiwan pr.", "erhua")


def _norm_py(s):
    return re.sub(r"\s+", " ", s.lower().replace("u:", "v")).strip()


def cedict_gloss(word):
    """Shortest sensible gloss for the entry whose pinyin matches; None if not found."""
    entries = _load_cedict().get(word)
    if not entries:
        return None
    want = _norm_py(" ".join(p[0] for p in pinyin(word, style=Style.TONE3, neutral_tone_with_five=True)))
    exact = [e for e in entries if _norm_py(e[0]) == want]
    loose = [e for e in entries if re.sub(r"\d", "", _norm_py(e[0])) == re.sub(r"\d", "", want)]
    cands = exact or loose or entries[:1]
    glosses = []
    for _, gl in cands:
        for g in gl:
            g = g.strip()
            if g and not g.lower().startswith(SKIP_GLOSS):
                glosses.append(re.sub(r"\s*\([^)]*\)", "", g).strip())
    glosses = [g for g in glosses if g][:3]
    if not glosses:
        return None
    return min(glosses, key=len)


# ---- Argos zh->en (chunks, and word gloss fallback) ----
_argos_ready = False


def _ensure_argos():
    """Install Argos zh->en package once (downloads from the Argos index, then fully local)."""
    global _argos_ready
    if _argos_ready:
        return True
    try:
        import argostranslate.package as apkg
        import argostranslate.translate as atr
        langs = atr.get_installed_languages()
        if not any(l.code == "zh" for l in langs):
            apkg.update_package_index()
            pkg = next(p for p in apkg.get_available_packages() if p.from_code == "zh" and p.to_code == "en")
            apkg.install_from_path(pkg.download())
        _argos_ready = True
    except Exception as e:  # English stays empty on failure
        print(f"[enrich] Argos unavailable: {e}")
        _argos_ready = False
    return _argos_ready


def translate_zh(text):
    if not CJK.search(text or "") or not _ensure_argos():
        return ""
    try:
        import argostranslate.translate as atr
        return atr.translate(text, "zh", "en").strip()
    except Exception as e:
        print(f"[enrich] translate failed for {text!r}: {e}")
        return ""


def zh_portion(text):
    """Chunk text without its embedded English words (mixed chunks translate only the Chinese part)."""
    return re.sub(r"\s+", " ", LATIN.sub(" ", text)).strip()


# ---- sections ----
def sections_of(chunks):
    """Breaks: (a) an English run lasting >= 12s that starts after a zh line, (b) English chunks with a
    lesson keyword. Breaks closer than 3 chunks are dropped. Label: 'Practice N' or the run's first words."""
    n = len(chunks)
    runs = {}  # start idx -> end idx of each English run
    i = 0
    while i < n:
        if chunks[i]["lang"] == "en":
            j = i
            while j + 1 < n and chunks[j + 1]["lang"] == "en":
                j += 1
            runs[i] = j
            i = j + 1
        else:
            i += 1

    breaks = set()
    for s, e in runs.items():
        if s == 0:
            continue
        long_run = chunks[e]["end"] - chunks[s]["start"] >= 12
        kw = any(k in chunks[s]["text"].lower() for k in KEYWORDS)
        if long_run or kw:
            breaks.add(s)
    starts = [0]
    for s in sorted(breaks):
        if s - starts[-1] >= 3:
            starts.append(s)

    secs = []
    for k, s in enumerate(starts):
        e = (starts[k + 1] - 1) if k + 1 < len(starts) else n - 1
        span = chunks[s:e + 1]
        en_first = next((c for c in span if c["lang"] == "en"), None)
        words = re.findall(r"[A-Za-z][A-Za-z'’-]*", en_first["text"]) if en_first else []
        phrase = " ".join(words[:5]) if words else "Mandarin practice"  # never raw Chinese in labels
        m, sec = divmod(int(chunks[s]["start"]), 60)
        secs.append({"id": f"s{k + 1}", "label": f"Section {k + 1} - {phrase} ({m}:{sec:02d})",
                     "start": s, "end": e})
    return secs


def chunk_english(text):
    """Short zh chunks (<= 4 chars): CC-CEDICT whole-phrase gloss first; otherwise Argos on the Chinese part."""
    hanzi = "".join(CJK.findall(text))
    if 0 < len(hanzi) <= 4:
        gloss = cedict_gloss(hanzi)
        if gloss:
            return gloss
    return translate_zh(zh_portion(text))


def run(n, chunks, title, duration):
    out = []
    for c in chunks:
        zh = c["lang"] == "zh"
        words = []
        if zh:
            for w in c.get("zhwords", []):
                gloss = cedict_gloss(w["text"])
                words.append({
                    "text": w["text"],
                    "pinyin": pinyin_of(w["text"]),
                    "pos": WORD_POS_OVERRIDE.get(w["text"]) or pos_of(w["text"], w["flag"]),
                    "english": gloss if gloss else translate_zh(w["text"]).rstrip(" ."),
                    "clip": w.get("clip"),
                })
        out.append({
            "id": c["id"],
            "start": c["start"],
            "end": c["end"],
            "lang": c["lang"],
            "text": c["text"],
            "pinyin": pinyin_of(c["text"]) if zh else "",
            "english": chunk_english(c["text"]) if zh else "",
            "clip": c.get("clip"),
            "words": words,
        })
    lesson = {
        "lesson": n,
        "title": title,
        "audio": f"episodes/lesson_{n:03d}.mp3",
        "duration": float(duration),
        "sections": sections_of(out),
        "chunks": out,
    }
    path = os.path.join(lesson_dir(n), "lesson.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(lesson, f, ensure_ascii=False, indent=1)
    return lesson
