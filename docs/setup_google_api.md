# Google API Setup Guide

TaskMasterAIでGmail・Googleカレンダー連携を行うための設定手順

## 1. Google Cloud Projectの作成

1. [Google Cloud Console](https://console.cloud.google.com/)にアクセス
2. 新規プロジェクトを作成: "TaskMasterAI"
3. プロジェクトを選択

## 2. APIの有効化

以下のAPIを有効化:

- **Gmail API**: メール読み取り・送信
- **Google Calendar API**: カレンダー管理

手順:
1. 「APIとサービス」→「ライブラリ」
2. 各APIを検索して「有効にする」

## 3. OAuth同意画面の設定

1. 「APIとサービス」→「OAuth同意画面」
2. ユーザータイプ: 「外部」（テスト用）または「内部」（組織内）
3. 必要情報を入力:
   - アプリ名: TaskMasterAI
   - ユーザーサポートメール: your@email.com
   - デベロッパー連絡先: your@email.com

## 4. スコープの追加

以下のスコープを追加:

```
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/gmail.compose
https://www.googleapis.com/auth/calendar.readonly
https://www.googleapis.com/auth/calendar.events
```

## 5. OAuth認証情報の作成

1. 「APIとサービス」→「認証情報」
2. 「認証情報を作成」→「OAuthクライアントID」
3. アプリケーションの種類: 「デスクトップアプリ」
4. 名前: "TaskMasterAI Desktop"
5. 作成後、JSONをダウンロード

## 6. 認証情報の配置

ダウンロードしたJSONファイルを配置:

```bash
mv ~/Downloads/client_secret_xxx.json config/credentials/google_oauth.json
```

## 7. 環境変数の設定

`.env`ファイルに認証情報を追加:

```bash
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
```

## 8. テストユーザーの追加（外部ユーザータイプの場合）

1. OAuth同意画面→「テストユーザー」
2. 自分のGmailアドレスを追加

## 初回認証フロー

初回実行時、ブラウザが開き認証を求められます:

```bash
python -m src.cli auth
```

1. Googleアカウントでログイン
2. 権限を確認して「許可」
3. 認証トークンが `config/credentials/token.json` に保存

## トラブルシューティング

### "Access blocked" エラー
- OAuth同意画面でテストユーザーに追加されているか確認

### "Invalid client" エラー
- client_id/client_secretが正しいか確認
- JSONファイルのパスが正しいか確認

### "Insufficient scope" エラー
- 必要なスコープがすべて追加されているか確認
- token.jsonを削除して再認証

## セキュリティ注意事項

- `config/credentials/` は `.gitignore` に含まれています
- 認証情報をGitにコミットしないでください
- 本番環境ではSecret Managerの使用を推奨
