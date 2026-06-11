#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stories.html の各スライド（.slide）を PNG に書き出す（Instagramストーリーズ用）。

サイズについて（意図的な設定）:
  - レイアウトは 1080×1920（Instagramストーリーズの表示サイズ）。
  - device_scale_factor=2 で実ファイルは 2160×3840 になる。これは
    Meta 側の縮小・再圧縮を経ても文字がくっきり残るようにするための
    意図的な2倍スーパーサンプリング。等倍にしたい場合は
    環境変数 RENDER_SCALE=1 で切り替えられる。

フォントについて:
  - Google Fonts（Noto Sans JP）の読み込みを document.fonts.ready で
    実際に待つ。固定スリープだとCIで間に合わず、代替フォントのまま
    書き出される日が出るため。

使い方:
    python scripts/build_stories.py     # まず stories.html を生成
    python scripts/render_png.py        # stories_1.png 〜 stories_5.png を出力
    RENDER_SCALE=1 python scripts/render_png.py   # 等倍（1080×1920）で出力
"""
import os
import pathlib
import sys

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    raise SystemExit("playwright が未インストールです。\n  pip install playwright && playwright install chromium")

HTML = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "stories.html").resolve()
if not HTML.exists():
    raise SystemExit(f"{HTML} がありません。先に build_stories.py を実行してください。")

SCALE = int(os.environ.get("RENDER_SCALE", "2"))


def wait_for_fonts(page):
    """Webフォントの読み込み完了を実際に待つ（最大15秒、失敗時はフォールバック）。"""
    try:
        # status が 'loaded' でも読み込み開始前の可能性があるため、
        # Noto Sans JP が実際に使えるかも合わせて確認する。
        page.wait_for_function(
            "document.fonts.status === 'loaded' && document.fonts.check('16px \"Noto Sans JP\"')",
            timeout=15000,
        )
        page.wait_for_timeout(200)  # レイアウト反映の小休止
        print("  Webフォント読み込み: 完了を確認")
    except Exception as e:
        # オフライン等で確認できない場合のフォールバック（従来より長めに待つ）
        print(f"  Webフォント確認をスキップ（{type(e).__name__}）。1.5秒待機にフォールバック。")
        page.wait_for_timeout(1500)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1080, "height": 1920},
            device_scale_factor=SCALE,
        )
        try:
            # networkidle でフォント等のリクエスト完了まで待つ（30秒で見切り）
            page.goto(HTML.as_uri(), wait_until="networkidle", timeout=30000)
        except PWTimeout:
            print("  networkidle 待ちがタイムアウト。読み込み済みの状態で続行します。")
        wait_for_fonts(page)
        slides = page.query_selector_all(".slide")
        for i, s in enumerate(slides, 1):
            out = f"stories_{i}.png"
            s.screenshot(path=out)
            print(f"  書き出し: {out}（{1080*SCALE}×{1920*SCALE}）")
        browser.close()
    print(f"OK: {len(slides)}枚のPNGを書き出しました。")


if __name__ == "__main__":
    main()
