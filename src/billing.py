"""
Billing Module - 課金・サブスクリプション管理

Stripe APIを使用した課金システムの基盤実装
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from .logging_config import get_logger
from .errors import (
    BillingError,
    ErrorCode,
    ErrorSeverity,
)

logger = get_logger(__name__, "billing")


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
            logger.warning(
                "Stripe APIキーが設定されていません。モックモードで動作します。"
            )

    def _init_stripe(self):
        """Stripe SDKの初期化"""
        try:
            import stripe
            stripe.api_key = self.stripe_api_key
            self._stripe = stripe
            logger.info("Stripe SDK初期化完了")
        except ImportError:
            logger.warning(
                "stripeパッケージがインストールされていません",
                data={"package": "stripe"}
            )

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
            logger.info(
                "モックカスタマー作成",
                data={"customer_id": customer_id, "user_id": user_id}
            )
            return customer_id

        try:
            customer = self._stripe.Customer.create(
                email=email,
                name=name,
                metadata={"user_id": user_id}
            )
            logger.info(
                "Stripeカスタマー作成完了",
                data={"customer_id": customer.id, "user_id": user_id, "email": email}
            )
            return customer.id
        except Exception as e:
            error = BillingError(
                code=ErrorCode.BILLING_STRIPE_ERROR,
                message=f"カスタマー作成エラー: {e}",
                details={"user_id": user_id, "email": email},
                cause=e
            )
            error.log()
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
            logger.info(
                "無料サブスクリプション作成",
                data={"user_id": user_id, "plan": plan.value}
            )
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
            logger.info(
                "モックサブスクリプション作成",
                data={"user_id": user_id, "plan": plan.value, "trial_days": trial_days}
            )
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
                logger.error(
                    "価格IDが設定されていません",
                    data={"plan": plan.value}
                )
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

            logger.info(
                "サブスクリプション作成完了",
                data={
                    "subscription_id": stripe_sub.id,
                    "user_id": user_id,
                    "plan": plan.value
                }
            )
            return subscription

        except Exception as e:
            error = BillingError(
                code=ErrorCode.BILLING_STRIPE_ERROR,
                message=f"サブスクリプション作成エラー: {e}",
                details={"user_id": user_id, "plan": plan.value},
                cause=e
            )
            error.log()
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
            logger.warning(
                "サブスクリプションが見つかりません",
                data={"user_id": user_id}
            )
            return False

        if subscription.plan == SubscriptionPlan.FREE:
            logger.warning(
                "無料プランはキャンセルできません",
                data={"user_id": user_id}
            )
            return False

        if not self._stripe:
            # モックモード
            subscription.cancel_at_period_end = at_period_end
            if not at_period_end:
                subscription.status = SubscriptionStatus.CANCELED
            logger.info(
                "モックサブスクリプションキャンセル",
                data={"user_id": user_id, "at_period_end": at_period_end}
            )
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

            logger.info(
                "サブスクリプションキャンセル完了",
                data={
                    "subscription_id": subscription.stripe_subscription_id,
                    "user_id": user_id,
                    "at_period_end": at_period_end
                }
            )
            return True

        except Exception as e:
            error = BillingError(
                code=ErrorCode.BILLING_STRIPE_ERROR,
                message=f"キャンセルエラー: {e}",
                details={"user_id": user_id},
                cause=e
            )
            error.log()
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
            logger.warning(
                "サブスクリプションが見つかりません",
                data={"user_id": user_id}
            )
            return False

        old_plan = subscription.plan

        if not self._stripe:
            # モックモード
            subscription.plan = new_plan
            logger.info(
                "モックプランアップグレード",
                data={"user_id": user_id, "old_plan": old_plan.value, "new_plan": new_plan.value}
            )
            return True

        # Stripe APIでのプラン変更は実装省略（Webhook処理が必要）
        subscription.plan = new_plan
        logger.info(
            "プランアップグレード",
            data={"user_id": user_id, "old_plan": old_plan.value, "new_plan": new_plan.value}
        )
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

    def get_savings_report(self, user_id: str) -> dict:
        """
        節約時間・ROIレポートを取得

        ユーザーの使用量に基づいて節約時間と金額換算を計算し、
        有料プランへのアップグレード価値を可視化します。

        Args:
            user_id: ユーザーID

        Returns:
            節約時間レポート辞書
        """
        subscription = self._subscriptions.get(user_id)
        if not subscription:
            return {"error": "サブスクリプションが見つかりません"}

        usage = subscription.usage

        # 機能ごとの推定節約時間（分）
        SAVINGS_PER_EMAIL_SUMMARY = 3  # 1通のメール要約で3分節約
        SAVINGS_PER_SCHEDULE_PROPOSAL = 10  # 1回のスケジュール提案で10分節約
        SAVINGS_PER_ACTION = 15  # 1回のアクション実行で15分節約

        # 計算
        email_savings_minutes = usage.email_summaries_used * SAVINGS_PER_EMAIL_SUMMARY
        schedule_savings_minutes = usage.schedule_proposals_used * SAVINGS_PER_SCHEDULE_PROPOSAL
        action_savings_minutes = usage.actions_executed * SAVINGS_PER_ACTION

        total_minutes = email_savings_minutes + schedule_savings_minutes + action_savings_minutes
        total_hours = total_minutes / 60

        # 金額換算（時給5000円として計算）
        HOURLY_RATE_JPY = 5000
        savings_value_jpy = int(total_hours * HOURLY_RATE_JPY)

        # プラン料金（月額）
        plan_prices_jpy = {
            SubscriptionPlan.FREE: 0,
            SubscriptionPlan.PERSONAL: 1480,
            SubscriptionPlan.PRO: 3980,
            SubscriptionPlan.TEAM: 2480,
            SubscriptionPlan.ENTERPRISE: 50000  # 概算
        }

        plan_price = plan_prices_jpy.get(subscription.plan, 0)
        net_savings_jpy = savings_value_jpy - plan_price
        roi_percent = (savings_value_jpy / plan_price * 100) if plan_price > 0 else float('inf')

        # アップグレード推奨判定
        limits = subscription.get_limits()
        usage_percent_email = (
            usage.email_summaries_used / limits.email_summaries_per_month * 100
            if limits.email_summaries_per_month > 0 else 0
        )
        usage_percent_schedule = (
            usage.schedule_proposals_used / limits.schedule_proposals_per_month * 100
            if limits.schedule_proposals_per_month > 0 else 0
        )

        upgrade_recommended = usage_percent_email > 80 or usage_percent_schedule > 80

        # 次のプラン推奨
        next_plan_recommendation = None
        if subscription.plan == SubscriptionPlan.FREE and upgrade_recommended:
            next_plan_recommendation = {
                "plan": "personal",
                "price_jpy": 1480,
                "additional_benefits": [
                    "月500通のメール要約（現在の10倍）",
                    "月100回のスケジュール提案（現在の10倍）",
                    "アクション自動実行機能"
                ]
            }
        elif subscription.plan == SubscriptionPlan.PERSONAL and upgrade_recommended:
            next_plan_recommendation = {
                "plan": "pro",
                "price_jpy": 3980,
                "additional_benefits": [
                    "月2000通のメール要約（現在の4倍）",
                    "月500回のスケジュール提案（現在の5倍）",
                    "優先サポート"
                ]
            }

        return {
            "usage_breakdown": {
                "email_summaries": {
                    "count": usage.email_summaries_used,
                    "savings_minutes": email_savings_minutes
                },
                "schedule_proposals": {
                    "count": usage.schedule_proposals_used,
                    "savings_minutes": schedule_savings_minutes
                },
                "actions_executed": {
                    "count": usage.actions_executed,
                    "savings_minutes": action_savings_minutes
                }
            },
            "total_savings": {
                "minutes": total_minutes,
                "hours": round(total_hours, 1),
                "value_jpy": savings_value_jpy,
                "calculation_rate_jpy_per_hour": HOURLY_RATE_JPY
            },
            "plan_cost": {
                "plan": subscription.plan.value,
                "monthly_price_jpy": plan_price
            },
            "net_savings": {
                "value_jpy": net_savings_jpy,
                "roi_percent": round(roi_percent, 1) if roi_percent != float('inf') else "unlimited"
            },
            "usage_status": {
                "email_usage_percent": round(usage_percent_email, 1),
                "schedule_usage_percent": round(usage_percent_schedule, 1),
                "upgrade_recommended": upgrade_recommended
            },
            "upgrade_recommendation": next_plan_recommendation,
            "generated_at": datetime.now().isoformat()
        }


# モッククライアント（テスト用）
class MockBillingService(BillingService):
    """テスト用のモック課金サービス"""

    def __init__(self):
        super().__init__(stripe_api_key=None)
        logger.info("MockBillingService初期化")


if __name__ == "__main__":
    from .logging_config import configure_logging

    configure_logging(level="INFO", console_output=True, file_output=False)

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
