#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
carousel.html の各スライドを 1080×1080 PNG に書き出す（Instagram投稿用）。

事前準備（初回のみ）:
    pip install playwright
    playwright install chromium

使い方:
    python build_carousel.py        # まず carousel.html を生成
    python render_png.py            # carousel_1.png 〜 carousel_3.png を出力

GitHub Actions では runner に Chromium を入れて同じコマンドを実行すれば、
毎日 prices.json から3枚のPNGが自動生成される。
"""
import pathlib
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    raise SystemExit("playwright が未インストールです。\n  pip install playwright && playwright install chromium")

HTML = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "stories.html").resolve()
if not HTML.exists():
    raise SystemExit(f"{HTML} がありません。先に build_carousel.py を実行してください。")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # device_scale_factor=2 で 2160×2160 相当の高精細PNGに
        page = browser.new_page(
            viewport={"width": 1080, "height": 1920},
            device_scale_factor=2,
        )
        page.goto(HTML.as_uri())
        page.wait_for_timeout(600)  # Webフォント読み込み待ち
        slides = page.query_selector_all(".slide")
        for i, s in enumerate(slides, 1):
            out = f"carousel_{i}.png"
            s.screenshot(path=out)
            print(f"  書き出し: {out}")
        browser.close()
    print(f"OK: {len(slides)}枚のPNGを書き出しました。")


if __name__ == "__main__":
    main()
