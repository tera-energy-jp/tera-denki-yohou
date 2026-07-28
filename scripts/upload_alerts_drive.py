# -*- coding: utf-8 -*-
"""
upload_alerts_drive.py — 価格アラート発火物を Google Drive へ格納（キーレス/ADC）
------------------------------------------------------------------------------
build_alerts.py が生成した当日の発火フォルダ（_alerts_out/<YYYYMMDD>/）を、
指定した Drive 親フォルダの下に「日付サブフォルダ」を作ってアップロードする。

認証は Application Default Credentials（ADC）。GitHub Actions では
google-github-actions/auth（Workload Identity Federation）が ADC を用意する。
ローカルや認証情報が無い環境では「アップロード予定の内容」を表示するだけで
安全に終了する（dry-run）。発火が無い日は何もしない。

環境変数:
  ALERT_DRIVE_PARENT_ID   格納先の親フォルダID（未設定なら dry-run）
  ALERT_OUT_DIR           発火物の出力先（既定: <repo>/_alerts_out）

出力:
  <出力先>/<YYYYMMDD>/_drive_url.txt に、作成した Drive フォルダのURLを書き出す
  （notify_alert_slack.py がこれを読んで Slack にリンクを載せる）
"""
import os
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent

DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
SCOPES = ["https://www.googleapis.com/auth/drive"]


def _out_root():
    return Path(os.environ.get("ALERT_OUT_DIR", REPO / "_alerts_out"))


def _today_slug():
    """対象日（翌日）のスラッグ YYYYMMDD。docs/prices.json 優先、無ければ最新フォルダ。"""
    prices = REPO / "docs" / "prices.json"
    if prices.exists():
        data = json.loads(prices.read_text(encoding="utf-8"))
        slug = data.get("date_raw", "").replace("/", "")
        if slug:
            return slug
    root = _out_root()
    dirs = sorted([p.name for p in root.glob("*") if p.is_dir()]) if root.exists() else []
    return dirs[-1] if dirs else ""


def main():
    parent_id = os.environ.get("ALERT_DRIVE_PARENT_ID", "").strip()
    slug = _today_slug()
    day_dir = _out_root() / slug if slug else None

    if not slug or not day_dir or not day_dir.exists():
        print(f"[upload] 本日の発火フォルダなし（{slug or '日付不明'}）。アップロードはスキップします。")
        return

    files = sorted(p for p in day_dir.iterdir()
                   if p.is_file() and p.name != "_drive_url.txt")
    if not files:
        print(f"[upload] {day_dir} にファイルがありません。スキップします。")
        return

    if not parent_id:
        print("[upload][dry-run] ALERT_DRIVE_PARENT_ID 未設定のため送信しません。")
        print(f"  格納予定フォルダ: {slug}")
        for f in files:
            print(f"    - {f.name}")
        return

    # --- ADC で認証（無ければ dry-run） ---
    try:
        import google.auth
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        creds, _ = google.auth.default(scopes=SCOPES)
    except Exception as e:
        print(f"[upload][dry-run] 認証情報が使えないため送信しません（{e.__class__.__name__}: {e}）。")
        print(f"  格納予定フォルダ: {slug} / 親: {parent_id}")
        for f in files:
            print(f"    - {f.name}")
        return

    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    # 日付サブフォルダを作成（親フォルダの下、共有ドライブ対応）
    folder = service.files().create(
        body={"name": slug, "mimeType": DRIVE_FOLDER_MIME, "parents": [parent_id]},
        fields="id, webViewLink",
        supportsAllDrives=True,
    ).execute()
    folder_id = folder["id"]
    folder_url = folder.get("webViewLink", "")

    for f in files:
        mime = "text/html" if f.suffix == ".html" else "text/plain; charset=utf-8"
        media = MediaFileUpload(str(f), mimetype=mime, resumable=False)
        service.files().create(
            body={"name": f.name, "parents": [folder_id]},
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        print(f"[upload] {f.name} → Drive")

    (day_dir / "_drive_url.txt").write_text(folder_url, encoding="utf-8")
    print(f"[upload] 完了: {folder_url}")


if __name__ == "__main__":
    main()
