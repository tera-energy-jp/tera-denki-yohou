#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
でんき予報 Slack通知（軽量版・自動投稿後の安否確認用）
--------------------
prices.json を読み、その日のサマリ（最安/高め）を Slack に短く通知する。
画像は載せず、Web版へのリンクを添える。
（Instagram Storiesへの投稿はワークフローが自動で行うため、手動投稿の案内は廃止）

環境変数:
  SLACK_WEBHOOK_URL  Slack Incoming Webhook の URL（GitHub Secrets）
  PAGES_BASE_URL     公開先のベースURL 例 https://OWNER.github.io/REPO（GitHub Variables）
使い方:
  python scripts/notify_slack.py            # prices.json を読む
  python scripts/notify_slack.py prices.json
"""
import json
import os
import sys
import urllib.request
from alert_config import price_level


def slot_label(i):
    return f"{i // 2}:{'30' if i % 2 else '00'}"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "prices.json"
    data = json.load(open(path, encoding="utf-8"))
    areas = data["areas"]
    date_label = data["date_label"]

    peaks = [max(arr) for arr in areas.values()]
    rep = sum(peaks) / len(peaks)              # 9エリアの日内最高値の平均
    lv, mood_label, _ = price_level(rep)       # 5段階（表紙と同じ判定）
    cheapest = min(areas, key=lambda a: min(areas[a]))
    carr = areas[cheapest]
    lo_i = carr.index(min(carr))
    hot = [a for a in areas if max(areas[a]) >= 17]   # 段階4以上（高め）のエリア
    if not hot:
        note = "🌿 高すぎる時間は無さそう。安心して使えるゾウ" if lv <= 2 else "🌿 ふつうの水準。時間を選べばお得に使えるゾウ"
    elif len(hot) >= 5:
        note = "⚠ 広い範囲で 高めの時間に注意"
    else:
        note = f"⚠ 高めの時間に注意：{'・'.join(hot)}"

    summary = (f"あしたは *{mood_label}*\n"
               f"*いちばんおだやか*：{cheapest}・{slot_label(lo_i)}ごろ"
               f"（約{min(carr):.0f}円/kWh）\n{note}")

    base = os.environ.get("PAGES_BASE_URL", "").rstrip("/")
    link_line = "✅ Web・Instagram Storiesに自動投稿しました"
    if base:
        link_line += f"｜<{base}|Web版を見る>"

    # 軽量化：画像5枚は載せず、サマリ＋完了リンクだけ
    blocks = [
        {"type": "header",
         "text": {"type": "plain_text", "text": f"☀ でんき予報 配信完了（{date_label}）"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
        {"type": "context", "elements": [
            {"type": "mrkdwn", "text": link_line}]},
    ]

    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        print("SLACK_WEBHOOK_URL が未設定です（ローカル確認時はスキップ）。\n--- 送信予定の内容 ---")
        print(summary)
        print(link_line)
        return

    payload = json.dumps({"blocks": blocks}).encode("utf-8")
    req = urllib.request.Request(webhook, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as res:
        print("Slack通知 送信:", res.status)


if __name__ == "__main__":
    main()
