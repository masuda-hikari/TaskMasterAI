# TaskMasterAI

**AI駆動の仮想エグゼクティブアシスタント**

TaskMasterAIは、単なるチャットボットではありません。ユーザーの許可のもとで実際にアクションを実行し、ルーチンワークを自動化するツールです。

## 主な機能

### メール管理
- **スマート受信トレイ要約**: 未読メールを優先度順に日次ダイジェスト
- **AI返信ドラフト**: コンテキストに適した返信案を自動生成
- **メールトリアージ**: 自動分類とアクションアイテムのハイライト

### カレンダー管理
- **インテリジェントスケジューリング**: 全参加者の空き時間を自動検索
- **コンフリクト検出**: スケジュールの競合を事前に検出・解決
- **スマートリマインダー**: 予定と優先度に基づくコンテキスト認識リマインダー

### タスク自動化
- **定型タスク実行**: 週次レポートやステータス更新を自動化
- **クロスアプリ連携**: メール、カレンダー、タスク管理ツールを統合
- **進捗追跡**: タスクの状態を追跡し、期限前にリマインド

## クイックスタート

### 前提条件

- Python 3.11以上
- pip（Pythonパッケージマネージャー）
- Google Cloud アカウント（Gmail/Calendar API用）

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/yourusername/TaskMasterAI.git
cd TaskMasterAI

# 仮想環境を作成・有効化
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

# 依存関係をインストール
pip install -r requirements.txt

# 環境変数テンプレートをコピー
cp config/.env.example config/.env
```

### Google API設定

1. [Google Cloud Console](https://console.cloud.google.com/)にアクセス
2. 新規プロジェクトを作成
3. Gmail API と Google Calendar API を有効化
4. OAuth 2.0 クライアントIDを作成
5. 認証情報をダウンロードして `config/credentials/` に配置

詳細は [Google API設定ガイド](docs/setup_google_api.md) を参照してください。

### 初回起動

```bash
# CLIを起動
python -m src.cli

# または直接コマンド実行
python -m src.cli inbox  # 受信トレイを要約
```

## 使用例

### CLI コマンド

```bash
# 受信トレイを要約
taskmaster inbox

# 特定の件数だけ要約
taskmaster inbox --max 5

# 今日の予定を確認
taskmaster today

# 会議をスケジュール
taskmaster schedule "週次ミーティング" --with alice@example.com bob@example.com --duration 30

# 返信ドラフトを作成
taskmaster draft --to "message_id_123"

# ヘルプを表示
taskmaster --help
```

### Web API

```bash
# サーバーを起動
uvicorn src.api:app --reload

# ユーザー登録
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password123"}'

# ログイン
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password123"}'

# メール要約（トークン付き）
curl -X POST "http://localhost:8000/email/summarize" \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{"max_emails": 10}'
```

### Python SDK

```python
from taskmaster import TaskMasterClient

# クライアントを初期化
client = TaskMasterClient(base_url="http://localhost:8000")

# ログイン
client.login("user@example.com", "password123")

# メール要約を取得
summaries = client.summarize_emails(max_emails=5)
for summary in summaries["summaries"]:
    print(f"[{summary['priority']}] {summary['subject']}")
    print(f"  要約: {summary['summary']}")

# スケジュール提案を取得
proposals = client.propose_schedule(
    title="チームミーティング",
    attendees=["alice@example.com", "bob@example.com"],
    duration_minutes=30
)
```

## API ドキュメント

開発サーバー起動時、以下のURLで対話的なAPIドキュメントにアクセスできます：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## 料金プラン

| プラン | 価格 | 対象ユーザー |
|--------|------|-------------|
| **Free** | 無料 | 機能を試したい方（50メール要約/月） |
| **Personal** | ¥1,480/月 | 個人プロフェッショナル（500メール要約/月） |
| **Pro** | ¥3,980/月 | パワーユーザー（2000メール要約/月） |
| **Team** | ¥2,480/ユーザー/月 | チーム利用（5000メール要約/月） |
| **Enterprise** | 要相談 | オンプレミス・カスタム統合 |

### ROI試算

- あなたの時給: ¥5,000
- TaskMasterAIで節約する時間: 週5時間
- **月間節約額**: ¥100,000+
- **月額コスト**: ¥1,480〜3,980
- **ROI**: 25〜70倍

## プロジェクト構造

```
TaskMasterAI/
├── src/
│   ├── __init__.py
│   ├── api.py          # FastAPI Webサーバー
│   ├── auth.py         # Google OAuth認証
│   ├── billing.py      # Stripe課金システム
│   ├── cli.py          # CLIインターフェース
│   ├── coordinator.py  # コマンド調整
│   ├── database.py     # SQLite永続化
│   ├── email_bot.py    # メール処理
│   ├── errors.py       # エラーハンドリング
│   ├── llm.py          # LLM抽象化レイヤー
│   ├── logging_config.py # 構造化ロギング
│   └── scheduler.py    # カレンダー処理
├── tests/              # テストスイート（400+テスト）
├── docs/               # ドキュメント
├── config/             # 設定ファイル
└── landing/            # ランディングページ
```

## セキュリティとプライバシー

- **OAuth 2.0**: Google等のプロバイダーとの安全な認証
- **データ非保存**: メール内容はリアルタイム処理のみ、サーバーに保存しない
- **確認モード**: すべてのアクションは明示的な承認を要求（デフォルト）
- **監査ログ**: 全自動アクションの詳細ログを保持
- **アクセス取消**: いつでもTaskMasterAIとの接続を解除可能

## ドキュメント

- [クイックスタートガイド](docs/quickstart.md)
- [Google API設定](docs/setup_google_api.md)
- [Stripe設定](docs/setup_stripe.md)
- [LLM API設定](docs/setup_llm_api.md)
- [CLIリファレンス](docs/cli_reference.md)
- [APIドキュメント](docs/api.md)
- [デプロイメントガイド](docs/deployment.md)

## 開発

### テスト実行

```bash
# 全テスト実行
pytest

# カバレッジ付き
pytest --cov=src --cov-report=html

# 特定モジュールのテスト
pytest tests/test_email_bot.py
```

### リント・フォーマット

```bash
# コードフォーマット
black src tests
isort src tests

# 型チェック
mypy src

# セキュリティチェック
bandit -r src
```

## 対応サービス

### 現在対応
- Gmail
- Google Calendar

### 今後対応予定
- Microsoft Outlook / Office 365
- Slack
- Trello / Asana
- Notion

## ライセンス

MIT License - [LICENSE](LICENSE) を参照

---

**時間を取り戻そう。TaskMasterAIに任せて。**
