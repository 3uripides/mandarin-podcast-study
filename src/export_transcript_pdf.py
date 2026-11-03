"""Save a lesson transcript as PDF by printing transcript.html from the running server.

Needs the server up (python -m src.server) and Playwright's Chromium (already in .venv).
Usage:
  .venv\\Scripts\\python.exe -m src.export_transcript_pdf --lesson 1
  options: --base http://127.0.0.1:8765  --out <pdf path>  --png <preview png>  --paper A4|Letter
"""
import argparse
import os

from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_OUT = os.path.join(ROOT, "data", "exports", "lesson_{:03d}_transcript.pdf")


def export(lesson, base="http://127.0.0.1:8765", out=None, png=None, paper="A4"):
    out = out or DEFAULT_OUT.format(lesson)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    url = f"{base.rstrip('/')}/transcript.html?n={lesson}"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, wait_until="load")
            # the page sets data-ready once the lesson has rendered (or failed to load)
            page.wait_for_selector("body[data-ready='1']", timeout=30000)
            if page.locator("#tx .line").count() == 0:
                raise RuntimeError(f"no transcript lines at {url}: {page.inner_text('#title')}")
            page.emulate_media(media="print")
            if png:
                # preview of page 1 at A4 size (96 dpi), with print styles applied
                page.set_viewport_size({"width": 794, "height": 1123})
                page.screenshot(path=png, full_page=False)
            page.pdf(path=out, format=paper, print_background=True, prefer_css_page_size=False,
                     margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
        finally:
            browser.close()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lesson transcript -> PDF via Playwright")
    ap.add_argument("--lesson", type=int, required=True)
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--out", default=None)
    ap.add_argument("--png", default=None, help="also save a page-1 screenshot")
    ap.add_argument("--paper", default="A4", choices=["A4", "Letter"])
    args = ap.parse_args(argv)
    path = export(args.lesson, args.base, args.out, args.png, args.paper)
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
