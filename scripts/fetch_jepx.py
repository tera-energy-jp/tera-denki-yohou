#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JEPXのスポット約定結果CSV（spot_summary_<年度>.csv）を取得し、
data/spot_summary.csv として保存する。

- 電力年度（4月始まり）を自動判定して現年度のCSVを取得する。
- 毎朝の自動実行（JEPX公表 10:30 の後）で使う想定。
- JEPX窓口に自動取得の可否は確認済み。

手元での確認:
    python scripts/fetch_jepx.py          # 現年度を自動判定
    python scripts/fetch_jepx.py 2025     # 年度を指定
"""
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

OUT = os.path.join("data", "spot_summary.csv")
DOWNLOAD_URL = "https://www.jepx.jp/_download.php"
REFERER = "https://www.jepx.jp/electricpower/market-data/spot/"


def fiscal_year(today=None):
    """電力年度（4月始まり）。1〜3月は前年を返す。"""
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


def fetch(fy=None):
    fy = fy or fiscal_year()
    fname = f"spot_summary_{fy}.csv"
    ts = int(time.time() * 1000)
    url = f"{DOWNLOAD_URL}?timestamp={ts}"
    payload = urllib.parse.urlencode(
        {"dir": "spot_summary", "file": fname}
    ).encode("ascii")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": REFERER,
            "User-Agent": "Mozilla/5.0 (tera-denki-yohou)",
        },
    )
    print(f"取得中: {fname}")
    with urllib.request.urlopen(req, timeout=60) as res:
        body = res.read()

    # 健全性チェック：HTMLエラーページやサイズ異常をはじく
    head = body[:300].lstrip().lower()
    if head[:1] == b"<" or b"<!doctype" in head or b"<html" in head:
        raise SystemExit(
            "CSVではなくHTMLが返りました。URL/パラメータ/年度の指定を確認してください。"
        )
    if len(body) < 1000:
        raise SystemExit(
            f"取得データが小さすぎます（{len(body)} bytes）。"
            f"年度ファイル {fname} の存在を確認してください。"
        )

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(body)
    print(f"OK: {OUT} に保存（年度 {fy} / {len(body):,} bytes）")


if __name__ == "__main__":
    arg_fy = int(sys.argv[1]) if len(sys.argv) > 1 else None
    fetch(arg_fy)
