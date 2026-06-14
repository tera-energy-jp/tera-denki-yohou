#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JEPX spot_summary CSV → 月平均比較ページ用 monthly.json 変換スクリプト

用途:
    エリアごとの「月平均エリアプライス」を 2022年1月以降ぶん集計する。
    Webの月平均比較ビュー（季節性／トレンド）と、
    「あしたの予報が過去の同時期と比べてどうか」の判定に使う。

データの考え方:
    - 日次48コマ → その月の全コマを単純平均（円/kWh）
    - 電力年度ファイル（4月始まり）を年またぎで読み、暦の年月で集計し直す
    - 当月が途中（まだ月末が来ていない）でも、その時点までの平均を出す

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ★重要な運用ルール（次の担当者・次のりんへ）★

 monthly.json は「生成物」であり、正本データは JEPX にある。
 このリポジトリは過去年度の生CSV（spot_summary_YYYY.csv）を持たない方針。

 2つのモードがある:

 (1) 既定（マージモード）… 毎日のworkflowで使う
     既存の docs/monthly.json を土台に、data/spot_summary.csv（当年度の最新）
     から計算した月平均だけを上書きマージする。過去の月は一切触らない。
     → 年度CSVが無くても動く。当月の平均が日々伸びていく。

 (2) --rebuild（全再生成モード）… 過去を作り直したいときだけ手動で
     data/spot_summary_YYYY.csv（年度ファイル群）から全期間を集計し直す。

 ☆☆ 過去データの改定・作り直しが必要になったとき ☆☆
   勝手に既存の monthly.json の数値を推論・補完してはいけない。
   必ず JEPX の公式サイトから該当年度の spot_summary_YYYY.csv を取得し、
   data/ に置いてから `--rebuild` で作り直すこと。
   JEPX: https://www.jepx.jp/electricpower/market-data/spot/
   （取得は scripts/fetch_jepx.py の仕組みも流用できる）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

手元での確認:
    cd <repo root>
    python scripts/build_monthly.py                    # マージ（既定）：当年度CSV→既存JSONへ反映
    python scripts/build_monthly.py --rebuild          # 全再生成：data/の年度ファイル群から
    python scripts/build_monthly.py --rebuild --from 2022-01   # 集計開始の年月を指定
    python scripts/build_monthly.py --rebuild a.csv b.csv      # CSVを明示指定
"""
import csv
import glob
import json
import os
import re
import sys
from collections import defaultdict

DATA_DIR = "data"
# build_prices.py / build_history.py と流儀を揃える：カレント直下に出力し、
# workflow 側で docs/ へコピーする。
OUTPUT_JSON = "monthly.json"
# マージモードで土台にする既存の公開ファイル
EXISTING_JSON = os.path.join("docs", "monthly.json")
# マージモードで読む当年度の最新CSV
LATEST_CSV = os.path.join(DATA_DIR, "spot_summary.csv")

COL_DATE = 0
COL_AREA_START = 6
AREAS = ["北海道", "東北", "東京", "中部", "北陸", "関西", "中国", "四国", "九州"]

DEFAULT_FROM = "2022-01"  # 集計開始の年月（YYYY-MM）


def load_rows(csv_path):
    with open(csv_path, encoding="cp932", newline="") as f:
        rows = list(csv.reader(f))
    return rows[1:]  # ヘッダー除く


def aggregate(csv_paths, from_ym):
    """CSV群を読み、(area -> {ym: 平均}) と 月リストを返す。"""
    acc = defaultdict(lambda: [0.0, 0])
    seen = set()  # (日付, 時刻コード) で重複計上を防ぐ
    for path in csv_paths:
        for r in load_rows(path):
            if not r or not r[COL_DATE]:
                continue
            m = re.match(r"(\d{4})/(\d{2})/(\d{2})", r[COL_DATE])
            if not m:
                continue
            ym = f"{m.group(1)}-{m.group(2)}"
            if ym < from_ym:
                continue
            key = (r[COL_DATE], r[1] if len(r) > 1 else "")
            if key in seen:
                continue
            seen.add(key)
            for i, a in enumerate(AREAS):
                try:
                    v = float(r[COL_AREA_START + i])
                except (IndexError, ValueError):
                    continue
                acc[(a, ym)][0] += v
                acc[(a, ym)][1] += 1

    monthly = {a: {} for a in AREAS}
    for (a, ym), (total, cnt) in acc.items():
        if cnt > 0:
            monthly[a][ym] = round(total / cnt, 2)
    return monthly


def find_year_csvs():
    """data/ 配下の spot_summary_YYYY.csv をすべて集める（--rebuild用）。"""
    files = sorted(glob.glob(os.path.join(DATA_DIR, "spot_summary_*.csv")))
    if os.path.exists(LATEST_CSV) and LATEST_CSV not in files:
        files.append(LATEST_CSV)
    return files


def rebuild(csv_paths, from_ym):
    """全再生成：年度CSV群から全期間を作り直す。"""
    monthly = aggregate(csv_paths, from_ym)
    months = sorted({ym for a in monthly for ym in monthly[a]})
    return {"from": from_ym, "months": months, "unit": "円/kWh", "areas": monthly}


def merge():
    """マージ：既存 docs/monthly.json を土台に、当年度CSVぶんだけ上書き反映。"""
    if not os.path.exists(EXISTING_JSON):
        raise SystemExit(
            f"既存の {EXISTING_JSON} が見つかりません。\n"
            "  → 初回は過去年度CSVを data/ に置いて `--rebuild` で作成してください。\n"
            "    年度CSVは JEPX から取得します: "
            "https://www.jepx.jp/electricpower/market-data/spot/"
        )
    if not os.path.exists(LATEST_CSV):
        raise SystemExit(f"当年度CSV {LATEST_CSV} が見つかりません（fetch_jepx.py を先に実行）。")

    base = json.load(open(EXISTING_JSON, encoding="utf-8"))
    from_ym = base.get("from", DEFAULT_FROM)

    # 当年度CSVから計算した月平均で、該当する年月だけ上書き（過去は保持）
    latest = aggregate([LATEST_CSV], from_ym)
    areas = base.get("areas", {a: {} for a in AREAS})
    for a in AREAS:
        areas.setdefault(a, {})
        for ym, v in latest.get(a, {}).items():
            areas[a][ym] = v  # 当月を含む最新ぶんを上書き

    months = sorted({ym for a in areas for ym in areas[a]})
    return {"from": from_ym, "months": months, "unit": "円/kWh", "areas": areas}


def main():
    args = list(sys.argv[1:])
    do_rebuild = False
    from_ym = DEFAULT_FROM
    csv_paths = []

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--rebuild":
            do_rebuild = True
            i += 1
        elif a == "--from" and i + 1 < len(args):
            from_ym = args[i + 1]
            i += 2
        elif a.endswith(".csv"):
            csv_paths.append(a)
            i += 1
        else:
            i += 1

    if do_rebuild:
        if not csv_paths:
            csv_paths = find_year_csvs()
        if not csv_paths:
            raise SystemExit(
                f"年度CSVが見つかりません（{DATA_DIR}/spot_summary_*.csv）。\n"
                "  → 過去を作り直すには JEPX から年度CSVを取得して data/ に置いてください。\n"
                "    https://www.jepx.jp/electricpower/market-data/spot/"
            )
        print("【全再生成モード】読み込むCSV:")
        for p in csv_paths:
            print(f"  - {p}")
        out = rebuild(csv_paths, from_ym)
    else:
        print("【マージモード】既存 docs/monthly.json に当年度ぶんを反映します。")
        out = merge()

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    n = len(out["months"])
    span = f"{out['months'][0]} 〜 {out['months'][-1]}" if out["months"] else "-"
    print(f"OK: {n}ヶ月分（{span}）を {OUTPUT_JSON} に書き出しました。")
    kix = out["areas"].get("関西", {})
    if kix:
        recent = sorted(kix.items())[-3:]
        print("  例）関西の直近3ヶ月平均: " + ", ".join(f"{ym}={v}円" for ym, v in recent))


if __name__ == "__main__":
    main()
