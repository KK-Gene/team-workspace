# Power Automate / Teams Reminder Integration

## 1. 目的

Team Workspaceが停止していても、登録済みリマインダーをPower Automateが指定時刻にTeamsへ通知できるようにする。

役割分担は以下とする。

```text
Team Workspace / SQLite
  タスク本体の正本
        │
        │ HTTPS JSON
        ▼
Flow A: TeamWorkspace Reminder Intake
        │
        ▼
SharePoint List: TeamWorkspaceReminders
  クラウド通知キューの正本
        │
        │ 5分ごと
        ▼
Flow B: TeamWorkspace Reminder Dispatcher
        │
        ▼
Microsoft Teams
```

Power AutomateはOneDrive上のSQLiteを直接読み書きしない。

## 2. 通知ルール

- `individual`: 担当者の個人チャットへ通知する。
- `channel`: チームチャンネルへ通知する。
- `hybrid`: 通常は担当者、Critical・期限超過・担当者メール未設定・接続テストはチャンネルにも通知する。
- 担当者メールが空の場合、個人通知は行わずチャンネルへフォールバックする。
- 時刻の保存と連携はUTC、Teams表示は日本時間とする。
- 同一`NotificationKey`は1件として扱い、重複通知を防止する。

## 3. SharePoint List

List名:

```text
TeamWorkspaceReminders
```

列は最初に英語名で作成する。後から表示名を日本語へ変更してもよいが、内部名は変更しない。

| 列名 | 種類 | 必須 | 設定・用途 |
|---|---|---:|---|
| `Title` | 1行テキスト | Yes | `NotificationKey`を格納。一意の値を強制する |
| `EventId` | 1行テキスト | Yes | Workspaceが生成するイベントUUID |
| `SchemaVersion` | 数値 | Yes | 現在は`1` |
| `Source` | 1行テキスト | Yes | `team-workspace` |
| `TaskId` | 数値 | No | SQLiteのTask ID |
| `TaskTitle` | 1行テキスト | Yes | タスクタイトル |
| `Description` | 複数行テキスト | No | タスク説明 |
| `Priority` | 選択肢 | Yes | Low / Medium / High / Critical |
| `TaskStatus` | 1行テキスト | Yes | Backlog / Todo / In Progress / Blocked / Done / Test |
| `AssigneeUserId` | 数値 | No | Workspace User ID |
| `AssigneeName` | 1行テキスト | No | 表示名 |
| `AssigneeEmail` | 1行テキスト | No | Teams個人通知先 |
| `DueAtUtc` | 日付と時刻 | No | UTC |
| `ReminderAtUtc` | 日付と時刻 | Yes | UTC、Dispatcherの判定対象 |
| `OccurrenceAtUtc` | 日付と時刻 | No | 繰り返しOccurrence識別 |
| `Recurring` | Yes/No | Yes | 繰り返しタスクか |
| `Tags` | 複数行テキスト | No | カンマ区切り |
| `DestinationMode` | 選択肢 | Yes | individual / channel / hybrid |
| `Status` | 選択肢 | Yes | Pending / Sending / Sent / Cancelled / Failed |
| `RetryCount` | 数値 | Yes | 初期値`0` |
| `SentAt` | 日付と時刻 | No | UTC |
| `LastError` | 複数行テキスト | No | 最新エラー |
| `PayloadJson` | 複数行テキスト | No | 調査用の受信JSON |
| `SourceUpdatedAt` | 日付と時刻 | Yes | `occurred_at_utc` |

推奨設定:

- `Title`: 一意の値を強制する。
- `Status`: インデックスを作成する。
- `ReminderAtUtc`: インデックスを作成する。
- `Status + ReminderAtUtc`を表示する`Pending`ビューを作成する。
- Versioningを有効化する。

## 4. Flow A — Reminder Intake

名称:

```text
TeamWorkspace Reminder Intake
```

### 4.1 Trigger

Teams Workflowsの次のTriggerを使用する。

```text
When a Teams webhook request is received
```

PythonアプリがMicrosoft Entraトークンを付けない構成では、外部アプリから呼べる認証設定が必要になる。Webhook URL自体を秘密情報として扱う。

TriggerのConcurrency Controlを有効化し、Degree of Parallelismを`1`にする。

### 4.2 Parse JSON

ContentにはTrigger Bodyを指定し、次のSchemaを使用する。

```json
{
  "type": "object",
  "required": [
    "schema_version",
    "event_id",
    "action",
    "notification_key",
    "source",
    "occurred_at_utc",
    "task",
    "assignee",
    "delivery"
  ],
  "properties": {
    "schema_version": { "type": "integer" },
    "event_id": { "type": "string" },
    "action": { "type": "string", "enum": ["upsert", "cancel", "test"] },
    "notification_key": { "type": "string" },
    "source": { "type": "string" },
    "occurred_at_utc": { "type": "string" },
    "task": {
      "type": "object",
      "required": ["title", "status", "priority", "recurring", "tags"],
      "properties": {
        "id": { "type": ["integer", "null"] },
        "title": { "type": "string" },
        "description": { "type": "string" },
        "status": { "type": "string" },
        "priority": { "type": "string" },
        "due_at_utc": { "type": ["string", "null"] },
        "reminder_at_utc": { "type": ["string", "null"] },
        "occurrence_at_utc": { "type": ["string", "null"] },
        "recurring": { "type": "boolean" },
        "tags": { "type": "array", "items": { "type": "string" } }
      }
    },
    "assignee": {
      "type": "object",
      "required": ["display_name", "email"],
      "properties": {
        "user_id": { "type": ["integer", "null"] },
        "display_name": { "type": "string" },
        "email": { "type": "string" }
      }
    },
    "delivery": {
      "type": "object",
      "required": ["mode"],
      "properties": {
        "mode": { "type": "string", "enum": ["individual", "channel", "hybrid"] }
      }
    }
  }
}
```

### 4.3 Get items

`TeamWorkspaceReminders`から同じキーを取得する。

```text
Filter Query:
Title eq '<notification_key>'

Top Count:
1
```

`notification_key`はアプリ生成値であり、引用符を含めない。

### 4.4 action = cancel

- 対象が存在すれば`Status = Cancelled`へ更新する。
- `EventId`、`SourceUpdatedAt`、`PayloadJson`も最新値へ更新する。
- 存在しなくても成功として終了する。

### 4.5 action = upsert / test

対象が存在しない場合:

- 新規Itemを作成する。
- `Status = Pending`
- `RetryCount = 0`

対象が存在する場合:

- Task情報、担当者、日時、Payloadを更新する。
- 既存Statusが`Sent`なら、同じキーでは`Sent`を維持する。
- 既存Statusが`Sent`以外なら`Pending`へ戻す。
- `test`は常に新しいキーなので`Pending`となる。

これにより、送信済みOccurrenceのタイトルだけを編集しても二重通知されない。期限・リマインダー日時が変わると新しい`NotificationKey`になるため、新しい通知として登録される。

### 4.6 Flow所有者

- 個人だけを所有者にしない。
- 運用アカウントをOwnerにする。
- 少なくとも1名をCo-ownerにする。
- SharePointとTeamsのConnectionも運用アカウントを推奨する。

## 5. Flow B — Reminder Dispatcher

名称:

```text
TeamWorkspace Reminder Dispatcher
```

### 5.1 Trigger

```text
Scheduled cloud flow
Repeat every: 5 minutes
Time zone: (UTC+09:00) Osaka, Sapporo, Tokyo
```

判定値は`utcNow()`を使用する。

### 5.2 Get items

`TeamWorkspaceReminders`を取得する。

```text
Filter Query:
Status eq 'Pending' and ReminderAtUtc le '<utcNow()>'

Order By:
ReminderAtUtc asc

Top Count:
100
```

デザイナーでは`<utcNow()>`部分へExpressionの`utcNow()`を差し込む。

### 5.3 Apply to each

- Concurrency Controlを有効化する。
- Degree of Parallelismを`1`にする。
- 投稿直前にGet itemし、Statusがまだ`Pending`であることを再確認する。
- `Status = Sending`へ更新してから投稿する。

### 5.4 Teams投稿条件

個人チャット:

```text
DestinationMode = individual または hybrid
AND AssigneeEmail が空でない
```

チャンネル:

```text
DestinationMode = channel
OR Priority = Critical
OR DueAtUtc <= utcNow()
OR AssigneeEmail が空
OR TaskStatus = Test
```

個人通知にはTeams Connectorの`Post a message in a chat or channel`を使用し、Flow botから`AssigneeEmail`宛てに投稿する。

### 5.5 推奨メッセージ

```text
⏰ タスクリマインダー

{TaskTitle}
優先度: {Priority}
期限: {DueAtUtcをTokyo Standard Timeへ変換}
担当: {AssigneeName}
タグ: {Tags}
```

日時表示には次のExpressionを利用できる。

```text
convertTimeZone(<DueAtUtc>, 'UTC', 'Tokyo Standard Time', 'yyyy-MM-dd HH:mm')
```

### 5.6 成功

必要な投稿がすべて成功したら更新する。

```text
Status = Sent
SentAt = utcNow()
LastError = 空
```

### 5.7 失敗

投稿処理を`Try` Scopeへ入れ、`Catch` Scopeを「失敗・タイムアウト時に実行」に設定する。

```text
RetryCount = RetryCount + 1
Status = RetryCount >= 5 ? Failed : Pending
LastError = 失敗内容
```

Power Automate自体のRetry Policyは短い一時障害に利用し、ListのRetryCountは複数回のScheduled Flowをまたぐ再試行に使用する。

## 6. Workspace設定

Webhook URLは共有フォルダー、Git、SQLite、READMEへ書かない。

Windowsのユーザー環境変数へ設定する。

```powershell
[Environment]::SetEnvironmentVariable(
  "TEAM_WORKSPACE_POWER_AUTOMATE_WEBHOOK_URL",
  "https://<Power-Automate-Webhook-URL>",
  "User"
)

[Environment]::SetEnvironmentVariable(
  "TEAM_WORKSPACE_NOTIFICATION_MODE",
  "hybrid",
  "User"
)
```

設定後はPowerShellとStreamlitを再起動する。

ユーザーの個人Teams通知には、WorkspaceのSettingsでUser MasterのEmailを設定する。未設定ユーザーはチャンネル通知へフォールバックする。

## 7. Workspace側の実装動作

- リマインダー付きTask作成: `upsert`
- Task更新: 同じキーへ`upsert`
- 期限・通知日時変更: 古いキーへ`cancel`、新しいキーへ`upsert`
- リマインダー無効化: `cancel`
- Task削除: `cancel`
- 通知確認済み: `cancel`
- 一回Task完了: 現在のキーへ`cancel`
- 繰り返しTask完了: 現在のキーへ`cancel`、次回キーへ`upsert`
- 通信失敗: SQLiteの`notification_outbox`に保持して再送

Webhook URL未設定でもTask操作は成功し、Outboxへ保持される。URL設定後、アプリ起動時またはSettingsの再送操作で同期する。連携開始前から存在するTaskは、Settingsの「全リマインダー同期」で一括登録する。

## 8. 受信Payload例

```json
{
  "schema_version": 1,
  "event_id": "b707c2f0-51a5-4f80-923a-3c36e5ae950d",
  "action": "upsert",
  "notification_key": "task:42:2026-10-02T08:00:00+00:00:reminder",
  "source": "team-workspace",
  "occurred_at_utc": "2026-09-29T04:30:00+00:00",
  "task": {
    "id": 42,
    "title": "Weekly Backup Check",
    "description": "バックアップ結果を確認する",
    "status": "Todo",
    "priority": "High",
    "due_at_utc": "2026-10-02T09:00:00+00:00",
    "reminder_at_utc": "2026-10-02T08:00:00+00:00",
    "occurrence_at_utc": "2026-10-02T08:00:00+00:00",
    "recurring": true,
    "tags": ["backup", "weekly"]
  },
  "assignee": {
    "user_id": 2,
    "display_name": "Member A",
    "email": "member.a@example.com"
  },
  "delivery": {
    "mode": "hybrid"
  }
}
```

## 9. 受入テスト

1. SettingsでConnectionが`Configured`になる。
2. 「テスト通知を送信」でSharePoint ListへTest Itemが作成される。
3. 5分以内にTeamsチャンネルへテスト通知が届く。
4. 相対リマインダーTaskを作成するとListへPendingで登録される。
5. 期限を変更すると旧ItemがCancelled、新ItemがPendingになる。
6. Taskを削除するとItemがCancelledになる。
7. Taskを完了するとItemがCancelledになる。
8. 繰り返しTask完了後、次回OccurrenceがPendingになる。
9. 同じTaskを複数回保存しても同一Occurrenceが複数通知されない。
10. Flow A停止中にTaskを保存し、再開後にSettingsから再送できる。
11. 担当者Emailなしの場合にチャンネルへフォールバックする。
12. Critical Taskが担当者とチャンネルの両方へ通知される。

## 10. 運用監視

- SharePointの`Failed`ビューを週1回確認する。
- Power AutomateのRun History失敗を通知対象にする。
- Workspace SettingsのFailed件数を確認する。
- Webhook URLを変更した場合は全PCのユーザー環境変数を更新する。
- Flow所有者の退職・ライセンス変更時はOwnerとConnectionを先に移管する。
