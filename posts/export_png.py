"""Export every feed post as Instagram-ready files: data/posts/png/<id>/1.png, 2.png, … (1080x1350)
and caption.txt (caption + hashtags). Renders the live /feed page, so the server must be running.

Usage: uv run --with playwright python posts/export_png.py [--url http://localhost:8103] [--only ID ...]
(playwright is not in requirements.txt; its Chromium: uv run --with playwright playwright install chromium)
"""
import argparse
import json
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "posts" / "png"
SCALE = 2.5  # a 432x540 slide pinned at the page's top-left corner -> exactly 1080x1350
SLIDE = {"x": 0, "y": 0, "width": 432, "height": 540}
EXPORT_CSS = (".count,.nav,.top{display:none!important} .slides{scroll-snap-type:none!important}"
              " article.x{position:fixed;top:0;left:0;width:432px;margin:0;border:0;border-radius:0;z-index:9}")


DISCLOSURE = "Sažetak je strojno pripremljen iz službenog zapisnika i pregledan prije objave. Ispravke uz izvor su dobrodošle."


def caption(post):
    return f"{post['caption']}\n\n{DISCLOSURE}\n\n{' '.join(post['hashtags'])}\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8103")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--captions-only", action="store_true", help="rewrite caption.txt files, no rendering")
    a = ap.parse_args()
    posts = json.load(urllib.request.urlopen(f"{a.url}/api/posts"))
    if a.captions_only:
        for post in posts:
            if not a.only or post["id"] in a.only:
                (OUT / post["id"]).mkdir(parents=True, exist_ok=True)
                (OUT / post["id"] / "caption.txt").write_text(caption(post))
        print(f"captions -> {OUT}")
        return
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 560, "height": 1000}, device_scale_factor=SCALE)
        # every post, in API order: the feed remembers a town and "Samo bitno" per viewer, so reset both
        page.add_init_script("localStorage.setItem('vij.important', '0'); localStorage.setItem('vij.city', '')")
        page.goto(f"{a.url}/feed")
        page.wait_for_selector("article")
        page.add_style_tag(content=EXPORT_CSS)
        page.evaluate("document.fonts.ready")
        arts = page.locator("article")
        done = 0
        for k, post in enumerate(posts):
            if a.only and post["id"] not in a.only:
                continue
            art = arts.nth(k)
            art.evaluate("el => el.classList.add('x')")
            d = OUT / post["id"]
            d.mkdir(parents=True, exist_ok=True)
            for i in range(art.locator(".slide").count()):
                art.locator(".slides").evaluate(f"el => el.scrollLeft = {i} * el.clientWidth")
                page.screenshot(path=str(d / f"{i + 1}.png"), clip=SLIDE)
            art.evaluate("el => el.classList.remove('x')")
            (d / "caption.txt").write_text(caption(post))
            done += 1
        browser.close()
    print(f"{done} posts -> {OUT}")


if __name__ == "__main__":
    main()
