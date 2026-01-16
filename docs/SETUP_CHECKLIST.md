# TaskMasterAI セットアップチェックリスト

本番運用に向けた認証情報取得・環境構築のチェックリスト。

## 前提条件

- [ ] Googleアカウント（Gmail）を持っている
- [ ] Stripeアカウントを作成済み（無料）
- [ ] OpenAI または Anthropic アカウントを作成済み

---

## 1. Google Cloud設定（必須）

### 1.1 プロジェクト作成
- [ ] [Google Cloud Console](https://console.cloud.google.com/) にアクセス
- [ ] 新規プロジェクト作成: `TaskMasterAI`
- [ ] プロジェクトを選択

### 1.2 API有効化
- [ ] 「APIとサービス」→「ライブラリ」
- [ ] **Gmail API** を検索して有効化
- [ ] **Google Calendar API** を検索して有効化

### 1.3 OAuth同意画面
- [ ] 「APIとサービス」→「OAuth同意画面」
- [ ] ユーザータイプ: `外部`
- [ ] アプリ名: `TaskMasterAI`
- [ ] サポートメール入力
- [ ] スコープ追加:
  - `https://www.googleapis.com/auth/gmail.readonly`
  - `https://www.googleapis.com/auth/gmail.compose`
  - `https://www.googleapis.com/auth/calendar.readonly`
  - `https://www.googleapis.com/auth/calendar.events`
- [ ] テストユーザーに自分のメールを追加

### 1.4 認証情報作成
- [ ] 「認証情報」→「認証情報を作成」→「OAuthクライアントID」
- [ ] アプリケーションの種類: `デスクトップアプリ`
- [ ] JSONファイルをダウンロード

### 1.5 環境変数設定
```
GOOGLE_CLIENT_ID=取得したClient ID
GOOGLE_CLIENT_SECRET=取得したClient Secret
```

---

## 2. Stripe設定（必須）

### 2.1 アカウント作成
- [ ] [Stripe Dashboard](https://dashboard.stripe.com/) にアクセス
- [ ] アカウント作成（無料）
- [ ] 開発者モードを確認

### 2.2 APIキー取得
- [ ] 「Developers」→「API keys」
- [ ] **Publishable key** をコピー
- [ ] **Secret key** をコピー

### 2.3 価格設定（Products）
- [ ] 「Products」→「Add product」

**Personal プラン:**
- [ ] 商品名: `TaskMasterAI Personal`
- [ ] 価格: `¥1,480/月` (月額サブスクリプション)
- [ ] Price ID をコピー

**Pro プラン:**
- [ ] 商品名: `TaskMasterAI Pro`
- [ ] 価格: `¥3,980/月`
- [ ] Price ID をコピー

**Team プラン:**
- [ ] 商品名: `TaskMasterAI Team`
- [ ] 価格: `¥2,480/月/人`
- [ ] Price ID をコピー

### 2.4 Webhook設定（オプション）
- [ ] 「Developers」→「Webhooks」→「Add endpoint」
- [ ] URL: `https://your-domain.com/webhook/stripe`
- [ ] イベント選択: `invoice.payment_succeeded`, `customer.subscription.deleted`
- [ ] Webhook Secret をコピー

### 2.5 環境変数設定
```
STRIPE_API_KEY=sk_test_...（Secret key）
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PERSONAL=price_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_TEAM=price_...
```

---

## 3. LLM API設定（いずれか1つ必須）

### 3.1 OpenAI（有料）
- [ ] [OpenAI Platform](https://platform.openai.com/) にアクセス
- [ ] アカウント作成・ログイン
- [ ] 「API Keys」→「Create new secret key」
- [ ] キーをコピー

```
OPENAI_API_KEY=sk-...
```

### 3.2 Anthropic（有料）
- [ ] [Anthropic Console](https://console.anthropic.com/) にアクセス
- [ ] アカウント作成・ログイン
- [ ] 「API Keys」→ 新規キー作成
- [ ] キーをコピー

```
ANTHROPIC_API_KEY=sk-ant-...
```

### 3.3 Groq（無料枠あり、推奨）
Groqは無料枠があり、高速な推論が可能です。開発・テスト用に最適。

- [ ] [Groq Console](https://console.groq.com/) にアクセス
- [ ] Googleアカウントでサインアップ（無料）
- [ ] 「API Keys」→「Create API Key」
- [ ] キーをコピー

```
GROQ_API_KEY=gsk_...
```

**無料枠の制限（2024年時点）:**
- 30リクエスト/分
- 14,400リクエスト/日
- Llama 3.1 8B, 70B等が利用可能

### 3.4 Ollama（完全無料、ローカル）
Ollamaはローカルで動作するLLMランナーです。インターネット接続不要、完全無料。

- [ ] [Ollama](https://ollama.ai/) をダウンロード・インストール
- [ ] ターミナルで `ollama pull llama3.2` を実行
- [ ] `ollama serve` でサーバー起動

```
OLLAMA_BASE_URL=http://localhost:11434
```

**メリット:**
- 完全無料、API料金なし
- プライバシー（データがローカルに留まる）
- オフライン動作可能

**デメリット:**
- GPU必要（CPUでも動作するが遅い）
- ストレージが必要（モデルサイズ数GB）

---

## 4. 環境変数ファイル作成

```bash
cd O:\Dev\Work\TaskMasterAI
copy config\.env.example .env
```

`.env` を編集し、上記で取得した値を設定。

### 必須設定チェック
- [ ] `GOOGLE_CLIENT_ID` 設定済み
- [ ] `GOOGLE_CLIENT_SECRET` 設定済み
- [ ] `STRIPE_API_KEY` 設定済み
- [ ] `STRIPE_PRICE_PERSONAL` 設定済み
- [ ] `STRIPE_PRICE_PRO` 設定済み
- [ ] `STRIPE_PRICE_TEAM` 設定済み
- [ ] `OPENAI_API_KEY` または `ANTHROPIC_API_KEY` 設定済み
- [ ] `JWT_SECRET_KEY` を本番用の強力な値に変更

---

## 5. 動作確認

### 5.1 依存関係インストール
```bash
pip install -r requirements.txt
```

### 5.2 環境検証
```bash
python scripts/verify_setup.py
```

### 5.3 テスト実行
```bash
pytest tests/ -v
```

### 5.4 サーバー起動
```bash
uvicorn src.api:app --reload
```

### 5.5 ヘルスチェック
ブラウザで `http://localhost:8000/health` にアクセス

---

## 6. デプロイ（Railway/Render）

### 6.1 Railway
- [ ] [Railway](https://railway.app/) でリポジトリ接続
- [ ] 環境変数を設定
- [ ] デプロイ確認

### 6.2 Render
- [ ] [Render](https://render.com/) でWeb Service作成
- [ ] `render.yaml` を使用
- [ ] 環境変数を設定
- [ ] デプロイ確認

---

## 完了確認

全てのチェックが完了したら:
- [ ] ヘルスチェックエンドポイントが正常応答
- [ ] ランディングページが表示される
- [ ] ベータ登録が動作する
- [ ] 管理ダッシュボードにログイン可能

---

## トラブルシューティング

### Google認証エラー
- OAuth同意画面でテストユーザーに追加されているか確認
- スコープが正しく設定されているか確認

### Stripe課金エラー
- テストモード/本番モードが一致しているか確認
- Price IDが正しいか確認

### LLMエラー
- APIキーが有効か確認
- レート制限に達していないか確認
- 残高/クレジットがあるか確認
