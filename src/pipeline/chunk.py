"""Split Whisper output into study chunks: Whisper segments, Chinese punctuation, pauses > 0.5s.

Output (data/lessons/NNN/chunks.json): [{"id","start","end","lang","text","words":[{"text","lead","start","end"}]}]
Text is normalised to Simplified Chinese with zhconv (per token, so word timings stay aligned).
"""
import json
import os
import re

import zhconv

from .paths import lesson_dir

CJK = re.compile(r"[\u4e00-\u9fff]")
ZH_PUNCT = "。！？，、"
PAUSE = 0.5
MIN_LEN = 0.4        # zh/any fragment below this is merged into a neighbour
EN_MIN_LEN = 1.0     # English fragments below this merge into an adjacent English chunk
# Whisper hallucinates runs like 谢谢谢谢: collapse runs of a 1-2 char unit (3+ copies) to 2 copies
REPEAT = re.compile(r"([\u4e00-\u9fff]{2}|[\u4e00-\u9fff])\1{2,}")


def simplify(s):
    return zhconv.convert(s, "zh-cn")


def _tokens(raw):
    """Flatten segments into word tokens (simplified, repeats collapsed) keeping segment index."""
    toks = []
    for si, seg in enumerate(raw["segments"]):
        words = seg["words"] or [{"start": seg["start"], "end": seg["end"], "word": seg["text"]}]
        for w in words:
            raw_t = simplify(w["word"])
            t = REPEAT.sub(lambda m: m.group(1) * 2, raw_t.strip())
            if not t:
                continue
            if toks and toks[-1]["text"] == t and len(t) <= 2 and CJK.search(t) and toks[-1]["seg"] == si:
                if sum(1 for x in toks[-2:] if x["text"] == t) >= 2:
                    continue  # third+ identical consecutive CJK token: drop
            toks.append({"text": t, "lead": raw_t[0].isspace(), "start": float(w["start"]),
                         "end": float(w["end"]), "seg": si})
    return toks


def _join(toks):
    """Join token texts; returns (text, owner) where owner[i] = token index of char i."""
    out, owner = "", []
    for k, t in enumerate(toks):
        ascii_join = out[-1:] and out[-1] in ".,!?;:" and t["text"][0].isascii() and t["text"][0].isalnum()
        if out and (t["lead"] and (out[-1].isascii() and out[-1].isalnum() or t["text"][0].isascii() and t["text"][0].isalnum()) or ascii_join):
            out += " "
            owner.append(k)
        out += t["text"]
        owner.extend([k] * len(t["text"]))
    return out, owner


WHISPER_FIXES = {"麻": "吗"}  # Whisper mishears the question particle 吗 as 麻 (hemp)
TERMINAL = ".?!。？！"


def _is_zh(text):
    """zh only when CJK characters make up at least half of the letters (not spaces or punctuation)."""
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(1 for c in letters if CJK.match(c)) / len(letters) >= 0.5


def _lang(g):
    return "zh" if _is_zh(_join(g)[0]) else "en"


def _dur(g):
    return g[-1]["end"] - g[0]["start"]


def _fix_group(g):
    """Known Whisper mishearings, applied per token (length-preserving, so timings stay aligned)."""
    text, _ = _join(g)
    hanzi = "".join(CJK.findall(text))
    if hanzi == "麻" or "question particle" in text.lower():
        for t in g:
            for bad, good in WHISPER_FIXES.items():
                t["text"] = t["text"].replace(bad, good)


def build_chunks(raw):
    toks = _tokens(raw)
    groups, cur = [], []
    for t in toks:
        if cur:
            prev = cur[-1]
            split = (
                t["seg"] != prev["seg"]
                or t["start"] - prev["end"] > PAUSE
                or prev["text"][-1] in ZH_PUNCT
                or prev["text"][-1] in TERMINAL  # one sentence per chunk
            )
            if split:
                groups.append(cur)
                cur = []
        cur.append(t)
    if cur:
        groups.append(cur)
    for g in groups:
        _fix_group(g)

    # merge fragments shorter than MIN_LEN into the previous group (or next, if first)
    merged = []
    for g in groups:
        if merged and _dur(g) < MIN_LEN:
            merged[-1] = merged[-1] + g
        else:
            merged.append(g)
    if len(merged) > 1 and _dur(merged[0]) < MIN_LEN:
        merged[1] = merged[0] + merged[1]
        merged.pop(0)

    # short English fragments without terminal punctuation merge forward (else backward) into English
    out, i = [], 0
    while i < len(merged):
        g = merged[i]
        unterminated = _join(g)[0][-1:] not in TERMINAL
        if _lang(g) == "en" and _dur(g) < EN_MIN_LEN and unterminated:
            if i + 1 < len(merged) and _lang(merged[i + 1]) == "en":
                merged[i + 1] = g + merged[i + 1]
                i += 1
                continue
            if out and _lang(out[-1]) == "en":
                out[-1] = out[-1] + g
                i += 1
                continue
        out.append(g)
        i += 1

    chunks = []
    for g in out:
        text, _ = _join(g)
        chunks.append({
            "id": len(chunks),
            "start": round(g[0]["start"], 3),
            "end": round(g[-1]["end"], 3),
            "lang": "zh" if _is_zh(text) else "en",
            "text": text,
            "words": [{"text": t["text"], "lead": t["lead"], "start": round(t["start"], 3),
                       "end": round(t["end"], 3)} for t in g],
        })
    return chunks


def split_words(chunk):
    """jieba.posseg split of a chunk, skipping punctuation/space.

    Returns [{"text","flag","start","end"}]; timings come from the Whisper tokens owning each char.
    """
    import jieba.posseg as pseg

    toks = chunk["words"]
    text, owner = _join(toks)
    out, pos = [], 0
    for w in pseg.cut(text):
        word, flag = w.word, w.flag
        i = text.find(word, pos)
        if i < 0:
            continue
        pos = i + len(word)
        if not CJK.search(word):  # English tokens inside zh chunks are not study words
            continue
        out.append({
            "text": word,
            "flag": flag,
            "start": toks[owner[i]]["start"],
            "end": toks[owner[pos - 1]]["end"],
        })
    return out


def run(n, raw):
    path = os.path.join(lesson_dir(n), "chunks.json")
    chunks = build_chunks(raw)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=1)
    return chunks


if __name__ == "__main__":
    # ponytail: self-check on a synthetic transcript
    raw = {"segments": [{"start": 0, "end": 3, "text": "", "words": [
        {"start": 0.0, "end": 0.5, "word": "你好"},
        {"start": 0.5, "end": 1.0, "word": "，"},
        {"start": 1.0, "end": 1.5, "word": "請"},
        {"start": 2.5, "end": 3.0, "word": "坐"},  # pause > 0.5s
        {"start": 3.0, "end": 3.5, "word": " hello"},
    ]}]}
    cs = build_chunks(raw)
    assert len(cs) == 3, cs
    assert cs[0]["text"] == "你好，" and cs[0]["lang"] == "zh"
    assert cs[1]["text"] == "请" and cs[1]["lang"] == "zh"  # 請 -> 请 simplified
    assert cs[2]["text"] == "坐 hello" and cs[2]["lang"] == "en"  # CJK is a minority -> en
    ws = split_words(cs[0])
    assert [w["text"] for w in ws] == ["你好"] and ws[0]["end"] == 0.5, ws
    assert _is_zh("好吧，Person a, saying 你好.") is False and _is_zh("你好，我") is True
    assert REPEAT.sub(lambda m: m.group(1) * 2, "谢谢谢谢") == "谢谢"
    print("chunk self-check ok")
