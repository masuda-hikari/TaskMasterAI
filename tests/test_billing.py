"""
Billing Module テスト

課金・サブスクリプション管理のユニットテスト
"""

import pytest
from datetime import datetime, timedelta
from src.billing import (
    SubscriptionPlan,
    SubscriptionStatus,
    PlanLimits,
    PlanPricing,
    UsageMetrics,
    Subscription,
    BillingService,
    MockBillingService
)


class TestPlanLimits:
    """PlanLimitsのテスト"""

    def test_free_plan_limits(self):
        """無料プランの制限"""
        limits = PlanLimits.for_plan(SubscriptionPlan.FREE)
        assert limits.email_summaries_per_month == 50
        assert limits.schedule_proposals_per_month == 10
        assert limits.auto_actions_enabled is False
        assert limits.max_integrations == 1
        assert limits.priority_support is False

    def test_personal_plan_limits(self):
        """Personalプランの制限"""
        limits = PlanLimits.for_plan(SubscriptionPlan.PERSONAL)
        assert limits.email_summaries_per_month == 500
        assert limits.schedule_proposals_per_month == 100
        assert limits.auto_actions_enabled is True
        assert limits.max_integrations == 2

    def test_pro_plan_limits(self):
        """Proプランの制限"""
        limits = PlanLimits.for_plan(SubscriptionPlan.PRO)
        assert limits.email_summaries_per_month == 2000
        assert limits.schedule_proposals_per_month == 500
        assert limits.priority_support is True

    def test_enterprise_plan_unlimited(self):
        """Enterpriseプランは無制限"""
        limits = PlanLimits.for_plan(SubscriptionPlan.ENTERPRISE)
        assert limits.email_summaries_per_month == -1
        assert limits.schedule_proposals_per_month == -1


class TestPlanPricing:
    """PlanPricingのテスト"""

    def test_free_plan_price(self):
        """無料プランは$0"""
        pricing = PlanPricing.for_plan(SubscriptionPlan.FREE)
        assert pricing.monthly_price_cents == 0
        assert pricing.annual_price_cents == 0

    def test_personal_plan_price(self):
        """Personalプランは$10/月"""
        pricing = PlanPricing.for_plan(SubscriptionPlan.PERSONAL)
        assert pricing.monthly_price_cents == 1000  # $10.00
        assert pricing.currency == "usd"

    def test_pro_plan_price(self):
        """Proプランは$25/月"""
        pricing = PlanPricing.for_plan(SubscriptionPlan.PRO)
        assert pricing.monthly_price_cents == 2500  # $25.00


class TestUsageMetrics:
    """UsageMetricsのテスト"""

    def test_initial_values(self):
        """初期値のテスト"""
        usage = UsageMetrics()
        assert usage.email_summaries_used == 0
        assert usage.schedule_proposals_used == 0
        assert usage.actions_executed == 0

    def test_reset(self):
        """リセットのテスト"""
        usage = UsageMetrics()
        usage.email_summaries_used = 100
        usage.schedule_proposals_used = 50
        usage.actions_executed = 25

        usage.reset()

        assert usage.email_summaries_used == 0
        assert usage.schedule_proposals_used == 0
        assert usage.actions_executed == 0
        assert usage.period_end is not None


class TestSubscription:
    """Subscriptionのテスト"""

    def test_is_active_with_active_status(self):
        """アクティブステータスのテスト"""
        sub = Subscription(
            user_id="test_user",
            plan=SubscriptionPlan.PERSONAL,
            status=SubscriptionStatus.ACTIVE
        )
        assert sub.is_active() is True

    def test_is_active_with_trialing_status(self):
        """トライアルステータスのテスト"""
        sub = Subscription(
            user_id="test_user",
            plan=SubscriptionPlan.PERSONAL,
            status=SubscriptionStatus.TRIALING
        )
        assert sub.is_active() is True

    def test_is_active_with_canceled_status(self):
        """キャンセルステータスのテスト"""
        sub = Subscription(
            user_id="test_user",
            plan=SubscriptionPlan.PERSONAL,
            status=SubscriptionStatus.CANCELED
        )
        assert sub.is_active() is False

    def test_can_use_feature_within_limit(self):
        """制限内での機能使用"""
        sub = Subscription(
            user_id="test_user",
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE
        )
        sub.usage.email_summaries_used = 10
        assert sub.can_use_feature("email_summary") is True

    def test_can_use_feature_at_limit(self):
        """制限に達した場合"""
        sub = Subscription(
            user_id="test_user",
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE
        )
        sub.usage.email_summaries_used = 50  # FREE制限
        assert sub.can_use_feature("email_summary") is False

    def test_can_use_auto_action_free_plan(self):
        """無料プランでの自動アクション"""
        sub = Subscription(
            user_id="test_user",
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE
        )
        assert sub.can_use_feature("auto_action") is False

    def test_can_use_auto_action_paid_plan(self):
        """有料プランでの自動アクション"""
        sub = Subscription(
            user_id="test_user",
            plan=SubscriptionPlan.PERSONAL,
            status=SubscriptionStatus.ACTIVE
        )
        assert sub.can_use_feature("auto_action") is True

    def test_record_usage(self):
        """使用量の記録"""
        sub = Subscription(
            user_id="test_user",
            plan=SubscriptionPlan.PERSONAL,
            status=SubscriptionStatus.ACTIVE
        )
        result = sub.record_usage("email_summary")
        assert result is True
        assert sub.usage.email_summaries_used == 1

    def test_record_usage_at_limit(self):
        """制限に達した場合の記録"""
        sub = Subscription(
            user_id="test_user",
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE
        )
        sub.usage.email_summaries_used = 50
        result = sub.record_usage("email_summary")
        assert result is False
        assert sub.usage.email_summaries_used == 50  # 増えない


class TestMockBillingService:
    """MockBillingServiceのテスト"""

    @pytest.fixture
    def service(self):
        """サービスのフィクスチャ"""
        return MockBillingService()

    def test_create_customer(self, service):
        """カスタマー作成"""
        customer_id = service.create_customer(
            user_id="test_user",
            email="test@example.com"
        )
        assert customer_id is not None
        assert "mock" in customer_id

    def test_create_free_subscription(self, service):
        """無料サブスクリプション作成"""
        sub = service.create_subscription(
            user_id="test_user",
            customer_id="cus_mock_1",
            plan=SubscriptionPlan.FREE
        )
        assert sub is not None
        assert sub.plan == SubscriptionPlan.FREE
        assert sub.status == SubscriptionStatus.ACTIVE

    def test_create_paid_subscription(self, service):
        """有料サブスクリプション作成"""
        sub = service.create_subscription(
            user_id="test_user",
            customer_id="cus_mock_1",
            plan=SubscriptionPlan.PERSONAL
        )
        assert sub is not None
        assert sub.plan == SubscriptionPlan.PERSONAL
        assert sub.stripe_subscription_id is not None

    def test_create_subscription_with_trial(self, service):
        """トライアル付きサブスクリプション"""
        sub = service.create_subscription(
            user_id="test_user",
            customer_id="cus_mock_1",
            plan=SubscriptionPlan.PRO,
            trial_days=14
        )
        assert sub is not None
        assert sub.status == SubscriptionStatus.TRIALING

    def test_get_subscription(self, service):
        """サブスクリプション取得"""
        service.create_subscription(
            user_id="test_user",
            customer_id="cus_mock_1",
            plan=SubscriptionPlan.FREE
        )
        sub = service.get_subscription("test_user")
        assert sub is not None
        assert sub.user_id == "test_user"

    def test_get_nonexistent_subscription(self, service):
        """存在しないサブスクリプション"""
        sub = service.get_subscription("nonexistent")
        assert sub is None

    def test_cancel_subscription(self, service):
        """サブスクリプションキャンセル"""
        service.create_subscription(
            user_id="test_user",
            customer_id="cus_mock_1",
            plan=SubscriptionPlan.PERSONAL
        )
        result = service.cancel_subscription("test_user")
        assert result is True

        sub = service.get_subscription("test_user")
        assert sub.cancel_at_period_end is True

    def test_cancel_free_subscription(self, service):
        """無料サブスクリプションのキャンセル"""
        service.create_subscription(
            user_id="test_user",
            customer_id="cus_mock_1",
            plan=SubscriptionPlan.FREE
        )
        result = service.cancel_subscription("test_user")
        assert result is False

    def test_upgrade_plan(self, service):
        """プランアップグレード"""
        service.create_subscription(
            user_id="test_user",
            customer_id="cus_mock_1",
            plan=SubscriptionPlan.PERSONAL
        )
        result = service.upgrade_plan("test_user", SubscriptionPlan.PRO)
        assert result is True

        sub = service.get_subscription("test_user")
        assert sub.plan == SubscriptionPlan.PRO

    def test_check_usage_limit_ok(self, service):
        """使用量チェック（OK）"""
        service.create_subscription(
            user_id="test_user",
            customer_id="cus_mock_1",
            plan=SubscriptionPlan.FREE
        )
        can_use, msg = service.check_usage_limit("test_user", "email_summary")
        assert can_use is True
        assert msg == "OK"

    def test_check_usage_limit_exceeded(self, service):
        """使用量チェック（制限超過）"""
        service.create_subscription(
            user_id="test_user",
            customer_id="cus_mock_1",
            plan=SubscriptionPlan.FREE
        )

        # 制限まで使用
        sub = service.get_subscription("test_user")
        sub.usage.email_summaries_used = 50

        can_use, msg = service.check_usage_limit("test_user", "email_summary")
        assert can_use is False
        assert "上限" in msg

    def test_record_usage(self, service):
        """使用量記録"""
        service.create_subscription(
            user_id="test_user",
            customer_id="cus_mock_1",
            plan=SubscriptionPlan.PERSONAL
        )
        result = service.record_usage("test_user", "email_summary")
        assert result is True

        sub = service.get_subscription("test_user")
        assert sub.usage.email_summaries_used == 1

    def test_get_usage_summary(self, service):
        """使用量サマリー取得"""
        service.create_subscription(
            user_id="test_user",
            customer_id="cus_mock_1",
            plan=SubscriptionPlan.PERSONAL
        )
        summary = service.get_usage_summary("test_user")

        assert summary["plan"] == "personal"
        assert summary["status"] == "active"
        assert "email_summaries" in summary
        assert "schedule_proposals" in summary

    def test_check_usage_creates_free_subscription(self, service):
        """存在しないユーザーへの使用量チェックで無料プラン作成"""
        can_use, msg = service.check_usage_limit("new_user", "email_summary")

        # 無料プランが自動作成される
        sub = service.get_subscription("new_user")
        assert sub is not None
        assert sub.plan == SubscriptionPlan.FREE


class TestBillingServiceWithStripe:
    """Stripe APIキーなしでのテスト"""

    def test_without_api_key(self):
        """APIキーなしでモックモード動作"""
        service = BillingService(stripe_api_key=None)
        customer_id = service.create_customer(
            user_id="test",
            email="test@example.com"
        )
        assert customer_id is not None
        assert "mock" in customer_id
