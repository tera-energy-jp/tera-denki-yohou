#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
でんき予報 Instagramストーリーズ生成（縦長1080×1920・地域別5枚）
公式WEB準拠の配色（黄×オレンジ）＋公式テラゾウ＋豆知識ランダム
  python build_stories.py [prices.json]
"""
import base64
import json
import os
import sys
from alert_config import price_level, yen_approx, HIGH_FLOOR

HERE = os.path.dirname(os.path.abspath(__file__))
PRICES_JSON = "prices.json"
OUTPUT_HTML = "stories.html"

GROUPS = [
    ("EAST JAPAN", "東日本", ["北海道", "東北", "東京"]),
    ("CENTRAL JAPAN", "中日本", ["中部", "北陸", "関西"]),
    ("WEST JAPAN", "西日本", ["中国", "四国", "九州"]),
]
LINE_COLORS = ["#6496C8", "#E1AF00", "#7A9A5A"]
# 各線の線種（位置で割当）：1本目=実線 / 2本目=破線 / 3本目=点線。
# 値が完全一致して重なっても線種で見分けられるようにするため。
LINE_DASHES = ["", "16 10", "3 9"]

# 「なんで時間で変わるの？」地域別の豆知識プール
# ※2026-06 改定でパネル自体を全スライドから非表示に。データは将来復活用に保持。
WHY_POOL = {
    "東日本": [
        "日中は冷暖房などで電気を使う人が増えて価格が上がるゾウ。早朝や深夜はみんな休んでいて需要が落ち着くから狙い目だゾウ。",
        "東日本はLNG（天然ガス）火力が多めだから、燃料の値段や寒さの影響を受けやすいゾウ。冬の朝晩はとくに高くなりやすいんだゾウ。",
        "人がたくさん住む東日本は、夕方〜夜に需要がぐっと集まるゾウ。みんなが帰宅して照明や料理に電気を使うからなんだゾウ。",
        "東と西で電気の周波数が違うって知ってた？東日本は50Hz。西の安い電気をたくさん運べない事情も、価格に効いてくるゾウ。",
    ],
    "中日本": [
        "晴れたお昼は太陽光で価格が下がることがあるゾウ。逆に夕方は仕事や家事が重なって需要が集まり、高くなりやすいんだゾウ。",
        "関西は原子力発電がベースにあるぶん、燃料価格の波の影響が比較的おだやかと言われるゾウ。",
        "春や秋は冷暖房をあまり使わないから、電気の市場価格も落ち着きやすい季節だゾウ。",
        "電気はためておくのが苦手。だから“使う時間”をずらすだけで、需給のバランスがよくなって価格も安定するんだゾウ。",
    ],
    "西日本": [
        "太陽光が多い地域は、晴れたお昼に電気があり余って価格がぐっと下がるゾウ。夕方は太陽が沈んで需要も残るから高くなりやすいんだゾウ。",
        "九州は太陽光がとても多くて、晴れた休日のお昼は電気が余って“出力制御”することもあるゾウ。それだけお昼が狙い目なんだゾウ。",
        "四国や九州はお昼の市場価格が全国でも特に安くなりやすいゾウ。洗濯や食洗機をお昼に寄せると、かしこく使えるゾウ。",
        "雨や曇りの日は太陽光が減るから、晴れの日ほどお昼が安くならないゾウ。お天気予報とセットで見るのがコツだゾウ。",
    ],
}


# 電気の豆知識プール（30種類・日替わり）
# ※ WEB版 index.html の TRIVIA_POOL と完全に同一。
#   どちらかを編集したら、もう一方も必ず同じ内容に揃えること（同じ日に同じ豆知識を出すため）。
TRIVIA_POOL = [
    "電気は「ためておく」のが苦手。使う量と作る量をリアルタイムで合わせる必要があるから、需要が集中する時間帯は価格が上がるんだゾウ。",
    "日本の電気の周波数は東日本が50Hz、西日本が60Hz。この違いのせいで東西で電気を大量に融通し合うのが難しく、価格差が生まれやすいんだゾウ。",
    "九州や四国では、晴れた春秋の昼間に太陽光が発電しすぎて電気が余り、市場価格がほぼゼロ円になることがあるゾウ。これを「出力制御」といって、太陽光パネルを一時的に止めることもあるんだゾウ。",
    "JEPXのスポット市場では、毎朝10時ごろに翌日48コマ分の価格が決まるゾウ。電力会社は前日の夜明けに入札していて、その結果がこの「でんき予報」の元データになってるゾウ。",
    "電気の「市場価格」と「電気料金」は別物。市場価格はJEPXで決まるけど、実際の料金には託送（電線の使用料）や再エネ賦課金なども加わるゾウ。",
    "再生可能エネルギーの賦課金は、毎年5月に見直されるゾウ。太陽光の普及が進むほど賦課金も増えてきたけど、最近は電気代の低下傾向もあって複雑な動きをしてるんだゾウ。",
    "夏の猛暑日は、午後2〜4時に冷房需要がピークになりやすいゾウ。特に東京では気温が1℃上がると電力需要が約100万kW増えるとも言われてるんだゾウ。",
    "天然ガス（LNG）火力発電はガスのタービンを回して発電するゾウ。起動・停止が柔軟にできる半面、燃料費の変動が電気の市場価格に直接響くんだゾウ。",
    "原子力発電は一定の出力で24時間動かし続けるのが得意。需要の少ない深夜でも発電を続けるため、夜間の電力価格が低くなりやすい要因の一つだゾウ。",
    "水力発電は燃料ゼロで発電できるぶん、市場価格が高いときに稼働させると収益が出やすいゾウ。ダムの水を「貯金」して、高値の時間帯に放流するという使い方もされてるんだゾウ。",
    "揚水発電は、電気が余ったとき（価格が安いとき）に水をくみ上げて位置エネルギーとして蓄え、電気が足りなくなったとき（高いとき）に放流して発電するゾウ。巨大な充電池みたいな役割だゾウ。",
    "蓄電池の普及が進むと、安い時間帯に充電して高い時間帯に放電・売電する動きが増えるゾウ。これが市場に広がると、価格の高値と安値の差が縮まっていく可能性があるんだゾウ。",
    "EVの充電は夜間〜早朝に集中させると、電力系統の安定にも貢献できるゾウ。将来はEVの蓄電池を家庭や系統に放電する「V2H」「V2G」という仕組みも広がる見込みだゾウ。",
    "でんき予報が使っているデータは「エリアプライス」という地域ごとの市場価格。日本には北海道・東北・東京・中部・北陸・関西・中国・四国・九州の9エリアがあって、それぞれ独立した価格がつくゾウ。",
    "電力の市場取引には、翌日の価格を決める「スポット市場」のほかに、1時間前まで入札できる「時間前市場」もあるゾウ。急な発電機の故障や需要の変動に対応する仕組みだゾウ。",
    "家庭の電気代に含まれる「燃料費調整額」は、LNGや石炭などの燃料価格の変動を電気代に反映する仕組みだゾウ。国際的な燃料価格が上がると電気代も上がるのはこのためだゾウ。",
    "太陽光パネルの発電量は気温が上がると少し下がるゾウ。真夏の猛暑日より、涼しい春の晴れの日のほうが発電効率が高いことがあるんだゾウ。",
    "洋上風力発電は、陸上より風が安定して強いため発電量が大きくなりやすいゾウ。日本でも2030年代に向けて大規模な洋上風力の整備が進んでいるんだゾウ。",
    "電力の「ベースロード電源」は24時間安定して動かす発電所（原子力・石炭など）、「ピーク電源」は需要の多いときだけ動かす発電所（ガスタービンなど）のことだゾウ。",
    "停電せずに電気を使えるのは、発電所・送電線・変電所の組み合わせが絶えず需要と供給をぴったり合わせているからだゾウ。この調整役を担うのが各エリアの「一般送配電事業者」だゾウ。",
    "日本の電力自由化は2016年4月に低圧（家庭・小規模店舗）向けにも全面開放されたゾウ。TERAのような新電力が参入できるようになったのもこの改革のおかげだゾウ。",
    "「省エネ」と「節電」は少し違うゾウ。省エネは機器の効率を上げて同じことをより少ない電気でこなすこと、節電は使う量そのものを減らすことだゾウ。両方組み合わせるのが電気代削減の近道だゾウ。",
    "エアコンの設定温度を1℃変えると、消費電力が約10%変わると言われるゾウ。夏は28℃・冬は20℃が省エネの目安とされてるけど、体感にあわせて無理なく調整するのが大切だゾウ。",
    "冷蔵庫の消費電力は家庭の電力消費の約15%を占めるゾウ。設定温度を「強」から「中」に変えたり、食品を詰めすぎないようにするだけで節電につながるんだゾウ。",
    "待機電力（コンセントに差したままの機器が消費する電力）は、家庭全体の電力消費の約6%を占めるとも言われるゾウ。長期不在のときはコンセントを抜くと節電になるんだゾウ。",
    "LED照明は、白熱電球と比べて消費電力が約85%少なく、寿命は約40倍長いゾウ。初期費用はかかるけど、長い目で見るとコストを大きく下げられるんだゾウ。",
    "電気料金の「基本料金」は、たとえ1kWhも使わなくても毎月かかるゾウ。契約アンペア数（電流の上限）によって決まることが多く、大きいほど基本料金も高くなるんだゾウ。",
    "太陽光発電の「FIT（固定価格買取制度）」では、家庭や企業が発電した電気を一定価格で買い取ってもらえるゾウ。この費用は再エネ賦課金として全国の電気利用者が負担しているんだゾウ。",
    "電力系統の安定を保つため、周波数は常に50Hzか60Hzに保たれているゾウ。発電量が需要を上回ると周波数が上がり、下回ると下がる。これがズレると大停電（ブラックアウト）につながることもあるんだゾウ。",
    "カーボンニュートラルに向けて、電力部門の脱炭素化が進んでいるゾウ。再エネ比率が上がるほど昼間の価格が下がりやすくなる一方、夜間の供給確保が課題になる「ダックカーブ問題」が世界各地で起きているんだゾウ。",
]


def daily_trivia(date_raw):
    """日付シードで豆知識を1件選ぶ（同じ日は同じ豆知識）。

    WEB版 index.html の getDailyTrivia と同一アルゴリズム：
    seed = 各文字コードを a*31+c で畳み込み → abs(seed) % len。
    seedは10^12程度でJSの安全整数(2^53)に収まるため、両者の結果は完全一致する。
    """
    s = (date_raw or "").replace("/", "")
    if not s:
        return TRIVIA_POOL[0]
    seed = 0
    for ch in s:
        seed = seed * 31 + ord(ch)
    return TRIVIA_POOL[abs(seed) % len(TRIVIA_POOL)]


def slot_label(i):
    return f"{i // 2}:{'30' if i % 2 else '00'}"


def load_terazou():
    try:
        with open(os.path.join(HERE, "terazou.png"), "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f'<img src="data:image/png;base64,{b64}" style="width:100%;height:100%;object-fit:contain;display:block;" alt="テラゾウ">'
    except FileNotFoundError:
        return ('<svg viewBox="0 0 100 60" width="100%" height="100%"><text x="50" y="38" '
                'text-anchor="middle" font-size="40">🐘</text></svg>')


TERAZOU = load_terazou()


def calm_band(prices):
    """最安コマを必ず内側に含む“おだやかな連続帯” (start, end) を返す。

    基準は min×1.3。最安コマを起点に左右へ「基準以下が続くあいだ」広げるので、
    表示する時間帯と最安値（約X円）が食い違わない。
    （以前は「最長の連続帯」を選んでいたため、最安コマが帯の外に出て
      『9:00〜10:00ごろ（約6円）』なのに帯内は7円台…というズレが起きていた）
    """
    if not prices:
        return (0, -1)
    ref = min(prices) * 1.3 + 0.01
    mi = prices.index(min(prices))
    s = e = mi
    while s - 1 >= 0 and prices[s - 1] <= ref:
        s -= 1
    while e + 1 < len(prices) and prices[e + 1] <= ref:
        e += 1
    return (s, e)


def line_chart_svg(series, w=960, h=600):
    pad_l, pad_r, pad_t, pad_b = 84, 28, 26, 62
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b
    allv = [v for arr in series.values() for v in arr]
    ymax = max(40, (int(max(allv)) // 10 + 1) * 10)

    def X(i): return pad_l + i / 47 * pw
    def Y(v): return pad_t + (1 - v / ymax) * ph

    p = []
    lo_area = min(series, key=lambda a: min(series[a]))
    cs, ce = calm_band(series[lo_area])
    if ce >= cs:
        x0, x1 = X(cs), X(ce)
        p.append(f'<rect x="{x0:.0f}" y="{pad_t}" width="{x1-x0:.0f}" height="{ph:.0f}" fill="#6496C8" opacity="0.10"/>')
        p.append(f'<text x="{(x0+x1)/2:.0f}" y="{pad_t+26:.0f}" text-anchor="middle" font-size="24" fill="#3a6fa5">おだやか</text>')
    for g in range(0, ymax + 1, 10):
        y = Y(g)
        p.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w-pad_r}" y2="{y:.0f}" stroke="#ece2d2" stroke-width="1.5"/>')
        p.append(f'<text x="{pad_l-14}" y="{y+9:.0f}" text-anchor="end" font-size="26" fill="#b3a892">{g}</text>')
    for hh in [0, 6, 12, 18, 24]:
        i = min(hh * 2, 47)
        p.append(f'<text x="{X(i):.0f}" y="{h-pad_b+40:.0f}" text-anchor="middle" font-size="25" fill="#b3a892">{hh}時</text>')
    p.append(f'<text x="{pad_l-60}" y="{pad_t+ph/2:.0f}" text-anchor="middle" font-size="23" fill="#b3a892" transform="rotate(-90 {pad_l-60} {pad_t+ph/2:.0f})">円/kWh</text>')

    arrs = list(series.items())
    # 各線に線種を割り当てる（実線→破線→点線）。値が完全一致して重なっても、
    # 破線・点線なら下の線が透けて見え、3エリアを描いていることが伝わる。
    # 描画は「実線→破線→点線」の順。後に描くほど前面なので、点線が必ず最前面に来る。
    for idx, (area, arr) in enumerate(arrs):
        c = LINE_COLORS[idx % len(LINE_COLORS)]
        dash = LINE_DASHES[idx % len(LINE_DASHES)]
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(arr))
        p.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="6" '
                 f'stroke-linejoin="round" stroke-linecap="round"{dash_attr}/>')
    # 最高値マーカーは線の上に（点線で隠れないよう最後にまとめて描画）
    for idx, (area, arr) in enumerate(arrs):
        c = LINE_COLORS[idx % len(LINE_COLORS)]
        mi = arr.index(max(arr))
        p.append(f'<circle cx="{X(mi):.1f}" cy="{Y(arr[mi]):.1f}" r="8" fill="{c}"/>')

    # 完全一致して重なっている区間に「重なり」注記を出す（B+DのD）。
    # 線種で見分けられても、完全一致区間はどうしても最前面の点線しか
    # 見えないため、そこだけ「ここは同じ価格です」と言葉でも伝える。
    if len(arrs) >= 2:
        seg = _longest_overlap_segment([a for _, a in arrs])
        if seg:
            s, e = seg
            xm = (X(s) + X(e)) / 2
            ym = Y(arrs[0][1][s]) - 18  # 重なっている線のすぐ上
            ym = max(ym, pad_t + 44)     # 「おだやか」ラベルや上端と被らせない
            p.append(f'<text x="{xm:.0f}" y="{ym:.0f}" text-anchor="middle" font-size="22" '
                     f'fill="#9b8e7c">3エリアほぼ同じ価格</text>')

    return f'<svg viewBox="0 0 {w} {h}" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">{"".join(p)}</svg>'


def _longest_overlap_segment(arrays, tol=0.05):
    """全系列の値がほぼ一致している最長の連続区間 (start, end) を返す。

    tol は「同じ価格」とみなす許容差（円/kWh）。差がこの範囲なら重なりとみなす。
    重なり区間が短すぎる（注記を置く意味がない）場合は None。
    """
    if len(arrays) < 2:
        return None
    n = len(arrays[0])
    best = None
    s = None
    for i in range(n):
        col = [a[i] for a in arrays]
        same = (max(col) - min(col)) <= tol
        if same and s is None:
            s = i
        elif not same and s is not None:
            if best is None or (i - 1 - s) > (best[1] - best[0]):
                best = (s, i - 1)
            s = None
    if s is not None:
        if best is None or (n - 1 - s) > (best[1] - best[0]):
            best = (s, n - 1)
    # 3コマ（1.5時間）未満の重なりは注記しない（誤差レベルなので）
    if best and (best[1] - best[0]) >= 3:
        return best
    return None


def legend_html(series):
    out = []
    for idx, (area, arr) in enumerate(series.items()):
        c = LINE_COLORS[idx % len(LINE_COLORS)]
        dash = LINE_DASHES[idx % len(LINE_DASHES)]
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        # 凡例も「色のドット」から「実際の線種サンプル」に変更。
        # グラフと同じ実線/破線/点線を見せることで、どの線がどのエリアか対応づく。
        sample = (f'<svg class="lsamp" width="46" height="14" viewBox="0 0 46 14">'
                  f'<line x1="2" y1="7" x2="44" y2="7" stroke="{c}" stroke-width="5" '
                  f'stroke-linecap="round"{dash_attr}/></svg>')
        hi = max(arr)
        lv, label, lvcolor = price_level(hi)
        tag = f'<span class="lvl" style="background:{lvcolor}">{label}</span>'
        out.append(f'<span class="lg">{sample}{area}'
                   f'<span class="lgv">最高 {hi:.0f}円</span>{tag}</span>')
    return "".join(out)


def good_tip(jp, series):
    lo_area = min(series, key=lambda a: min(series[a]))
    arr = series[lo_area]
    cs, ce = calm_band(arr)
    band = f"{slot_label(cs)}〜{slot_label(ce)}ごろ" if ce > cs else f"{slot_label(arr.index(min(arr)))}ごろ"
    return (f"{jp}でいちばんおだやかなのは {lo_area}・{band}（{yen_approx(min(arr))}）。"
            f"洗濯・食洗機・充電など“時間をずらせる電気”は、ここに寄せるとお得だゾウ。")


CLOUD = ('<svg class="cloud" viewBox="0 0 320 200" xmlns="http://www.w3.org/2000/svg">'
         '<g fill="#FBE6C8"><circle cx="90" cy="120" r="60"/><circle cx="160" cy="90" r="72"/>'
         '<circle cx="235" cy="120" r="58"/><circle cx="135" cy="150" r="55"/><circle cx="205" cy="150" r="50"/></g></svg>')


def national_summary(areas):
    peaks = [max(arr) for arr in areas.values()]
    rep = sum(peaks) / len(peaks)         # 9エリアの日内最高値の平均
    lv, mood, color = price_level(rep)    # 5段階のラベル・色
    cheapest = min(areas, key=lambda a: min(areas[a]))
    carr = areas[cheapest]
    lo_i = carr.index(min(carr))
    # 「高め（レベル4）」以上のエリアを注意対象として列挙。
    # しきい値は alert_config.HIGH_FLOOR（PRICE_LEVELSから自動導出）に一本化。
    hot = [a for a in areas if max(areas[a]) >= HIGH_FLOOR]
    if not hot:
        if lv <= 2:
            hot_line = '<span class="ok">&#9728; 高すぎる時間は無さそう。安心して使えるゾウ</span>'
        else:
            hot_line = '<span class="ok">&#9728; ふつうの水準。時間を選べばお得に使えるゾウ</span>'
    elif len(hot) >= 5:
        hot_line = '<span class="warn">&#9650; 広い範囲で 高めの時間に注意</span>'
    else:
        hot_line = f'<span class="warn">&#9650; 高めの時間に注意</span>　{"・".join(hot)}'
    return {
        "pre": "あしたは、", "mood": mood, "color": color,
        "cheap_area": cheapest, "cheap_time": slot_label(lo_i), "cheap_val": yen_approx(min(carr)),
        "hot_line": hot_line,
    }


def header(date_label):
    return (f'<div class="sheader"><div class="szou">{TERAZOU}</div>'
            f'<div class="stxt"><div class="st1">テラゾウの #でんき予報</div>'
            f'<div class="st2">{date_label}</div></div></div>')


def chart_story(en, jp, series, date_label, pageno):
    return STORY_CHART.format(
        header=header(date_label), en=en, jp=jp, chart=line_chart_svg(series),
        legend=legend_html(series), good=good_tip(jp, series), pageno=pageno)


def build(prices_path):
    data = json.load(open(prices_path, encoding="utf-8"))
    date_label = data["date_label"]
    areas = data["areas"]
    s = national_summary(areas)

    stories = ""
    page = 2
    for en, jp, names in GROUPS:
        series = {n: areas[n] for n in names if n in areas}
        stories += chart_story(en, jp, series, date_label, f"{page} / 6")
        page += 1

    # きょうの豆知識（日付シードで決定論的に選択／WEB版と完全一致）
    trivia = daily_trivia(data.get("date_raw", ""))

    cover_cloud = CLOUD.replace('class="cloud"', 'class="cloud" style="top:-60px;right:-80px;"')
    close_cloud = CLOUD.replace('class="cloud"', 'class="cloud" style="bottom:60px;left:-120px;width:380px;opacity:.7;"')
    trivia_cloud = CLOUD.replace('class="cloud"', 'class="cloud" style="top:-40px;right:-90px;width:420px;opacity:.55;"')
    return PAGE.format(
        date_label=date_label, mood=s["mood"], mood_color=s["color"],
        cheap_area=s["cheap_area"], cheap_time=s["cheap_time"], cheap_val=s["cheap_val"],
        hot_line=s["hot_line"], terazou=TERAZOU, header=header(date_label),
        cover_cloud=cover_cloud, close_cloud=close_cloud, stories=stories,
        trivia=trivia, trivia_cloud=trivia_cloud)


STORY_CHART = '''
  <div class="slide story">
    <div class="pad">
      {header}
      <div class="eyebrow">{en}</div>
      <h2>{jp}<span class="hen">編</span></h2>
      <div class="chartbox"><div style="height:680px;">{chart}</div>
        <div class="legend">{legend}</div></div>
      <div class="tip tip-good"><span class="tt">&#9786; お得な狙い目</span><span class="tb">{good}</span></div>
      <div class="foot">&#8596; ほかのエリアの編も スワイプでチェックだゾウ</div>
    </div>
    <div class="pageno">{pageno}</div>
  </div>'''


PAGE = '''<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700;900&display=swap" rel="stylesheet">
<style>
  *{{margin:0;box-sizing:border-box;}}
  body{{background:#cabfa9;padding:24px;display:flex;flex-wrap:wrap;gap:24px;justify-content:center;
       font-family:"Noto Sans JP",sans-serif;color:#573C2C;}}
  .slide{{width:1080px;height:1920px;background:#FBF7EF;position:relative;overflow:hidden;flex:0 0 auto;}}
  .pad{{position:absolute;top:172px;left:64px;right:64px;bottom:196px;display:flex;flex-direction:column;z-index:1;}}
  .cloud{{position:absolute;width:520px;z-index:0;}}
  .eyebrow{{font-size:30px;letter-spacing:.2em;color:#F2A03D;font-weight:700;text-transform:uppercase;}}
  .pageno{{position:absolute;top:172px;right:64px;font-size:27px;color:#E0B57A;letter-spacing:.08em;font-weight:500;z-index:2;}}
  h2{{font-weight:900;color:#573C2C;}}

  .sheader{{display:flex;align-items:center;gap:18px;margin-bottom:14px;}}
  .szou{{width:120px;height:60px;flex:0 0 auto;}}
  .st1{{font-size:30px;font-weight:700;color:#573C2C;}}
  .st2{{font-size:34px;color:#F28C22;font-weight:800;margin-top:2px;letter-spacing:.03em;}}

  .cover .pad{{justify-content:space-between;}}
  .cover .czou{{width:380px;height:auto;margin-top:14px;}}
  .cover .ct1{{font-size:48px;font-weight:900;margin-top:24px;color:#573C2C;}}
  .cover .ct2{{font-size:26px;color:#9b8e7c;font-weight:400;margin-top:8px;}}
  .cover .date{{font-size:48px;color:#573C2C;font-weight:700;margin-top:30px;letter-spacing:.04em;}}
  .mood .pre{{font-size:50px;color:#9b8e7c;font-weight:300;}}
  .mood .big{{font-size:96px;font-weight:900;line-height:1.26;}}
  .summary{{margin-top:30px;background:#fff;border-radius:28px;padding:30px 34px;box-shadow:0 8px 30px rgba(243,154,43,.10);}}
  .srow{{font-size:34px;font-weight:500;color:#5c5346;line-height:1.5;}}
  .srow + .srow{{margin-top:16px;}}
  .srow .lo{{color:#185FA5;font-weight:700;}}
  .srow .warn{{color:#C0531E;font-weight:700;}}
  .srow .ok{{color:#5A9E2F;font-weight:700;}}
  .swipe{{display:inline-flex;align-items:center;gap:13px;background:#F39A2B;color:#fff;font-size:30px;font-weight:700;padding:22px 40px;border-radius:50px;}}

  .story .eyebrow{{margin-top:6px;}}
  .story h2{{font-size:66px;margin-top:4px;}}
  .story h2 .hen{{font-size:38px;color:#E0A24A;margin-left:8px;font-weight:700;}}
  .chartbox{{background:#fff;border-radius:36px;padding:30px 30px 22px;margin-top:22px;box-shadow:0 8px 30px rgba(243,154,43,.10);}}
  .legend{{display:flex;gap:30px;flex-wrap:wrap;margin-top:18px;justify-content:center;}}
  .lg{{display:flex;align-items:center;gap:11px;font-size:32px;font-weight:500;color:#573C2C;}}
  .lg .dot{{width:24px;height:24px;border-radius:50%;}}
  .lg .lsamp{{flex:0 0 auto;}}
  .lg .lgv{{font-size:26px;color:#9b8e7c;margin-left:4px;font-weight:400;}}
  .lg .lvl{{font-size:24px;color:#fff;padding:4px 16px;border-radius:16px;margin-left:7px;font-weight:700;}}
  .tip{{border-radius:34px;padding:48px 52px;margin-top:46px;}}
  .tip .tt{{display:block;font-weight:700;margin-bottom:18px;}}
  .tip .tb{{display:block;color:#5c5346;font-weight:400;}}
  .tip-good{{background:#FFF3DE;}}
  .tip-good .tt{{color:#E8800E;font-size:45px;}}
  .tip-good .tb{{font-size:42px;line-height:1.72;}}
  .foot{{text-align:center;font-size:28px;color:#C99A2E;font-weight:700;margin-top:auto;padding-top:24px;}}

  .closing .pad{{justify-content:space-between;}}
  .closing .msg{{font-size:74px;font-weight:900;color:#573C2C;line-height:1.5;}}
  .closing .msg em{{color:#F39A2B;font-style:normal;}}
  .closing .lead{{font-size:34px;color:#7a6f5f;line-height:1.9;margin-top:34px;font-weight:300;}}
  .linkcue{{display:inline-flex;align-items:center;gap:22px;background:#F39A2B;color:#fff;font-size:31px;font-weight:700;padding:32px 48px;border-radius:44px;line-height:1.5;}}
  .linkcue .lc-ico{{flex:0 0 auto;}}
  .linkcue .lc-txt{{text-align:left;}}
  .footnote{{font-size:23px;color:#b3a892;line-height:1.7;font-weight:300;margin-top:30px;}}

  .trivia .pad{{justify-content:space-between;}}
  .trivia .tv-title{{font-size:74px;font-weight:900;color:#573C2C;line-height:1.42;}}
  .trivia .tv-title em{{color:#F39A2B;font-style:normal;}}
  .tv-card{{background:#fff;border-radius:40px;padding:64px 60px;box-shadow:0 8px 30px rgba(243,154,43,.10);
            display:flex;flex-direction:column;align-items:center;text-align:center;}}
  .tv-card .tv-zou{{width:240px;height:120px;flex:0 0 auto;margin-bottom:34px;}}
  .tv-card .tv-body{{font-size:46px;line-height:1.82;color:#5c5346;font-weight:400;}}
  .trivia .tv-next{{display:inline-flex;align-items:center;gap:14px;background:#FFF3DE;color:#E8800E;
            font-size:32px;font-weight:700;padding:28px 44px;border-radius:44px;line-height:1.5;}}
</style></head>
<body>

  <div class="slide cover">
    {cover_cloud}
    <div class="pad">
      <div>
        <div class="eyebrow">DENKI FORECAST</div>
        <div class="czou">{terazou}</div>
        <div class="ct1">テラゾウの でんき予報</div>
        <div class="ct2">エリア別・電気の市場価格のめやす</div>
        <div class="date">{date_label}</div>
      </div>
      <div>
        <div class="mood"><div class="big" style="color:{mood_color}">{mood}</div></div>
        <div class="summary">
          <div class="srow"><span class="lo">&#9660; いちばんおだやか</span>　{cheap_area}・{cheap_time}ごろ（{cheap_val}）</div>
          <div class="srow">{hot_line}</div>
        </div>
      </div>
      <div><span class="swipe">スワイプして、あなたのエリアへ &#8594;</span></div>
    </div>
    <div class="pageno">1 / 6</div>
  </div>
{stories}
  <div class="slide closing">
    {close_cloud}
    <div class="pad">
      <div>
        {header}
        <div class="eyebrow" style="margin-top:30px;">MESSAGE</div>
        <div class="msg" style="margin-top:26px;">使う時間を、<br>すこし<em>選んでみる</em>。<br>それだけで、<br>ほっとする毎日に。</div>
        <div class="lead">電気は、ただのエネルギーじゃない。<br>いつ使うかを自分で選べることが、<br>おだやかな安心につながりますように。</div>
      </div>
      <div>
        <span class="linkcue"><span class="lc-ico">&#128279;</span><span class="lc-txt">各エリアの予報は<br>プロフィールのリンクから確認できるゾウ</span></span>
        <div class="footnote">※市場価格（JEPXエリアプライス）のめやすです。実際の電気料金には託送料金やTERAの手数料などが加わります。</div>
      </div>
    </div>
    <div class="pageno">5 / 6</div>
  </div>

  <div class="slide trivia">
    {trivia_cloud}
    <div class="pad">
      <div>
        {header}
        <div class="eyebrow" style="margin-top:30px;">TODAY'S TRIVIA</div>
        <div class="tv-title" style="margin-top:22px;">きょうの<br>テラゾウ<em>まめ知識</em></div>
      </div>
      <div class="tv-card">
        <div class="tv-zou">{terazou}</div>
        <div class="tv-body">{trivia}</div>
      </div>
      <div>
        <div class="tv-next">&#128064; あしたのまめ知識も、お楽しみにだゾウ</div>
        <div class="footnote" style="margin-top:22px;">毎日のでんき予報といっしょに、電気のあれこれを少しずつお届けするゾウ。</div>
      </div>
    </div>
    <div class="pageno">6 / 6</div>
  </div>

  <div style="flex-basis:100%;text-align:center;color:#8a7d68;font-size:15px;padding:8px;">
    ↑ Instagramストーリーズ6枚（各1080×1920）のプレビュー。実投稿はPNG書き出し（render_png.py）。
  </div>
</body></html>'''


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else PRICES_JSON
    if not os.path.exists(path):
        raise SystemExit(f"prices.json が見つかりません: {path}")
    html = build(path)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK: {OUTPUT_HTML} を生成（公式テラゾウ・豆知識ランダム・表紙詳細）")


if __name__ == "__main__":
    main()
