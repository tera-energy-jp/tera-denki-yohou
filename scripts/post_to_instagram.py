#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【完全自動化用・近日中に有効化】Instagram ストーリーズ自動投稿
-------------------------------------------------------------
GitHub Pages 上の stories_1〜5.png を Graph API でストーリーズに投稿する。
半自動の notify_slack.py と差し替える（または併用）形で使う。

前提（Meta側・初回のみ）:
  - Instagram プロアカウント（ビジネス/クリエイター）＋ Facebookページ連携
  - Meta開発者アプリ＋ instagram_content_publish 権限
  - 長期アクセストークン

環境変数（GitHub Secrets / Variables）:
  IG_USER_ID        InstaのビジネスアカウントID
  IG_ACCESS_TOKEN   長期アクセストークン
  PAGES_BASE_URL    例 https://OWNER.github.io/REPO

投稿フロー（1枚ごとに2ステップ）:
  ① POST /{IG_USER_ID}/media  (media_type=STORIES, image_url=公開URL) → creation_id
  ② POST /{IG_USER_ID}/media_publish (creation_id) → 公開
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

GRAPH = "https://graph.facebook.com/v21.0"


def _post(path, params):
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(f"{GRAPH}/{path}", data=data)
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode())


def create_container(ig_user, image_url, token):
    r = _post(f"{ig_user}/media", {
        "media_type": "STORIES",
        "image_url": image_url,
        "access_token": token,
    })
    return r["id"]


def publish(ig_user, creation_id, token):
    return _post(f"{ig_user}/media_publish", {
        "creation_id": creation_id,
        "access_token": token,
    })


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "prices.json"
    data = json.load(open(path, encoding="utf-8"))
    ver = data["date_raw"].replace("/", "")

    ig_user = os.environ["IG_USER_ID"]
    token = os.environ["IG_ACCESS_TOKEN"]
    base = os.environ["PAGES_BASE_URL"].rstrip("/")

    for i in range(1, 6):
        url = f"{base}/stories/stories_{i}.png?v={ver}"
        cid = create_container(ig_user, url, token)
        time.sleep(5)  # コンテナ処理待ち
        res = publish(ig_user, cid, token)
        print(f"  投稿 {i}/5: {res}")
        time.sleep(3)  # レート制限に配慮

    print("OK: ストーリーズ5枚を投稿しました。")


if __name__ == "__main__":
    main()
