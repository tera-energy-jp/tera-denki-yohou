#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IGアクセストークンの失効事前チェック
------------------------------------
長命トークン（約60日）の残り日数を毎朝の配信フローの中で確認し、
失効が近づいたら（既定: 14日前から）Slackに更新を促す警告を出す。
失効してから気づくのではなく、失効する前に人間が動けるようにするのが目的。

仕組み:
  Graph API の debug_token エンドポイントでトークン自身を検査し、
  expires_at（失効日時）と is_valid を取得する。
  ※ input_token と access_token に同じユーザートークンを渡す方式は、
    そのトークンがアプリの開発者のものであれば有効。

設計方針:
  - このチェックは「お知らせ」であり、配信本体を止める理由にはしない。
    どんな失敗でも exit 0 で終わる（ワークフロー側でも continue-on-error）。
  - トークンがすでに無効な場合は、直後のIG投稿ステップが失敗して
    Slackの安否確認（notify_slack.py）が ⚠ を報告する。ここでは
    「なぜ失敗するか」を先回りして知らせる役割。

環境変数:
  IG_ACCESS_TOKEN     検査対象のトークン（GitHub Secrets）
  SLACK_WEBHOOK_URL   警告の送り先（無ければ標準出力のみ）
  IG_TOKEN_WARN_DAYS  何日前から警告するか（既定 14）
"""
import datetime
import os
import sys
import requests
from notify_slack import post_webhook

API_VERSION = "v21.0"
API = f"https://graph.facebook.com/{API_VERSION}"

RENEW_GUIDE = (
    "*更新手順*：Meta for Developers（Graph APIエクスプローラ）で長命トークンを再発行し、"
    "GitHub リポジトリの Settings → Secrets → `IG_ACCESS_TOKEN` を差し替える。"
)


def inspect_token(token):
    r = requests.get(
        f"{API}/debug_token",
        params={"input_token": token, "access_token": token},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("data", {})


def notify(webhook, title, body):
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": title}},
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
    ]
    if webhook:
        post_webhook(webhook, blocks)
    else:
        print("SLACK_WEBHOOK_URL 未設定。--- 送信予定の内容 ---")
        print(title)
        print(body)


def main():
    token = os.environ.get("IG_ACCESS_TOKEN")
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    warn_days = int(os.environ.get("IG_TOKEN_WARN_DAYS", "14"))

    if not token:
        print("IG_ACCESS_TOKEN が未設定のためチェックをスキップします。")
        return

    try:
        data = inspect_token(token)
    except Exception as e:
        # ネットワーク不調などでの検査失敗は警告止まり（配信は続行）
        print(f"トークン検査に失敗しました（チェックのみスキップ）: {e}", file=sys.stderr)
        return

    if not data.get("is_valid", False):
        notify(
            webhook,
            "🚨 IGトークンが無効です",
            "Instagramのアクセストークンが*すでに無効*です。"
            "本日の自動投稿は失敗します。\n" + RENEW_GUIDE,
        )
        return

    expires_at = data.get("expires_at", 0)
    if not expires_at:
        print("トークンに有効期限がありません（無期限）。チェック不要です。")
        return

    expiry = datetime.datetime.fromtimestamp(expires_at, datetime.timezone.utc)
    days_left = (expiry - datetime.datetime.now(datetime.timezone.utc)).days
    expiry_jst = expiry.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
    label = expiry_jst.strftime("%Y-%m-%d %H:%M JST")

    if days_left <= warn_days:
        notify(
            webhook,
            f"⏰ IGトークン失効まで あと{days_left}日",
            f"Instagramのアクセストークンが *{label}* に失効します。\n"
            f"失効すると、でんき予報のStories自動投稿が止まります。\n{RENEW_GUIDE}",
        )
    else:
        print(f"IGトークンOK（失効: {label} / 残り {days_left}日）")


if __name__ == "__main__":
    main()
