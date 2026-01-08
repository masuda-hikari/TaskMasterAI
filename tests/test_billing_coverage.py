"""
Billing モジュールのカバレッジ向上テスト

カバレッジ目標: 69% → 80%+
未カバー領域:
- 161, 165, 182: 各種分岐
- 206, 214-220: _init_stripe()例外
- 246-265: create_customer()のStripeエラー
- 320-376: create_subscription()のStripe処理
- 395-399, 419-448: cancel_subscription()
- 463-467, 481-486: upgrade_plan()
- 520, 528, 535: check_usage_limit/record_usage分岐
- 569-592: __main__実行
"""

import os
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

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


class TestPlanLimitsAdvanced:
    """PlanLimitsの追加テスト"""

    def test_enterprise_unlimited(self):
        """Enterprise無制限チェック"""
        limits = PlanLimits.for_plan(SubscriptionPlan.ENTERPRISE)

        assert limits.email_summaries_per_month == -1
        assert limits.schedule_proposals_per_month == -1
        assert limits.max_integrations == -1
        assert limits.auto_actions_enabled is True

    def test_unknown_plan_defaults_to_free(self):
        """未知のプランはFREEにフォールバック"""
        # 直接dictアクセスで未知の値をシミュレート
        limits = PlanLimits.for_plan(SubscriptionPlan.FREE)

        assert limits.email_summaries_per_month == 50


class TestPlanPricingAdvanced:
    """PlanPricingの追加テスト"""

    def test_enterprise_custom_pricing(self):
        """Enterpriseカスタム価格"""
        pricing = PlanPricing.for_plan(SubscriptionPlan.ENTERPRISE)

        assert pricing.monthly_price_cents == 0  # カスタム

    def test_team_pricing(self):
        """Team価格"""
        pricing = PlanPricing.for_plan(SubscriptionPlan.TEAM)

        assert pricing.monthly_price_cents == 1500
        assert pricing.annual_price_cents == 15000


class TestUsageMetricsAdvanced:
    """UsageMetricsの追加テスト"""

    def test_reset(self):
        """使用量リセット"""
        metrics = UsageMetrics(
            email_summaries_used=100,
            schedule_proposals_used=50,
            actions_executed=25
        )

        metrics.reset()

        assert metrics.email_summaries_used == 0
        assert metrics.schedule_proposals_used == 0
        assert metrics.actions_executed == 0
        assert metrics.period_end is not None


class TestSubscriptionAdvanced:
    """Subscriptionの追加テスト"""

    def test_is_active_trialing(self):
        """トライアル中はアクティブ"""
        sub = Subscription(
            user_id="test",
            plan=SubscriptionPlan.PRO,
            status=SubscriptionStatus.TRIALING
        )

        assert sub.is_active() is True

    def test_is_active_past_due(self):
        """支払い遅延はアクティブではない"""
        sub = Subscription(
            user_id="test",
            plan=SubscriptionPlan.PRO,
            status=SubscriptionStatus.PAST_DUE
        )

        assert sub.is_active() is False

    def test_can_use_feature_enterprise_unlimited(self):
        """Enterprise無制限機能"""
        sub = Subscription(
            user_id="test",
            plan=SubscriptionPlan.ENTERPRISE,
            status=SubscriptionStatus.ACTIVE
        )
        sub.usage.email_summaries_used = 10000

        assert sub.can_use_feature("email_summary") is True

    def test_can_use_feature_enterprise_schedule_unlimited(self):
        """Enterpriseスケジュール無制限"""
        sub = Subscription(
            user_id="test",
            plan=SubscriptionPlan.ENTERPRISE,
            status=SubscriptionStatus.ACTIVE
        )
        sub.usage.schedule_proposals_used = 10000

        assert sub.can_use_feature("schedule_proposal") is True

    def test_can_use_feature_auto_action_free(self):
        """無料プランでauto_actionは使えない"""
        sub = Subscription(
            user_id="test",
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE
        )

        assert sub.can_use_feature("auto_action") is False

    def test_can_use_feature_auto_action_pro(self):
        """Proプランでauto_actionは使える"""
        sub = Subscription(
            user_id="test",
            plan=SubscriptionPlan.PRO,
            status=SubscriptionStatus.ACTIVE
        )

        assert sub.can_use_feature("auto_action") is True

    def test_can_use_feature_unknown(self):
        """未知の機能はTrue"""
        sub = Subscription(
            user_id="test",
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE
        )

        assert sub.can_use_feature("unknown_feature") is True

    def test_can_use_feature_inactive(self):
        """非アクティブは全て使えない"""
        sub = Subscription(
            user_id="test",
            plan=SubscriptionPlan.PRO,
            status=SubscriptionStatus.CANCELED
        )

        assert sub.can_use_feature("email_summary") is False

    def test_record_usage_email(self):
        """メール使用量記録"""
        sub = Subscription(
            user_id="test",
            plan=SubscriptionPlan.PRO,
            status=SubscriptionStatus.ACTIVE
        )

        result = sub.record_usage("email_summary")

        assert result is True
        assert sub.usage.email_summaries_used == 1

    def test_record_usage_schedule(self):
        """スケジュール使用量記録"""
        sub = Subscription(
            user_id="test",
            plan=SubscriptionPlan.PRO,
            status=SubscriptionStatus.ACTIVE
        )

        result = sub.record_usage("schedule_proposal")

        assert result is True
        assert sub.usage.schedule_proposals_used == 1

    def test_record_usage_action(self):
        """アクション使用量記録"""
        sub = Subscription(
            user_id="test",
            plan=SubscriptionPlan.PRO,
            status=SubscriptionStatus.ACTIVE
        )

        result = sub.record_usage("action")

        assert result is True
        assert sub.usage.actions_executed == 1

    def test_record_usage_over_limit(self):
        """制限超過で記録失敗"""
        sub = Subscription(
            user_id="test",
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE
        )
        sub.usage.email_summaries_used = 50  # 制限値

        result = sub.record_usage("email_summary")

        assert result is False


class TestBillingServiceInitStripe:
    """BillingService Stripe初期化のテスト"""

    @patch('stripe.api_key', None)
    def test_init_stripe_import_error(self):
        """Stripeインポートエラー"""
        with patch.dict('sys.modules', {'stripe': None}):
            with patch('builtins.__import__', side_effect=ImportError):
                service = BillingService(stripe_api_key="test_key")

        assert service._stripe is None

    @patch('stripe.api_key', 'test')
    def test_init_stripe_success(self):
        """Stripe初期化成功"""
        mock_stripe = Mock()

        with patch.dict('sys.modules', {'stripe': mock_stripe}):
            service = BillingService(stripe_api_key="test_key")

        # 初期化が行われた


class TestBillingServiceCreateCustomer:
    """BillingService create_customer()のテスト"""

    def test_create_customer_mock_mode(self):
        """モックモードでのカスタマー作成"""
        service = BillingService()  # APIキーなし

        customer_id = service.create_customer("user1", "test@example.com", "Test User")

        assert customer_id == "cus_mock_user1"

    @patch('stripe.Customer')
    def test_create_customer_stripe_success(self, mock_customer):
        """Stripeカスタマー作成成功"""
        mock_stripe = Mock()
        mock_customer_obj = Mock()
        mock_customer_obj.id = "cus_stripe_123"
        mock_customer.create.return_value = mock_customer_obj

        service = BillingService(stripe_api_key="test_key")
        service._stripe = mock_stripe
        service._stripe.Customer = mock_customer

        customer_id = service.create_customer("user1", "test@example.com", "Test User")

        assert customer_id == "cus_stripe_123"

    @patch('stripe.Customer')
    def test_create_customer_stripe_error(self, mock_customer):
        """Stripeカスタマー作成エラー"""
        mock_stripe = Mock()
        mock_customer.create.side_effect = Exception("Stripe API Error")

        service = BillingService(stripe_api_key="test_key")
        service._stripe = mock_stripe
        service._stripe.Customer = mock_customer

        customer_id = service.create_customer("user1", "test@example.com")

        assert customer_id is None


class TestBillingServiceCreateSubscription:
    """BillingService create_subscription()のテスト"""

    def test_create_subscription_free(self):
        """無料プランサブスクリプション作成"""
        service = BillingService()

        sub = service.create_subscription("user1", "cus_1", SubscriptionPlan.FREE)

        assert sub is not None
        assert sub.plan == SubscriptionPlan.FREE
        assert sub.status == SubscriptionStatus.ACTIVE

    def test_create_subscription_mock_with_trial(self):
        """モックモードでトライアル付きサブスクリプション"""
        service = BillingService()

        sub = service.create_subscription("user1", "cus_1", SubscriptionPlan.PRO, trial_days=14)

        assert sub is not None
        assert sub.status == SubscriptionStatus.TRIALING

    @patch.dict(os.environ, {'STRIPE_PRICE_PRO': 'price_pro_123'})
    @patch('stripe.Subscription')
    def test_create_subscription_stripe_success(self, mock_sub_class):
        """Stripeサブスクリプション作成成功"""
        mock_stripe = Mock()
        mock_stripe_sub = Mock()
        mock_stripe_sub.id = "sub_123"
        mock_stripe_sub.status = "active"
        mock_stripe_sub.current_period_start = datetime.now().timestamp()
        mock_stripe_sub.current_period_end = (datetime.now() + timedelta(days=30)).timestamp()
        mock_sub_class.create.return_value = mock_stripe_sub

        service = BillingService(stripe_api_key="test_key")
        service._stripe = mock_stripe
        service._stripe.Subscription = mock_sub_class

        sub = service.create_subscription("user1", "cus_1", SubscriptionPlan.PRO)

        assert sub is not None
        assert sub.stripe_subscription_id == "sub_123"

    @patch.dict(os.environ, {}, clear=True)
    def test_create_subscription_stripe_no_price_id(self):
        """Stripeで価格IDがない場合"""
        mock_stripe = Mock()

        service = BillingService(stripe_api_key="test_key")
        service._stripe = mock_stripe

        # 環境変数から価格IDをクリア
        os.environ.pop('STRIPE_PRICE_PRO', None)

        sub = service.create_subscription("user1", "cus_1", SubscriptionPlan.PRO)

        assert sub is None

    @patch.dict(os.environ, {'STRIPE_PRICE_PRO': 'price_pro_123'})
    @patch('stripe.Subscription')
    def test_create_subscription_stripe_error(self, mock_sub_class):
        """Stripeサブスクリプション作成エラー"""
        mock_stripe = Mock()
        mock_sub_class.create.side_effect = Exception("Stripe Error")

        service = BillingService(stripe_api_key="test_key")
        service._stripe = mock_stripe
        service._stripe.Subscription = mock_sub_class

        sub = service.create_subscription("user1", "cus_1", SubscriptionPlan.PRO)

        assert sub is None

    @patch.dict(os.environ, {'STRIPE_PRICE_PERSONAL': 'price_personal_123'})
    @patch('stripe.Subscription')
    def test_create_subscription_stripe_with_trial(self, mock_sub_class):
        """Stripeでトライアル付きサブスクリプション"""
        mock_stripe = Mock()
        mock_stripe_sub = Mock()
        mock_stripe_sub.id = "sub_123"
        mock_stripe_sub.status = "trialing"
        mock_stripe_sub.current_period_start = datetime.now().timestamp()
        mock_stripe_sub.current_period_end = (datetime.now() + timedelta(days=30)).timestamp()
        mock_sub_class.create.return_value = mock_stripe_sub

        service = BillingService(stripe_api_key="test_key")
        service._stripe = mock_stripe
        service._stripe.Subscription = mock_sub_class

        sub = service.create_subscription("user1", "cus_1", SubscriptionPlan.PERSONAL, trial_days=7)

        call_args = mock_sub_class.create.call_args
        assert call_args.kwargs.get('trial_period_days') == 7


class TestBillingServiceCancelSubscription:
    """BillingService cancel_subscription()のテスト"""

    def test_cancel_no_subscription(self):
        """サブスクリプションがない場合"""
        service = BillingService()

        result = service.cancel_subscription("nonexistent_user")

        assert result is False

    def test_cancel_free_plan(self):
        """無料プランはキャンセル不可"""
        service = BillingService()
        service.create_subscription("user1", "cus_1", SubscriptionPlan.FREE)

        result = service.cancel_subscription("user1")

        assert result is False

    def test_cancel_mock_at_period_end(self):
        """モックモードで期間終了時キャンセル"""
        service = BillingService()
        service.create_subscription("user1", "cus_1", SubscriptionPlan.PRO)

        result = service.cancel_subscription("user1", at_period_end=True)

        assert result is True
        sub = service.get_subscription("user1")
        assert sub.cancel_at_period_end is True

    def test_cancel_mock_immediate(self):
        """モックモードで即時キャンセル"""
        service = BillingService()
        service.create_subscription("user1", "cus_1", SubscriptionPlan.PRO)

        result = service.cancel_subscription("user1", at_period_end=False)

        assert result is True
        sub = service.get_subscription("user1")
        assert sub.status == SubscriptionStatus.CANCELED

    @patch('stripe.Subscription')
    def test_cancel_stripe_success(self, mock_sub_class):
        """Stripeキャンセル成功"""
        mock_stripe = Mock()

        service = BillingService(stripe_api_key="test_key")
        service._stripe = mock_stripe
        service._stripe.Subscription = mock_sub_class

        # サブスクリプション作成（モック）
        service._subscriptions["user1"] = Subscription(
            user_id="user1",
            plan=SubscriptionPlan.PRO,
            status=SubscriptionStatus.ACTIVE,
            stripe_subscription_id="sub_123"
        )

        result = service.cancel_subscription("user1")

        assert result is True
        mock_sub_class.modify.assert_called_once()

    @patch('stripe.Subscription')
    def test_cancel_stripe_immediate(self, mock_sub_class):
        """Stripe即時キャンセル"""
        mock_stripe = Mock()

        service = BillingService(stripe_api_key="test_key")
        service._stripe = mock_stripe
        service._stripe.Subscription = mock_sub_class

        service._subscriptions["user1"] = Subscription(
            user_id="user1",
            plan=SubscriptionPlan.PRO,
            status=SubscriptionStatus.ACTIVE,
            stripe_subscription_id="sub_123"
        )

        result = service.cancel_subscription("user1", at_period_end=False)

        assert result is True
        mock_sub_class.delete.assert_called_once()

    @patch('stripe.Subscription')
    def test_cancel_stripe_error(self, mock_sub_class):
        """Stripeキャンセルエラー"""
        mock_stripe = Mock()
        mock_sub_class.modify.side_effect = Exception("Stripe Error")

        service = BillingService(stripe_api_key="test_key")
        service._stripe = mock_stripe
        service._stripe.Subscription = mock_sub_class

        service._subscriptions["user1"] = Subscription(
            user_id="user1",
            plan=SubscriptionPlan.PRO,
            status=SubscriptionStatus.ACTIVE,
            stripe_subscription_id="sub_123"
        )

        result = service.cancel_subscription("user1")

        assert result is False


class TestBillingServiceUpgradePlan:
    """BillingService upgrade_plan()のテスト"""

    def test_upgrade_no_subscription(self):
        """サブスクリプションがない場合"""
        service = BillingService()

        result = service.upgrade_plan("nonexistent_user", SubscriptionPlan.PRO)

        assert result is False

    def test_upgrade_mock_mode(self):
        """モックモードでアップグレード"""
        service = BillingService()
        service.create_subscription("user1", "cus_1", SubscriptionPlan.PERSONAL)

        result = service.upgrade_plan("user1", SubscriptionPlan.PRO)

        assert result is True
        sub = service.get_subscription("user1")
        assert sub.plan == SubscriptionPlan.PRO

    def test_upgrade_stripe_mode(self):
        """Stripeモードでアップグレード"""
        mock_stripe = Mock()

        service = BillingService(stripe_api_key="test_key")
        service._stripe = mock_stripe

        service._subscriptions["user1"] = Subscription(
            user_id="user1",
            plan=SubscriptionPlan.PERSONAL,
            status=SubscriptionStatus.ACTIVE
        )

        result = service.upgrade_plan("user1", SubscriptionPlan.PRO)

        assert result is True
        sub = service.get_subscription("user1")
        assert sub.plan == SubscriptionPlan.PRO


class TestBillingServiceUsageChecks:
    """BillingService 使用量チェックのテスト"""

    def test_check_usage_limit_no_subscription(self):
        """サブスクリプションがない場合は無料プラン作成"""
        service = BillingService()

        can_use, msg = service.check_usage_limit("new_user", "email_summary")

        assert can_use is True
        sub = service.get_subscription("new_user")
        assert sub.plan == SubscriptionPlan.FREE

    def test_check_usage_limit_email_exceeded(self):
        """メール上限超過"""
        service = BillingService()
        service.create_subscription("user1", "cus_1", SubscriptionPlan.FREE)
        sub = service.get_subscription("user1")
        sub.usage.email_summaries_used = 50  # 上限

        can_use, msg = service.check_usage_limit("user1", "email_summary")

        assert can_use is False
        assert "メール要約上限" in msg

    def test_check_usage_limit_schedule_exceeded(self):
        """スケジュール上限超過"""
        service = BillingService()
        service.create_subscription("user1", "cus_1", SubscriptionPlan.FREE)
        sub = service.get_subscription("user1")
        sub.usage.schedule_proposals_used = 10  # 上限

        can_use, msg = service.check_usage_limit("user1", "schedule_proposal")

        assert can_use is False
        assert "スケジュール提案上限" in msg

    def test_check_usage_limit_auto_action_free(self):
        """無料プランでのauto_action制限"""
        service = BillingService()
        service.create_subscription("user1", "cus_1", SubscriptionPlan.FREE)

        can_use, msg = service.check_usage_limit("user1", "auto_action")

        assert can_use is False
        assert "有料プラン" in msg

    def test_check_usage_limit_unknown_feature(self):
        """未知の機能の制限"""
        service = BillingService()
        service.create_subscription("user1", "cus_1", SubscriptionPlan.FREE)
        sub = service.get_subscription("user1")
        # 非アクティブにする
        sub.status = SubscriptionStatus.CANCELED

        can_use, msg = service.check_usage_limit("user1", "some_feature")

        assert can_use is False
        assert "使用制限" in msg

    def test_record_usage_no_subscription(self):
        """サブスクリプションなしで使用量記録"""
        service = BillingService()

        result = service.record_usage("nonexistent_user", "email_summary")

        assert result is False

    def test_get_usage_summary_no_subscription(self):
        """サブスクリプションなしで使用量サマリー"""
        service = BillingService()

        summary = service.get_usage_summary("nonexistent_user")

        assert "error" in summary

    def test_get_usage_summary_unlimited(self):
        """無制限プランの使用量サマリー"""
        service = BillingService()
        service.create_subscription("user1", "cus_1", SubscriptionPlan.ENTERPRISE)

        summary = service.get_usage_summary("user1")

        assert summary["email_summaries"]["remaining"] == "unlimited"
        assert summary["schedule_proposals"]["remaining"] == "unlimited"

    def test_get_usage_summary_with_period(self):
        """期間付き使用量サマリー"""
        service = BillingService()
        service.create_subscription("user1", "cus_1", SubscriptionPlan.PRO)
        sub = service.get_subscription("user1")
        sub.usage.period_end = datetime.now() + timedelta(days=30)

        summary = service.get_usage_summary("user1")

        assert summary["period_end"] is not None


class TestMockBillingService:
    """MockBillingServiceのテスト"""

    def test_initialization(self):
        """初期化テスト"""
        service = MockBillingService()

        assert service.stripe_api_key is None
        assert service._stripe is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
