# TaskMasterAI CLI リファレンス

## 概要

TaskMasterAI CLI は、コマンドラインからAI駆動のエグゼクティブアシスタント機能にアクセスするためのインターフェースです。

## 起動方法

### 対話モード

```bash
python -m src.cli
```

対話的なシェルが起動し、連続してコマンドを入力できます。

### 単一コマンドモード

```bash
python -m src.cli <command>
```

単一のコマンドを実行して終了します。

### 認証モード

```bash
python -m src.cli auth
```

Google API認証フローを実行します（初回セットアップ時に必要）。

## コマンド一覧

### メール管理

| コマンド | 説明 | 例 |
|---------|------|-----|
| `inbox` | 受信トレイのメールを要約表示 | `inbox` |
| `inbox <count>` | 指定件数のメールを要約 | `inbox 5` |
| `draft <subject>` | メール下書きを作成 | `draft "週報について"` |

#### inbox コマンド詳細

```bash
taskmaster> inbox
```

**出力例:**
```
📧 受信トレイ要約 (10件)

1. [重要] プロジェクト進捗報告
   送信者: manager@company.com
   概要: Q4の目標達成状況について確認依頼
   アクション: 返信が必要

2. [情報] チームミーティング議事録
   送信者: team@company.com
   概要: 昨日のミーティング内容のまとめ
   アクション: 確認のみ
```

### カレンダー管理

| コマンド | 説明 | 例 |
|---------|------|-----|
| `today` | 今日の予定を表示 | `today` |
| `schedule <title>` | 会議をスケジュール | `schedule "1on1" with bob@example.com 30min` |
| `free` | 空き時間を表示 | `free` |

#### schedule コマンド詳細

```bash
taskmaster> schedule "プロジェクトレビュー" with alice@example.com bob@example.com 60min
```

**オプション:**
- `with <attendees>`: 参加者（スペース区切りで複数指定可）
- `<duration>min`: 所要時間（分単位）

**出力例:**
```
📅 スケジュール提案

タイトル: プロジェクトレビュー
参加者: alice@example.com, bob@example.com
所要時間: 60分

候補時間:
  1. 2026-01-10 10:00-11:00 (全員空き)
  2. 2026-01-10 14:00-15:00 (全員空き)
  3. 2026-01-11 09:00-10:00 (全員空き)

予定を作成しますか？ [番号を入力/n でキャンセル]
```

### ステータス確認

| コマンド | 説明 | 例 |
|---------|------|-----|
| `status` | システムステータス表示 | `status` |
| `usage` | 使用量を表示 | `usage` |
| `help` | ヘルプを表示 | `help` |

### システムコマンド

| コマンド | 説明 |
|---------|------|
| `help` | コマンドヘルプを表示 |
| `quit` / `exit` / `q` | CLIを終了 |

## 動作モード

TaskMasterAI は安全性を重視した3つの動作モードをサポートしています。

### Draft Mode（デフォルト）

メール送信などのアクションは下書きとして保存され、実際の送信は手動で行います。

### Confirmation Mode（デフォルト）

すべてのアクション実行前に確認を求めます。

```
📤 メール送信の確認

宛先: client@example.com
件名: プロジェクト進捗報告
本文: （プレビュー表示）

この内容で送信しますか？ [y/n]
```

### Auto Mode

事前に設定したルールに基づき、確認なしで自動実行します。**明示的に有効化が必要です。**

## 環境変数

CLIの動作をカスタマイズするための環境変数：

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `TASKMASTER_LOG_LEVEL` | ログレベル | `INFO` |
| `TASKMASTER_AUDIT_LOG` | 監査ログのパス | `logs/audit_log.json` |
| `TASKMASTER_MODE` | 動作モード（draft/confirmation/auto） | `confirmation` |

## 設定ファイル

### config/.env

```bash
# Google API
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret

# LLM API
OPENAI_API_KEY=your_openai_key
# または
ANTHROPIC_API_KEY=your_anthropic_key

# 動作設定
TASKMASTER_MODE=confirmation
```

## トラブルシューティング

### 認証エラー

```
❌ 認証に失敗しました
```

**解決方法:**
1. `python -m src.cli auth` を実行
2. ブラウザでGoogleアカウントにログイン
3. 必要な権限を許可

### API制限エラー

```
使用制限に達しました。プランをアップグレードしてください。
```

**解決方法:**
- `usage` コマンドで現在の使用量を確認
- 必要に応じてプランをアップグレード

### 接続エラー

```
接続エラー: ネットワークを確認してください
```

**解決方法:**
- インターネット接続を確認
- プロキシ設定を確認（企業ネットワークの場合）

## 使用例シナリオ

### 朝のルーティン

```bash
# 今日の予定を確認
taskmaster> today

# 重要なメールを確認
taskmaster> inbox 5

# 返信ドラフトを作成
taskmaster> draft reply to <email_id>
```

### 会議のスケジューリング

```bash
# 空き時間を確認
taskmaster> free

# 会議を提案
taskmaster> schedule "週次ミーティング" with team@company.com 30min

# 候補から選択して確定
```

## バージョン情報

```bash
python -m src.cli --version
```

**現在のバージョン:** 0.1.0
