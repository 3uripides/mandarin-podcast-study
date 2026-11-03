"""Create the placeholder test fixture: python tests/fixtures/make_fixture.py"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from src.build_demo import CHUNKS, SECTIONS, write_index, write_tone_lesson  # noqa: E402

DATA = os.path.join(ROOT, "tests", "fixtures", "data")

if __name__ == "__main__":
    write_tone_lesson(DATA, 900, "Fixture lesson (placeholder)", CHUNKS, SECTIONS)
    write_index(DATA, [
        {"lesson": 900, "title": "Fixture lesson (placeholder)", "processed": True},
        {"lesson": 901, "title": "Unprocessed fixture lesson", "processed": False},
    ])
    print("fixture written to", DATA)
