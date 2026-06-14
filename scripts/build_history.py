#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JEPX spot_summary CSV → でんき予報ページ用 history.json 変換スクリプト

運用:
    1. このスクリプトを build_prices.py の直後に実行する
    2. CSVに入っているすべての日付（48コマが揃っている日のみ）を history.json に書き出す
    3. GitHub Actions が history.json を docs/ へコピー＆コミット → GitHub Pages が自動公開

手元での確認:
    cd scripts
    python build_history.py                        # data/spot_summary.csv から直近180日（既定）
    python build_history.py path/to/other.csv      # CSVパスを指定
    python build_history.py --days 90              # 直近90日に絞る
    python build_history.py --all                  # 全期間（重くなるので通常は使わない）
"""
import csv
import json
import os
import sys
from datetime import date

DEFAULT_CSV = os.path.join("data", "spot_summary.csv")
# build_prices.py と流儀を揃える：カレント直下に出力し、workflow 側で docs/ へコピーする。
# （手元で `python scripts/build_history.py` を叩いたときも docs/ を汚さない）
OUTPUT_JSON = "history.json"

# 30分データの日次グラフは直近 DEFAULT_DAYS 日に固定する。
# 全期間を持つとファイルが重くなり、スマホでの初回ロードが遅くなるため。
# 長期の傾向は別途 monthly.json（月平均）で見せる方針。
DEFAULT_DAYS = 180

COL_DATE = 0
COL_SLOT = 1
COL_AREA_START = 6
AREAS = ["北海道", "東北", "東京", "中部", "北陸", "関西", "中国", "四国", "九州"]


def format_jp_date(ymd: str) -> str:
    y, m, d = map(int, ymd.split("/"))
    wd = ["月", "火", "水", "木", "金", "土", "日"][date(y, m, d).weekday()]
    return f"{y}年{m}月{d}日({wd})"


def load_rows(csv_path: str):
    if not os.path.exists(csv_path):
        raise SystemExit(f"CSVが見つかりません: {csv_path}")
    with open(csv_path, encoding="cp932", newline="") as f:
        rows = list(csv.reader(f))
    return rows[1:]  # ヘッダーを除く


def build(csv_path: str = DEFAULT_CSV, max_days: int = None) -> dict:
    rows = load_rows(csv_path)

    # 日付ごとにまとめる
    by_date: dict[str, list] = {}
    for r in rows:
        if not r or not r[COL_DATE]:
            continue
        d = r[COL_DATE]
        by_date.setdefault(d, []).append(r)

    # 各日付を変換（48コマ揃っている日のみ）
    data: dict[str, dict] = {}
    skipped = []
    for d, day_rows in by_date.items():
        day_rows.sort(key=lambda r: int(r[COL_SLOT]))
        if len(day_rows) != 48:
            skipped.append((d, len(day_rows)))
            continue
        area_prices = {a: [] for a in AREAS}
        for r in day_rows:
            for i, a in enumerate(AREAS):
                try:
                    area_prices[a].append(round(float(r[COL_AREA_START + i]), 2))
                except (IndexError, ValueError):
                    area_prices[a].append(0.0)
        data[d] = {
            "date_label": format_jp_date(d),
            "areas": area_prices,
        }

    if skipped:
        for d, n in skipped:
            print(f"  ⚠ {d}: コマ数 {n}/48 → スキップ")

    # 新しい順に並べる
    dates = sorted(data.keys(), reverse=True)

    # 件数制限
    if max_days and len(dates) > max_days:
        dates = dates[:max_days]
        data = {d: data[d] for d in dates}

    return {"dates": dates, "data": data}


def main():
    args = list(sys.argv[1:])
    csv_path = DEFAULT_CSV
    max_days = DEFAULT_DAYS  # 既定は直近180日

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--days" and i + 1 < len(args):
            max_days = int(args[i + 1])
            i += 2
        elif a == "--all":
            max_days = None  # 全期間（重くなるので通常は使わない）
            i += 1
        elif a.endswith(".csv"):
            csv_path = a
            i += 1
        else:
            i += 1

    out = build(csv_path, max_days)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))  # 圧縮形式で出力

    n = len(out["dates"])
    oldest = out["dates"][-1] if out["dates"] else "-"
    newest = out["dates"][0] if out["dates"] else "-"
    print(f"OK: {n}日分を {OUTPUT_JSON} に書き出しました（{oldest} 〜 {newest}）")


if __name__ == "__main__":
    main()
