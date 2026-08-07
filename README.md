# でんき予報システム仕様書

このドキュメントは、`tera-denki-yohou-main` リポジトリ内で動作する「でんき予報」の仕組みと運用をわかりやすくまとめたものです。

---

## 1. 目的

このシステムは、JEPX の翌日スポット価格データを取り込み、

- GitHub Pages 向け Web コンテンツ生成
- Instagram Stories 生成・投稿
- 価格アラート判定と通知

を自動化することを目的としています。

従来は手作業だった JEPX の確認から投稿までの一連の流れを、自動化しています。

---

## 2. 目次

- 3. 主要ファイルと役割
- 4. システム構成
- 5. 実行フロー
- 6. アラート判定仕様（概要）
- 7. 監視フロー
- 8. 運用情報
- 9. 重要な注意点
- 10. まとめ

---

## 3. 主要ファイルと役割

### 3.1 データ取得・変換

- `scripts/fetch_jepx.py`
  - JEPX 公式サイトから当該年度の CSV を取得し、`data/spot_summary.csv` に保存
- `scripts/build_prices.py`
  - `data/spot_summary.csv` から翌日の `prices.json` を生成
- `scripts/build_history.py`
  - 過去データを `history.json` に変換
- `scripts/build_monthly.py`
  - 月平均データを `monthly.json` に更新

### 3.2 Web / Instagram 生成

- `scripts/build_stories.py`
  - `prices.json` を元に縦長 HTML (`stories.html`) を生成
- `scripts/render_png.py`
  - `stories.html` を PNG に変換し `stories_*.png` を生成

### 3.3 価格アラート / 通知

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

### 3.4 Instagram 投稿

- `scripts/post_instagram_stories.py`
  - `docs/stories/stories_*.png` を Instagram Stories に投稿
- `scripts/check_ig_token.py`
  - Instagram アクセストークンの期限を監視

### 3.5 GitHub Actions

- `.github/workflows/daily-denki-yohou.yml`
  - メインの自動実行フロー
- `.github/workflows/denki-yohou-watchdog.yml`
  - 当日未配信・遅延を監視するワークフロー
- `.github/workflows/alert-test.yml`
  - 価格アラートの手動テスト用

---

## 4. システム構成

### 4.1 起動方法

このシステムは、主に次の方法で起動します。

- GitHub Actions のスケジュール実行
  - 10:40 JST
  - 11:10 JST
  - 11:40 JST
- GitHub Actions の `workflow_dispatch`
  - 手動実行、`force=true` で強制再実行
- `push`
  - `data/spot_summary.csv` の更新時
- `cron-job.org`
  - `workflow_dispatch` を呼び出す外部 cron 運用

### 4.2 重複実行防止

- `docs/.last_run` を確認し、当日実行済みなら本体処理をスキップ
- `workflow_dispatch` の `force=true` は例外で強制実行
- `scripts/post_instagram_stories.py` は `.ig_state.json` で投稿進捗を管理し、二重送信を防止

---

## 5. 実行フロー

### 5.1 メイン処理

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
7. `docs/` へ成果物を配置
   - `stories_*.png` を `docs/stories/`
   - `prices.json` と `history.json`, `monthly.json` を `docs/` にコピー

### 5.2 価格アラート関連

以下は本体公開とは独立して動く補助処理です。

- `scripts/build_alerts.py docs/prices.json`
  - 価格発火判定と配信用素材の生成
- `scripts/upload_alerts_drive.py`
  - 発火物を Google Drive に格納
- `scripts/notify_alert_slack.py`
  - 発火状況を Slack に通知

これらは `continue-on-error: true` になっており、失敗しても主要公開フローを止めません。

### 5.3 公開と Instagram 投稿

1. GitHub へコミット＆プッシュ
2. GitHub Pages 反映の確認
   - `pages_base_url/prices.json` が今回の日付になるまで待機
3. `scripts/check_ig_token.py`
   - IG トークン期限をチェック
4. `scripts/post_instagram_stories.py`
   - Stories 画像を Instagram に投稿
5. `docs/.last_run` を更新
   - Instagram 投稿成功後に当日完了マーカーを記録
6. `scripts/notify_slack.py`
   - 最終的な安否確認通知を Slack に送信

---

## 6. アラート判定仕様（概要）

- 閾値は `scripts/alert_config.py` で定義されています。
  - `THRESHOLDS` : Lv1（高め） — 情報提供（Instagram＋希望者メール）
  - `NOTICE_THRESHOLDS` : Lv2（注意） — 全顧客メール（該当エリア）を送るトリガ
  - `WARNING_THRESHOLDS` : Lv3（警戒） — 全顧客メール＋より強い注意喚起
  - `SEVERE_LINE` : Lv4（重大） — 絶対値（150 円/kWh）の非常事態

- メール本文では、Lv2（注意）以上のときに日内最高値を `xx.xx円/kWh` で示します。

### 6.1 判定ロジック

- `alert_level(area, peak)` は日内最高値 `peak`（円/kWh）を受け取り、以下の順で評価してレベルを返します。
  1. `peak >= SEVERE_LINE` → Lv4（重大）
  2. `peak >= WARNING_THRESHOLDS[area]` → Lv3（警戒）
  3. `peak >= NOTICE_THRESHOLDS[area]` → Lv2（注意）
  4. `peak >= THRESHOLDS[area]` → Lv1（高め）
  5. 上記いずれでもない → Lv0（発火なし)

- `should_push_mail(area, peak)` は内部で `alert_level()` を呼び、レベルが `>= 2`（= 注意 以上）であれば `True` を返します。
  つまり「全顧客へのメール送信」は Lv2（注意）以上がトリガです。

### 6.2 補助

- `HIGH_FLOOR` は表示用の5段階 `PRICE_LEVELS` から自動導出される「高め帯の下限」です。
  - `notify_slack.py` や `build_stories.py` が「高めのエリア」を判定するときに使います。
- `yen_approx(v)` は円表記を整形するユーティリティです（例: "約12円"）。

---

## 7. 監視フロー

`denki-yohou-watchdog.yml` は次の時間に実行されます。

- 11:30 JST
- 12:30 JST

### 7.1 監視内容

- `docs/.last_run` の確認
- 当日未配信であれば Slack に警告
- 当日配信済みでも完了が遅い場合は遅延注意を Slack に送信

---

## 8. 運用情報

### 8.1 環境変数

- `SLACK_WEBHOOK_URL`
  - Slack 通知用
- `PAGES_BASE_URL`
  - GitHub Pages ベース URL
- `IG_ACCESS_TOKEN`
  - Instagram 長期アクセストークン
- `IG_USER_ID`
  - Instagram Business Account ID

### 8.2 ローカル実行コマンド例

- `python3 scripts/fetch_jepx.py`
- `python3 scripts/build_prices.py --require-tomorrow`
- `python3 scripts/build_history.py --days 90`
- `python3 scripts/build_monthly.py --rebuild`

### 8.3 トラブルシューティング

- CSV が見つからない
  - `scripts/fetch_jepx.py` を実行して `data/spot_summary.csv` を生成
- `prices.json` が生成されない
  - `build_prices.py` の実行ログを確認し、`--require-tomorrow` の挙動を確認
- Slack 通知が失敗する
  - `SLACK_WEBHOOK_URL` を確認し、`python3 scripts/notify_slack.py` を実行
- Instagram 投稿エラー
  - `scripts/check_ig_token.py` でトークンの有効期限を確認

---

## 9. 重要な注意点

- `build_prices.py --require-tomorrow` は「翌日のデータ」を明示的に要求します。
  - JEPX の公表遅延時に古いデータを誤配信しないためです。
- `post_instagram_stories.py` は `.ig_state.json` で投稿済み進捗を管理し、途中失敗時の二重投稿を防ぎます。
- 価格アラート関連は本体公開と独立しているため、アラート側の問題があっても Web/Instagram 配信は継続します。

---

## 10. まとめ

このシステムの基本的な流れは、

1. JEPX CSV 取得
2. `prices.json` 生成
3. `history.json` / `monthly.json` 更新
4. Web・Stories 生成
5. 価格アラート判定
6. GitHub Pages 公開
7. Instagram Stories 投稿
8. `docs/.last_run` 更新