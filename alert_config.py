# -*- coding: utf-8 -*-
"""
でんき予報アラート 設定
-----------------------
エリア別の高騰しきい値（円/kWh・税抜のエリアプライス）。
2022/04〜2026/06 の5年実績から「日内最高値がこの値を超える日 ≒ 月2回」になる
ように逆算した初期値。運用しながらこの数字だけ調整すればよい。

判定方式: その日の48コマのうち「日内最高値」がしきい値を超えたら高騰とみなす。
"""

# 月2回ベースのエリア別しきい値（円/kWh）
THRESHOLDS = {
    "北海道": 44,
    "東北":   43,
    "東京":   45,
    "中部":   40,
    "北陸":   40,
    "関西":   39,
    "中国":   38,
    "四国":   37,
    "九州":   36,
}

# === メールアラート用：エリア別・多段階の判定しきい値 =====================
# 判定軸はすべて「その日の日内最高値（円/kWh・エリアプライス税抜）」。
# 完全4年度（FY2022〜2025・1461日）のJEPXスポット実績から、発火頻度（日/年）
# ベースで較正した確定値。運用しながらこの数字だけ調整すればよい。
#
#   高め (Lv1) = THRESHOLDS         月2回・24日/年 … Instagram＋希望者メールのみ（全顧客プッシュなし）
#   注意 (Lv2) = NOTICE_THRESHOLDS  月1回・12日/年 … 全顧客メール プッシュ開始（該当エリア）
#   警戒 (Lv3) = WARNING_THRESHOLDS 年4回・ 4日/年 … 全顧客メール＋円換算
#   重大 (Lv4) = SEVERE_LINE        150円・絶対値  … 全顧客メール＋電話フォロー（高圧は電話重点）
#
# ※「狼少年化」を避けるため、全顧客へのメールプッシュは Lv2（注意）以上に集約する。
#   Lv1（高め）は情報提供どまりで、でんき予報／Instagram と希望者メールで扱う。
#   顧客告知（上手な使い方ガイド）の「注意・警戒・重大の三段階」＝ Lv2〜4 と一致。

# 注意（月1回・12日/年）
NOTICE_THRESHOLDS = {
    "北海道": 51, "東北": 50, "東京": 50, "中部": 50, "北陸": 45,
    "関西": 45, "中国": 45, "四国": 45, "九州": 41,
}

# 警戒（年4回・4日/年）
WARNING_THRESHOLDS = {
    "北海道": 70, "東北": 70, "東京": 70, "中部": 70, "北陸": 55,
    "関西": 55, "中国": 52, "四国": 52, "九州": 50,
}

# 重大（全国共通・絶対値）。4年間で発火は東京4日/北海道1日/東北1日のみ＝極端高騰時。
SEVERE_LINE = 150  # 円/kWh

# レベル属性表（番号, 呼称, 全顧客メールプッシュ, チャネル）
ALERT_LEVELS = [
    (0, "—",    False, "なし"),
    (1, "高め", False, "Instagram＋希望者メール"),
    (2, "注意", True,  "全顧客メール（該当エリア）"),
    (3, "警戒", True,  "全顧客メール＋円換算"),
    (4, "重大", True,  "全顧客メール＋電話フォロー"),
]


def alert_level(area, peak):
    """エリアと日内最高値(円/kWh) → (レベル番号0-4, 呼称)。0=発火なし。"""
    if peak >= SEVERE_LINE:
        return 4, "重大"
    if peak >= WARNING_THRESHOLDS.get(area, float("inf")):
        return 3, "警戒"
    if peak >= NOTICE_THRESHOLDS.get(area, float("inf")):
        return 2, "注意"
    if peak >= THRESHOLDS.get(area, float("inf")):
        return 1, "高め"
    return 0, "—"


def should_push_mail(area, peak):
    """全顧客メールを送るべきか（Lv2 注意以上）。→ (bool, レベル番号, 呼称)。"""
    lv, label = alert_level(area, peak)
    return lv >= 2, lv, label


# でんき予報 表示用の5段階レベル（判定＝その日の「日内最高値」・円/kWh）
# ※ 絶対的な価格水準ベース。メールアラート用の THRESHOLDS（上）とは別物。
PRICE_LEVELS = [
    # (この値未満なら該当, ラベル, 色)。最後の None は「それ以上すべて」
    (8,    "とてもおだやか", "#5A9E2F"),  # 〜8円
    (11,   "おだやか",       "#8FB23A"),  # 8〜11円
    (17,   "ふつう",         "#E1AF00"),  # 11〜17円
    (35,   "高め",           "#EE8B1F"),  # 17〜35円
    (None, "とても高め",     "#C0531E"),  # 35円〜
]


def price_level(peak):
    """日内最高値(円/kWh) → (レベル番号1-5, ラベル, 色) を返す。"""
    for i, (upper, label, color) in enumerate(PRICE_LEVELS, 1):
        if upper is None or peak < upper:
            return i, label, color
    last = PRICE_LEVELS[-1]
    return len(PRICE_LEVELS), last[1], last[2]


def _high_floor():
    """「高め」帯（レベル4）に入る下限値（円/kWh）を PRICE_LEVELS から導出する。
    = ひとつ下の帯「ふつう」の上限。これにより「高めのエリア」の判定を
    PRICE_LEVELS と一致させ、しきい値を変えるときは PRICE_LEVELS だけ直せばよい。
    （以前は build_stories.py / notify_slack.py に 17 がベタ書きで二重管理だった）"""
    for i, (_upper, label, _color) in enumerate(PRICE_LEVELS):
        if label == "高め" and i > 0:
            return PRICE_LEVELS[i - 1][0]
    # フォールバック：上から2番目の境界
    return PRICE_LEVELS[-2][0] if len(PRICE_LEVELS) >= 2 else 0


# 日内最高値がこの値以上なら「高め（以上）」とみなす下限（円/kWh）。
HIGH_FLOOR = _high_floor()


def yen_approx(v, unit="円"):
    """概算の円表示（「約X円」）。表記を一箇所に集約しておく窓口。
    0.01円のような最安値も「約0円」と出すのは、四捨五入として誤りではなく、
    かつ『ほぼタダの時間帯がある』という安さのインパクトが伝わりやすいため。
    （※実際の電気料金は託送料金・手数料が加わる旨はストーリーズ脚注で明記）"""
    return f"約{v:.0f}{unit}"


# 毎日便りメールを「希望する」お客様の購読エリア（CIS連携前の暫定。
# 実運用では購読者管理から動的に取得する）。空なら全エリアぶんを生成。
DAILY_SUBSCRIBE_AREAS = []  # 例: ["関西", "東京"]

# （旧）Instagramカルーセル用の FEATURE_AREAS / REGION_BLOCKS などは、
# 現行 build_stories.py が GROUPS / LINE_COLORS を自前で持つようになり
# 未使用（デッド設定）になったため削除した。必要になれば build_stories.py 側で定義する。
