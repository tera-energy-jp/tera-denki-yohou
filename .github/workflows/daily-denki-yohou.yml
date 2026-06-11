name: でんき予報 デイリー生成（自動）
# 起動タイミング：
#  - 毎朝 10:40 / 11:10 / 11:40 JST の3回（GitHubの遅延対策で複数仕掛ける）。
#    当日まだ「配信完了」していなければ実処理し、完了済みならスキップ。
#    ※ 配信済みマーカー（docs/.last_run）は Instagram 投稿の成功後にのみ書く。
#      → 途中で失敗した回があっても、後続の cron が自動でリトライしてくれる。
#  - data/spot_summary.csv を更新push したとき（手動差し替え時のフォールバック）
#  - 手動実行（Run workflow）は常に実行（ガード無視）
#  ※ 実運用の定時起動は cron-job.org からの workflow_dispatch を主役にしている。
on:
  schedule:
    - cron: '40 1 * * *'   # 10:40 JST
    - cron: '10 2 * * *'   # 11:10 JST
    - cron: '40 2 * * *'   # 11:40 JST
  push:
    paths:
      - 'data/spot_summary.csv'
  workflow_dispatch:
permissions:
  contents: write   # 生成したPNG/JSONを docs/ にコミットするため
jobs:
  # 当日すでに配信済みかを判定（複数cronの重複実行を防ぐ）
  guard:
    runs-on: ubuntu-latest
    outputs:
      should_run: ${{ steps.check.outputs.should_run }}
    steps:
      - uses: actions/checkout@v4
      - id: check
        run: |
          TODAY=$(TZ=Asia/Tokyo date +%Y-%m-%d)
          if [ -f docs/.last_run ] && [ "$(cat docs/.last_run)" = "$TODAY" ]; then
            echo "本日（$TODAY）は配信済み。スキップします。"
            echo "should_run=false" >> "$GITHUB_OUTPUT"
          else
            echo "本日（$TODAY）は未配信。実行します。"
            echo "should_run=true" >> "$GITHUB_OUTPUT"
          fi
  build-and-notify:
    needs: guard
    # 自動実行（cron）は「当日未配信」のときだけ。
    # 手動実行（workflow_dispatch）と CSV手動差し替え（push）は常に実行
    # （push はフォールバック用なので、配信済みガードに阻まれないようにする）。
    if: needs.guard.outputs.should_run == 'true' || github.event_name == 'workflow_dispatch' || github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - name: チェックアウト
        uses: actions/checkout@v4
      - name: Python セットアップ
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: 依存インストール（Playwright + Chromium + requests）
        run: |
          pip install playwright requests
          playwright install --with-deps chromium
      - name: ⓪ JEPXから最新CSVを取得
        run: python scripts/fetch_jepx.py
      - name: ① prices.json を生成（鮮度チェック付き）
        # --require-tomorrow：CSVの最新日ではなく「あした（JST）」を明示要求。
        # あしたのデータがまだ無ければここで失敗し、古いデータの再配信を防ぐ。
        # マーカー未記録のまま終わるので、後続の cron が自動でリトライする。
        run: python scripts/build_prices.py --require-tomorrow
      - name: ② stories.html を生成
        run: python scripts/build_stories.py
      - name: ③ PNG（5枚）を書き出し
        run: python scripts/render_png.py stories.html
      - name: ④ 公開ディレクトリ（docs/）へ配置
        run: |
          mkdir -p docs/stories
          cp stories_*.png docs/stories/
          cp prices.json   docs/prices.json
      - name: ⑤ コミット＆プッシュ（GitHub Pages 公開）
        run: |
          git config user.name  "tera-denki-bot"
          git config user.email "bot@users.noreply.github.com"
          git add docs/
          git commit -m "でんき予報 $(TZ=Asia/Tokyo date +%Y-%m-%d)" || echo "変更なし（スキップ）"
          git push
      - name: ⑥ Pages 反映待ち（prices.json の日付で実確認）
        # 固定 sleep だとデプロイ遅延時に旧画像をIG側が掴むため、
        # 公開URLの prices.json が今回の日付になるまでポーリングする（最大5分）。
        run: |
          EXPECTED=$(python -c "import json; print(json.load(open('prices.json'))['date_raw'])")
          echo "期待する配信日: $EXPECTED"
          for i in $(seq 1 20); do
            LIVE=$(curl -fsSL "${{ vars.PAGES_BASE_URL }}/prices.json?nocache=$(date +%s)" \
                   | python -c "import json,sys; print(json.load(sys.stdin).get('date_raw',''))" \
                   2>/dev/null || echo "")
            if [ "$LIVE" = "$EXPECTED" ]; then
              echo "Pages 反映を確認しました（$LIVE）"
              exit 0
            fi
            echo "  反映待ち ($i/20)… 公開中: '$LIVE'"
            sleep 15
          done
          echo "::error::Pages の反映を5分以内に確認できませんでした。"
          exit 1
      - name: ⑦ IGトークンの残り日数チェック（失効14日前からSlack警告）
        # お知らせ専用。チェック自体が失敗しても配信は止めない。
        continue-on-error: true
        env:
          IG_ACCESS_TOKEN: ${{ secrets.IG_ACCESS_TOKEN }}
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        run: python scripts/check_ig_token.py
      - name: ⑧ Instagram Stories へ投稿
        id: instagram
        env:
          IG_ACCESS_TOKEN: ${{ secrets.IG_ACCESS_TOKEN }}
          IG_USER_ID: ${{ secrets.IG_USER_ID }}
          PAGES_BASE_URL: ${{ vars.PAGES_BASE_URL }}
        run: python scripts/post_instagram_stories.py
      - name: ⑨ 配信済みマーカーを記録（IG投稿の成功後のみ）
        # ここまで到達＝Instagram投稿まで成功。マーカーを書いて当日分を完了扱いに。
        # 途中で失敗した場合はマーカーが書かれず、後続 cron がリトライする。
        run: |
          TZ=Asia/Tokyo date +%Y-%m-%d > docs/.last_run
          git config user.name  "tera-denki-bot"
          git config user.email "bot@users.noreply.github.com"
          git add docs/.last_run
          git commit -m "配信済みマーカー $(TZ=Asia/Tokyo date +%Y-%m-%d)"
          git push
      - name: ⑩ Slack へ通知（安否確認・失敗しても本体に影響させない）
        if: always()              # 途中のステップが失敗した日こそ必ず通知する
        continue-on-error: true   # Slack自体の失敗でジョブを赤にしない
        timeout-minutes: 2        # かつての約20分ハングの再発防止（強制打ち切り）
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
          PAGES_BASE_URL: ${{ vars.PAGES_BASE_URL }}
          IG_RESULT: ${{ steps.instagram.outcome }}
          RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        run: python scripts/notify_slack.py
