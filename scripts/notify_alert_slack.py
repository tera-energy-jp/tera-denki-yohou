# -*- coding: utf-8 -*-
"""
notify_alert_slack.py — 価格アラート発火を Slack へ通知（Incoming Webhook）
--------------------------------------------------------------------------
build_alerts.py の当日発火フォルダを見て、発火があれば Slack へ
「対象日・エリア・レベル・件名・Driveリンク」を通知する。
発火が無い日は何も送らない（狼少年化させない）。

Webhook は添付非対応のため、本文HTMLは Drive リンク先から開く運用。
追加ライブラリ不要（標準の urllib のみ）。

環境変数:
  SLACK_ALERT_WEBHOOK_URL  通知先（未設定なら dry-run で内容表示のみ）
  ALERT_OUT_DIR            発火物の出力先（既定: <repo>/_alerts_out）
"""
import os
import json
from pathlib import Path
import urllib.request

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent


def _out_root():
    return Path(os.environ.get("ALERT_OUT_DIR", REPO / "_alerts_out"))


def _today_slug():
    prices = REPO / "docs" / "prices.json"
    if prices.exists():
        data = json.loads(prices.read_text(encoding="utf-8"))
        slug = data.get("date_raw", "").replace("/", "")
        if slug:
            return slug
    root = _out_root()
    dirs = sorted([p.name for p in root.glob("*") if p.is_dir()]) if root.exists() else []
    return dirs[-1] if dirs else ""


def _collect(day_dir):
    """発火エリア一覧と件名を <エリア>_<レベル>.txt から集める。"""
    items = []
    for txt in sorted(day_dir.glob("*.txt")):
        if txt.name.startswith("_"):
            continue
        area, _, label = txt.stem.partition("_")
        subject = ""
        lines = txt.read_text(encoding="utf-8").splitlines()
        if lines and lines[0].startswith("件名:"):
            subject = lines[0].replace("件名:", "").strip()
        items.append((area, label, subject))
    return items


def main():
    webhook = os.environ.get("SLACK_ALERT_WEBHOOK_URL", "").strip()
    slug = _today_slug()
    day_dir = _out_root() / slug if slug else None

    if not slug or not day_dir or not day_dir.exists():
        print(f"[slack] 本日の発火なし（{slug or '日付不明'}）。通知しません。")
        return

    items = _collect(day_dir)
    if not items:
        print("[slack] 発火エリアが見つかりません。通知しません。")
        return

    drive_url = ""
    p = day_dir / "_drive_url.txt"
    if p.exists():
        drive_url = p.read_text(encoding="utf-8").strip()

    date_label = slug
    prices = REPO / "docs" / "prices.json"
    if prices.exists():
        date_label = json.loads(prices.read_text(encoding="utf-8")).get("date_label", slug)

    lines = [f"*⚡ 価格アラート発火* — 対象日 {date_label}", ""]
    for area, label, subject in items:
        lines.append(f"• *{area}* ｜ {label}")
        if subject:
            lines.append(f"    件名: {subject}")
    lines.append("")
    if drive_url:
        lines.append(f"📁 本文HTML（Driveから開いて配配に貼付）: {drive_url}")
    else:
        lines.append("📁 Driveリンクなし（アップロード未実行/失敗の可能性）")
    lines.append("")
    lines.append("→ 『配信操作手順書』に沿って、テスト配信 → GO → 本配信をお願いします。")
    text = "\n".join(lines)

    if not webhook:
        print("[slack][dry-run] SLACK_ALERT_WEBHOOK_URL 未設定。送信予定の内容:")
        print(text)
        return

    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(f"[slack] 送信完了 (HTTP {resp.status})")


if __name__ == "__main__":
    main()
