# TaskMasterAI API リファレンス

## 概要

TaskMasterAI REST API は、FastAPIベースのWebインターフェースを提供します。JWT認証を使用し、メール要約、スケジュール提案、使用量追跡などの機能にプログラマティックにアクセスできます。

## ベースURL

- **開発環境:** `http://localhost:8000`
- **本番環境:** `https://api.taskmaster.ai` （予定）

## 認証

### JWT Bearer認証

すべての保護されたエンドポイントは、`Authorization` ヘッダーにBearer トークンを必要とします。

```http
Authorization: Bearer <access_token>
```

### トークンの取得

1. `/auth/register` でユーザー登録
2. `/auth/login` でログインしてトークンを取得
3. 以降のリクエストにトークンを付与

## エンドポイント

### ヘルスチェック

#### GET /health

サービスの稼働状態を確認します。

**リクエスト:**
```bash
curl -X GET "http://localhost:8000/health"
```

**レスポンス:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2026-01-08T10:30:00Z"
}
```

---

### 認証

#### POST /auth/register

新規ユーザーを登録します。

**リクエスト:**
```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepassword123",
    "name": "山田太郎"
  }'
```

**リクエストボディ:**
| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| email | string | Yes | メールアドレス |
| password | string | Yes | パスワード |
| name | string | No | 表示名 |

**レスポンス (200 OK):**
```json
{
  "id": "uuid-string",
  "email": "user@example.com",
  "name": "山田太郎",
  "plan": "free",
  "created_at": "2026-01-08T10:30:00Z"
}
```

**エラーレスポンス (400 Bad Request):**
```json
{
  "detail": "このメールアドレスは既に使用されています"
}
```

---

#### POST /auth/login

ログインしてアクセストークンを取得します。

**リクエスト:**
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepassword123"
  }'
```

**レスポンス (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

**エラーレスポンス (401 Unauthorized):**
```json
{
  "detail": "メールアドレスまたはパスワードが正しくありません"
}
```

---

#### GET /auth/me

現在のユーザー情報を取得します。

**リクエスト:**
```bash
curl -X GET "http://localhost:8000/auth/me" \
  -H "Authorization: Bearer <access_token>"
```

**レスポンス (200 OK):**
```json
{
  "id": "uuid-string",
  "email": "user@example.com",
  "name": "山田太郎",
  "plan": "free",
  "created_at": "2026-01-08T10:30:00Z"
}
```

---

### メール機能

#### POST /email/summarize

受信トレイのメールを要約します。

**リクエスト:**
```bash
curl -X POST "http://localhost:8000/email/summarize" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "max_emails": 10
  }'
```

**リクエストボディ:**
| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|------|-----------|------|
| max_emails | integer | No | 10 | 要約するメール件数 |

**レスポンス (200 OK):**
```json
{
  "summaries": [
    {
      "id": "email_123",
      "subject": "プロジェクト進捗報告",
      "from": "manager@company.com",
      "summary": "Q4目標の達成状況確認の依頼。返信必要。",
      "priority": "high",
      "action_required": true
    }
  ],
  "count": 1
}
```

**エラーレスポンス (402 Payment Required):**
```json
{
  "detail": "今月の使用制限に達しました。プランをアップグレードしてください。"
}
```

---

### スケジュール機能

#### POST /schedule/propose

会議のスケジュール候補を提案します。

**リクエスト:**
```bash
curl -X POST "http://localhost:8000/schedule/propose" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "週次ミーティング",
    "duration_minutes": 30,
    "attendees": ["alice@example.com", "bob@example.com"],
    "max_proposals": 5
  }'
```

**リクエストボディ:**
| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|------|-----------|------|
| title | string | Yes | - | 会議タイトル |
| duration_minutes | integer | No | 30 | 所要時間（分） |
| attendees | array[string] | No | [] | 参加者メールアドレス |
| max_proposals | integer | No | 5 | 候補数の上限 |

**レスポンス (200 OK):**
```json
{
  "proposals": [
    {
      "start": "2026-01-10T10:00:00Z",
      "end": "2026-01-10T10:30:00Z",
      "availability": "all_available"
    },
    {
      "start": "2026-01-10T14:00:00Z",
      "end": "2026-01-10T14:30:00Z",
      "availability": "all_available"
    }
  ],
  "count": 2
}
```

---

### 使用量

#### GET /usage

現在の使用量と制限を取得します。

**リクエスト:**
```bash
curl -X GET "http://localhost:8000/usage" \
  -H "Authorization: Bearer <access_token>"
```

**レスポンス (200 OK):**
```json
{
  "plan": "free",
  "status": "active",
  "email_summaries": {
    "used": 25,
    "limit": 50,
    "remaining": 25
  },
  "schedule_proposals": {
    "used": 5,
    "limit": 10,
    "remaining": 5
  },
  "actions_executed": 0
}
```

---

## 料金プラン別制限

| プラン | メール要約/月 | スケジュール提案/月 | 自動実行 |
|--------|-------------|-------------------|---------|
| Free | 50 | 10 | 不可 |
| Personal ($10/月) | 500 | 50 | 確認付き |
| Pro ($25/月) | 2000 | 200 | 確認付き |
| Team ($15/月/人) | 5000 | 500 | ルールベース |

---

## エラーコード

| HTTPステータス | 意味 | 対処法 |
|---------------|------|--------|
| 400 | リクエスト不正 | リクエストボディを確認 |
| 401 | 認証エラー | トークンを再取得 |
| 402 | 支払い必要 | プランをアップグレード |
| 403 | 権限なし | 必要な権限を確認 |
| 404 | リソースなし | URLを確認 |
| 429 | レート制限 | しばらく待って再試行 |
| 500 | サーバーエラー | サポートに連絡 |

---

## SDK / クライアントライブラリ

### Python

```python
import requests

class TaskMasterClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.token = None

    def login(self, email: str, password: str):
        response = requests.post(
            f"{self.base_url}/auth/login",
            json={"email": email, "password": password}
        )
        response.raise_for_status()
        self.token = response.json()["access_token"]

    def summarize_emails(self, max_emails: int = 10):
        response = requests.post(
            f"{self.base_url}/email/summarize",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"max_emails": max_emails}
        )
        response.raise_for_status()
        return response.json()

# 使用例
client = TaskMasterClient()
client.login("user@example.com", "password123")
summaries = client.summarize_emails(5)
```

### JavaScript / TypeScript

```typescript
class TaskMasterClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string = "http://localhost:8000") {
    this.baseUrl = baseUrl;
  }

  async login(email: string, password: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await response.json();
    this.token = data.access_token;
  }

  async summarizeEmails(maxEmails: number = 10): Promise<any> {
    const response = await fetch(`${this.baseUrl}/email/summarize`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${this.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ max_emails: maxEmails }),
    });
    return response.json();
  }
}
```

---

## OpenAPI / Swagger

開発サーバー起動時、以下のURLで対話的なAPIドキュメントにアクセスできます：

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

---

## レート制限

- **認証エンドポイント:** 10リクエスト/分/IP
- **その他のエンドポイント:** 60リクエスト/分/ユーザー

レート制限超過時は `429 Too Many Requests` が返されます。

---

## Webhooks（将来実装予定）

重要なイベントの通知を受け取るためのWebhookエンドポイント：

- 新規メール受信
- 予定のリマインダー
- 使用量アラート

---

## サポート

API に関するお問い合わせ：
- GitHub Issues: https://github.com/yourusername/TaskMasterAI/issues
- Email: support@taskmaster.ai
