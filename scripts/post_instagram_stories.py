#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
でんき予報の5枚PNGを Instagram Stories に自動投稿するスクリプト。

仕組み（Graph API の2段階フロー・各画像ごとに繰り返す）:
  1) コンテナ作成  POST /{ig-user-id}/media   （media_type=STORIES, image_url=公開URL）
  2) 状態を確認    GET  /{creation-id}        （FINISHED になるまで待つ）
  3) 公開          POST /{ig-user-id}/media_publish

必要な環境変数（GitHub Secrets / Variables から渡す）:
  - IG_ACCESS_TOKEN : 長命アクセストークン（60日）
  - IG_USER_ID      : Instagram Business Account ID（17841434541981596）
  - PAGES_BASE_URL  : GitHub Pages の公開URLのベース（例 https://tera-energy-jp.github.io/tera-denki-yohou）
"""

import os
import sys
import glob
import time
import requests

API_VERSION = "v21.0"
API = f"https://graph.facebook.com/{API_VERSION}"

# --- 環境変数の読み込み（無ければ分かりやすく終了） ---
def env(name):
    v = os.environ.get(name)
    if not v:
        print(f"[エラー] 環境変数 {name} が設定されていません。", file=sys.stderr)
        sys.exit(1)
    return v

IG_USER_ID     = env("IG_USER_ID")
ACCESS_TOKEN   = env("IG_ACCESS_TOKEN")
PAGES_BASE_URL = env("PAGES_BASE_URL").rstrip("/")


def create_container(image_url):
    """① Storiesコンテナを作成し、creation_id を返す"""
    r = requests.post(
        f"{API}/{IG_USER_ID}/media",
        data={
            "image_url": image_url,
            "media_type": "STORIES",
            "access_token": ACCESS_TOKEN,
        },
        timeout=60,
    )
    # 失敗時は中身を表示して止める（トークン切れ・URL不正などをここで検知）
    if not r.ok:
        print(f"[エラー] コンテナ作成に失敗: {r.status_code} {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json()["id"]


def wait_finished(creation_id, tries=10, interval=3):
    """② コンテナの処理が FINISHED になるまで待つ"""
    for _ in range(tries):
        s = requests.get(
            f"{API}/{creation_id}",
            params={"fields": "status_code", "access_token": ACCESS_TOKEN},
            timeout=30,
        ).json()
        code = s.get("status_code")
        if code == "FINISHED":
            return True
        if code == "ERROR":
            raise RuntimeError(f"コンテナ処理エラー: {s}")
        time.sleep(interval)
    raise TimeoutError(f"コンテナが時間内にFINISHEDになりませんでした: {creation_id}")


def publish(creation_id):
    """③ コンテナを公開し、投稿された media_id を返す"""
    r = requests.post(
        f"{API}/{IG_USER_ID}/media_publish",
        data={"creation_id": creation_id, "access_token": ACCESS_TOKEN},
        timeout=60,
    )
    if not r.ok:
        print(f"[エラー] 公開に失敗: {r.status_code} {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json()["id"]


def main():
    # 投稿対象の画像（docs/stories/stories_1.png ... をファイル名順に）
    files = sorted(glob.glob("docs/stories/stories_*.png"))
    if not files:
        print("[エラー] 投稿する画像（docs/stories/stories_*.png）が見つかりません。", file=sys.stderr)
        sys.exit(1)

    print(f"=== Instagram Stories 投稿開始（{len(files)}枚） ===")
    for i, path in enumerate(files, 1):
        name = os.path.basename(path)
        image_url = f"{PAGES_BASE_URL}/stories/{name}"
        print(f"[{i}/{len(files)}] {name} → {image_url}")

        creation_id = create_container(image_url)
        wait_finished(creation_id)
        media_id = publish(creation_id)
        print(f"    公開完了 media_id={media_id}")

        # 連続投稿のレート対策（最後の1枚の後は待たない）
        if i < len(files):
            time.sleep(5)

    print("=== 全Storiesの投稿が完了しました ===")


if __name__ == "__main__":
    main()
