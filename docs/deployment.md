# TaskMasterAI デプロイメントガイド

## 概要

TaskMasterAI を本番環境にデプロイするための手順を説明します。

## デプロイオプション

| プラットフォーム | 特徴 | 推奨用途 |
|----------------|------|---------|
| Railway | 簡単セットアップ、自動スケール | MVP、スタートアップ |
| Render | 無料枠あり、GitHub連携 | 個人プロジェクト |
| Docker Compose | 完全制御、オンプレミス対応 | エンタープライズ |
| Kubernetes | 大規模スケール | 大企業向け |

---

## Railway へのデプロイ

### 1. Railway アカウント作成

https://railway.app でアカウントを作成

### 2. プロジェクト作成

```bash
# Railway CLI インストール
npm install -g @railway/cli

# ログイン
railway login

# プロジェクト作成
railway init
```

### 3. 環境変数設定

Railway ダッシュボードで以下を設定：

```
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
OPENAI_API_KEY=your_openai_key
JWT_SECRET_KEY=your-secure-secret-key
STRIPE_API_KEY=your_stripe_key
STRIPE_WEBHOOK_SECRET=your_webhook_secret
```

### 4. デプロイ

```bash
railway up
```

### 5. ドメイン設定

Railway ダッシュボードで：
1. Settings → Domains
2. Generate Domain（または独自ドメイン設定）

---

## Render へのデプロイ

### 1. render.yaml の確認

プロジェクトルートの `render.yaml` が正しく設定されていることを確認

### 2. Render でサービス作成

1. https://render.com でアカウント作成
2. New → Web Service
3. GitHub リポジトリを接続
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `uvicorn src.api:app --host 0.0.0.0 --port $PORT`

### 3. 環境変数設定

Render ダッシュボードの Environment タブで設定

### 4. デプロイ

GitHub にプッシュすると自動デプロイ

---

## Docker Compose（ローカル/オンプレミス）

### 1. 環境変数ファイル作成

```bash
cp config/.env.example .env
# .env を編集
```

### 2. ビルドと起動

```bash
# 開発環境
docker-compose up -d

# 本番環境（マルチステージビルド）
docker-compose -f docker-compose.prod.yml up -d
```

### 3. 動作確認

```bash
curl http://localhost:8000/health
```

### 4. ログ確認

```bash
docker-compose logs -f
```

---

## 環境変数一覧

### 必須

| 変数名 | 説明 |
|--------|------|
| `GOOGLE_CLIENT_ID` | Google OAuth クライアントID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth クライアントシークレット |
| `JWT_SECRET_KEY` | JWT署名用シークレット（本番は長いランダム文字列） |

### LLM（どちらか必須）

| 変数名 | 説明 |
|--------|------|
| `OPENAI_API_KEY` | OpenAI API キー |
| `ANTHROPIC_API_KEY` | Anthropic API キー |

### 課金（本番必須）

| 変数名 | 説明 |
|--------|------|
| `STRIPE_API_KEY` | Stripe シークレットキー |
| `STRIPE_WEBHOOK_SECRET` | Stripe Webhook シークレット |
| `STRIPE_PRICE_FREE` | 無料プランの価格ID |
| `STRIPE_PRICE_PERSONAL` | Personalプランの価格ID |
| `STRIPE_PRICE_PRO` | Proプランの価格ID |
| `STRIPE_PRICE_TEAM` | Teamプランの価格ID |

### オプション

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `CORS_ORIGINS` | 許可するオリジン（カンマ区切り） | `*` |
| `LOG_LEVEL` | ログレベル | `INFO` |
| `DATABASE_URL` | データベースURL | `sqlite:///taskmaster.db` |

---

## SSL/TLS 設定

### Railway / Render

自動的にHTTPS化されます。

### Docker（自己管理）

#### Nginx リバースプロキシ

```nginx
server {
    listen 443 ssl;
    server_name api.taskmaster.ai;

    ssl_certificate /etc/letsencrypt/live/api.taskmaster.ai/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.taskmaster.ai/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Let's Encrypt 証明書取得

```bash
certbot certonly --nginx -d api.taskmaster.ai
```

---

## データベース設定

### SQLite（開発/小規模）

デフォルトで `taskmaster.db` が作成されます。

### PostgreSQL（本番推奨）

```bash
DATABASE_URL=postgresql://user:password@host:5432/taskmaster
```

マイグレーションは初回起動時に自動実行されます。

---

## 監視・ログ

### ログ出力

構造化JSON形式でログが出力されます：

```json
{
  "timestamp": "2026-01-08T10:30:00Z",
  "level": "INFO",
  "logger": "src.api",
  "message": "リクエスト処理完了",
  "request_id": "uuid",
  "user_id": "user_uuid",
  "duration_ms": 150
}
```

### ヘルスチェック

```bash
curl http://localhost:8000/health
```

監視サービス（UptimeRobot等）でこのエンドポイントを監視

### メトリクス（将来実装）

- Prometheus エンドポイント: `/metrics`
- Grafana ダッシュボード

---

## スケーリング

### 水平スケーリング

Railway/Render ではインスタンス数を増やすだけ。

### Docker Compose

```yaml
services:
  api:
    deploy:
      replicas: 3
```

### ロードバランサー

複数インスタンス時は Nginx または クラウドLB を使用

---

## バックアップ

### データベース

```bash
# SQLite
cp taskmaster.db taskmaster.db.backup

# PostgreSQL
pg_dump taskmaster > backup.sql
```

### 認証トークン

`config/credentials/` ディレクトリを安全にバックアップ

---

## セキュリティチェックリスト

- [ ] `JWT_SECRET_KEY` が十分に長いランダム文字列
- [ ] 本番環境で `DEBUG=False`
- [ ] CORS オリジンを本番ドメインに限定
- [ ] Stripe Webhook シークレットを設定
- [ ] データベースパスワードを強力に
- [ ] HTTPS を強制
- [ ] レート制限を有効化

---

## トラブルシューティング

### コンテナが起動しない

```bash
docker logs taskmaster-api
```

### データベース接続エラー

- `DATABASE_URL` の形式を確認
- データベースサービスが起動しているか確認

### メモリ不足

Railway/Render でプランをアップグレード、またはリソース制限を調整

---

## サポート

デプロイに関する問題：
- GitHub Issues でレポート
- 環境情報とエラーログを添付
