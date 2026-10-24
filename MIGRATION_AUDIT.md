# 本家ハルキューの独立移設・監査記録（2026-10-24）

## 移設元と独立性
- 移設元：`yuhevita-wq/keirin-ai-predictor`
- 移設元の固定運用ブランチ：`production/flagship-haruqube-20260321-live-v1`
- 元の固定コードのコミット：`cf534f05945dc73747b4906eb1f2e2ff469f4983`
- 新リポジトリ：`yuhevita-wq/haruq` / `main`
- 元の運用ブランチ・モデル・購入規則への書き込み：なし

## 内容の照合
元コードの機能に必要な `config.py`、`data/`、`db/`、`features/`、`models/`、固定スナップショット、`scripts/flagship_live_predict.py`、`scripts/haruq_operating_policy.py`、`scripts/haruq_publish_web.py`、回帰テスト、および `docs/haruq/results/` と監査資料をGit blob SHAで照合。
**84ファイル/84ファイルがバイト一致、差分0件。**
保存済み予測結果フォルダは56ファイル（23レース、32件のラン保存、1索引）。

## 固定モデルと履歴資産
- 固定モデルSHA256：`e70690f4538b77e927a042e7ae2db312f8a0a4f16bf72def37e7ccad3568c193`
- 新モデルRelease：`haruqube-20260321-flagship-v1`、モデル約1.5MB。原本モデル照合後の正確なコピー。
- 新履歴Release：`haruqube-20260321-history-cache-live`、約173MBの暗号化SQLiteとチェックサム。平文データ・鍵をGitへ置かない。
- 新Release生成に使用したGitHub Actions：`39985296122`、成功。
- 固定ルールの回帰テスト：GitHub Actions `39985010551`、成功。

## 新環境での差分（必要な実行パスの移設のみ）
- 単レース・ミッドナイトActionsの対象ブランチを`main`へ。
- 同名のモデル・履歴Releaseを新リポジトリから取得するよう指定。
- UIページの履歴JSON取得先を新リポジトリ`main/docs/haruq/results/`へ。
- 予測値、特徴量、モデル本体、HIGH判定・金額は変更なし。

## 復号キー不一致の解消（2026-10-24）
- 新環境のシークレットは旧暗号化履歴と一致しなかった。既存の新環境シークレットを変更せず、元と同じ履歴を再暗号化した。
- 移行先Release：`haruqube-20260321-history-cache-haruq-v1`。元のRelease・固定モデル・旧本番ブランチは変更していない。
- 新環境でパスフレーズ保護された一時受信鍵を作成（Actions `40048273956`）。旧環境の別運用ブランチで元履歴を復号・SHA256照合し、受信公開鍵に暗号化して転送（`40048330860`）。
- 新環境で復号し、既存シークレットでAES256再暗号化。別ファイルへ復号し直し、元とのSHA256照合・バイト比較・SQLite quick_checkを全て通過（`40048382799`）。
- 単レース・全日・ミッドナイトの3ワークフローの履歴参照先を新Releaseへ変更。末尾のCR/LFのみ除去する処理を統一。予測モデル・特徴量・閾値・買い目・配分のコード変更なし。
- 秘密値および平文履歴は公開しない。runner上の一時平文は終了時に削除する。

## 移設後の確認結果
1. **復号：解消済み。** 新環境に既に登録されたシークレットで履歴を開ける。キーの再登録は不要。
2. **Web：公開済み。** `https://yuhevita-wq.github.io/haruq/haruq/daily.html?date=2026-10-24`。
3. **ライブ同等性：確認済み。** 新環境の通常単レースActions `40048448605` は名古屋5R（`202610244205`）を予測・Web掲載まで成功。旧環境の保存結果 `39993544283` と `ranked`（順位・スコア）、`confidence`、`bets`（買い目・金額）、`total_yen`、`s3_policy`、`model_sha256` が全て完全一致。
4. **履歴鮮度の継続：従来の残課題。** 今回は復号キー不一致のみ解消し、履歴自動更新の仕様は変更していない。

## 方針
本家固定AIを再学習・改造しない。裏ハルキューの実験は`yuhevita-wq/ura-haruq`で分離する。
