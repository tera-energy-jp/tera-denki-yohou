#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
でんき予報のPNG（カバー・エリア3枚・クロージング・豆知識の計6枚）を Instagram Stories に自動投稿するスクリプト。

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
import json
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


def wait_finished(creation_id, tries=20, interval=3, settle=3):
    """② コンテナの処理が FINISHED になるまで待つ

    【2026-08 修正】
    FINISHED は「publish が通る保証」ではない。Meta の status_code は
    結果整合のため、FINISHED 直後に publish を叩くと 9007
    （Media ID is not available）が返ることがある。
      - FINISHED 確認後に settle 秒だけ間を置く
      - 待ちの上限を 30秒 → 60秒 に延長
      - 状態確認GETの失敗を黙って素通りさせず警告を出す
    """
    last = None
    for _ in range(tries):
        r = requests.get(
            f"{API}/{creation_id}",
            params={"fields": "status_code,status", "access_token": ACCESS_TOKEN},
            timeout=30,
        )
        if not r.ok:
            print(f"    [警告] 状態確認に失敗: {r.status_code} {r.text}", file=sys.stderr)
            time.sleep(interval)
            continue

        s = r.json()
        last = s.get("status_code")

        if last == "FINISHED":
            time.sleep(settle)
            return True
        if last in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"コンテナ処理エラー({last}): {s}")

        time.sleep(interval)

    raise TimeoutError(
        f"コンテナが時間内にFINISHEDになりませんでした: {creation_id} (last={last})"
    )


def publish(creation_id, tries=5, base_wait=8):
    """③ コンテナを公開し、投稿された media_id を返す

    【2026-08 修正】
    9007 / subcode 2207027（Media ID is not available）のときだけ
    一時エラーとみなして指数バックオフで再試行する。
    待ち時間: 8秒 → 16秒 → 32秒 → 64秒（最大 約2分）
    それ以外のエラー（トークン切れ等）は従来どおり即座に失敗させる。
    """
    for attempt in range(1, tries + 1):
        r = requests.post(
            f"{API}/{IG_USER_ID}/media_publish",
            data={"creation_id": creation_id, "access_token": ACCESS_TOKEN},
            timeout=60,
        )
        if r.ok:
            if attempt > 1:
                print(f"    {attempt}回目の試行で公開成功")
            return r.json()["id"]

        code = subcode = None
        try:
            err = r.json().get("error", {})
            code = err.get("code")
            subcode = err.get("error_subcode")
        except ValueError:
            pass

        is_not_ready = (code == 9007) or (subcode == 2207027)

        if is_not_ready and attempt < tries:
            wait = base_wait * (2 ** (attempt - 1))
            print(
                f"    [警告] 公開の準備が未完了(9007)。{wait}秒待って再試行 "
                f"({attempt}/{tries - 1})",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue

        print(f"[エラー] 公開に失敗: {r.status_code} {r.text}", file=sys.stderr)
        r.raise_for_status()

    raise RuntimeError(f"9007 が {tries} 回続いたため中断: {creation_id}")


STATE_FILE = ".ig_state.json"


def delivery_date_key():
    """進捗ファイルのキー。配信日（prices.json の date_raw）で日替わりリセットする。"""
    try:
        with open("prices.json", encoding="utf-8") as f:
            return json.load(f)["date_raw"].replace("/", "")
    except Exception:
        return "unknown"


def load_posted(date_key):
    """すでに投稿済みの {画像名: media_id} を返す。日付が変わっていれば空。

    ⑧が途中で落ちた日に、次の起動が1枚目から投稿し直して
    Storiesに二重投稿されるのを防ぐための進捗記録。
    """
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        return {}
    if st.get("date") != date_key:
        return {}
    return st.get("posted", {}) or {}


def save_posted(date_key, posted):
    """1枚公開するごとに呼ぶ。途中で落ちても進捗が残るよう即時に書く。"""
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"date": date_key, "posted": posted}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def cache_buster():
    """画像URLに付けるバージョン文字列（その日の配信日付）。

    PNGのファイル名が毎日同じなので、素のURLだと GitHub Pages や
    Meta 側のCDNが前日の画像をキャッシュから返す恐れがある。
    クエリを日替わりにすることで必ず最新を取りに行かせる。
    """
    try:
        with open("prices.json", encoding="utf-8") as f:
            return json.load(f)["date_raw"].replace("/", "")
    except Exception:
        return time.strftime("%Y%m%d%H%M")


def main():
    # 投稿対象の画像（docs/stories/stories_1.png ... をファイル名順に）
    files = sorted(glob.glob("docs/stories/stories_*.png"))
    if not files:
        print("[エラー] 投稿する画像（docs/stories/stories_*.png）が見つかりません。", file=sys.stderr)
        sys.exit(1)

    ver = cache_buster()
    date_key = delivery_date_key()
    posted = load_posted(date_key)
    if posted:
        print(f"※前回の実行で {len(posted)}枚 が投稿済みです（{date_key}）。残りだけ投稿します。")
    print(f"=== Instagram Stories 投稿開始（{len(files)}枚 / v={ver}） ===")
    newly = 0
    for i, path in enumerate(files, 1):
        name = os.path.basename(path)
        if name in posted:
            print(f"[{i}/{len(files)}] {name} → 投稿済みのためスキップ（media_id={posted[name]}）")
            continue
        image_url = f"{PAGES_BASE_URL}/stories/{name}?v={ver}"
        print(f"[{i}/{len(files)}] {name} → {image_url}")

        creation_id = create_container(image_url)
        wait_finished(creation_id)
        media_id = publish(creation_id)
        print(f"    公開完了 media_id={media_id}")

        # 1枚ごとに進捗を保存する。ここで落ちても、次の起動は残りだけを投稿する。
        posted[name] = media_id
        save_posted(date_key, posted)
        newly += 1

        # 連続投稿のレート対策（最後の1枚の後は待たない）
        if i < len(files):
            time.sleep(5)

    if newly == 0:
        print("=== すべて投稿済みでした（新規投稿なし） ===")
    else:
        print(f"=== Storiesの投稿が完了しました（新規{newly}枚 / 全{len(files)}枚） ===")


if __name__ == "__main__":
    main()
