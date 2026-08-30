# -*- coding: utf-8 -*-
"""
notify_alert_slack.py — 価格アラート発火を Slack へ通知（Incoming Webhook）
--------------------------------------------------------------------------
build_alerts.py の当日発火フォルダを見て、発火があれば Slack へ
「対象日・エリア・レベル・最高値/最安値・件名・Driveリンク」を通知する。
発火が無い日は何も送らない（狼少年化させない）。

最高値・最安値は prices.json（判定に使ったのと同じファイル）から直接計算する。
サマリーのドキュメントを開かなくても、Slack通知だけで水準が分かるようにするため
（2026-08 現場フィードバック反映）。

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


def _prices_json():
    """判定に使った prices.json のパス。ALERT_PRICES_JSON 最優先、既定 docs/prices.json。"""
    pj = os.environ.get("ALERT_PRICES_JSON", "").strip()
    return Path(pj) if pj else (REPO / "docs" / "prices.json")


def _today_slug():
    """対象日のスラッグ YYYYMMDD。ALERT_PRICES_JSON→docs/prices.json→最新フォルダの順。"""
    pj = _prices_json()
    if pj.exists():
        data = json.loads(pj.read_text(encoding="utf-8"))
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


def _price_stats():
    """エリア別の（日内最高値, 日内最安値）。prices.json が読めなければ空dict。

    価格が取れない異常時でも通知自体は止めない（価格の行だけ省く）。
    """
    pj = _prices_json()
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
        return {a: (max(v), min(v)) for a, v in data.get("areas", {}).items() if v}
    except Exception as e:
        print(f"[slack] 価格データを読めませんでした（価格表示なしで通知継続）: {e}")
        return {}


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
    pj = _prices_json()
    if pj.exists():
        date_label = json.loads(pj.read_text(encoding="utf-8")).get("date_label", slug)

    stats = _price_stats()

    lines = [f"*⚡ 価格アラート発火* — 対象日 {date_label}", ""]
    for area, label, subject in items:
        line = f"• *{area}* ｜ {label}"
        if area in stats:
            peak, low = stats[area]
            line += f"：最高値 {peak:.2f}円 ／ 最安値 {low:.2f}円"
        lines.append(line)
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
