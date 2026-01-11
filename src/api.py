"""
Web API Module - FastAPIベースのREST API

SaaS提供のためのWebインターフェース基盤
"""

import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


# ===== レート制限 =====
class RateLimiter:
    """
    トークンバケットアルゴリズムによるレート制限

    DDoS対策およびAPI濫用防止のためのレート制限機能
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int = 10
    ):
        """
        初期化

        Args:
            requests_per_minute: 1分あたりの許可リクエスト数
            burst_size: バースト時の許可リクエスト数
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self._tokens: dict[str, float] = {}
        self._last_update: dict[str, float] = {}
        self._lock_until: dict[str, float] = {}

    def _refill_tokens(self, key: str) -> None:
        """トークンを補充"""
        now = time.time()

        # 初回アクセス時はバーストサイズで初期化
        if key not in self._tokens or key not in self._last_update:
            self._tokens[key] = float(self.burst_size)
            self._last_update[key] = now
            return

        elapsed = now - self._last_update[key]
        # 1秒あたりのトークン補充量
        refill_rate = self.requests_per_minute / 60.0
        self._tokens[key] = min(
            self.burst_size,
            self._tokens[key] + elapsed * refill_rate
        )
        self._last_update[key] = now

    def is_allowed(self, key: str) -> tuple[bool, dict]:
        """
        リクエストを許可するかチェック

        Args:
            key: レート制限のキー（IPアドレスやユーザーID）

        Returns:
            (許可するか, メタデータ辞書)
        """
        # ロック中かチェック
        if key in self._lock_until:
            if time.time() < self._lock_until[key]:
                remaining = int(self._lock_until[key] - time.time())
                return False, {
                    "retry_after": remaining,
                    "reason": "too_many_requests",
                    "locked": True
                }
            else:
                del self._lock_until[key]

        self._refill_tokens(key)

        if self._tokens[key] >= 1.0:
            self._tokens[key] -= 1.0
            return True, {
                "remaining": int(self._tokens[key]),
                "limit": self.requests_per_minute,
                "reset_in": int(60 - (time.time() - self._last_update[key]) % 60)
            }
        else:
            # トークン不足時は一時ロック
            self._lock_until[key] = time.time() + 60
            return False, {
                "retry_after": 60,
                "reason": "rate_limit_exceeded",
                "limit": self.requests_per_minute
            }

    def reset(self, key: str) -> None:
        """特定キーのレート制限をリセット"""
        if key in self._tokens:
            del self._tokens[key]
        if key in self._last_update:
            del self._last_update[key]
        if key in self._lock_until:
            del self._lock_until[key]

    def get_status(self, key: str) -> dict:
        """レート制限の現在状態を取得"""
        self._refill_tokens(key)
        return {
            "remaining": int(self._tokens[key]),
            "limit": self.requests_per_minute,
            "burst_size": self.burst_size,
            "locked": key in self._lock_until
        }


# グローバルレートリミッターインスタンス
# エンドポイント別に異なる制限を設定
rate_limiters = {
    "default": RateLimiter(requests_per_minute=60, burst_size=10),
    "auth": RateLimiter(requests_per_minute=10, burst_size=5),  # 認証は厳しく制限
    "beta": RateLimiter(requests_per_minute=30, burst_size=5),  # ベータ登録も制限
    "api": RateLimiter(requests_per_minute=100, burst_size=20),  # 認証済みAPIは緩め
}


# ===== メトリクス収集 =====
class MetricsCollector:
    """
    リクエスト統計・メトリクス収集

    Prometheus形式での出力をサポートし、外部監視システムとの統合を可能にする
    """

    def __init__(self):
        """初期化"""
        self._start_time = time.time()
        self._request_count: dict[str, int] = defaultdict(int)
        self._error_count: dict[str, int] = defaultdict(int)
        self._response_times: dict[str, list[float]] = defaultdict(list)
        self._status_codes: dict[int, int] = defaultdict(int)
        # 直近のレスポンスタイムのみ保持（メモリ節約）
        self._max_response_samples = 1000

    def record_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        response_time_ms: float
    ) -> None:
        """
        リクエストを記録

        Args:
            endpoint: エンドポイントパス
            method: HTTPメソッド
            status_code: レスポンスステータスコード
            response_time_ms: レスポンスタイム（ミリ秒）
        """
        key = f"{method}:{endpoint}"
        self._request_count[key] += 1
        self._status_codes[status_code] += 1

        if status_code >= 400:
            self._error_count[key] += 1

        # レスポンスタイムを記録（最新のサンプルのみ保持）
        times = self._response_times[key]
        times.append(response_time_ms)
        if len(times) > self._max_response_samples:
            self._response_times[key] = times[-self._max_response_samples:]

    def get_metrics(self) -> dict:
        """
        メトリクスを辞書形式で取得

        Returns:
            メトリクス辞書
        """
        uptime = time.time() - self._start_time
        total_requests = sum(self._request_count.values())
        total_errors = sum(self._error_count.values())

        # 全体のレスポンスタイム統計
        all_times = []
        for times in self._response_times.values():
            all_times.extend(times)

        avg_response_time = (
            sum(all_times) / len(all_times) if all_times else 0
        )
        max_response_time = max(all_times) if all_times else 0

        return {
            "uptime_seconds": round(uptime, 2),
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": round(total_errors / total_requests, 4) if total_requests > 0 else 0,
            "avg_response_time_ms": round(avg_response_time, 2),
            "max_response_time_ms": round(max_response_time, 2),
            "requests_per_minute": round(total_requests / (uptime / 60), 2) if uptime > 0 else 0,
            "status_codes": dict(self._status_codes),
            "endpoints": {
                key: {
                    "count": count,
                    "errors": self._error_count.get(key, 0),
                    "avg_response_time_ms": round(
                        sum(self._response_times.get(key, [])) /
                        len(self._response_times.get(key, [1])), 2
                    ) if self._response_times.get(key) else 0
                }
                for key, count in self._request_count.items()
            }
        }

    def get_prometheus_metrics(self) -> str:
        """
        Prometheus形式でメトリクスを出力

        Returns:
            Prometheus形式のメトリクス文字列
        """
        lines = []
        metrics = self.get_metrics()

        # アップタイム
        lines.append("# HELP taskmasterai_uptime_seconds サーバー稼働時間（秒）")
        lines.append("# TYPE taskmasterai_uptime_seconds gauge")
        lines.append(f"taskmasterai_uptime_seconds {metrics['uptime_seconds']}")

        # 総リクエスト数
        lines.append("# HELP taskmasterai_requests_total 総リクエスト数")
        lines.append("# TYPE taskmasterai_requests_total counter")
        lines.append(f"taskmasterai_requests_total {metrics['total_requests']}")

        # エラー数
        lines.append("# HELP taskmasterai_errors_total 総エラー数")
        lines.append("# TYPE taskmasterai_errors_total counter")
        lines.append(f"taskmasterai_errors_total {metrics['total_errors']}")

        # エラー率
        lines.append("# HELP taskmasterai_error_rate エラー率")
        lines.append("# TYPE taskmasterai_error_rate gauge")
        lines.append(f"taskmasterai_error_rate {metrics['error_rate']}")

        # 平均レスポンスタイム
        lines.append("# HELP taskmasterai_response_time_avg_ms 平均レスポンスタイム（ミリ秒）")
        lines.append("# TYPE taskmasterai_response_time_avg_ms gauge")
        lines.append(f"taskmasterai_response_time_avg_ms {metrics['avg_response_time_ms']}")

        # ステータスコード別
        lines.append("# HELP taskmasterai_http_status HTTPステータスコード別カウント")
        lines.append("# TYPE taskmasterai_http_status counter")
        for code, count in metrics['status_codes'].items():
            lines.append(f'taskmasterai_http_status{{code="{code}"}} {count}')

        # エンドポイント別リクエスト数
        lines.append("# HELP taskmasterai_endpoint_requests エンドポイント別リクエスト数")
        lines.append("# TYPE taskmasterai_endpoint_requests counter")
        for endpoint, data in metrics['endpoints'].items():
            method, path = endpoint.split(":", 1) if ":" in endpoint else ("UNKNOWN", endpoint)
            lines.append(f'taskmasterai_endpoint_requests{{method="{method}",path="{path}"}} {data["count"]}')

        return "\n".join(lines)

    def reset(self) -> None:
        """メトリクスをリセット"""
        self._request_count.clear()
        self._error_count.clear()
        self._response_times.clear()
        self._status_codes.clear()


# グローバルメトリクスコレクター
metrics_collector = MetricsCollector()

# FastAPIのインポート（オプショナル）
try:
    from fastapi import FastAPI, HTTPException, Depends, status, Header
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, EmailStr
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logger.warning("FastAPIがインストールされていません。Web APIは利用できません。")


# JWT処理（オプショナル）
try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger.warning("PyJWTがインストールされていません。")


# リクエスト/レスポンスモデル
if FASTAPI_AVAILABLE:

    class UserCreate(BaseModel):
        """ユーザー登録リクエスト"""
        email: EmailStr
        password: str
        name: Optional[str] = None

    class UserLogin(BaseModel):
        """ログインリクエスト"""
        email: EmailStr
        password: str

    class TokenResponse(BaseModel):
        """トークンレスポンス"""
        access_token: str
        token_type: str = "bearer"
        expires_in: int

    class UserResponse(BaseModel):
        """ユーザー情報レスポンス"""
        id: str
        email: str
        name: Optional[str]
        plan: str
        created_at: datetime

    class EmailSummaryRequest(BaseModel):
        """メール要約リクエスト"""
        max_emails: int = 10

    class EmailSummaryResponse(BaseModel):
        """メール要約レスポンス"""
        summaries: list[dict]
        count: int

    class ScheduleProposalRequest(BaseModel):
        """スケジュール提案リクエスト"""
        title: str
        duration_minutes: int = 30
        attendees: list[str] = []
        max_proposals: int = 5

    class ScheduleProposalResponse(BaseModel):
        """スケジュール提案レスポンス"""
        proposals: list[dict]
        count: int

    class UsageResponse(BaseModel):
        """使用量レスポンス"""
        plan: str
        status: str
        email_summaries: dict
        schedule_proposals: dict
        actions_executed: int

    class HealthResponse(BaseModel):
        """ヘルスチェックレスポンス"""
        status: str
        version: str
        timestamp: datetime

    class BetaSignupRequest(BaseModel):
        """ベータ登録リクエスト"""
        email: EmailStr

    class BetaSignupResponse(BaseModel):
        """ベータ登録レスポンス"""
        success: bool
        message: str
        email: str


@dataclass
class User:
    """ユーザーデータ"""
    id: str
    email: str
    password_hash: str
    name: Optional[str]
    plan: str
    created_at: datetime


class AuthService:
    """
    認証サービス

    JWT認証とユーザー管理を提供
    """

    def __init__(self, secret_key: Optional[str] = None):
        """
        初期化

        Args:
            secret_key: JWTシークレットキー
        """
        self.secret_key = secret_key or os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 60 * 24  # 24時間

        # インメモリユーザーストア（本番はDB）
        self._users: dict[str, User] = {}
        self._user_by_email: dict[str, str] = {}

    def _hash_password(self, password: str) -> str:
        """パスワードをハッシュ化（本番はbcrypt等を使用）"""
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """パスワードを検証"""
        return self._hash_password(password) == password_hash

    def create_user(self, email: str, password: str, name: Optional[str] = None) -> Optional[User]:
        """
        ユーザーを作成

        Args:
            email: メールアドレス
            password: パスワード
            name: 名前

        Returns:
            Userオブジェクト（失敗時はNone）
        """
        if email in self._user_by_email:
            logger.warning(f"メールアドレスは既に使用されています: {email}")
            return None

        import uuid
        user_id = str(uuid.uuid4())

        user = User(
            id=user_id,
            email=email,
            password_hash=self._hash_password(password),
            name=name,
            plan="free",
            created_at=datetime.now()
        )

        self._users[user_id] = user
        self._user_by_email[email] = user_id

        logger.info(f"ユーザー作成完了: {user_id}")
        return user

    def authenticate(self, email: str, password: str) -> Optional[User]:
        """
        ユーザー認証

        Args:
            email: メールアドレス
            password: パスワード

        Returns:
            Userオブジェクト（認証失敗時はNone）
        """
        user_id = self._user_by_email.get(email)
        if not user_id:
            return None

        user = self._users.get(user_id)
        if not user:
            return None

        if not self._verify_password(password, user.password_hash):
            return None

        logger.info(f"ユーザー認証成功: {user_id}")
        return user

    def create_access_token(self, user_id: str) -> str:
        """
        アクセストークンを生成

        Args:
            user_id: ユーザーID

        Returns:
            JWTトークン
        """
        if not JWT_AVAILABLE:
            # モックトークン
            return f"mock_token_{user_id}"

        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=self.access_token_expire_minutes)
        payload = {
            "sub": user_id,
            "exp": expire,
            "iat": now
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[str]:
        """
        トークンを検証

        Args:
            token: JWTトークン

        Returns:
            ユーザーID（無効なトークンはNone）
        """
        if not JWT_AVAILABLE:
            # モックトークンの検証
            if token.startswith("mock_token_"):
                return token.replace("mock_token_", "")
            return None

        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload.get("sub")
        except jwt.ExpiredSignatureError:
            logger.warning("トークンの有効期限切れ")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"無効なトークン: {e}")
            return None

    def get_user(self, user_id: str) -> Optional[User]:
        """ユーザーIDからユーザーを取得"""
        return self._users.get(user_id)


def create_app() -> "FastAPI":
    """
    FastAPIアプリケーションを作成

    Returns:
        FastAPIインスタンス
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPIがインストールされていません")

    from .billing import BillingService, SubscriptionPlan
    from .coordinator import Coordinator
    from .database import create_database

    app = FastAPI(
        title="TaskMasterAI API",
        description="""
## AI駆動の仮想エグゼクティブアシスタント API

TaskMasterAI APIは、メール管理、カレンダー管理、タスク自動化のためのRESTfulインターフェースを提供します。

### 主な機能

* **メール管理**: 受信トレイの要約、返信ドラフト作成
* **カレンダー管理**: 空き時間検索、会議スケジュール提案
* **使用量追跡**: プラン別の利用状況確認

### 認証

すべての保護されたエンドポイントはJWT Bearer認証を必要とします。
`/auth/login` でトークンを取得し、`Authorization: Bearer <token>` ヘッダーで送信してください。

### 料金プラン

| プラン | 価格 | メール要約/月 | スケジュール提案/月 |
|--------|------|--------------|-------------------|
| Free | 無料 | 50 | 10 |
| Personal | $10/月 | 500 | 50 |
| Pro | $25/月 | 2000 | 200 |
| Team | $15/月/人 | 5000 | 500 |
        """,
        version="0.1.0",
        contact={
            "name": "TaskMasterAI Support",
            "email": "support@taskmaster.ai",
        },
        license_info={
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT",
        },
        openapi_tags=[
            {
                "name": "ヘルスチェック",
                "description": "サービス稼働状態の確認",
            },
            {
                "name": "認証",
                "description": "ユーザー登録・ログイン・トークン管理",
            },
            {
                "name": "メール",
                "description": "メール要約・ドラフト作成機能",
            },
            {
                "name": "スケジュール",
                "description": "カレンダー管理・会議提案機能",
            },
            {
                "name": "使用量",
                "description": "プラン別使用量の確認",
            },
            {
                "name": "ベータ登録",
                "description": "ベータテスター登録・ウェイトリスト管理",
            },
        ],
    )

    # CORS設定
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # セキュリティヘッダーミドルウェア
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        """
        セキュリティヘッダーを追加するミドルウェア

        OWASP推奨のセキュリティヘッダーを全レスポンスに付与
        """

        async def dispatch(self, request: Request, call_next) -> Response:
            response = await call_next(request)

            # XSS対策
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-XSS-Protection"] = "1; mode=block"

            # クリックジャッキング対策
            response.headers["X-Frame-Options"] = "DENY"

            # HTTPS強制（本番環境のみ）
            if os.getenv("ENVIRONMENT", "development") == "production":
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

            # Content Security Policy（API向け、厳格）
            csp = (
                "default-src 'none'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
            response.headers["Content-Security-Policy"] = csp

            # Referrer情報制御
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

            # Permissions Policy（API向け）
            response.headers["Permissions-Policy"] = (
                "accelerometer=(), camera=(), geolocation=(), "
                "gyroscope=(), magnetometer=(), microphone=(), "
                "payment=(), usb=()"
            )

            # キャッシュ制御（認証済みレスポンス向け）
            if "/auth/" in str(request.url) or "/admin/" in str(request.url):
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
                response.headers["Pragma"] = "no-cache"

            return response

    app.add_middleware(SecurityHeadersMiddleware)

    # レート制限ミドルウェア
    from starlette.responses import JSONResponse

    class RateLimitMiddleware(BaseHTTPMiddleware):
        """
        レート制限ミドルウェア

        エンドポイントごとに異なるレート制限を適用
        DDoS対策およびAPI濫用防止
        """

        async def dispatch(self, request: Request, call_next) -> Response:
            # クライアントIPを取得（プロキシ考慮）
            client_ip = request.headers.get(
                "X-Forwarded-For",
                request.client.host if request.client else "unknown"
            )
            if "," in client_ip:
                client_ip = client_ip.split(",")[0].strip()

            # エンドポイントに応じたレートリミッター選択
            path = str(request.url.path)
            if path.startswith("/auth/"):
                limiter = rate_limiters["auth"]
                limiter_name = "auth"
            elif path.startswith("/beta/"):
                limiter = rate_limiters["beta"]
                limiter_name = "beta"
            elif path.startswith("/email/") or path.startswith("/schedule/"):
                limiter = rate_limiters["api"]
                limiter_name = "api"
            else:
                limiter = rate_limiters["default"]
                limiter_name = "default"

            # ヘルスチェックはレート制限対象外
            if path == "/health":
                return await call_next(request)

            # レート制限チェック
            allowed, meta = limiter.is_allowed(client_ip)

            if not allowed:
                logger.warning(f"レート制限超過: {client_ip} ({limiter_name})")
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "リクエストが多すぎます。しばらく待ってから再試行してください。",
                        "retry_after": meta.get("retry_after", 60),
                        "limit": meta.get("limit", 60)
                    },
                    headers={
                        "Retry-After": str(meta.get("retry_after", 60)),
                        "X-RateLimit-Limit": str(meta.get("limit", 60)),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(meta.get("retry_after", 60))
                    }
                )

            # リクエスト処理
            response = await call_next(request)

            # レート制限ヘッダーを追加
            response.headers["X-RateLimit-Limit"] = str(meta.get("limit", 60))
            response.headers["X-RateLimit-Remaining"] = str(meta.get("remaining", 0))
            response.headers["X-RateLimit-Reset"] = str(meta.get("reset_in", 60))

            return response

    # レート制限有効化（環境変数で無効化可能）
    if os.getenv("DISABLE_RATE_LIMIT", "").lower() != "true":
        app.add_middleware(RateLimitMiddleware)

    # メトリクス収集ミドルウェア
    class MetricsMiddleware(BaseHTTPMiddleware):
        """リクエスト統計収集ミドルウェア"""

        async def dispatch(self, request: Request, call_next):
            # メトリクスエンドポイント自体は計測対象外
            if str(request.url.path) in ["/metrics", "/metrics/prometheus"]:
                return await call_next(request)

            start_time = time.time()
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000

            # メトリクスを記録
            metrics_collector.record_request(
                endpoint=str(request.url.path),
                method=request.method,
                status_code=response.status_code,
                response_time_ms=duration_ms
            )

            return response

    # メトリクス収集有効化（環境変数で無効化可能）
    if os.getenv("DISABLE_METRICS", "").lower() != "true":
        app.add_middleware(MetricsMiddleware)

    # サービスの初期化
    auth_service = AuthService()
    billing_service = BillingService()
    security = HTTPBearer()

    # データベースパス（ベータ登録永続化用）
    db_path = os.getenv("DATABASE_PATH", "taskmaster.db")

    # インメモリDBの場合はグローバルインスタンスを保持（テスト用）
    _db_instance = None
    _db_is_memory = db_path == ":memory:"

    def get_db():
        """リクエストごとにDB接続を取得（スレッドセーフ）"""
        nonlocal _db_instance
        if _db_is_memory:
            # インメモリDBは単一インスタンスを共有（テスト用）
            if _db_instance is None:
                _db_instance = create_database(db_path)
            return _db_instance
        # ファイルDBは新しい接続を返す（本番用、スレッドセーフ）
        return create_database(db_path)

    # 依存性注入
    async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> User:
        """現在のユーザーを取得"""
        token = credentials.credentials
        user_id = auth_service.verify_token(token)

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="無効または期限切れのトークンです"
            )

        user = auth_service.get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="ユーザーが見つかりません"
            )

        return user

    # ヘルスチェック
    @app.get("/health", response_model=HealthResponse, tags=["ヘルスチェック"],
             summary="サービス稼働状態を確認",
             description="サービスが正常に稼働しているかを確認します。認証不要。")
    async def health_check():
        """ヘルスチェックエンドポイント"""
        return HealthResponse(
            status="healthy",
            version="0.1.0",
            timestamp=datetime.now()
        )

    # メトリクスエンドポイント
    @app.get("/metrics", tags=["監視"],
             summary="サービスメトリクスを取得",
             description="リクエスト統計、レスポンスタイム等のメトリクスを取得します。認証不要。")
    async def get_metrics():
        """メトリクスエンドポイント（JSON形式）"""
        return metrics_collector.get_metrics()

    @app.get("/metrics/prometheus", tags=["監視"],
             summary="Prometheusメトリクスを取得",
             description="Prometheus形式のメトリクスを取得します。外部監視システム連携用。")
    async def get_prometheus_metrics():
        """メトリクスエンドポイント（Prometheus形式）"""
        from starlette.responses import PlainTextResponse
        return PlainTextResponse(
            content=metrics_collector.get_prometheus_metrics(),
            media_type="text/plain; charset=utf-8"
        )

    # 認証エンドポイント
    @app.post("/auth/register", response_model=UserResponse, tags=["認証"],
              summary="新規ユーザー登録",
              description="メールアドレスとパスワードで新規ユーザーを登録します。登録時は無料プランが適用されます。")
    async def register(request: UserCreate):
        """ユーザー登録"""
        user = auth_service.create_user(
            email=request.email,
            password=request.password,
            name=request.name
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="このメールアドレスは既に使用されています"
            )

        # 無料サブスクリプションを作成
        billing_service.create_subscription(
            user_id=user.id,
            customer_id=f"local_{user.id}",
            plan=SubscriptionPlan.FREE
        )

        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            plan=user.plan,
            created_at=user.created_at
        )

    @app.post("/auth/login", response_model=TokenResponse, tags=["認証"],
              summary="ログイン",
              description="メールアドレスとパスワードで認証し、アクセストークンを取得します。トークンは24時間有効です。")
    async def login(request: UserLogin):
        """ログイン"""
        user = auth_service.authenticate(request.email, request.password)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="メールアドレスまたはパスワードが正しくありません"
            )

        access_token = auth_service.create_access_token(user.id)

        return TokenResponse(
            access_token=access_token,
            expires_in=auth_service.access_token_expire_minutes * 60
        )

    @app.get("/auth/me", response_model=UserResponse, tags=["認証"],
             summary="現在のユーザー情報を取得",
             description="認証トークンに紐づくユーザーの情報を返します。")
    async def get_me(current_user: User = Depends(get_current_user)):
        """現在のユーザー情報を取得"""
        return UserResponse(
            id=current_user.id,
            email=current_user.email,
            name=current_user.name,
            plan=current_user.plan,
            created_at=current_user.created_at
        )

    # メールエンドポイント
    @app.post("/email/summarize", response_model=EmailSummaryResponse, tags=["メール"],
              summary="受信メールを要約",
              description="受信トレイのメールをAIで要約します。使用量はプランの制限に従います。",
              responses={
                  402: {"description": "使用量制限超過。プランのアップグレードが必要です。"}
              })
    async def summarize_emails(
        request: EmailSummaryRequest,
        current_user: User = Depends(get_current_user)
    ):
        """メール要約"""
        # 使用量チェック
        can_use, message = billing_service.check_usage_limit(current_user.id, "email_summary")
        if not can_use:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=message
            )

        # Coordinatorを使用（モックデータ）
        coordinator = Coordinator()
        result = coordinator.process_command("inbox")

        if result.success and result.data:
            billing_service.record_usage(current_user.id, "email_summary")
            summaries = result.data.get("summaries", [])
        else:
            summaries = []

        return EmailSummaryResponse(
            summaries=summaries,
            count=len(summaries)
        )

    # スケジュールエンドポイント
    @app.post("/schedule/propose", response_model=ScheduleProposalResponse, tags=["スケジュール"],
              summary="会議スケジュールを提案",
              description="参加者全員の空き時間を検索し、最適な会議時間を提案します。",
              responses={
                  402: {"description": "使用量制限超過。プランのアップグレードが必要です。"}
              })
    async def propose_schedule(
        request: ScheduleProposalRequest,
        current_user: User = Depends(get_current_user)
    ):
        """スケジュール提案"""
        # 使用量チェック
        can_use, message = billing_service.check_usage_limit(current_user.id, "schedule_proposal")
        if not can_use:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=message
            )

        # Coordinatorを使用
        coordinator = Coordinator()
        attendees_str = " ".join(request.attendees)
        command = f"schedule {request.title} with {attendees_str} {request.duration_minutes}min"
        result = coordinator.process_command(command)

        if result.success and result.data:
            billing_service.record_usage(current_user.id, "schedule_proposal")
            proposals = result.data.get("proposals", [])
        else:
            proposals = []

        return ScheduleProposalResponse(
            proposals=proposals,
            count=len(proposals)
        )

    # 使用量エンドポイント
    @app.get("/usage", response_model=UsageResponse, tags=["使用量"],
             summary="使用量と制限を取得",
             description="現在のプランにおける使用量と残り利用可能回数を返します。")
    async def get_usage(current_user: User = Depends(get_current_user)):
        """使用量を取得"""
        summary = billing_service.get_usage_summary(current_user.id)

        if "error" in summary:
            # サブスクリプションがない場合は新規作成
            billing_service.create_subscription(
                user_id=current_user.id,
                customer_id=f"local_{current_user.id}",
                plan=SubscriptionPlan.FREE
            )
            summary = billing_service.get_usage_summary(current_user.id)

        return UsageResponse(
            plan=summary.get("plan", "free"),
            status=summary.get("status", "active"),
            email_summaries=summary.get("email_summaries", {}),
            schedule_proposals=summary.get("schedule_proposals", {}),
            actions_executed=summary.get("actions_executed", 0)
        )

    # ベータ登録エンドポイント（DB永続化）
    @app.post("/beta/signup", response_model=BetaSignupResponse, tags=["ベータ登録"],
              summary="ベータテスターとして登録",
              description="メールアドレスでベータテスターのウェイトリストに登録します。認証不要。データはDBに永続化されます。")
    async def beta_signup(request: BetaSignupRequest):
        """ベータ登録（DB永続化）"""
        email = request.email.lower()
        db = get_db()
        success, message = db.add_beta_signup(email, source="api")
        count = db.get_beta_signup_count()
        logger.info(f"ベータ登録: {email} (合計: {count}件)")

        return BetaSignupResponse(
            success=success,
            message=message,
            email=email
        )

    @app.get("/beta/count", tags=["ベータ登録"],
             summary="ベータ登録者数を取得",
             description="現在のベータ登録者数を返します。")
    async def beta_count():
        """ベータ登録者数"""
        db = get_db()
        return {"count": db.get_beta_signup_count()}

    # ===== 管理ダッシュボードエンドポイント =====
    # インメモリ管理者リスト（本番は環境変数/DBで管理）
    _admin_emails: set[str] = set(os.getenv("ADMIN_EMAILS", "admin@taskmaster.ai").split(","))

    async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
        """管理者権限チェック"""
        if current_user.email not in _admin_emails:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="管理者権限が必要です"
            )
        return current_user

    @app.get("/admin/stats", tags=["管理"],
             summary="システム統計を取得",
             description="管理者向けのシステム全体の統計情報を返します。")
    async def admin_stats(admin: User = Depends(get_admin_user)):
        """システム統計"""
        db = get_db()
        total_users = len(auth_service._users)
        beta_signups = db.get_beta_signup_count()

        # プラン別ユーザー数
        plan_counts = {"free": 0, "personal": 0, "pro": 0, "team": 0}
        for user in auth_service._users.values():
            plan = user.plan.lower()
            if plan in plan_counts:
                plan_counts[plan] += 1

        return {
            "total_users": total_users,
            "beta_signups": beta_signups,
            "plan_distribution": plan_counts,
            "timestamp": datetime.now().isoformat()
        }

    @app.get("/admin/users", tags=["管理"],
             summary="ユーザー一覧を取得",
             description="全ユーザーの一覧を返します（パスワードハッシュは除外）。")
    async def admin_users(
        admin: User = Depends(get_admin_user),
        limit: int = 100,
        offset: int = 0
    ):
        """ユーザー一覧"""
        users = list(auth_service._users.values())
        paginated = users[offset:offset + limit]

        return {
            "users": [
                {
                    "id": u.id,
                    "email": u.email,
                    "name": u.name,
                    "plan": u.plan,
                    "created_at": u.created_at.isoformat()
                }
                for u in paginated
            ],
            "total": len(users),
            "limit": limit,
            "offset": offset
        }

    @app.get("/admin/revenue", tags=["管理"],
             summary="収益概算を取得",
             description="プラン別の月間収益概算を返します。")
    async def admin_revenue(admin: User = Depends(get_admin_user)):
        """収益概算"""
        # 料金表（日本円）
        plan_prices = {
            "free": 0,
            "personal": 1480,
            "pro": 3980,
            "team": 2480  # ユーザーあたり
        }

        plan_counts = {"free": 0, "personal": 0, "pro": 0, "team": 0}
        for user in auth_service._users.values():
            plan = user.plan.lower()
            if plan in plan_counts:
                plan_counts[plan] += 1

        # 収益計算
        revenue_by_plan = {}
        total_revenue = 0
        for plan, count in plan_counts.items():
            revenue = count * plan_prices.get(plan, 0)
            revenue_by_plan[plan] = {
                "users": count,
                "price_per_user": plan_prices.get(plan, 0),
                "revenue": revenue
            }
            total_revenue += revenue

        return {
            "monthly_revenue_jpy": total_revenue,
            "by_plan": revenue_by_plan,
            "currency": "JPY",
            "timestamp": datetime.now().isoformat()
        }

    @app.get("/admin/beta-emails", tags=["管理"],
             summary="ベータ登録メール一覧を取得",
             description="ベータ登録者のメールアドレス一覧を返します（DB永続化）。")
    async def admin_beta_emails(admin: User = Depends(get_admin_user)):
        """ベータ登録メール一覧（DB永続化）"""
        db = get_db()
        emails = db.get_beta_emails()
        return {
            "emails": emails,
            "count": len(emails)
        }

    @app.get("/admin/beta-signups", tags=["管理"],
             summary="ベータ登録詳細一覧を取得",
             description="ベータ登録者の詳細情報（登録日時、ソース、ステータス）を返します。")
    async def admin_beta_signups(
        admin: User = Depends(get_admin_user),
        limit: int = 100,
        offset: int = 0
    ):
        """ベータ登録詳細一覧"""
        db = get_db()
        signups = db.get_beta_signups(limit=limit, offset=offset)
        total = db.get_beta_signup_count()
        return {
            "signups": signups,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    @app.get("/admin/health-detailed", tags=["管理"],
             summary="詳細ヘルスチェック",
             description="各サービスの詳細な稼働状態を返します。")
    async def admin_health_detailed(admin: User = Depends(get_admin_user)):
        """詳細ヘルスチェック"""
        import sys

        checks = {
            "api": {"status": "healthy", "message": "APIサーバー稼働中"},
            "auth": {"status": "healthy", "users_loaded": len(auth_service._users)},
            "billing": {"status": "healthy"},
            "python_version": sys.version,
            "fastapi_available": FASTAPI_AVAILABLE,
            "jwt_available": JWT_AVAILABLE,
        }

        # 全体ステータス
        all_healthy = all(
            c.get("status") == "healthy"
            for c in checks.values()
            if isinstance(c, dict) and "status" in c
        )

        return {
            "status": "healthy" if all_healthy else "degraded",
            "checks": checks,
            "timestamp": datetime.now().isoformat()
        }

    # ===== デモモードエンドポイント =====
    # API認証情報がなくてもサービスの機能を体験可能

    class DemoEmailSummaryResponse(BaseModel):
        """デモ用メール要約レスポンス"""
        summaries: list[dict]
        count: int
        demo_mode: bool = True
        message: str

    class DemoScheduleResponse(BaseModel):
        """デモ用スケジュール提案レスポンス"""
        proposals: list[dict]
        count: int
        demo_mode: bool = True
        message: str

    # デモ用サンプルデータ
    DEMO_EMAIL_SUMMARIES = [
        {
            "id": "demo_1",
            "from": "田中一郎 <tanaka@example.com>",
            "subject": "明日のミーティングについて",
            "summary": "明日10時からのミーティングのアジェンダを共有したい。事前に資料を確認してほしい。",
            "priority": "high",
            "received_at": "2026-01-11T09:30:00"
        },
        {
            "id": "demo_2",
            "from": "営業部 <sales@example.com>",
            "subject": "週次レポート: 1月第2週",
            "summary": "今週の売上は前週比15%増。新規顧客3社獲得。来週の目標設定が必要。",
            "priority": "medium",
            "received_at": "2026-01-11T08:00:00"
        },
        {
            "id": "demo_3",
            "from": "システム通知 <noreply@example.com>",
            "subject": "月次バックアップ完了",
            "summary": "定期バックアップが正常に完了しました。対応不要。",
            "priority": "low",
            "received_at": "2026-01-11T03:00:00"
        }
    ]

    DEMO_SCHEDULE_PROPOSALS = [
        {
            "id": "prop_1",
            "start": "2026-01-13T14:00:00",
            "end": "2026-01-13T15:00:00",
            "title": "チームミーティング",
            "score": 95,
            "reason": "全員の空き時間。午後の集中しやすい時間帯。"
        },
        {
            "id": "prop_2",
            "start": "2026-01-14T10:00:00",
            "end": "2026-01-14T11:00:00",
            "title": "チームミーティング",
            "score": 88,
            "reason": "朝の時間帯。1名が他の予定と近接。"
        },
        {
            "id": "prop_3",
            "start": "2026-01-15T16:00:00",
            "end": "2026-01-15T17:00:00",
            "title": "チームミーティング",
            "score": 75,
            "reason": "週末前の金曜夕方。一部メンバーが早退の可能性。"
        }
    ]

    @app.get("/demo/emails", response_model=DemoEmailSummaryResponse, tags=["デモ"],
             summary="デモ: メール要約を体験",
             description="サンプルデータでメール要約機能を体験できます。認証不要。実際のメールは取得しません。")
    async def demo_email_summary():
        """デモ用メール要約"""
        return DemoEmailSummaryResponse(
            summaries=DEMO_EMAIL_SUMMARIES,
            count=len(DEMO_EMAIL_SUMMARIES),
            demo_mode=True,
            message="これはデモデータです。実際のサービスではあなたの受信トレイから重要なメールを自動要約します。"
        )

    @app.get("/demo/schedule", response_model=DemoScheduleResponse, tags=["デモ"],
             summary="デモ: スケジュール提案を体験",
             description="サンプルデータでスケジュール提案機能を体験できます。認証不要。実際のカレンダーは参照しません。")
    async def demo_schedule_proposal():
        """デモ用スケジュール提案"""
        return DemoScheduleResponse(
            proposals=DEMO_SCHEDULE_PROPOSALS,
            count=len(DEMO_SCHEDULE_PROPOSALS),
            demo_mode=True,
            message="これはデモデータです。実際のサービスでは参加者全員のカレンダーを分析し、最適な会議時間を提案します。"
        )

    @app.get("/demo/features", tags=["デモ"],
             summary="デモ: 利用可能な機能一覧",
             description="TaskMasterAIで利用可能な全機能の概要を返します。")
    async def demo_features():
        """利用可能な機能一覧"""
        return {
            "features": [
                {
                    "id": "email_summary",
                    "name": "スマートメール管理",
                    "description": "未読メールを自動要約し、優先度順に整理",
                    "demo_endpoint": "/demo/emails"
                },
                {
                    "id": "schedule_proposal",
                    "name": "インテリジェントスケジューリング",
                    "description": "参加者全員の空き時間を検索し、最適な会議時間を提案",
                    "demo_endpoint": "/demo/schedule"
                },
                {
                    "id": "draft_reply",
                    "name": "返信ドラフト作成",
                    "description": "メールの文脈を理解し、適切な返信案を生成",
                    "available_in": ["personal", "pro", "team"]
                },
                {
                    "id": "task_automation",
                    "name": "タスク自動化",
                    "description": "定型業務のルール設定と自動実行",
                    "available_in": ["pro", "team"]
                }
            ],
            "pricing": {
                "free": {"price": 0, "currency": "JPY", "email_limit": 50, "schedule_limit": 10},
                "personal": {"price": 1480, "currency": "JPY", "email_limit": 500, "schedule_limit": 100},
                "pro": {"price": 3980, "currency": "JPY", "email_limit": 2000, "schedule_limit": 500}
            },
            "demo_mode": True
        }

    logger.info("FastAPIアプリケーション作成完了（管理ダッシュボードAPI + デモモード含む）")
    return app


# アプリケーションインスタンス（uvicornで使用）
if FASTAPI_AVAILABLE:
    app = create_app()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if not FASTAPI_AVAILABLE:
        print("FastAPIがインストールされていません。")
        print("pip install fastapi uvicorn pyjwt で必要なパッケージをインストールしてください。")
    else:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8000)
