# Team Workspace

4〜5名の小規模チーム向けに、タスク・リマインダー・スニペット・リンク・用語・ノートを一か所へ集約する Streamlit アプリです。Windows PC 上で各自が起動し、SQLite データベースを OneDrive 共有フォルダー経由で同期する前提です。

> **重要:** OneDrive はデータベースサーバーではありません。本構成は「読み取り中心・書き込み少なめ」の小規模 MVP としてのみ利用してください。同時書き込みに対する強い整合性保証はありません。

## 主な機能

- Windows ユーザー名による自動識別（最初の利用者は Admin）
- Dashboard / My Day / Team Status
- 期限日・任意の期限時刻・優先度・担当者・タグ付きタスク
- 絶対日時／期限からの相対リマインダー
- 日次・週次・月次・N週間隔の繰り返しと完了履歴
- Snippets / Links / Glossary / Notes の CRUD
- 横断検索、Favorite、Activity Log
- CSV エクスポート
- SQLite migration、整合性チェック、世代管理バックアップ

## アーキテクチャ

```text
Streamlit UI (app.py, views/)
             ↓
Services (workspace/services.py)
             ↓
Repositories (workspace/repositories/)
             ↓
SQLite adapter (workspace/database.py)
             ↓
data/workspace.db
```

UI に SQL・通知計算・繰り返し計算を置かず、各責務をサービス／リポジトリへ分離しています。現在時刻は `Clock` 経由で扱うため、時刻依存テストも固定時刻で実行できます。

## 必要環境

- Windows 10/11
- Python 3.11 以上
- OneDrive 同期クライアント（共有運用時のみ）
- Git（更新運用する場合）

## 初回セットアップ

PowerShell でリポジトリへ移動し、仮想環境を作成します。

```powershell
cd C:\path\to\team-workspace
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

起動:

```powershell
python -m streamlit run app.py
```

または `start.bat` をダブルクリックします。初回起動時に `data/workspace.db` とスキーマが自動作成されます。最初に起動した Windows ユーザーは Admin、それ以降の未知のユーザーは Member として登録されます。

## フォルダー構成

```text
app.py                    Streamlit エントリーポイント
views/                    Dashboard・Tasks・Knowledge・Settings 等
workspace/                モデル、サービス、DB、リポジトリ
database/migrations/      番号付き SQL migration
data/                     実データベース（Git対象外）
backups/                  自動／手動バックアップ（Git対象外）
logs/workspace.log        技術ログ（Git対象外）
scripts/seed_dev.py       明示実行専用の開発データ投入
tests/                    一時SQLiteを使うpytest
```

## OneDrive 配置と運用ルール

1. リポジトリ一式をチームの OneDrive 共有フォルダーへ置きます。
2. `data` と `backups` を含むフォルダーを **「このデバイス上で常に保持する」** に設定します。
3. 初回は1台だけで起動し、DB作成後に同期完了を待ちます。
4. 他PCは同期完了後に起動します。
5. 一括編集、migration、復旧は全員のアプリを停止して1台で実施します。
6. OneDrive の「競合コピー」を発見したら書き込みを止め、どちらかを安易に削除しないでください。

SQLite 設定は次のとおりです。

```sql
PRAGMA journal_mode = DELETE;
PRAGMA synchronous = FULL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
```

WAL は `.db`、`-wal`、`-shm` が別々に同期される危険があるため使用しません。接続は操作単位で開閉し、書き込みは短いトランザクションで実行します。ローカルロックは有限回リトライしますが、別PCの OneDrive レプリカ間競合は検出・解決できません。

## Backup

- 起動時に前回バックアップから24時間以上経過していれば自動作成
- Settings から手動作成可能
- SQLite Backup API を使用
- 作成後に `PRAGMA integrity_check` を実行
- 既定で最新15世代を保持

環境変数で変更できます。

```powershell
$env:TEAM_WORKSPACE_BACKUP_INTERVAL_HOURS = "12"
$env:TEAM_WORKSPACE_BACKUP_RETENTION = "20"
```

## Restore

1. 全PCでアプリを停止します。
2. OneDrive の同期完了を確認します。
3. 現在の `data/workspace.db` と競合コピーを別フォルダーへ退避します。
4. `backups/` から最新の正常なバックアップを選びます。
5. バックアップをコピーして `data/workspace.db` にします。
6. 1台だけで起動し、Settings の「整合性チェック」を実行します。
7. 正常なら同期完了後に他PCを再開します。

復旧前のファイルは、調査と手作業でのデータ救出が終わるまで削除しないでください。

## Migration

`database/migrations/NNN_description.sql` を番号順に適用し、`schema_version` に記録します。新バージョンの配布時は全利用者を停止し、1台で更新・起動・整合性確認・OneDrive同期を完了してから他PCを再開してください。古いアプリと新しいスキーマを同時利用しないでください。

## CSV Export

Settings から Tasks、Snippets、Links、Glossary、Notes を UTF-8 BOM付きCSVとしてダウンロードできます。CSV は利便性・部分復旧用であり、完全バックアップの代替ではありません。

## Tests

```powershell
python -m pytest
```

テストは pytest の一時ディレクトリに専用DBを作成し、本番の `data/workspace.db` を使用しません。

## Optional Development Seed

本番DBへ誤投入しないよう、対象パスと確認フラグが必須です。空の開発DBにだけ投入できます。

```powershell
python scripts/seed_dev.py --database data/dev.db --confirm
$env:TEAM_WORKSPACE_DB = "data/dev.db"
python -m streamlit run app.py
```

## Troubleshooting

### `database is locked`

- 数秒待って再実行する
- 同じPCで複数の書き込み操作をしていないか確認する
- OneDrive 同期完了を確認する
- 改善しない場合は全員のアプリを停止して再確認する

### 起動できない

- `python --version` が3.11以上か確認
- `python -m pip install -r requirements.txt` を再実行
- `logs/workspace.log` を確認
- DBがローカルに完全ダウンロードされているか確認

### OneDrive 競合コピー

編集を停止し、各DBを保存してください。各コピーへ整合性チェックを行い、最も新しく完全なDBを基準に復旧します。SQLite DB同士をファイルレベルで結合することはできません。必要な差分はCSVや個別照合で救出します。

## 既知の制約

- アプリを閉じている間はリマインダーを表示できません。
- 複数PCの同時書き込みを安全に直列化できません。
- OneDrive 同期中のロストアップデートや競合コピーを完全には防げません。
- Favorite は Snippet、Link、Glossary、Note が対象です。
- Custom Interval は MVP では N週間隔です。
- 大規模データ、高頻度更新、重要な監査記録には適しません。

利用規模や書き込み頻度が増えた場合は、Repository interface を維持したまま共有DB/API（SharePoint Lists、Microsoft Lists、SQLサービス等）へ移行してください。
