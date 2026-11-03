"""Shared paths and helpers for the pipeline (data contract: DECISIONS.md)."""
import os
import imageio_ffmpeg

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "data")
FEED_URL = "https://www.melnyks.com/feed/podcast/"


def episode_mp3(n):
    return os.path.join(DATA, "episodes", f"lesson_{n:03d}.mp3")


def lesson_dir(n):
    return os.path.join(DATA, "lessons", f"{n:03d}")


def ffmpeg():
    return imageio_ffmpeg.get_ffmpeg_exe()
