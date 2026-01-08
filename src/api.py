"""
Web API Module - FastAPIベースのREST API

SaaS提供のためのWebインターフェース基盤
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

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

    app = FastAPI(
        title="TaskMasterAI API",
        description="AI-Powered Virtual Executive Assistant API",
        version="0.1.0"
    )

    # CORS設定
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # サービスの初期化
    auth_service = AuthService()
    billing_service = BillingService()
    security = HTTPBearer()

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
    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """ヘルスチェックエンドポイント"""
        return HealthResponse(
            status="healthy",
            version="0.1.0",
            timestamp=datetime.now()
        )

    # 認証エンドポイント
    @app.post("/auth/register", response_model=UserResponse)
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

    @app.post("/auth/login", response_model=TokenResponse)
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

    @app.get("/auth/me", response_model=UserResponse)
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
    @app.post("/email/summarize", response_model=EmailSummaryResponse)
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
    @app.post("/schedule/propose", response_model=ScheduleProposalResponse)
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
    @app.get("/usage", response_model=UsageResponse)
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

    logger.info("FastAPIアプリケーション作成完了")
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
