#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stories.html の各スライド（.slide）を 1080×1920 PNG に書き出す（Instagramストーリーズ用）。

使い方:
    python scripts/build_stories.py     # まず stories.html を生成
    python scripts/render_png.py        # stories_1.png 〜 stories_5.png を出力
"""
import pathlib
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    raise SystemExit("playwright が未インストールです。\n  pip install playwright && playwright install chromium")

HTML = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "stories.html").resolve()
if not HTML.exists():
    raise SystemExit(f"{HTML} がありません。先に build_stories.py を実行してください。")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1080, "height": 1920},
            device_scale_factor=2,
        )
        page.goto(HTML.as_uri())
        page.wait_for_timeout(600)  # Webフォント読み込み待ち
        slides = page.query_selector_all(".slide")
        for i, s in enumerate(slides, 1):
            out = f"stories_{i}.png"
            s.screenshot(path=out)
            print(f"  書き出し: {out}")
        browser.close()
    print(f"OK: {len(slides)}枚のPNGを書き出しました。")


if __name__ == "__main__":
    main()
