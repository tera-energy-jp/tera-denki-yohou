# -*- coding: utf-8 -*-
"""
build_alerts.py — 価格アラート判定＆配信本文の生成
--------------------------------------------------
prices.json（翌日のエリアプライス・9エリア×48コマ）を読み、
alert_config.py の多段階しきい値で各エリアの発火レベルを判定する。
Lv2（注意）以上のエリアについて、配配メールに貼り付けるアラート本文（.txt）と、
オペレーター向けのサマリー（_summary.txt）を出力する。

パイプライン上の位置: fetch_jepx.py → build_prices.py → [build_alerts.py] → 手動GO → 配配で送信

使い方:
    python scripts/build_alerts.py [prices.json]   # 省略時は docs/prices.json

出力:
    docs/alerts/<YYYYMMDD>/<エリア>_<レベル>.txt   … 配配に貼る 件名＋本文
    docs/alerts/<YYYYMMDD>/_summary.txt            … 全エリア判定一覧＋運用手順
"""
import os
import sys
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import alert_config as cfg  # noqa: E402

REPO = SCRIPT_DIR.parent
# 出力先は公開ルート(docs/)の外に置く（GitHub Pages 公開事故の防止）。
# ALERT_OUT_DIR で上書き可能（既定: <repo>/_alerts_out・.gitignore済み）。
ALERTS_ROOT = Path(os.environ["ALERT_OUT_DIR"]) if os.environ.get("ALERT_OUT_DIR") else (REPO / "_alerts_out")
WEB_URL = "https://tera-energy-jp.github.io/tera-denki-yohou/"
TEMPLATE_PATH = SCRIPT_DIR / "templates" / "alert_mail_template.html"
LEVEL_COLORS = {2: "#E1AF00", 3: "#EE8B1F", 4: "#C0531E"}  # 注意/警戒/重大


def slot_to_time(slot):
    """48コマ制の slot 番号（0始まり・30分刻み）→ 'HH:MM' 開始時刻。"""
    h, m = divmod((slot % 48) * 30, 60)
    return f"{h:02d}:{m:02d}"


def high_windows(prices, floor):
    """しきい値 floor 以上が続く時間帯を、連続する区間ごとに列挙して返す。

    最高値の1コマ（30分）だけを示すと、実際には数時間高い日でも
    「30分だけ高い」と誤解させてしまうため、超過している帯を全部返す。
    離れた区間（例: 早朝と深夜）は繋げず別区間として扱う。
    戻り値: ["18:30 〜 21:00", ...]
    """
    idx = [i for i, v in enumerate(prices) if v >= floor]
    runs = []
    for i in idx:
        if runs and i == runs[-1][-1] + 1:
            runs[-1].append(i)
        else:
            runs.append([i])
    return [f"{slot_to_time(r[0])} 〜 {slot_to_time(r[-1] + 1)}" for r in runs]


def peak_window(prices):
    """日内最高値と、それが出る30分コマの開始時刻を返す。"""
    peak = max(prices)
    idx = prices.index(peak)
    return peak, slot_to_time(idx)


# --- 段階別の文面パーツ（叩き台。最終文言・フッターは追って確定） -----------
_HEAD = {
    2: "明日は電力価格が高くなります。",
    3: "明日は電力価格がかなり高くなります。",
    4: "【重要】明日は電力価格が極端に高騰します。",
}
_ADVICE = {
    2: "電気を多く使う家事や設備の稼働を、価格が落ち着く時間帯に少しずらしていただくと、負担をやわらげられます。",
    3: "可能な範囲で、この時間帯の電気のご使用を控えめにすることをおすすめします。",
    4: "この時間帯の不要不急のご使用は、できるだけお控えください。状況に応じて、お電話でも重ねてご案内する場合があります。",
}


def build_subject(area, label, date_label):
    """配信メールの件名。配配・Slack通知の両方でこの1箇所を使う。"""
    return f"【テラエナジーでんき】{label}：明日 {date_label} {area}エリアの電力価格にご注意ください"


def build_body(area, level, label, peak, peak_at, windows, date_label):
    """配配に貼り付ける 件名・本文（プレーンテキスト叩き台）を返す。"""
    yen = f"{peak:.2f}円"  # 確定値なので約なし・小数2桁（JEPX刻みと一致）
    win = "、".join(windows)  # 閾値以上の帯をすべて列挙
    subject = build_subject(area, label, date_label)
    body = f"""{area}エリアのお客さまへ

{_HEAD[level]}
{date_label}の{area}エリアは、下記の価格水準となることが確定しています。

■ 確定した価格水準（JEPXエリアプライス）
　日内最高値：{yen}/kWh（{peak_at} ごろ）
　高い時間帯：{win}

■ おすすめの過ごし方
　{_ADVICE[level]}

翌日の30分ごとの価格推移は、でんき予報でご確認いただけます。
　{WEB_URL}

──────────────────────
このメールは、市場連動プランをご契約のお客さまに、電気料金に関わる
価格情報としてお送りしています（広告メールではありません）。
上記は JEPX（日本卸電力取引所）のエリアプライス（税抜）にもとづく確定値です。
実際のご請求額は、このエリアプライスに送電ロスを加味し、託送料金・
再エネ発電賦課金・容量拠出金・弊社手数料を加えて算出されます。
※本メールは送信専用のため、ご返信いただいてもお答えできません。
お問い合わせは customer@tera-energy.com までお願いいたします。

TERA Energy株式会社　テラエナジーでんき
"""
    return subject, body


def build_html_body(area, level, label, peak, peak_at, windows, date_label):
    """配配のHTMLメールエディタに貼り付ける HTML本文を返す。"""
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    repl = {
        "LEVEL_COLOR": LEVEL_COLORS[level],
        "LEVEL_LABEL": label,
        "AREA": area,
        "DATE": date_label,
        "PEAK": f"{peak:.2f}円",
        "PEAK_TIME": "、".join(windows),
        "PEAK_AT": peak_at,
        "HEAD": _HEAD[level],
        "ADVICE": _ADVICE[level],
    }
    for k, v in repl.items():
        html = html.replace("{{" + k + "}}", str(v))
    return html


def main():
    prices_path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "docs" / "prices.json"
    data = json.loads(prices_path.read_text(encoding="utf-8"))
    date_label = data.get("date_label", "")
    date_slug = data.get("date_raw", "").replace("/", "")
    areas = data["areas"]

    # 全エリア判定
    results = []  # (area, lv, label, peak, peak_at, windows, push, low)
    for area, prices in areas.items():
        peak, peak_at = peak_window(prices)
        low = min(prices)  # 日内最安値（安い時間帯へのシフト余地の目安）
        lv, label = cfg.alert_level(area, peak)
        push, _, _ = cfg.should_push_mail(area, peak)
        # 「高い時間帯」の下限は、そのエリアで顧客に知らせる基準＝注意しきい値に揃える。
        windows = high_windows(prices, cfg.NOTICE_THRESHOLDS.get(area, peak))
        results.append((area, lv, label, peak, peak_at, windows, push, low))

    fired = [r for r in results if r[6]]  # Lv2（注意）以上＝プッシュ対象

    out_dir = ALERTS_ROOT / date_slug
    if fired:
        out_dir.mkdir(parents=True, exist_ok=True)
        for area, lv, label, peak, peak_at, windows, _, _low in fired:
            subject, body = build_body(area, lv, label, peak, peak_at, windows, date_label)
            (out_dir / f"{area}_{label}.txt").write_text(
                f"件名: {subject}\n\n{body}", encoding="utf-8")
            html = build_html_body(area, lv, label, peak, peak_at, windows, date_label)
            (out_dir / f"{area}_{label}.html").write_text(html, encoding="utf-8")

    # サマリー
    L = [f"=== 価格アラート判定  {date_label}  ({prices_path.name}) ===", ""]
    L.append("[全エリア判定]（日内最高値／最安値・税抜エリアプライス）")
    for area, lv, label, peak, peak_at, windows, push, low in results:
        mark = "★送信" if push else "  —"
        L.append(f"  {area:<4} 最高 {peak:>7.2f}円 / 最安 {low:>6.2f}円  Lv{lv} {label:<4} {mark}")
    L.append("")
    if fired:
        L.append(f"[配信対象] {len(fired)}エリア（Lv2 注意以上）")
        for area, lv, label, *_ in fired:
            L.append(f"  ・{area}（{label}）→ {area}_{label}.html（件名は {area}_{label}.txt 1行目）")
        L += [
            "",
            "[配配メールでの送信手順]",
            "  1. 配配メール管理画面にログイン（From＝カスタマー系）",
            "  2. 「エリア」セグメントで該当エリアを選択",
            "  3. 件名 = <エリア>_<レベル>.txt の1行目をコピー",
            "  4. 本文 = <エリア>_<レベル>.html をHTMLメールエディタに貼付",
            "  5. テスト配信で表示確認 → GO確認の上で本配信",
            "",
            "  ※価格アラートは配信停止なし・該当エリア全員へ送信。",
        ]
    else:
        L.append("[配信対象] なし（全エリア平常〜高め止まり。メール送信不要）")
    summary = "\n".join(L)

    if fired:
        (out_dir / "_summary.txt").write_text(summary, encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
