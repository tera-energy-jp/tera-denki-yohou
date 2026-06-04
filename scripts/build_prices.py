#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JEPX spot_summary CSV → でんき予報ページ用 prices.json 変換スクリプト（運用版）

運用（半自動）:
    1. JEPXからDLしたCSVを data/spot_summary.csv として置く（上書き）
    2. このスクリプトが最新日の9エリア×48コマを抜き出し prices.json を生成
    3. GitHub Actions が prices.json をコミット → GitHub Pages が自動公開

手元での確認:
    python build_prices.py                      # data/spot_summary.csv の最新日
    python build_prices.py 2026/06/02           # 日付を指定
    python build_prices.py path/to/other.csv    # CSVパスを指定
"""
import csv
import json
import os
import sys
from datetime import date

DEFAULT_CSV = os.path.join("data", "spot_summary.csv")
OUTPUT_JSON = "prices.json"

COL_DATE = 0
COL_SLOT = 1
COL_AREA_START = 6
AREAS = ["北海道", "東北", "東京", "中部", "北陸", "関西", "中国", "四国", "九州"]


def load_rows(csv_path):
    if not os.path.exists(csv_path):
        raise SystemExit(
            f"CSVが見つかりません: {csv_path}\n"
            f"  → JEPXのCSVを {DEFAULT_CSV} に置いてから実行してください。"
        )
    with open(csv_path, encoding="shift_jis", newline="") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        raise SystemExit(f"CSVにデータ行がありません: {csv_path}")
    return rows[1:]


def pick_target_date(rows, target=None):
    dates = [r[COL_DATE] for r in rows if r and r[COL_DATE]]
    if target:
        if target not in dates:
            raise SystemExit(f"指定日 {target} がCSVに見つかりません。CSVの範囲を確認してください。")
        return target
    return max(dates)


def format_jp_date(ymd):
    y, m, d = map(int, ymd.split("/"))
    wd = ["月", "火", "水", "木", "金", "土", "日"][date(y, m, d).weekday()]
    return f"{y}年{m}月{d}日({wd})"


def build(csv_path, target=None):
    rows = load_rows(csv_path)
    target_date = pick_target_date(rows, target)

    day_rows = [r for r in rows if r[COL_DATE] == target_date]
    day_rows.sort(key=lambda r: int(r[COL_SLOT]))

    if len(day_rows) != 48:
        print(f"  ※注意: {target_date} のコマ数が {len(day_rows)} 件です（通常48）。")

    area_prices = {a: [] for a in AREAS}
    for r in day_rows:
        for i, a in enumerate(AREAS):
            area_prices[a].append(round(float(r[COL_AREA_START + i]), 2))

    return {
        "date_raw": target_date,
        "date_label": format_jp_date(target_date),
        "unit": "円/kWh",
        "slots": 48,
        "areas": area_prices,
    }


def main():
    args = list(sys.argv[1:])
    csv_path = DEFAULT_CSV
    target = None
    for a in args:
        if a.endswith(".csv"):
            csv_path = a
        else:
            target = a

    out = build(csv_path, target)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"OK: {out['date_label']} のデータを {OUTPUT_JSON} に書き出しました。")
    for a in AREAS:
        p = out["areas"][a]
        def t(i):
            return f"{i // 2}:{'30' if i % 2 else '00'}"
        print(f"  {a:<3} 最安 {t(p.index(min(p))):>5} {min(p):>6}円 / 最高 {t(p.index(max(p))):>5} {max(p):>6}円")


if __name__ == "__main__":
    main()
