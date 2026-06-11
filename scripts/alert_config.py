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
