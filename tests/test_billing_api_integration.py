"""
Billing + API統合テスト

課金システムとWeb APIの統合動作を検証
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from src.billing import (
    BillingService,
    MockBillingService,
    SubscriptionPlan,
    SubscriptionStatus,
    Subscription,
    PlanLimits,
    PlanPricing,
)
from src.database import Database, create_database


class TestBillingAPIIntegration:
    """Billing + API統合テスト"""

    def setup_method(self):
        """テストセットアップ"""
        self.billing = MockBillingService()
        self.db = create_database()

    def test_user_registration_with_free_plan(self):
        """ユーザー登録時の無料プラン付与"""
        # DBユーザー作成
        user = self.db.create_user(
            user_id="api-user-1",
            email="api@example.com",
            password_hash="hash123"
        )

        # Billing側でサブスクリプション作成
        customer_id = self.billing.create_customer(
            user_id=user.id,
            email=user.email
        )
        sub = self.billing.create_subscription(
            user_id=user.id,
            customer_id=customer_id,
            plan=SubscriptionPlan.FREE
        )

        assert sub.plan == SubscriptionPlan.FREE
        assert sub.is_active()

        # 使用量チェック
        can_use, _ = self.billing.check_usage_limit(user.id, "email_summary")
        assert can_use is True

    def test_api_usage_tracking(self):
        """API使用量の追跡"""
        user_id = "usage-track-user"

        # サブスクリプション作成
        self.billing.create_subscription(
            user_id=user_id,
            customer_id=f"cus_{user_id}",
            plan=SubscriptionPlan.PERSONAL
        )

        # 使用量記録
        for i in range(10):
            self.billing.record_usage(user_id, "email_summary")
            self.billing.record_usage(user_id, "schedule_proposal")

        # サマリー確認
        summary = self.billing.get_usage_summary(user_id)
        assert summary["email_summaries"]["used"] == 10
        assert summary["schedule_proposals"]["used"] == 10

    def test_usage_limit_enforcement_across_api_calls(self):
        """API呼び出し間での使用量制限の強制"""
        user_id = "limit-enforce-user"

        # 無料プラン（50件/月）
        self.billing.create_subscription(
            user_id=user_id,
            customer_id=f"cus_{user_id}",
            plan=SubscriptionPlan.FREE
        )

        # 50件まで使用可能
        for i in range(50):
            can_use, _ = self.billing.check_usage_limit(user_id, "email_summary")
            assert can_use is True, f"Iteration {i}: should be usable"
            self.billing.record_usage(user_id, "email_summary")

        # 51件目は不可
        can_use, msg = self.billing.check_usage_limit(user_id, "email_summary")
        assert can_use is False
        assert "上限" in msg

    def test_subscription_upgrade_restores_access(self):
        """サブスクリプションアップグレードでアクセス復活"""
        user_id = "upgrade-restore-user"

        # 無料プランで上限到達
        self.billing.create_subscription(
            user_id=user_id,
            customer_id=f"cus_{user_id}",
            plan=SubscriptionPlan.FREE
        )
        for _ in range(50):
            self.billing.record_usage(user_id, "email_summary")

        can_use, _ = self.billing.check_usage_limit(user_id, "email_summary")
        assert can_use is False

        # アップグレード
        self.billing.upgrade_plan(user_id, SubscriptionPlan.PERSONAL)

        # アクセス復活
        can_use, _ = self.billing.check_usage_limit(user_id, "email_summary")
        assert can_use is True


class TestBillingDatabaseSync:
    """Billing + Database同期テスト"""

    def setup_method(self):
        """テストセットアップ"""
        self.billing = MockBillingService()
        self.db = create_database()

    def test_user_plan_sync(self):
        """ユーザープランの同期"""
        # DBユーザー作成
        user = self.db.create_user(
            user_id="sync-user",
            email="sync@example.com",
            password_hash="hash"
        )
        assert user.plan == "free"

        # Billing側でアップグレード
        self.billing.create_subscription(
            user_id=user.id,
            customer_id=f"cus_{user.id}",
            plan=SubscriptionPlan.FREE
        )
        self.billing.upgrade_plan(user.id, SubscriptionPlan.PRO)

        # DB側も更新
        self.db.update_user(user.id, plan="pro")

        # 両方で確認
        updated_user = self.db.get_user_by_id(user.id)
        billing_sub = self.billing.get_subscription(user.id)

        assert updated_user.plan == "pro"
        assert billing_sub.plan == SubscriptionPlan.PRO

    def test_usage_persistence(self):
        """使用量の永続化"""
        user_id = "persist-usage-user"
        period_start = datetime(2026, 1, 1)
        period_end = datetime(2026, 2, 1)

        # DB使用量記録
        for _ in range(5):
            self.db.record_usage(user_id, "email_summary", period_start, period_end)

        # 使用量取得
        usage = self.db.get_usage(user_id, "email_summary", period_start)
        assert usage == 5

    def test_subscription_lifecycle_sync(self):
        """サブスクリプションライフサイクル同期"""
        user_id = "lifecycle-sync-user"

        # DBユーザー作成
        self.db.create_user(
            user_id=user_id,
            email="lifecycle@example.com",
            password_hash="hash"
        )

        # Billingサブスクリプション作成
        sub = self.billing.create_subscription(
            user_id=user_id,
            customer_id=f"cus_{user_id}",
            plan=SubscriptionPlan.PERSONAL
        )

        # DBサブスクリプション作成
        db_sub = self.db.create_subscription(
            subscription_id=f"sub_{user_id}",
            user_id=user_id,
            plan="personal"
        )

        # 両方で確認
        assert sub.plan == SubscriptionPlan.PERSONAL
        assert db_sub.plan == "personal"


class TestAPIEndpointBillingIntegration:
    """APIエンドポイントとBillingの統合"""

    def test_email_summarize_with_billing_check(self):
        """メール要約とBillingチェック"""
        billing = MockBillingService()
        user_id = "endpoint-user"

        # サブスクリプション作成
        billing.create_subscription(
            user_id=user_id,
            customer_id=f"cus_{user_id}",
            plan=SubscriptionPlan.FREE
        )

        # API呼び出しのシミュレート
        def simulate_api_call():
            can_use, msg = billing.check_usage_limit(user_id, "email_summary")
            if not can_use:
                return {"error": msg, "status": 402}
            billing.record_usage(user_id, "email_summary")
            return {"data": "summary", "status": 200}

        # 50回は成功
        for i in range(50):
            result = simulate_api_call()
            assert result["status"] == 200, f"Call {i} should succeed"

        # 51回目は失敗（402 Payment Required）
        result = simulate_api_call()
        assert result["status"] == 402

    def test_schedule_propose_with_billing_check(self):
        """スケジュール提案とBillingチェック"""
        billing = MockBillingService()
        user_id = "schedule-endpoint-user"

        billing.create_subscription(
            user_id=user_id,
            customer_id=f"cus_{user_id}",
            plan=SubscriptionPlan.FREE  # 10件/月
        )

        def simulate_api_call():
            can_use, msg = billing.check_usage_limit(user_id, "schedule_proposal")
            if not can_use:
                return {"error": msg, "status": 402}
            billing.record_usage(user_id, "schedule_proposal")
            return {"data": "proposal", "status": 200}

        # 10回は成功（FREE planの制限）
        for i in range(10):
            result = simulate_api_call()
            assert result["status"] == 200, f"Call {i} should succeed"

        # 11回目は失敗
        result = simulate_api_call()
        assert result["status"] == 402


class TestPlanFeatures:
    """プラン機能テスト"""

    def test_auto_action_feature_per_plan(self):
        """プランごとの自動アクション機能"""
        billing = MockBillingService()

        # FREE: 自動アクション不可
        billing.create_subscription(
            user_id="free-auto",
            customer_id="cus_free",
            plan=SubscriptionPlan.FREE
        )
        can_use, _ = billing.check_usage_limit("free-auto", "auto_action")
        assert can_use is False

        # PERSONAL: 自動アクション可能
        billing.create_subscription(
            user_id="personal-auto",
            customer_id="cus_personal",
            plan=SubscriptionPlan.PERSONAL
        )
        can_use, _ = billing.check_usage_limit("personal-auto", "auto_action")
        assert can_use is True

        # PRO: 自動アクション可能
        billing.create_subscription(
            user_id="pro-auto",
            customer_id="cus_pro",
            plan=SubscriptionPlan.PRO
        )
        can_use, _ = billing.check_usage_limit("pro-auto", "auto_action")
        assert can_use is True

    def test_plan_limits_accuracy(self):
        """プラン制限の正確性"""
        limits_free = PlanLimits.for_plan(SubscriptionPlan.FREE)
        limits_personal = PlanLimits.for_plan(SubscriptionPlan.PERSONAL)
        limits_pro = PlanLimits.for_plan(SubscriptionPlan.PRO)
        limits_enterprise = PlanLimits.for_plan(SubscriptionPlan.ENTERPRISE)

        # FREE
        assert limits_free.email_summaries_per_month == 50
        assert limits_free.auto_actions_enabled is False

        # PERSONAL
        assert limits_personal.email_summaries_per_month == 500
        assert limits_personal.auto_actions_enabled is True

        # PRO
        assert limits_pro.email_summaries_per_month == 2000
        assert limits_pro.priority_support is True

        # ENTERPRISE
        assert limits_enterprise.email_summaries_per_month == -1  # 無制限

    def test_plan_pricing_accuracy(self):
        """プラン価格の正確性"""
        pricing_free = PlanPricing.for_plan(SubscriptionPlan.FREE)
        pricing_personal = PlanPricing.for_plan(SubscriptionPlan.PERSONAL)
        pricing_pro = PlanPricing.for_plan(SubscriptionPlan.PRO)

        # FREE
        assert pricing_free.monthly_price_cents == 0

        # PERSONAL: $10/月
        assert pricing_personal.monthly_price_cents == 1000

        # PRO: $25/月
        assert pricing_pro.monthly_price_cents == 2500


class TestSubscriptionCancellation:
    """サブスクリプションキャンセルテスト"""

    def test_cancel_at_period_end(self):
        """期間終了時キャンセル"""
        billing = MockBillingService()

        billing.create_subscription(
            user_id="cancel-end-user",
            customer_id="cus_cancel",
            plan=SubscriptionPlan.PERSONAL
        )

        # キャンセル（期間終了時）
        success = billing.cancel_subscription("cancel-end-user", at_period_end=True)
        assert success is True

        sub = billing.get_subscription("cancel-end-user")
        assert sub.cancel_at_period_end is True
        assert sub.status != SubscriptionStatus.CANCELED  # まだアクティブ

    def test_cancel_immediately(self):
        """即時キャンセル"""
        billing = MockBillingService()

        billing.create_subscription(
            user_id="cancel-now-user",
            customer_id="cus_cancel",
            plan=SubscriptionPlan.PRO
        )

        # 即時キャンセル
        success = billing.cancel_subscription("cancel-now-user", at_period_end=False)
        assert success is True

        sub = billing.get_subscription("cancel-now-user")
        assert sub.status == SubscriptionStatus.CANCELED

    def test_cancel_free_plan_fails(self):
        """無料プランのキャンセルは失敗"""
        billing = MockBillingService()

        billing.create_subscription(
            user_id="cancel-free-user",
            customer_id="cus_free",
            plan=SubscriptionPlan.FREE
        )

        success = billing.cancel_subscription("cancel-free-user")
        assert success is False


class TestUsageSummaryAPI:
    """使用量サマリーAPIテスト"""

    def test_usage_summary_structure(self):
        """使用量サマリーの構造"""
        billing = MockBillingService()

        billing.create_subscription(
            user_id="summary-user",
            customer_id="cus_summary",
            plan=SubscriptionPlan.PERSONAL
        )

        # 使用量記録
        for _ in range(3):
            billing.record_usage("summary-user", "email_summary")
        for _ in range(2):
            billing.record_usage("summary-user", "schedule_proposal")

        summary = billing.get_usage_summary("summary-user")

        # 必須フィールド確認
        assert "plan" in summary
        assert "status" in summary
        assert "email_summaries" in summary
        assert "schedule_proposals" in summary
        assert "actions_executed" in summary

        # 値の確認
        assert summary["plan"] == "personal"
        assert summary["email_summaries"]["used"] == 3
        assert summary["schedule_proposals"]["used"] == 2

    def test_usage_summary_remaining_calculation(self):
        """残り使用量の計算"""
        billing = MockBillingService()

        billing.create_subscription(
            user_id="remaining-user",
            customer_id="cus_remaining",
            plan=SubscriptionPlan.PERSONAL  # 500件/月
        )

        for _ in range(100):
            billing.record_usage("remaining-user", "email_summary")

        summary = billing.get_usage_summary("remaining-user")

        assert summary["email_summaries"]["used"] == 100
        assert summary["email_summaries"]["limit"] == 500
        assert summary["email_summaries"]["remaining"] == 400


class TestMultiTenantBilling:
    """マルチテナントBillingテスト"""

    def test_isolated_usage_per_tenant(self):
        """テナントごとの使用量分離"""
        billing = MockBillingService()

        # 3テナント作成
        tenants = ["tenant-a", "tenant-b", "tenant-c"]
        for tenant in tenants:
            billing.create_subscription(
                user_id=tenant,
                customer_id=f"cus_{tenant}",
                plan=SubscriptionPlan.PERSONAL
            )

        # 各テナントで異なる使用量
        for i in range(10):
            billing.record_usage("tenant-a", "email_summary")
        for i in range(20):
            billing.record_usage("tenant-b", "email_summary")
        for i in range(5):
            billing.record_usage("tenant-c", "email_summary")

        # 使用量が分離されている
        summary_a = billing.get_usage_summary("tenant-a")
        summary_b = billing.get_usage_summary("tenant-b")
        summary_c = billing.get_usage_summary("tenant-c")

        assert summary_a["email_summaries"]["used"] == 10
        assert summary_b["email_summaries"]["used"] == 20
        assert summary_c["email_summaries"]["used"] == 5

    def test_different_plans_per_tenant(self):
        """テナントごとの異なるプラン"""
        billing = MockBillingService()

        billing.create_subscription("t-free", "cus_1", SubscriptionPlan.FREE)
        billing.create_subscription("t-personal", "cus_2", SubscriptionPlan.PERSONAL)
        billing.create_subscription("t-pro", "cus_3", SubscriptionPlan.PRO)

        sub_free = billing.get_subscription("t-free")
        sub_personal = billing.get_subscription("t-personal")
        sub_pro = billing.get_subscription("t-pro")

        assert sub_free.plan == SubscriptionPlan.FREE
        assert sub_personal.plan == SubscriptionPlan.PERSONAL
        assert sub_pro.plan == SubscriptionPlan.PRO


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
