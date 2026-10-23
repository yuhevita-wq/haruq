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

## 残作業（完了と扱わない）
1. **復号シークレットの引継ぎ：** 旧リポジトリ内のGitHub Actionsシークレット `COLLECTOR_PASSPHRASE` は新リポジトリには自動コピーされない。所有者が新リポジトリのSettings → Secrets and variables → Actionsで同一の値を登録する必要がある。値はチャットへ送らない。
2. **Web公開設定：** GitHub Pages はActions側の初回有効化が権限不足で拒否されたため未公開。所有者が新リポジトリのSettings → Pagesで`Deploy from a branch`、`main`、`/docs`を選択してSaveする。画面は`docs/index.html`と`docs/haruq/index.html`に移設済み。失敗を繰り返さないよう自動PagesデプロイActionは削除した。
3. **ライブ同等性試験：** シークレットが設定されたら同じレースIDで新旧の予測順位・confidence・2車単・3連単・配分を比較して一致を確認する。検証前に新環境の本番切替を宣言しない。
4. **履歴鮮度の継続：** 新履歴は移設時点のスナップショット。今後の更新運用は未設定。履歴最終日から7日を超える将来レースは現行予測コードの鮮度検査で拒否されるため、継続運用には履歴更新経路が必要。

## 方針
本家固定AIを再学習・改造しない。裏ハルキューの実験は`yuhevita-wq/ura-haruq`で分離する。
