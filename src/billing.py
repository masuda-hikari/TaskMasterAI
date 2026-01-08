"""
Billing Module - 課金・サブスクリプション管理

Stripe APIを使用した課金システムの基盤実装
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import os

logger = logging.getLogger(__name__)


class SubscriptionPlan(Enum):
    """サブスクリプションプラン"""
    FREE = "free"
    PERSONAL = "personal"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(Enum):
    """サブスクリプション状態"""
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    TRIALING = "trialing"
    INCOMPLETE = "incomplete"


@dataclass
class PlanLimits:
    """プラン毎の制限"""
    email_summaries_per_month: int
    schedule_proposals_per_month: int
    auto_actions_enabled: bool
    max_integrations: int
    priority_support: bool

    @classmethod
    def for_plan(cls, plan: SubscriptionPlan) -> "PlanLimits":
        """プランに応じた制限を返す"""
        limits = {
            SubscriptionPlan.FREE: cls(
                email_summaries_per_month=50,
                schedule_proposals_per_month=10,
                auto_actions_enabled=False,
                max_integrations=1,
                priority_support=False
            ),
            SubscriptionPlan.PERSONAL: cls(
                email_summaries_per_month=500,
                schedule_proposals_per_month=100,
                auto_actions_enabled=True,
                max_integrations=2,
                priority_support=False
            ),
            SubscriptionPlan.PRO: cls(
                email_summaries_per_month=2000,
                schedule_proposals_per_month=500,
                auto_actions_enabled=True,
                max_integrations=10,
                priority_support=True
            ),
            SubscriptionPlan.TEAM: cls(
                email_summaries_per_month=5000,
                schedule_proposals_per_month=1000,
                auto_actions_enabled=True,
                max_integrations=50,
                priority_support=True
            ),
            SubscriptionPlan.ENTERPRISE: cls(
                email_summaries_per_month=-1,  # 無制限
                schedule_proposals_per_month=-1,
                auto_actions_enabled=True,
                max_integrations=-1,
                priority_support=True
            )
        }
        return limits.get(plan, limits[SubscriptionPlan.FREE])


@dataclass
class PlanPricing:
    """プラン価格"""
    monthly_price_cents: int  # セント単位
    annual_price_cents: int   # 年額（セント単位）
    currency: str = "usd"

    @classmethod
    def for_plan(cls, plan: SubscriptionPlan) -> "PlanPricing":
        """プランに応じた価格を返す"""
        pricing = {
            SubscriptionPlan.FREE: cls(0, 0),
            SubscriptionPlan.PERSONAL: cls(1000, 10000),   # $10/月, $100/年
            SubscriptionPlan.PRO: cls(2500, 25000),        # $25/月, $250/年
            SubscriptionPlan.TEAM: cls(1500, 15000),       # $15/月/人, $150/年/人
            SubscriptionPlan.ENTERPRISE: cls(0, 0),        # カスタム価格
        }
        return pricing.get(plan, pricing[SubscriptionPlan.FREE])


@dataclass
class UsageMetrics:
    """使用量メトリクス"""
    email_summaries_used: int = 0
    schedule_proposals_used: int = 0
    actions_executed: int = 0
    period_start: datetime = field(default_factory=datetime.now)
    period_end: Optional[datetime] = None

    def reset(self):
        """使用量をリセット（月初に呼び出し）"""
        self.email_summaries_used = 0
        self.schedule_proposals_used = 0
        self.actions_executed = 0
        self.period_start = datetime.now()
        self.period_end = self.period_start + timedelta(days=30)


@dataclass
class Subscription:
    """サブスクリプション情報"""
    user_id: str
    plan: SubscriptionPlan
    status: SubscriptionStatus
    stripe_subscription_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    usage: UsageMetrics = field(default_factory=UsageMetrics)

    def is_active(self) -> bool:
        """アクティブなサブスクリプションか"""
        return self.status in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]

    def get_limits(self) -> PlanLimits:
        """現在のプランの制限を取得"""
        return PlanLimits.for_plan(self.plan)

    def can_use_feature(self, feature: str) -> bool:
        """機能が使用可能か判定"""
        if not self.is_active():
            return False

        limits = self.get_limits()

        if feature == "email_summary":
            if limits.email_summaries_per_month == -1:
                return True
            return self.usage.email_summaries_used < limits.email_summaries_per_month
        elif feature == "schedule_proposal":
            if limits.schedule_proposals_per_month == -1:
                return True
            return self.usage.schedule_proposals_used < limits.schedule_proposals_per_month
        elif feature == "auto_action":
            return limits.auto_actions_enabled
        else:
            return True

    def record_usage(self, feature: str) -> bool:
        """使用量を記録"""
        if not self.can_use_feature(feature):
            return False

        if feature == "email_summary":
            self.usage.email_summaries_used += 1
        elif feature == "schedule_proposal":
            self.usage.schedule_proposals_used += 1
        elif feature == "action":
            self.usage.actions_executed += 1

        return True


class BillingService:
    """
    課金サービス

    Stripe APIを使用したサブスクリプション管理
    """

    def __init__(self, stripe_api_key: Optional[str] = None):
        """
        初期化

        Args:
            stripe_api_key: Stripe APIキー（省略時は環境変数から取得）
        """
        self.stripe_api_key = stripe_api_key or os.getenv("STRIPE_API_KEY")
        self._stripe = None
        self._subscriptions: dict[str, Subscription] = {}  # ユーザーID -> サブスクリプション

        if self.stripe_api_key:
            self._init_stripe()
        else:
            logger.warning("Stripe APIキーが設定されていません。モックモードで動作します。")

    def _init_stripe(self):
        """Stripe SDKの初期化"""
        try:
            import stripe
            stripe.api_key = self.stripe_api_key
            self._stripe = stripe
            logger.info("Stripe SDK初期化完了")
        except ImportError:
            logger.warning("stripeパッケージがインストールされていません")

    def create_customer(self, user_id: str, email: str, name: Optional[str] = None) -> Optional[str]:
        """
        Stripeカスタマーを作成

        Args:
            user_id: 内部ユーザーID
            email: メールアドレス
            name: 名前

        Returns:
            StripeカスタマーID（失敗時はNone）
        """
        if not self._stripe:
            # モックモード
            customer_id = f"cus_mock_{user_id}"
            logger.info(f"モックカスタマー作成: {customer_id}")
            return customer_id

        try:
            customer = self._stripe.Customer.create(
                email=email,
                name=name,
                metadata={"user_id": user_id}
            )
            logger.info(f"Stripeカスタマー作成完了: {customer.id}")
            return customer.id
        except Exception as e:
            logger.error(f"カスタマー作成エラー: {e}")
            return None

    def create_subscription(
        self,
        user_id: str,
        customer_id: str,
        plan: SubscriptionPlan,
        trial_days: int = 0
    ) -> Optional[Subscription]:
        """
        サブスクリプションを作成

        Args:
            user_id: 内部ユーザーID
            customer_id: StripeカスタマーID
            plan: サブスクリプションプラン
            trial_days: トライアル日数

        Returns:
            Subscriptionオブジェクト（失敗時はNone）
        """
        if plan == SubscriptionPlan.FREE:
            # 無料プランはStripe不要
            subscription = Subscription(
                user_id=user_id,
                plan=plan,
                status=SubscriptionStatus.ACTIVE,
                current_period_start=datetime.now(),
                current_period_end=None  # 無期限
            )
            self._subscriptions[user_id] = subscription
            logger.info(f"無料サブスクリプション作成: {user_id}")
            return subscription

        if not self._stripe:
            # モックモード
            subscription = Subscription(
                user_id=user_id,
                plan=plan,
                status=SubscriptionStatus.TRIALING if trial_days > 0 else SubscriptionStatus.ACTIVE,
                stripe_subscription_id=f"sub_mock_{user_id}",
                stripe_customer_id=customer_id,
                current_period_start=datetime.now(),
                current_period_end=datetime.now() + timedelta(days=30)
            )
            self._subscriptions[user_id] = subscription
            logger.info(f"モックサブスクリプション作成: {user_id} -> {plan.value}")
            return subscription

        try:
            # 価格IDのマッピング（実際にはStripe Dashboardで設定）
            price_ids = {
                SubscriptionPlan.PERSONAL: os.getenv("STRIPE_PRICE_PERSONAL"),
                SubscriptionPlan.PRO: os.getenv("STRIPE_PRICE_PRO"),
                SubscriptionPlan.TEAM: os.getenv("STRIPE_PRICE_TEAM"),
            }

            price_id = price_ids.get(plan)
            if not price_id:
                logger.error(f"プラン {plan.value} の価格IDが設定されていません")
                return None

            sub_params = {
                "customer": customer_id,
                "items": [{"price": price_id}],
                "metadata": {"user_id": user_id}
            }

            if trial_days > 0:
                sub_params["trial_period_days"] = trial_days

            stripe_sub = self._stripe.Subscription.create(**sub_params)

            subscription = Subscription(
                user_id=user_id,
                plan=plan,
                status=SubscriptionStatus(stripe_sub.status),
                stripe_subscription_id=stripe_sub.id,
                stripe_customer_id=customer_id,
                current_period_start=datetime.fromtimestamp(stripe_sub.current_period_start),
                current_period_end=datetime.fromtimestamp(stripe_sub.current_period_end)
            )
            self._subscriptions[user_id] = subscription

            logger.info(f"サブスクリプション作成完了: {stripe_sub.id}")
            return subscription

        except Exception as e:
            logger.error(f"サブスクリプション作成エラー: {e}")
            return None

    def get_subscription(self, user_id: str) -> Optional[Subscription]:
        """ユーザーのサブスクリプションを取得"""
        return self._subscriptions.get(user_id)

    def cancel_subscription(self, user_id: str, at_period_end: bool = True) -> bool:
        """
        サブスクリプションをキャンセル

        Args:
            user_id: ユーザーID
            at_period_end: 期間終了時にキャンセルするか（即時キャンセルならFalse）

        Returns:
            成功: True, 失敗: False
        """
        subscription = self._subscriptions.get(user_id)
        if not subscription:
            logger.warning(f"サブスクリプションが見つかりません: {user_id}")
            return False

        if subscription.plan == SubscriptionPlan.FREE:
            logger.warning("無料プランはキャンセルできません")
            return False

        if not self._stripe:
            # モックモード
            subscription.cancel_at_period_end = at_period_end
            if not at_period_end:
                subscription.status = SubscriptionStatus.CANCELED
            logger.info(f"モックサブスクリプションキャンセル: {user_id}")
            return True

        try:
            self._stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=at_period_end
            )
            subscription.cancel_at_period_end = at_period_end

            if not at_period_end:
                self._stripe.Subscription.delete(subscription.stripe_subscription_id)
                subscription.status = SubscriptionStatus.CANCELED

            logger.info(f"サブスクリプションキャンセル完了: {subscription.stripe_subscription_id}")
            return True

        except Exception as e:
            logger.error(f"キャンセルエラー: {e}")
            return False

    def upgrade_plan(self, user_id: str, new_plan: SubscriptionPlan) -> bool:
        """
        プランをアップグレード

        Args:
            user_id: ユーザーID
            new_plan: 新しいプラン

        Returns:
            成功: True, 失敗: False
        """
        subscription = self._subscriptions.get(user_id)
        if not subscription:
            logger.warning(f"サブスクリプションが見つかりません: {user_id}")
            return False

        if not self._stripe:
            # モックモード
            subscription.plan = new_plan
            logger.info(f"モックプランアップグレード: {user_id} -> {new_plan.value}")
            return True

        # Stripe APIでのプラン変更は実装省略（Webhook処理が必要）
        logger.info(f"プランアップグレード: {user_id} -> {new_plan.value}")
        subscription.plan = new_plan
        return True

    def check_usage_limit(self, user_id: str, feature: str) -> tuple[bool, str]:
        """
        使用量制限をチェック

        Args:
            user_id: ユーザーID
            feature: 機能名

        Returns:
            (使用可能か, メッセージ)
        """
        subscription = self._subscriptions.get(user_id)
        if not subscription:
            # サブスクリプションがない場合は無料プラン扱い
            subscription = Subscription(
                user_id=user_id,
                plan=SubscriptionPlan.FREE,
                status=SubscriptionStatus.ACTIVE
            )
            self._subscriptions[user_id] = subscription

        can_use = subscription.can_use_feature(feature)

        if not can_use:
            limits = subscription.get_limits()
            if feature == "email_summary":
                return False, f"月間メール要約上限（{limits.email_summaries_per_month}件）に達しました。プランをアップグレードしてください。"
            elif feature == "schedule_proposal":
                return False, f"月間スケジュール提案上限（{limits.schedule_proposals_per_month}件）に達しました。プランをアップグレードしてください。"
            elif feature == "auto_action":
                return False, "自動アクション機能は有料プランで利用できます。"
            else:
                return False, "使用制限に達しました。"

        return True, "OK"

    def record_usage(self, user_id: str, feature: str) -> bool:
        """使用量を記録"""
        subscription = self._subscriptions.get(user_id)
        if not subscription:
            return False
        return subscription.record_usage(feature)

    def get_usage_summary(self, user_id: str) -> dict:
        """使用量サマリーを取得"""
        subscription = self._subscriptions.get(user_id)
        if not subscription:
            return {"error": "サブスクリプションが見つかりません"}

        limits = subscription.get_limits()
        usage = subscription.usage

        return {
            "plan": subscription.plan.value,
            "status": subscription.status.value,
            "email_summaries": {
                "used": usage.email_summaries_used,
                "limit": limits.email_summaries_per_month,
                "remaining": max(0, limits.email_summaries_per_month - usage.email_summaries_used) if limits.email_summaries_per_month > 0 else "unlimited"
            },
            "schedule_proposals": {
                "used": usage.schedule_proposals_used,
                "limit": limits.schedule_proposals_per_month,
                "remaining": max(0, limits.schedule_proposals_per_month - usage.schedule_proposals_used) if limits.schedule_proposals_per_month > 0 else "unlimited"
            },
            "actions_executed": usage.actions_executed,
            "period_start": usage.period_start.isoformat() if usage.period_start else None,
            "period_end": usage.period_end.isoformat() if usage.period_end else None
        }


# モッククライアント（テスト用）
class MockBillingService(BillingService):
    """テスト用のモック課金サービス"""

    def __init__(self):
        super().__init__(stripe_api_key=None)
        logger.info("MockBillingService初期化")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # テスト実行
    print("=== BillingService テスト ===")

    service = MockBillingService()

    # 無料プランのサブスクリプション作成
    sub = service.create_subscription(
        user_id="test_user_1",
        customer_id="cus_mock_1",
        plan=SubscriptionPlan.FREE
    )
    print(f"無料プラン: {sub}")

    # 使用量チェック
    can_use, msg = service.check_usage_limit("test_user_1", "email_summary")
    print(f"メール要約可能: {can_use} - {msg}")

    # 使用量サマリー
    summary = service.get_usage_summary("test_user_1")
    print(f"使用量サマリー: {summary}")
