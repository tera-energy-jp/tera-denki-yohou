# -*- coding: utf-8 -*-
"""
hiyori_config.py — でんき日和（安値のお知らせ）の判定設定とロジック
====================================================================
高値アラート（alert_config.py）の対になる、安値側の判定。
ただし判定の考え方は高値と対称ではない。理由は次のとおり。

    高値は上限200円/kWhまで青天井に分布が伸びるが、安値は0.01円で床にぶつかる。
    JEPXの下限が0.01円のため、安い日の大半がそこに張り付き、価格では日ごとの
    順位がつかない（九州は「最安3時間平均≦1.0円」の日が年133回あり、価格を
    いくら下げても年16回に絞れない）。
    → そこで判定軸を「価格」ではなく **安い時間の長さ** にした。

さらに、固定しきい値では年ごとの変動に追従できないことが実測で判明した。
    FY2023は全国293日発火／FY2025は48日。4年平均で較正した固定しきい値を
    当てると、FY2025の西日本は年1〜3日しか発火しない。
    → **直近90日の分布から毎日しきい値を再計算する**ローリング相対方式にした。
    副次効果として季節偏りも解消した（5月70回・1月0.2回 → 4月44回・2月10回）。

判定の流れ:
    1. その日の48コマのうち LOW_PRICE_LINE 以下のコマを「安コマ」とする
    2. 安コマが連続した最長の長さ（時間）をその日の指標とする
    3. 直近 WINDOW_DAYS 日の指標の分布から、目標発火数に最も近い候補を
       しきい値として選ぶ（前日比 ±MAX_STEP に制限して急変を抑える）
    4. 当日の指標がしきい値以上なら「でんき日和」発火

較正の根拠: 2021-04-01〜2026-09-15（1994日）のJEPXスポット実績で検証済み。
            詳細は Vault_take/99_りんの記憶/2026-09-14_でんき日和_判定ロジック確定.md
"""

AREAS = ['北海道', '東北', '東京', '中部', '北陸', '関西', '中国', '四国', '九州']

# --- 判定パラメータ（すべて実データ検証で確定した値）-----------------------

LOW_PRICE_LINE = 1.0   # この価格以下（円/kWh・税抜エリアプライス）を「安コマ」とする
WINDOW_DAYS = 90       # しきい値算出に使う直近日数。365日は追従が1年遅れて逆効果だった
TARGET_PER_YEAR = 14   # 目標発火数。離散性により実績は14〜17回に着地する
MIN_HOURS = 3.0        # 絶対下限。これ未満の日は相対的に上位でも発火させない
MAX_STEP = 0.5         # しきい値の1日あたり変化上限。短い窓での跳ねを抑える

# 履歴ファイル（{"YYYY-MM-DD": {"東京": 4.5, ...}, ...}）
HISTORY_FILENAME = "low_history.json"

# 発火に必要な最低日数。これ未満しか履歴がないうちは判定しない（初期の誤発火防止）
MIN_HISTORY_DAYS = WINDOW_DAYS

HIYORI_LABEL = "日和"       # 出力ファイル名などに使う短い呼称
HIYORI_COLOR = "#6496C8"    # TERAブランドのブルー（フィラメント）。高値の暖色と対にする


def slot_to_time(slot):
    """48コマ制の slot 番号（0始まり・30分刻み）→ 'HH:MM' 開始時刻。"""
    h, m = divmod((slot % 48) * 30, 60)
    return f"{h:02d}:{m:02d}"


def cheap_runs(prices, line=LOW_PRICE_LINE):
    """安コマが連続する区間を [(開始slot, 終了slot+1), ...] で返す。"""
    runs = []
    for i, v in enumerate(prices):
        if v <= line:
            if runs and i == runs[-1][1]:
                runs[-1][1] = i + 1
            else:
                runs.append([i, i + 1])
    return [tuple(r) for r in runs]


def longest_cheap_hours(prices, line=LOW_PRICE_LINE):
    """その日の『安コマが続いた最長の時間』（時間・0.5刻み）を返す。"""
    runs = cheap_runs(prices, line)
    if not runs:
        return 0.0
    return max(b - a for a, b in runs) / 2.0


def longest_cheap_window(prices, line=LOW_PRICE_LINE):
    """最長の安値帯を (開始slot, 終了slot+1, 時間) で返す。無ければ None。"""
    runs = cheap_runs(prices, line)
    if not runs:
        return None
    a, b = max(runs, key=lambda r: r[1] - r[0])
    return a, b, (b - a) / 2.0


def pick_threshold(history_hours, target_per_year=TARGET_PER_YEAR,
                   window_days=WINDOW_DAYS, min_hours=MIN_HOURS, prev=None,
                   max_step=MAX_STEP):
    """直近の指標リストから、その日のしきい値（時間）を決める。

    連続時間は0.5h刻みの離散値で、分位点付近に同値の日が大量にある。
    分位点を丸める方式では該当日数が桁で変わって過剰発火するため、
    「目標に最も近い日数が発火する候補」を総当たりで選ぶ。
    同数で並ぶ場合は厳しい側（時間が長いほう）を採る——送りすぎより
    送らなすぎのほうが害が小さいため。

    prev を渡すと、前日のしきい値からの変化を ±max_step に制限する。
    """
    if len(history_hours) < window_days:
        return None
    window = history_hours[-window_days:]
    target = target_per_year * window_days / 365.0

    hi = max([min_hours] + list(window))
    cands = []
    h = min_hours
    while h <= hi + 1e-9:
        cands.append(round(h, 1))
        h += 0.5

    best, best_gap = cands[0], None
    for c in cands:                      # 昇順に見て、同点なら後勝ち＝厳しい側
        n = sum(1 for v in window if v >= c)
        gap = abs(n - target)
        if best_gap is None or gap <= best_gap:
            best, best_gap = c, gap

    if prev is not None:
        best = min(max(best, prev - max_step), prev + max_step)
        best = max(best, min_hours)
    return round(best, 1)


def should_fire(hours, threshold):
    """その日の指標としきい値から、発火するかを返す。"""
    if threshold is None:
        return False
    return hours >= threshold
