# TaskMasterAI クイックスタートガイド

## はじめに

TaskMasterAI を最速でセットアップし、使い始めるためのガイドです。

## 前提条件

- Python 3.11以上
- Git
- Google アカウント（Gmail / Google Calendar 連携用）

## セットアップ手順

### 1. リポジトリのクローン

```bash
git clone https://github.com/yourusername/TaskMasterAI.git
cd TaskMasterAI
```

### 2. Python仮想環境の作成

```bash
# 仮想環境を作成
python -m venv venv

# 有効化（Windows）
venv\Scripts\activate

# 有効化（macOS/Linux）
source venv/bin/activate
```

### 3. 依存関係のインストール

```bash
pip install -r requirements.txt
```

### 4. 環境変数の設定

```bash
# 設定ファイルをコピー
cp config/.env.example config/.env
```

`config/.env` を編集し、以下を設定：

```bash
# Google API（必須）
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret

# LLM API（どちらか一方）
OPENAI_API_KEY=your_openai_key
# または
ANTHROPIC_API_KEY=your_anthropic_key
```

### 5. Google API認証

```bash
python -m src.cli auth
```

ブラウザが開き、Googleアカウントへのアクセス許可を求められます。
許可後、認証情報が保存されます。

### 6. 動作確認

```bash
# 対話モードで起動
python -m src.cli
```

## 最初のコマンド

### メールを確認

```
taskmaster> inbox
```

受信トレイの最新メールが要約表示されます。

### 今日の予定を確認

```
taskmaster> today
```

今日のカレンダー予定が表示されます。

### ヘルプを表示

```
taskmaster> help
```

利用可能なコマンド一覧が表示されます。

## Web API を使う場合

### APIサーバーの起動

```bash
# 開発サーバー
uvicorn src.api:app --reload

# 本番サーバー
uvicorn src.api:app --host 0.0.0.0 --port 8000
```

### APIドキュメント

サーバー起動後、以下のURLでAPIドキュメントにアクセス：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Docker を使う場合

```bash
# ビルド
docker build -t taskmaster-ai .

# 実行
docker run -p 8000:8000 --env-file config/.env taskmaster-ai
```

## 次のステップ

- [CLI リファレンス](cli_reference.md) - 全コマンドの詳細
- [API リファレンス](api.md) - REST API の使い方
- [Google API セットアップ](setup_google_api.md) - 認証情報の取得方法
- [Stripe セットアップ](setup_stripe.md) - 課金システムの設定

## トラブルシューティング

### 「認証に失敗しました」

- Google Cloud Console で OAuth 認証情報を再確認
- `config/credentials/` 内のトークンファイルを削除して再認証

### 「APIキーが無効です」

- `.env` ファイルの API キーを確認
- キーに余分なスペースや改行がないか確認

### 「モジュールが見つかりません」

```bash
pip install -r requirements.txt
```

依存関係を再インストールしてください。

## サポート

問題が解決しない場合：
- GitHub Issues でレポート
- `logs/` ディレクトリのログを添付
