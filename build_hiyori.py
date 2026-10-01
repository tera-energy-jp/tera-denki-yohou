# -*- coding: utf-8 -*-
"""
build_hiyori.py — でんき日和（安値のお知らせ）の判定＆配信本文の生成
====================================================================
prices.json（翌日のエリアプライス・9エリア×48コマ）を読み、
hiyori_config.py のローリング相対基準で各エリアの発火を判定する。
発火したエリアについて、配配メールに貼り付ける本文（.html / .txt）と、
オペレーター向けのサマリー（_summary.txt）を出力する。

build_alerts.py（高値アラート）とは独立して動く。高値側は運用中のため、
そこに手を入れずに済むよう別スクリプトにしている。出力の形は揃えてある。

パイプライン上の位置:
    fetch_jepx.py → build_prices.py → [build_hiyori.py] → 手動GO → 配配で送信

前提:
    data/low_history.json が存在すること（init_low_history.py で初期構築）。
    このスクリプトは判定のたびに当日ぶんを履歴へ追記する。

使い方:
    python scripts/build_hiyori.py [prices.json]    # 省略時は docs/prices.json
    python scripts/build_hiyori.py --dry-run        # 履歴に追記せず判定だけ行う

出力:
    _alerts_out/<YYYYMMDD>/<エリア>_日和.html   … 配配に貼る本文
    _alerts_out/<YYYYMMDD>/<エリア>_日和.txt    … 件名＋テキスト版
    _alerts_out/<YYYYMMDD>/_hiyori_summary.txt  … 全エリア判定一覧＋運用手順
"""
import os
import sys
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import hiyori_config as hc  # noqa: E402

REPO = SCRIPT_DIR.parent
DATA_DIR = REPO / "data"
HISTORY_PATH = DATA_DIR / hc.HISTORY_FILENAME
# 出力先は公開ルート(docs/)の外。build_alerts.py と同じ置き場に揃える。
ALERTS_ROOT = Path(os.environ["ALERT_OUT_DIR"]) if os.environ.get("ALERT_OUT_DIR") else (REPO / "_alerts_out")
TEMPLATE_PATH = SCRIPT_DIR / "templates" / "hiyori_mail_template.html"
WEB_URL = "https://tera-energy-jp.github.io/tera-denki-yohou/"


# --- 文面パーツ -------------------------------------------------------------
# 高値アラートが「備えてください」なら、日和は「使ってみてください」。
# 同じ市場連動プランの両面であることが伝わる書き方にする。
_HEAD = "明日は、電気がとても安くなる時間帯があります。"
_ADVICE = ("洗濯や食洗機、電気自動車の充電など、時間をずらせる電気の使い方を"
           "この時間帯に寄せていただくと、電気代をおさえられます。")
_ADVICE_LONG = ("まとまった時間続きますので、ふだんは夜にまわしている家事を"
                "この時間帯に動かしてみるのもおすすめです。")
LONG_HOURS = 6.0    # この時間以上続くときは _ADVICE_LONG を添える
SUB_WINDOW_MIN = 1.5  # 2本目以降の安値帯は、この時間以上のものだけ紹介する
                      # （30分だけ安くても行動できず、並べるとノイズになる）


def load_history():
    if not HISTORY_PATH.exists():
        sys.exit(
            f"履歴ファイルがありません: {HISTORY_PATH}\n"
            f"先に `python scripts/init_low_history.py` を実行してください。")
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))


def save_history(history):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=0, sort_keys=True),
        encoding="utf-8")


def thresholds_for(history, target_date):
    """target_date の判定に使うしきい値を、エリアごとに返す。

    その日より前の履歴だけを参照する（当日を含めると自己参照になる）。
    平滑化（前日比 ±MAX_STEP）は較正時と同じく、履歴の先頭から日ごとに
    しきい値を連鎖的に求めて prev を引き継ぐ。前日1日だけを見る方式だと
    前日が跳ねた日に今日も跳ねてしまい、平滑化が効かない。
    （履歴は1日9値なので、全日連鎖しても計算量は無視できる）
    """
    dates = sorted(d for d in history if d < target_date)
    out = {}
    for a in hc.AREAS:
        series = [history[d][a] for d in dates]
        if len(series) < hc.MIN_HISTORY_DAYS:
            out[a] = None
            continue
        prev = None
        for i in range(hc.MIN_HISTORY_DAYS, len(series) + 1):
            prev = hc.pick_threshold(series[:i], prev=prev)
        out[a] = prev
    return out


def out_name(area):
    """出力ファイルの基底名。<エリア>_日和 にして高値側（<エリア>_<レベル>）と形を揃える。

    notify_alert_slack.py / upload_alerts_drive.py は同じ日付フォルダの
    <エリア>_<ラベル>.txt を拾う。この形なら高値側のスクリプトに手を入れずに
    Slack通知が「東京 ｜ 日和」と出て、Driveにも同じフォルダに格納される。
    """
    return f"{area}_{hc.HIYORI_LABEL}"


def high_alert_fired(out_dir, area):
    """同じ日付フォルダに高値アラート（<エリア>_<レベル>.txt）が既にあるか。"""
    if not out_dir.exists():
        return False
    return any(p.name != f"{out_name(area)}.txt"
               for p in out_dir.glob(f"{area}_*.txt"))


def build_subject(area, date_label):
    return f"【テラエナジーでんき】{date_label} は電気が安い時間があります（{area}エリア）"


def format_window(win):
    """(開始slot, 終了slot+1, 時間) → '10:00 〜 15:30（5時間30分）'"""
    a, b, hours = win
    h = int(hours)
    m = int(round((hours - h) * 60))
    dur = f"{h}時間" + (f"{m}分" if m else "")
    return f"{hc.slot_to_time(a)} 〜 {hc.slot_to_time(b)}", dur


def format_price(avg):
    """平均単価を顧客向けの表記にする。

    安値帯は0.01円に張り付くことが多く、素直に小数1桁で丸めると
    「約0.0円」という不自然な表示になる。1円未満は実額を出し、
    ほぼ底値のときは「ほぼ0円」と言い切るほうが伝わる。
    """
    if avg < 0.02:
        return "ほぼ0円"
    if avg < 1.0:
        return f"約{avg:.2f}円"
    return f"約{avg:.1f}円"


def build_text(area, date_label, win, avg_price, all_windows):
    span, dur = format_window(win)
    lines = [
        f"{area}エリアのお客さまへ",
        "",
        _HEAD,
        "",
        f"■ 安い時間帯　{span}（{dur}）",
        f"　 この時間帯の平均　{format_price(avg_price)}/kWh",
    ]
    if len(all_windows) > 1:
        others = "、".join(
            f"{hc.slot_to_time(a)} 〜 {hc.slot_to_time(b)}"
            for a, b, h in all_windows
            if (a, b) != (win[0], win[1]) and h >= SUB_WINDOW_MIN)
        if others:
            lines.append(f"　 このほか {others} も安くなります")
    lines += [
        "",
        _ADVICE,
    ]
    if win[2] >= LONG_HOURS:
        lines.append(_ADVICE_LONG)
    lines += [
        "",
        f"30分ごとの価格推移はこちら： {WEB_URL}",
        "",
        "─────────────────────────────",
        "このメールは、市場連動プランをご契約のお客さまに、電気料金に関わる",
        "価格情報としてお送りしています（広告メールではありません）。",
        "上記はJEPX（日本卸電力取引所）のエリアプライス（税抜）にもとづく確定値です。",
        "実際のご請求額は、このエリアプライスに送電ロスを加味し、託送料金・",
        "再エネ発電賦課金・容量拠出金・弊社手数料を加えて算出されます。",
        "※本メールは送信専用のため、ご返信いただいてもお答えできません。",
        "　お問い合わせは customer@tera-energy.com までお願いいたします。",
        "",
        "TERA Energy株式会社　テラエナジーでんき",
        "〒615-0854 京都府京都市右京区西京極堤外町18-124",
    ]
    return "\n".join(lines)


def build_html(area, date_label, win, avg_price, all_windows):
    tpl = TEMPLATE_PATH.read_text(encoding="utf-8")
    span, dur = format_window(win)
    others = ""
    if len(all_windows) > 1:
        o = "、".join(
            f"{hc.slot_to_time(a)} 〜 {hc.slot_to_time(b)}"
            for a, b, h in all_windows
            if (a, b) != (win[0], win[1]) and h >= SUB_WINDOW_MIN)
        others = f"このほか {o} も安くなります" if o else ""
    advice = _ADVICE + (("<br>" + _ADVICE_LONG) if win[2] >= LONG_HOURS else "")
    repl = {
        "{{AREA}}": area,
        "{{DATE}}": date_label,
        "{{HEAD}}": _HEAD,
        "{{ADVICE}}": advice,
        "{{CHEAP_TIME}}": span,
        "{{CHEAP_DURATION}}": dur,
        "{{CHEAP_AVG}}": format_price(avg_price),
        "{{OTHER_WINDOWS}}": others,
        "{{THEME_COLOR}}": hc.HIYORI_COLOR,
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)
    return tpl


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    prices_path = Path(args[0]) if args else REPO / "docs" / "prices.json"

    data = json.loads(prices_path.read_text(encoding="utf-8"))
    date_label = data.get("date_label", "")
    date_raw = data.get("date_raw", "")
    date_key = date_raw.replace("/", "-") if date_raw else ""
    date_slug = date_raw.replace("/", "")
    areas = data["areas"]

    history = load_history()
    ths = thresholds_for(history, date_key)

    results = []   # (area, hours, threshold, fired, win, avg)
    for area in hc.AREAS:
        prices = areas.get(area)
        if not prices:
            results.append((area, None, ths.get(area), False, None, None))
            continue
        hours = hc.longest_cheap_hours(prices)
        th = ths.get(area)
        fired = hc.should_fire(hours, th)
        win = hc.longest_cheap_window(prices) if fired else None
        avg = None
        if win:
            seg = prices[win[0]:win[1]]
            avg = sum(seg) / len(seg)
        results.append((area, hours, th, fired, win, avg))

    out_dir = ALERTS_ROOT / date_slug
    # 同日に高値アラートが出ているエリアは、高値を優先して日和を見送る
    # （同じ顧客に「明日は高い」と「明日は安い」が同時に届くと混乱するため）。
    skipped = [r[0] for r in results if r[3] and high_alert_fired(out_dir, r[0])]
    fired = [r for r in results if r[3] and r[0] not in skipped]

    if fired:
        out_dir.mkdir(parents=True, exist_ok=True)
        for area, hours, th, _f, win, avg in fired:
            all_w = [(a, b, (b - a) / 2.0) for a, b in hc.cheap_runs(areas[area])]
            subject = build_subject(area, date_label)
            text = build_text(area, date_label, win, avg, all_w)
            (out_dir / f"{out_name(area)}.txt").write_text(
                f"件名: {subject}\n\n{text}", encoding="utf-8")
            (out_dir / f"{out_name(area)}.html").write_text(
                build_html(area, date_label, win, avg, all_w), encoding="utf-8")

    # --- サマリー ---------------------------------------------------------
    L = [f"=== でんき日和 判定  {date_label}  ({prices_path.name}) ===", ""]
    L.append(f"[判定方式] {hc.LOW_PRICE_LINE}円/kWh以下が続く最長時間 ≧ しきい値")
    L.append(f"           しきい値は直近{hc.WINDOW_DAYS}日から自動算出（目標 年{hc.TARGET_PER_YEAR}回）")
    L.append("")
    L.append("[全エリア判定]")
    for area, hours, th, f, _w, _a in results:
        mark = "★送信" if f else "  —"
        if area in skipped:
            mark = "見送り（高値アラート優先）"
        hs = f"{hours:>5.1f}h" if hours is not None else "   ―"
        ts = f"{th:>5.1f}h" if th is not None else "   ―"
        L.append(f"  {area:<4} 最長安値 {hs} / しきい値 {ts}  {mark}")
    L.append("")
    if fired:
        L.append(f"[配信対象] {len(fired)}エリア")
        for area, _h, _t, _f, win, avg in fired:
            span, dur = format_window(win)
            L.append(f"  ・{area}　{span}（{dur}）平均 {format_price(avg)}/kWh"
                     f"　→ {out_name(area)}.html")
        L += [
            "",
            "[配配メールでの送信手順]",
            "  1. 配配メール管理画面にログイン（From＝カスタマー系）",
            "  2. 「エリア」セグメントで該当エリアを選択",
            "  3. 件名 = <エリア>_日和.txt の1行目をコピー",
            "  4. 本文 = <エリア>_日和.html をHTMLメールエディタに貼付",
            "  5. テスト配信で表示確認 → GO確認の上で本配信",
            "",
            "  ※でんき日和も価格アラートと同じく配信停止なし・該当エリア全員へ送信。",
            "  ※高値アラートと同日に発火した場合は、高値を優先し日和は見送る。",
        ]
    else:
        L.append("[配信対象] なし（メール送信不要）")
    if skipped:
        L.append("")
        L.append("[見送り] 高値アラートと同日発火のため日和は送らない: " + "、".join(skipped))
    summary = "\n".join(L)

    if fired:
        (out_dir / "_hiyori_summary.txt").write_text(summary, encoding="utf-8")
    print(summary)

    # --- 履歴へ追記 --------------------------------------------------------
    if not dry_run and date_key:
        history[date_key] = {
            a: (hc.longest_cheap_hours(areas[a]) if areas.get(a) else 0.0)
            for a in hc.AREAS}
        save_history(history)
        print(f"\n履歴を更新しました（{date_key} を追記／全{len(history)}日）")
    elif dry_run:
        print("\n--dry-run のため履歴は更新していません。")


if __name__ == "__main__":
    main()
