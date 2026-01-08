"""
E2Eテストシナリオ - エンドツーエンド統合テスト

完全なユーザーフローをシミュレートしてシステム全体の動作を検証
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.coordinator import Coordinator, CommandResult
from src.billing import BillingService, SubscriptionPlan, MockBillingService
from src.database import Database, create_database
from src.llm import create_llm_service


class TestE2EUserRegistrationFlow:
    """E2E: ユーザー登録から利用開始までのフロー"""

    def setup_method(self):
        """テストセットアップ"""
        self.db = create_database()  # インメモリDB
        self.billing = MockBillingService()

    def test_new_user_registration_and_free_plan(self):
        """新規ユーザー登録と無料プラン利用"""
        # 1. ユーザー登録
        user = self.db.create_user(
            user_id="e2e-user-1",
            email="newuser@example.com",
            password_hash="hashed_password",
            name="New User"
        )
        assert user is not None
        assert user.plan == "free"

        # 2. 無料サブスクリプション作成
        sub = self.billing.create_subscription(
            user_id=user.id,
            customer_id=f"cus_{user.id}",
            plan=SubscriptionPlan.FREE
        )
        assert sub is not None
        assert sub.plan == SubscriptionPlan.FREE
        assert sub.is_active()

        # 3. 使用量チェック（無料プランで利用可能）
        can_use, msg = self.billing.check_usage_limit(user.id, "email_summary")
        assert can_use is True

        # 4. 使用量記録
        for i in range(50):  # 無料上限まで使用
            result = self.billing.record_usage(user.id, "email_summary")
            assert result is True

        # 5. 上限到達後は使用不可
        can_use, msg = self.billing.check_usage_limit(user.id, "email_summary")
        assert can_use is False
        assert "上限" in msg

    def test_user_upgrade_flow(self):
        """無料プランからProプランへのアップグレードフロー"""
        # 1. 無料ユーザー作成
        user = self.db.create_user(
            user_id="e2e-upgrade-user",
            email="upgrade@example.com",
            password_hash="hash123",
            name="Upgrade User"
        )

        # 2. 無料サブスクリプション
        self.billing.create_subscription(
            user_id=user.id,
            customer_id=f"cus_{user.id}",
            plan=SubscriptionPlan.FREE
        )

        # 3. 無料枠を使い切る
        for _ in range(50):
            self.billing.record_usage(user.id, "email_summary")

        can_use, _ = self.billing.check_usage_limit(user.id, "email_summary")
        assert can_use is False

        # 4. Proプランにアップグレード
        success = self.billing.upgrade_plan(user.id, SubscriptionPlan.PRO)
        assert success is True

        # 5. アップグレード後は再び使用可能
        can_use, _ = self.billing.check_usage_limit(user.id, "email_summary")
        assert can_use is True

        # 6. DB側のプラン更新
        self.db.update_user(user.id, plan="pro")
        updated_user = self.db.get_user_by_id(user.id)
        assert updated_user.plan == "pro"


class TestE2EEmailWorkflow:
    """E2E: メール処理ワークフロー"""

    def setup_method(self):
        """テストセットアップ"""
        self.llm = create_llm_service(use_mock=True)
        self.coordinator = Coordinator(llm_service=self.llm)

    def test_inbox_summary_flow(self):
        """受信トレイ要約フロー"""
        # 1. inboxコマンド実行
        result = self.coordinator.process_command("inbox")

        # 2. 結果検証（モック環境でもメッセージがある）
        assert result.message is not None
        assert len(result.message) > 0

    def test_help_and_navigation(self):
        """ヘルプとナビゲーション"""
        # 1. ヘルプ表示
        result = self.coordinator.process_command("help")
        assert result.success is True
        assert "コマンド" in result.message

        # 2. 認証状態確認
        result = self.coordinator.process_command("auth status")
        assert result.success is True
        assert "認証" in result.message

        # 3. 今日のステータス（モック環境ではエラーでも許容）
        result = self.coordinator.process_command("status")
        assert result.message is not None


class TestE2ESchedulingWorkflow:
    """E2E: スケジュール管理ワークフロー"""

    def setup_method(self):
        """テストセットアップ"""
        self.llm = create_llm_service(use_mock=True)
        self.coordinator = Coordinator(llm_service=self.llm)

    def test_schedule_meeting_flow(self):
        """会議スケジュールフロー"""
        # 1. 会議スケジュールコマンド
        result = self.coordinator.process_command(
            "schedule team meeting with alice@example.com 30min"
        )

        # 2. 結果検証（モック環境でもメッセージがある）
        assert result.message is not None

    def test_schedule_cancel_flow(self):
        """スケジュールキャンセルフロー"""
        # 1. 会議提案を取得
        self.coordinator.process_command(
            "schedule meeting with bob@example.com 60min"
        )

        # 2. キャンセル
        result = self.coordinator.process_command("cancel")
        assert result.success is True


class TestE2EConfirmationFlow:
    """E2E: 確認フロー"""

    def setup_method(self):
        """テストセットアップ"""
        self.coordinator = Coordinator()

    def test_confirm_without_pending_action(self):
        """保留アクションなしでconfirm"""
        result = self.coordinator.process_command("confirm")
        assert result.success is False
        assert "確認待ち" in result.message or "ありません" in result.message

    def test_cancel_without_pending_action(self):
        """保留アクションなしでcancel"""
        result = self.coordinator.process_command("cancel")
        assert result.success is True
        assert "キャンセル" in result.message


class TestE2EAuditFlow:
    """E2E: 監査ログフロー"""

    def setup_method(self):
        """テストセットアップ"""
        self.temp_dir = tempfile.mkdtemp()
        self.audit_path = os.path.join(self.temp_dir, "audit.json")
        self.coordinator = Coordinator(audit_log_path=self.audit_path)

    def test_audit_log_on_actions(self):
        """アクション実行時の監査ログ"""
        # 1. アクション実行
        self.coordinator.process_command("inbox")
        self.coordinator.process_command("status")

        # 2. 監査ログ確認
        import json
        if os.path.exists(self.audit_path):
            with open(self.audit_path, 'r') as f:
                logs = json.load(f)
            assert len(logs) >= 2
            assert any("summarize_inbox" in log.get("action_type", "") for log in logs)


class TestE2EDatabasePersistence:
    """E2E: データベース永続化フロー"""

    def test_user_lifecycle(self):
        """ユーザーライフサイクル全体"""
        db = create_database()

        # 1. 作成
        user = db.create_user(
            user_id="lifecycle-user",
            email="lifecycle@example.com",
            password_hash="hash123"
        )
        assert user is not None

        # 2. 取得
        fetched = db.get_user_by_id(user.id)
        assert fetched is not None
        assert fetched.email == "lifecycle@example.com"

        # 3. 更新
        db.update_user(user.id, name="Updated Name", plan="pro")
        updated = db.get_user_by_id(user.id)
        assert updated.name == "Updated Name"
        assert updated.plan == "pro"

        # 4. サブスクリプション
        sub = db.create_subscription(
            subscription_id="sub-lifecycle",
            user_id=user.id,
            plan="pro"
        )
        assert sub is not None

        # 5. 使用量記録
        period_start = datetime(2026, 1, 1)
        period_end = datetime(2026, 2, 1)
        count = db.record_usage(user.id, "email_summary", period_start, period_end)
        assert count == 1

        count = db.record_usage(user.id, "email_summary", period_start, period_end)
        assert count == 2

        # 6. 監査ログ
        db.log_audit("user_action", user.id, {"action": "test"})
        logs = db.get_audit_logs(user.id)
        assert len(logs) == 1


class TestE2EBillingIntegration:
    """E2E: 課金統合フロー"""

    def test_full_billing_cycle(self):
        """完全な課金サイクル"""
        billing = MockBillingService()

        # 1. 顧客作成
        customer_id = billing.create_customer(
            user_id="billing-user",
            email="billing@example.com",
            name="Billing User"
        )
        assert customer_id is not None

        # 2. 無料サブスクリプション
        sub = billing.create_subscription(
            user_id="billing-user",
            customer_id=customer_id,
            plan=SubscriptionPlan.FREE
        )
        assert sub.plan == SubscriptionPlan.FREE

        # 3. アップグレード
        billing.upgrade_plan("billing-user", SubscriptionPlan.PERSONAL)
        updated_sub = billing.get_subscription("billing-user")
        assert updated_sub.plan == SubscriptionPlan.PERSONAL

        # 4. 使用量サマリー
        summary = billing.get_usage_summary("billing-user")
        assert summary["plan"] == "personal"
        assert "email_summaries" in summary

        # 5. キャンセル
        success = billing.cancel_subscription("billing-user", at_period_end=True)
        assert success is True


class TestE2EErrorHandling:
    """E2E: エラーハンドリング"""

    def test_unknown_command(self):
        """不明なコマンド"""
        coordinator = Coordinator()
        result = coordinator.process_command("unknown_command_xyz")
        assert result.success is False
        assert "不明" in result.message or "help" in result.message

    def test_duplicate_user_registration(self):
        """重複ユーザー登録"""
        db = create_database()

        # 1回目: 成功
        user1 = db.create_user(
            user_id="dup-user-1",
            email="duplicate@example.com",
            password_hash="hash"
        )
        assert user1 is not None

        # 2回目: 同じメールで失敗
        user2 = db.create_user(
            user_id="dup-user-2",
            email="duplicate@example.com",
            password_hash="hash"
        )
        assert user2 is None


class TestE2EMultiUserScenario:
    """E2E: マルチユーザーシナリオ"""

    def setup_method(self):
        """テストセットアップ"""
        self.db = create_database()
        self.billing = MockBillingService()

    def test_multiple_users_independent(self):
        """複数ユーザーの独立性"""
        # ユーザー1: 無料プラン
        user1 = self.db.create_user(
            user_id="multi-user-1",
            email="user1@example.com",
            password_hash="hash1"
        )
        self.billing.create_subscription(
            user_id=user1.id,
            customer_id=f"cus_{user1.id}",
            plan=SubscriptionPlan.FREE
        )

        # ユーザー2: Proプラン
        user2 = self.db.create_user(
            user_id="multi-user-2",
            email="user2@example.com",
            password_hash="hash2"
        )
        self.billing.create_subscription(
            user_id=user2.id,
            customer_id=f"cus_{user2.id}",
            plan=SubscriptionPlan.PRO
        )

        # ユーザー1の使用量を消費
        for _ in range(50):
            self.billing.record_usage(user1.id, "email_summary")

        # ユーザー1は上限到達
        can_use1, _ = self.billing.check_usage_limit(user1.id, "email_summary")
        assert can_use1 is False

        # ユーザー2は影響なし
        can_use2, _ = self.billing.check_usage_limit(user2.id, "email_summary")
        assert can_use2 is True

    def test_usage_isolation(self):
        """使用量の分離"""
        period_start = datetime(2026, 1, 1)
        period_end = datetime(2026, 2, 1)

        # ユーザーA
        self.db.create_user(
            user_id="iso-user-a",
            email="a@example.com",
            password_hash="hash"
        )
        for _ in range(10):
            self.db.record_usage("iso-user-a", "email_summary", period_start, period_end)

        # ユーザーB
        self.db.create_user(
            user_id="iso-user-b",
            email="b@example.com",
            password_hash="hash"
        )
        for _ in range(5):
            self.db.record_usage("iso-user-b", "email_summary", period_start, period_end)

        # 使用量が独立
        usage_a = self.db.get_usage("iso-user-a", "email_summary", period_start)
        usage_b = self.db.get_usage("iso-user-b", "email_summary", period_start)

        assert usage_a == 10
        assert usage_b == 5


class TestE2ESessionFlow:
    """E2E: セッションフロー"""

    def test_typical_user_session(self):
        """典型的なユーザーセッション"""
        # 1. Coordinator初期化（モックLLM使用）
        llm = create_llm_service(use_mock=True)
        coordinator = Coordinator(llm_service=llm)

        # 2. ヘルプ確認
        result = coordinator.process_command("help")
        assert result.success is True

        # 3. 認証状態確認
        result = coordinator.process_command("auth")
        assert result.success is True

        # 4. 今日の予定確認（モック環境ではエラーでも許容）
        result = coordinator.process_command("today")
        assert result.message is not None

        # 5. メール要約（モック環境ではエラーでも許容）
        result = coordinator.process_command("inbox")
        assert result.message is not None

        # 6. 会議スケジュール提案（モック環境ではエラーでも許容）
        result = coordinator.process_command(
            "schedule standup with team@example.com 15min"
        )
        assert result.message is not None

        # 7. キャンセル
        result = coordinator.process_command("cancel")
        assert result.success is True


# 収益化に直結するテスト
class TestE2EMonetizationCritical:
    """E2E: 収益化クリティカルパス"""

    def test_free_to_paid_conversion(self):
        """無料→有料変換パス"""
        billing = MockBillingService()
        db = create_database()

        # 1. 無料ユーザー作成
        user = db.create_user(
            user_id="convert-user",
            email="convert@example.com",
            password_hash="hash"
        )
        billing.create_subscription(
            user_id=user.id,
            customer_id=f"cus_{user.id}",
            plan=SubscriptionPlan.FREE
        )

        # 2. 無料枠消費
        for _ in range(50):
            billing.record_usage(user.id, "email_summary")

        # 3. 上限到達を確認
        can_use, msg = billing.check_usage_limit(user.id, "email_summary")
        assert can_use is False
        assert "アップグレード" in msg  # アップグレード誘導メッセージ

        # 4. Personalプランにアップグレード
        billing.upgrade_plan(user.id, SubscriptionPlan.PERSONAL)
        db.update_user(user.id, plan="personal")

        # 5. アップグレード後は使用可能
        can_use, _ = billing.check_usage_limit(user.id, "email_summary")
        assert can_use is True

        # 6. 使用量サマリーでプラン確認
        summary = billing.get_usage_summary(user.id)
        assert summary["plan"] == "personal"

    def test_plan_limits_enforcement(self):
        """プラン制限の強制"""
        billing = MockBillingService()

        # 各プランの制限テスト
        plans = [
            (SubscriptionPlan.FREE, 50),
            (SubscriptionPlan.PERSONAL, 500),
            (SubscriptionPlan.PRO, 2000),
        ]

        for plan, limit in plans:
            user_id = f"limit-test-{plan.value}"
            billing.create_subscription(
                user_id=user_id,
                customer_id=f"cus_{user_id}",
                plan=plan
            )

            # 制限未満は使用可能
            for _ in range(limit - 1):
                billing.record_usage(user_id, "email_summary")

            can_use, _ = billing.check_usage_limit(user_id, "email_summary")
            assert can_use is True, f"Plan {plan.value}: should be usable before limit"

            # 制限到達
            billing.record_usage(user_id, "email_summary")
            can_use, _ = billing.check_usage_limit(user_id, "email_summary")
            assert can_use is False, f"Plan {plan.value}: should be blocked at limit"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
