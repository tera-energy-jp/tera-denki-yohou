#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
でんき予報 Slack通知
--------------------
prices.json を読み、その日のサマリ（最安/高め）と
GitHub Pages 上の5枚のストーリーズPNGを Slack に通知する。

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

from alert_config import THRESHOLDS


def slot_label(i):
    return f"{i // 2}:{'30' if i % 2 else '00'}"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "prices.json"
    data = json.load(open(path, encoding="utf-8"))
    areas = data["areas"]
    date_label = data["date_label"]

    cheapest = min(areas, key=lambda a: min(areas[a]))
    carr = areas[cheapest]
    lo_i = carr.index(min(carr))
    hot = [a for a in areas if max(areas[a]) > THRESHOLDS.get(a, 40)]

    if hot:
        mood = f"⚠ 高めにご注意：{'・'.join(hot)}"
    else:
        mood = "🌿 高すぎる時間は無さそう。おだやかな一日です"

    summary = (f"*いちばんおだやか*：{cheapest}・{slot_label(lo_i)}ごろ"
               f"（約{min(carr):.0f}円/kWh）\n{mood}")

    base = os.environ.get("PAGES_BASE_URL", "").rstrip("/")
    ver = data["date_raw"].replace("/", "")  # キャッシュ回避用
    imgs = [f"{base}/stories/stories_{i}.png?v={ver}" for i in range(1, 6)]

    blocks = [
        {"type": "header",
         "text": {"type": "plain_text", "text": f"☀ 今日のでんき予報ができたゾウ（{date_label}）"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
        {"type": "divider"},
    ]
    for i, u in enumerate(imgs, 1):
        labels = ["表紙", "東日本編", "中日本編", "西日本編", "締め"]
        blocks.append({"type": "image", "image_url": u,
                       "alt_text": labels[i - 1], "title": {"type": "plain_text", "text": f"{i}. {labels[i-1]}"}})
    blocks.append({"type": "context", "elements": [
        {"type": "mrkdwn",
         "text": "確認して、Instagramストーリーズに 1→5 の順で投稿してね（最後にWeb版へのリンクスタンプも忘れずに）。"}]})

    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        print("SLACK_WEBHOOK_URL が未設定です（ローカル確認時はスキップ）。\n--- 送信予定の内容 ---")
        print(summary)
        for u in imgs:
            print(u)
        return

    payload = json.dumps({"blocks": blocks}).encode("utf-8")
    req = urllib.request.Request(webhook, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as res:
        print("Slack通知 送信:", res.status)


if __name__ == "__main__":
    main()
