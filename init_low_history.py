# -*- coding: utf-8 -*-
"""
init_low_history.py — でんき日和の履歴ファイルを初期構築する
============================================================
でんき日和の判定には直近90日ぶんの「安コマ最長連続時間」が必要だが、
prices.json には翌日ぶんしか入っていない。そこで日々の値を追記していく
履歴ファイル（data/low_history.json）を持つ。

このスクリプトは、その履歴を JEPXスポット実績CSV から一括生成する。
初回セットアップ時に1度だけ実行すればよい（以降は build_hiyori.py が追記する）。

データ: data/spot_summary*.csv
        （列: 受渡日, 時刻コード, エリアプライス{エリア}(円/kWh)・cp932）

使い方:
    python scripts/init_low_history.py              # data/low_history.json を作成
    python scripts/init_low_history.py --force      # 既存ファイルを上書き
    python scripts/init_low_history.py --from 2024-01-01   # 開始日を絞る

出力形式:
    {"2026-09-14": {"北海道": 4.5, "東北": 0.0, ...}, ...}
"""
import sys
import csv
import json
import glob
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import hiyori_config as hc  # noqa: E402

REPO = SCRIPT_DIR.parent
DATA_DIR = REPO / "data"
OUT_PATH = DATA_DIR / hc.HISTORY_FILENAME


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def read_csv_rows(path):
    """cp932想定でCSVを読み、dictのリストで返す。"""
    for enc in ("cp932", "utf-8-sig", "utf-8"):
        try:
            with open(path, newline="", encoding=enc) as f:
                return list(csv.DictReader(f))
        except (UnicodeDecodeError, LookupError):
            continue
    raise RuntimeError(f"encodingを判別できません: {path}")


def normalize_date(s):
    """'2026/9/14' や '2026-09-14' を 'YYYY-MM-DD' に揃える。"""
    s = s.strip().replace("/", "-")
    y, m, d = s.split("-")[:3]
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def main():
    force = "--force" in sys.argv
    since = arg("--from")

    if OUT_PATH.exists() and not force:
        sys.exit(f"すでに存在します: {OUT_PATH}\n上書きするなら --force を付けてください。")

    files = sorted(glob.glob(str(DATA_DIR / "spot_summary*.csv")))
    if not files:
        sys.exit(f"CSVが見つかりません: {DATA_DIR}/spot_summary*.csv")

    # 受渡日 → {エリア: [48コマの価格]}
    by_date = {}
    for path in files:
        for row in read_csv_rows(path):
            if not row.get("受渡日"):
                continue
            date = normalize_date(row["受渡日"])
            if since and date < since:
                continue
            try:
                slot = int(row["時刻コード"]) - 1      # CSVは1始まり、内部は0始まり
            except (ValueError, TypeError, KeyError):
                continue
            if not (0 <= slot < 48):
                continue
            day = by_date.setdefault(date, {a: [None] * 48 for a in hc.AREAS})
            for a in hc.AREAS:
                col = f"エリアプライス{a}(円/kWh)"
                v = row.get(col)
                if v not in (None, "",):
                    try:
                        day[a][slot] = float(v)
                    except ValueError:
                        pass

    history = {}
    skipped = 0
    for date in sorted(by_date):
        day = by_date[date]
        # コマ欠けの日は履歴に入れない（分布を歪めるため）
        if any(None in day[a] for a in hc.AREAS):
            skipped += 1
            continue
        history[date] = {a: hc.longest_cheap_hours(day[a]) for a in hc.AREAS}

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=0, sort_keys=True),
        encoding="utf-8")

    dates = sorted(history)
    print(f"履歴を作成しました: {OUT_PATH}")
    print(f"  期間: {dates[0]} 〜 {dates[-1]}（{len(dates)}日）")
    if skipped:
        print(f"  ※コマ欠けのため除外: {skipped}日")
    print(f"  判定に必要な日数: {hc.MIN_HISTORY_DAYS}日 → "
          f"{'足りています' if len(dates) >= hc.MIN_HISTORY_DAYS else '不足しています'}")

    # 参考：現時点のしきい値を表示
    print(f"\n[現時点のしきい値]（直近{hc.WINDOW_DAYS}日・目標年{hc.TARGET_PER_YEAR}回）")
    for a in hc.AREAS:
        series = [history[d][a] for d in dates]
        th = hc.pick_threshold(series)
        print(f"  {a:<4} {th if th is not None else '—':>5}h")


if __name__ == "__main__":
    main()
