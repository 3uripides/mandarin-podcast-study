"""Build the GitHub Pages demo and the placeholder test fixture.

Placeholder content only (invented sentences, sine-tone audio). Never real lesson content.
Run: .venv\\Scripts\\python.exe -m src.build_demo
"""
import json
import os
import shutil
import subprocess

from src.pipeline.paths import ffmpeg  # imageio_ffmpeg exe

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB = os.path.join(ROOT, "src", "web")
DEMO = os.path.join(ROOT, "demo")

# Invented placeholder lesson. Not from any real podcast.
CHUNKS = [
    {"lang": "en", "text": "Listen to the first placeholder sentence."},
    {"lang": "zh", "text": "你好。", "pinyin": "Nǐ hǎo.", "english": "Hello.",
     "words": [{"text": "你好", "pinyin": "nǐ hǎo", "pos": "other", "english": "hello"}]},
    {"lang": "en", "text": "Now a sentence about feeling."},
    {"lang": "zh", "text": "我很好。", "pinyin": "Wǒ hěn hǎo.", "english": "I am fine.",
     "words": [{"text": "我", "pinyin": "wǒ", "pos": "pron", "english": "I"},
               {"text": "很", "pinyin": "hěn", "pos": "adv", "english": "very"},
               {"text": "好", "pinyin": "hǎo", "pos": "adj", "english": "good"}]},
    {"lang": "zh", "text": "谢谢你。", "pinyin": "Xièxie nǐ.", "english": "Thank you.",
     "words": [{"text": "谢谢", "pinyin": "xièxie", "pos": "verb", "english": "to thank"},
               {"text": "你", "pinyin": "nǐ", "pos": "pron", "english": "you"}]},
]
SECTIONS = [
    {"id": "s1", "label": "Greetings", "start": 0, "end": 1},
    {"id": "s2", "label": "Feelings and thanks", "start": 2, "end": 4},
]


def _tone(path, freq, dur):
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"sine=frequency={freq}:duration={dur}", "-ac", "1", "-ar", "22050",
                    "-b:a", "32k", path], check=True)


def write_index(data_dir, entries):
    os.makedirs(os.path.join(data_dir, "lessons"), exist_ok=True)
    with open(os.path.join(data_dir, "lessons", "index.json"), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)


def write_tone_lesson(data_dir, lesson_no, title, chunks, sections, dur=1.5):
    """Write lesson.json, sentence clips and an episode file made of sine tones."""
    tag = f"{lesson_no:03d}"
    ldir = os.path.join(data_dir, "lessons", tag)
    os.makedirs(os.path.join(ldir, "clips"), exist_ok=True)
    os.makedirs(os.path.join(data_dir, "episodes"), exist_ok=True)
    out_chunks, tones, t = [], [], 0.0
    for i, c in enumerate(chunks):
        clip = os.path.join(ldir, "clips", f"{i:04d}.mp3")
        _tone(clip, 330 + 40 * (i % 8), dur)
        tones.append(clip)
        out_chunks.append({
            "id": i, "start": round(t, 3), "end": round(t + dur, 3), "lang": c["lang"],
            "text": c["text"], "pinyin": c.get("pinyin", ""), "english": c.get("english", ""),
            "clip": f"lessons/{tag}/clips/{i:04d}.mp3",
            "words": [{"text": w["text"], "pinyin": w["pinyin"], "pos": w["pos"],
                       "english": w["english"], "clip": None} for w in c.get("words", [])],
        })
        t += dur
    episode = os.path.join(data_dir, "episodes", f"lesson_{tag}.mp3")
    cmd = [ffmpeg(), "-y", "-loglevel", "error"]
    for p in tones:
        cmd += ["-i", p]
    cmd += ["-filter_complex", f"concat=n={len(tones)}:v=0:a=1", "-b:a", "32k", episode]
    subprocess.run(cmd, check=True)
    lesson = {"lesson": lesson_no, "title": title, "audio": f"episodes/lesson_{tag}.mp3",
              "duration": round(t, 3), "sections": sections, "chunks": out_chunks}
    with open(os.path.join(ldir, "lesson.json"), "w", encoding="utf-8") as f:
        json.dump(lesson, f, ensure_ascii=False, indent=1)
    return lesson


def build_demo():
    os.makedirs(DEMO, exist_ok=True)
    for name in ("index.html", "lesson.html", "transcript.html", "app.js", "transcript.js", "style.css"):
        src = os.path.join(WEB, name)
        dst = os.path.join(DEMO, name)
        if name.endswith(".html"):
            # every page that talks to /api gets the fake API shim before its script
            html = open(src, encoding="utf-8").read()
            tag = '<script src="%s"' % ("app.js" if name != "transcript.html" else "transcript.js")
            assert tag in html, f"{name} must load its script with a plain script tag"
            html = html.replace(tag, '<script src="shim.js"></script>\n  ' + tag, 1)
            open(dst, "w", encoding="utf-8").write(html)
        else:
            shutil.copyfile(src, dst)
    shutil.copyfile(os.path.join(ROOT, "src", "demo_shim.js"), os.path.join(DEMO, "shim.js"))
    data = os.path.join(DEMO, "data")
    write_tone_lesson(data, 1, "Demo Lesson (placeholder content)", CHUNKS, SECTIONS)
    write_index(data, [
        {"lesson": 1, "title": "Demo Lesson (placeholder content)", "processed": True},
        {"lesson": 2, "title": "Another placeholder lesson", "processed": False},
    ])
    print("demo built at", DEMO)


if __name__ == "__main__":
    build_demo()
