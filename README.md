# でんき予報システム実行フロー

このドキュメントは、`tera-denki-yohou-main` リポジトリ内で動作する実行フローをわかりやすくまとめたものです。

---

## 1. 目的

このシステムは、JEPX の翌日スポット価格データを取り込み、

- GitHub Pages 向け Web コンテンツ生成
- Instagram Stories 生成・投稿
- 価格アラート判定と通知

を自動化することを目的としています。

---

## 2. 主要ファイルと役割

### データ取得・変換

- `scripts/fetch_jepx.py`
  - JEPX 公式サイトから当該年度の CSV を取得し、`data/spot_summary.csv` に保存
- `scripts/build_prices.py`
  - `data/spot_summary.csv` から翌日の `prices.json` を生成
- `scripts/build_history.py`
  - 過去データを `history.json` に変換
- `scripts/build_monthly.py`
  - 月平均データを `monthly.json` に更新

### Web / Instagram 生成

- `scripts/build_stories.py`
  - `prices.json` を元に縦長 HTML (`stories.html`) を生成
- `scripts/render_png.py`
  - `stories.html` を PNG に変換し `stories_*.png` を生成

### 価格アラート / 通知

- `scripts/alert_config.py`
  - 価格レベル判定の閾値とラベル定義
- `scripts/build_alerts.py`
  - `prices.json` から価格アラート判定と配信用素材を生成
- `scripts/upload_alerts_drive.py`
  - 発火物を Google Drive に格納
- `scripts/notify_alert_slack.py`
  - 発火状況を Slack に通知
- `scripts/notify_slack.py`
  - Web/Instagram 投稿の安否確認を Slack に通知

### Instagram 投稿

- `scripts/post_instagram_stories.py`
  - `docs/stories/stories_*.png` を Instagram Stories に投稿
- `scripts/check_ig_token.py`
  - Instagram アクセストークンの期限を監視

### GitHub Actions

- `.github/workflows/daily-denki-yohou.yml`
  - メインの自動実行フロー
- `.github/workflows/denki-yohou-watchdog.yml`
  - 当日未配信・遅延を監視するワークフロー
- `.github/workflows/alert-test.yml`
  - 価格アラートの手動テスト用

---

## 3. 通常の実行フロー

以下が、実際に動くときの順番です。

### 1) トリガ

`daily-denki-yohou.yml` は次の条件で起動します。

- GitHub Actions のネイティブ `schedule`
  - 10:40 JST
  - 11:10 JST
  - 11:40 JST
- `workflow_dispatch`
  - 手動実行。`force=true` で強制再配信
- `push`
  - `data/spot_summary.csv` の更新時

このリポジトリでは、さらに `cron-job.org` から `workflow_dispatch` で起動する運用が想定されています。

### 2) 同一日重複実行防止

- `guard` ジョブが `docs/.last_run` を確認
- 今日のマーカーが存在すれば本体はスキップ
- `workflow_dispatch` の `force=true` だけは例外で強制実行

### 3) メイン処理

`build-and-notify` ジョブで以下を順番に実行します。

1. `scripts/fetch_jepx.py`
   - JEPX から最新 CSV を取得
2. `scripts/build_prices.py --require-tomorrow`
   - あしたのデータを明示要求して `prices.json` を生成
3. `scripts/build_history.py`
   - `history.json` を生成
4. `scripts/build_monthly.py`
   - `monthly.json` を更新
5. `scripts/build_stories.py`
   - `stories.html` を生成
6. `scripts/render_png.py stories.html`
   - `stories_*.png` を生成
7. `docs/` へ配置
   - `stories_*.png` を `docs/stories/`
   - `prices.json` を `docs/prices.json`
   - `history.json` / `monthly.json` を `docs/` にコピー

### 4) 価格アラート関連

以下は本体公開とは独立して動く補助処理です。

- `scripts/build_alerts.py docs/prices.json`
  - 価格発火判定と配信用素材の生成
- `scripts/upload_alerts_drive.py`
  - 発火物を Google Drive に格納
- `scripts/notify_alert_slack.py`
  - 発火状況を Slack に通知

これらは `continue-on-error: true` になっており、失敗しても主要公開フローを止めません。

### 5) 公開と Instagram 投稿

8. GitHub へコミット＆プッシュ
   - `docs/` と `data/spot_summary.csv` を push
9. GitHub Pages 反映の確認
   - `pages_base_url/prices.json` が今回の日付になるまで待機
10. `scripts/check_ig_token.py`
   - IG トークン期限をチェック
11. `scripts/post_instagram_stories.py`
   - Stories 画像を Instagram に投稿
12. `docs/.last_run` を更新
   - Instagram 投稿成功後に当日完了マーカーを記録
13. `scripts/notify_slack.py`
   - 最終的な安否確認通知を Slack に送信

---

## 4. 監視フロー

`denki-yohou-watchdog.yml` は以下で動きます。

- 11:30 JST
- 12:30 JST

実行内容:

- `docs/.last_run` を確認
- 当日未配信であれば Slack に警告
- 当日配信済みでも完了が遅い場合は遅延注意を Slack に送信

---

## 5. 重要な注意点

- `build_prices.py --require-tomorrow` は「翌日のデータ」を明示的に要求します。
  - JEPX の公表遅延時に古いデータを誤配信しないようにするためです。
- `post_instagram_stories.py` は `.ig_state.json` で投稿済み進捗を管理し、
  途中失敗時の二重投稿を防ぎます。
- 価格アラート関連は本体公開と独立しているため、
  アラート周りに問題があっても Web/Instagram 配信は継続します。

---

## 6. まとめ

このシステムの基本的な流れは、

1. JEPX CSV 取得
2. `prices.json` 生成
3. Web・Stories 生成
4. 価格アラート判定
5. GitHub Pages 公開
6. Instagram Stories 投稿
7. 当日配信マーカー記録


**アラート判定仕様（概要）**

- 閾値はスクリプト `scripts/alert_config.py` で定義されています（主な定数）：
  - `THRESHOLDS` : Lv1（高め） — 情報提供（Instagram＋希望者メール）
  - `NOTICE_THRESHOLDS` : Lv2（注意） — 全顧客メール（該当エリア）を送るトリガ
  - `WARNING_THRESHOLDS` : Lv3（警戒） — 全顧客メール＋より強い注意喚起
  - `SEVERE_LINE` : Lv4（重大） — 絶対値（150 円/kWh）の非常事態

- メール本文では、Lv2（注意）以上のときに日内最高値を `xx.xx円/kWh` で示します。

- 判定ロジック（関数）:
  - `alert_level(area, peak)` は日内最高値 `peak`（円/kWh）を受け取り、
    以下の順で評価してレベルを返します。
    1. `peak >= SEVERE_LINE` → Lv4（重大）
    2. `peak >= WARNING_THRESHOLDS[area]` → Lv3（警戒）
    3. `peak >= NOTICE_THRESHOLDS[area]` → Lv2（注意）
    4. `peak >= THRESHOLDS[area]` → Lv1（高め）
    5. 上記いずれでもない → Lv0（発火なし）

- 配信判定:
  - `should_push_mail(area, peak)` は内部で `alert_level()` を呼び、
    レベルが `>= 2`（= 注意 以上）であれば `True` を返します。
    つまり「全顧客へのメール送信」は Lv2（注意）以上がトリガです。

- 補助:
  - `HIGH_FLOOR` は表示用の5段階 `PRICE_LEVELS` から自動導出される「高め帯の下限」で、
    `notify_slack.py` や `build_stories.py` が「高めのエリア」を判定するときに使われます。
  - `yen_approx(v)` は円表記を整形するユーティリティ（例: "約12円"）です。

