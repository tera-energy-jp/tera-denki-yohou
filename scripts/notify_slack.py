#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
でんき予報 Slack通知（安否確認用）
--------------------
prices.json を読み、その日のサマリ（最安/高め）と「Instagram投稿の成否」を
Slack に短く通知する。画像は載せず、Web版へのリンクを添える。

設計方針：
  - Slackはあくまで「おまけの安否確認」。失敗しても配信本体（IG投稿）を
    道連れにしないよう、ワークフロー側で if: always() ＋ continue-on-error
    ＋ timeout-minutes を付けて実行する。
  - urlopen に timeout を付け、短いリトライで素早く諦める
    （かつて timeout 未指定で約20分ハングし、後続のIG投稿を巻き添えにした）。
  - IG_RESULT（ワークフローから渡される steps.instagram.outcome）を見て、
    成功なら ✅、失敗・スキップなら ⚠ を正直に報告する。

環境変数:
  SLACK_WEBHOOK_URL  Slack Incoming Webhook の URL（GitHub Secrets）
  PAGES_BASE_URL     公開先のベースURL 例 https://OWNER.github.io/REPO（GitHub Variables）
  IG_RESULT          Instagram投稿ステップの結果 success / failure / skipped / cancelled
  RUN_URL            GitHub Actions の実行ページURL（失敗時の確認用リンク）
使い方:
  python scripts/notify_slack.py            # prices.json を読む
  python scripts/notify_slack.py prices.json
"""
import json
import os
import sys
import time
import urllib.request
from alert_config import price_level, yen_approx, HIGH_FLOOR


def slot_label(i):
    return f"{i // 2}:{'30' if i % 2 else '00'}"


def post_webhook(webhook, blocks, tries=3, interval=5, timeout=10):
    """Webhook送信。短いタイムアウト＋リトライで、ハングを起こさない。"""
    payload = json.dumps({"blocks": blocks}).encode("utf-8")
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(
                webhook, data=payload,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as res:
                print("Slack通知 送信:", res.status)
                return True
        except Exception as e:
            print(f"Slack送信失敗 ({attempt}/{tries}): {e}", file=sys.stderr)
            if attempt < tries:
                time.sleep(interval)
    return False


def ig_status_line(base):
    """IG_RESULT に応じた、嘘をつかないステータス行を作る。"""
    ig = os.environ.get("IG_RESULT", "")
    run_url = os.environ.get("RUN_URL", "")
    if ig == "success":
        line = "✅ Web・Instagram Storiesに自動投稿しました"
    elif ig in ("failure", "cancelled", "skipped"):
        line = "⚠ *Instagram Storiesへの投稿が完了していません*（要手動確認）"
        if run_url:
            line += f"｜<{run_url}|実行ログを見る>"
    else:
        # ローカル実行などで IG_RESULT が無い場合
        line = "✅ Webに公開しました"
    if base:
        line += f"｜<{base}|Web版を見る>"
    return line


def summary_blocks(path, base):
    data = json.load(open(path, encoding="utf-8"))
    areas = data["areas"]
    date_label = data["date_label"]

    peaks = [max(arr) for arr in areas.values()]
    rep = sum(peaks) / len(peaks)              # 9エリアの日内最高値の平均
    lv, mood_label, _ = price_level(rep)       # 5段階（表紙と同じ判定）
    cheapest = min(areas, key=lambda a: min(areas[a]))
    carr = areas[cheapest]
    lo_i = carr.index(min(carr))
    hot = [a for a in areas if max(areas[a]) >= HIGH_FLOOR]   # 「高め」以上のエリア（alert_configで一本化）
    if not hot:
        note = "🌿 高すぎる時間は無さそう。安心して使えるゾウ" if lv <= 2 else "🌿 ふつうの水準。時間を選べばお得に使えるゾウ"
    elif len(hot) >= 5:
        note = "⚠ 広い範囲で 高めの時間に注意"
    else:
        note = f"⚠ 高めの時間に注意：{'・'.join(hot)}"

    summary = (f"あしたは *{mood_label}*\n"
               f"*いちばんおだやか*：{cheapest}・{slot_label(lo_i)}ごろ"
               f"（{yen_approx(min(carr), '円/kWh')}）\n{note}")

    return [
        {"type": "header",
         "text": {"type": "plain_text", "text": f"☀ でんき予報 配信処理 完了（{date_label}）"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
        {"type": "context", "elements": [
            {"type": "mrkdwn", "text": ig_status_line(base)}]},
    ]


def error_blocks(reason, base):
    """prices.json が無い＝生成段階で失敗した日のための最低限の通知。"""
    run_url = os.environ.get("RUN_URL", "")
    text = f"⚠ *配信処理が途中で失敗しました*\n{reason}"
    if run_url:
        text += f"\n<{run_url}|実行ログを見る>"
    if base:
        text += f"｜<{base}|Web版（前回分）>"
    return [
        {"type": "header",
         "text": {"type": "plain_text", "text": "⚠ でんき予報 配信エラー"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
    ]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "prices.json"
    base = os.environ.get("PAGES_BASE_URL", "").rstrip("/")

    if os.path.exists(path):
        blocks = summary_blocks(path, base)
    else:
        blocks = error_blocks(
            f"`{path}` が生成されていません（JEPXの公表遅延や取得失敗の可能性）。"
            "後続のリトライ実行が自動で再試行します。", base)

    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        print("SLACK_WEBHOOK_URL が未設定です（ローカル確認時はスキップ）。\n--- 送信予定の内容 ---")
        print(json.dumps(blocks, ensure_ascii=False, indent=2))
        return

    if not post_webhook(webhook, blocks):
        # 通知は諦めるが、原因がログに残るよう失敗コードで終える
        # （ワークフロー側の continue-on-error でジョブ全体は守られる）
        raise SystemExit("Slack通知をリトライしましたが届きませんでした。")


if __name__ == "__main__":
    main()
