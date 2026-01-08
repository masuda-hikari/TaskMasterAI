"""
Database Module テスト

SQLite永続化層のテスト
"""

import pytest
from datetime import datetime, timedelta
import tempfile
import os

from src.database import (
    Database,
    DBUser,
    DBSubscription,
    DBUsageRecord,
    create_database
)


class TestDatabaseInitialization:
    """データベース初期化テスト"""

    def test_memory_database(self):
        """インメモリデータベースの作成"""
        db = Database()
        assert db.db_path == ":memory:"

    def test_file_database(self, tmp_path):
        """ファイルデータベースの作成"""
        db_path = str(tmp_path / "test.db")
        db = Database(db_path)
        assert db.db_path == db_path
        assert os.path.exists(db_path)

    def test_create_database_helper(self):
        """create_database関数のテスト"""
        db = create_database()
        assert db is not None
        assert db.db_path == ":memory:"


class TestUserOperations:
    """ユーザー操作テスト"""

    def test_create_user(self):
        """ユーザー作成"""
        db = Database()
        user = db.create_user(
            user_id="user-123",
            email="test@example.com",
            password_hash="hashed_password",
            name="Test User"
        )

        assert user is not None
        assert user.id == "user-123"
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.plan == "free"

    def test_create_duplicate_user(self):
        """重複ユーザー作成の防止"""
        db = Database()
        db.create_user(
            user_id="user-1",
            email="test@example.com",
            password_hash="hash1"
        )

        # 同じメールアドレスで再作成
        duplicate = db.create_user(
            user_id="user-2",
            email="test@example.com",
            password_hash="hash2"
        )

        assert duplicate is None

    def test_get_user_by_id(self):
        """IDでユーザー取得"""
        db = Database()
        db.create_user(
            user_id="user-456",
            email="user456@example.com",
            password_hash="hash"
        )

        user = db.get_user_by_id("user-456")
        assert user is not None
        assert user.email == "user456@example.com"

    def test_get_user_by_email(self):
        """メールアドレスでユーザー取得"""
        db = Database()
        db.create_user(
            user_id="user-789",
            email="findme@example.com",
            password_hash="hash"
        )

        user = db.get_user_by_email("findme@example.com")
        assert user is not None
        assert user.id == "user-789"

    def test_get_nonexistent_user(self):
        """存在しないユーザーの取得"""
        db = Database()
        user = db.get_user_by_id("nonexistent")
        assert user is None

    def test_update_user(self):
        """ユーザー更新"""
        db = Database()
        db.create_user(
            user_id="update-user",
            email="update@example.com",
            password_hash="hash",
            name="Original Name"
        )

        result = db.update_user(
            user_id="update-user",
            name="Updated Name",
            plan="personal"
        )

        assert result is True

        user = db.get_user_by_id("update-user")
        assert user.name == "Updated Name"
        assert user.plan == "personal"

    def test_update_user_stripe_id(self):
        """StripeカスタマーID更新"""
        db = Database()
        db.create_user(
            user_id="stripe-user",
            email="stripe@example.com",
            password_hash="hash"
        )

        db.update_user(
            user_id="stripe-user",
            stripe_customer_id="cus_12345"
        )

        user = db.get_user_by_id("stripe-user")
        assert user.stripe_customer_id == "cus_12345"

    def test_update_nonexistent_user(self):
        """存在しないユーザーの更新"""
        db = Database()
        result = db.update_user(
            user_id="nonexistent",
            name="New Name"
        )
        assert result is False


class TestSubscriptionOperations:
    """サブスクリプション操作テスト"""

    def test_create_subscription(self):
        """サブスクリプション作成"""
        db = Database()
        db.create_user(
            user_id="sub-user",
            email="sub@example.com",
            password_hash="hash"
        )

        sub = db.create_subscription(
            subscription_id="sub-123",
            user_id="sub-user",
            plan="personal"
        )

        assert sub is not None
        assert sub.id == "sub-123"
        assert sub.plan == "personal"
        assert sub.status == "active"

    def test_get_subscription_by_user(self):
        """ユーザーIDでサブスクリプション取得"""
        db = Database()
        db.create_user(
            user_id="get-sub-user",
            email="getsub@example.com",
            password_hash="hash"
        )
        db.create_subscription(
            subscription_id="get-sub",
            user_id="get-sub-user",
            plan="pro"
        )

        sub = db.get_subscription_by_user("get-sub-user")
        assert sub is not None
        assert sub.plan == "pro"

    def test_get_nonexistent_subscription(self):
        """存在しないサブスクリプションの取得"""
        db = Database()
        sub = db.get_subscription_by_user("no-sub-user")
        assert sub is None

    def test_update_subscription(self):
        """サブスクリプション更新"""
        db = Database()
        db.create_user(
            user_id="upd-sub-user",
            email="updsub@example.com",
            password_hash="hash"
        )
        db.create_subscription(
            subscription_id="upd-sub",
            user_id="upd-sub-user",
            plan="free"
        )

        result = db.update_subscription(
            subscription_id="upd-sub",
            plan="pro",
            status="active"
        )

        assert result is True

        sub = db.get_subscription_by_user("upd-sub-user")
        assert sub.plan == "pro"

    def test_subscription_with_stripe(self):
        """Stripeサブスクリプション連携"""
        db = Database()
        db.create_user(
            user_id="stripe-sub-user",
            email="stripesub@example.com",
            password_hash="hash"
        )

        sub = db.create_subscription(
            subscription_id="stripe-sub",
            user_id="stripe-sub-user",
            plan="personal",
            stripe_subscription_id="sub_stripe123"
        )

        assert sub.stripe_subscription_id == "sub_stripe123"


class TestUsageOperations:
    """使用量操作テスト"""

    def test_record_usage(self):
        """使用量記録"""
        db = Database()
        now = datetime.now()
        period_start = datetime(now.year, now.month, 1)
        period_end = period_start + timedelta(days=30)

        count = db.record_usage(
            user_id="usage-user",
            feature="email_summary",
            period_start=period_start,
            period_end=period_end
        )

        assert count == 1

    def test_increment_usage(self):
        """使用量インクリメント"""
        db = Database()
        now = datetime.now()
        period_start = datetime(now.year, now.month, 1)
        period_end = period_start + timedelta(days=30)

        # 3回記録
        db.record_usage("inc-user", "email_summary", period_start, period_end)
        db.record_usage("inc-user", "email_summary", period_start, period_end)
        count = db.record_usage("inc-user", "email_summary", period_start, period_end)

        assert count == 3

    def test_get_usage(self):
        """使用量取得"""
        db = Database()
        now = datetime.now()
        period_start = datetime(now.year, now.month, 1)
        period_end = period_start + timedelta(days=30)

        db.record_usage("get-usage-user", "email_summary", period_start, period_end)
        db.record_usage("get-usage-user", "email_summary", period_start, period_end)

        count = db.get_usage("get-usage-user", "email_summary", period_start)
        assert count == 2

    def test_get_zero_usage(self):
        """未使用の取得"""
        db = Database()
        now = datetime.now()
        period_start = datetime(now.year, now.month, 1)

        count = db.get_usage("no-usage-user", "email_summary", period_start)
        assert count == 0

    def test_get_all_usage(self):
        """全機能の使用量取得"""
        db = Database()
        now = datetime.now()
        period_start = datetime(now.year, now.month, 1)
        period_end = period_start + timedelta(days=30)

        # 複数機能の使用量を記録
        db.record_usage("all-usage-user", "email_summary", period_start, period_end)
        db.record_usage("all-usage-user", "email_summary", period_start, period_end)
        db.record_usage("all-usage-user", "schedule_proposal", period_start, period_end)

        all_usage = db.get_all_usage("all-usage-user", period_start)

        assert all_usage["email_summary"] == 2
        assert all_usage["schedule_proposal"] == 1

    def test_usage_separate_periods(self):
        """期間ごとの使用量分離"""
        db = Database()
        period1_start = datetime(2026, 1, 1)
        period1_end = datetime(2026, 2, 1)
        period2_start = datetime(2026, 2, 1)
        period2_end = datetime(2026, 3, 1)

        db.record_usage("period-user", "email_summary", period1_start, period1_end)
        db.record_usage("period-user", "email_summary", period1_start, period1_end)
        db.record_usage("period-user", "email_summary", period2_start, period2_end)

        count1 = db.get_usage("period-user", "email_summary", period1_start)
        count2 = db.get_usage("period-user", "email_summary", period2_start)

        assert count1 == 2
        assert count2 == 1


class TestAuditLogOperations:
    """監査ログ操作テスト"""

    def test_log_audit(self):
        """監査ログ記録"""
        db = Database()
        db.log_audit(
            action="user_login",
            user_id="audit-user",
            details={"ip": "192.168.1.1"},
            ip_address="192.168.1.1"
        )

        logs = db.get_audit_logs("audit-user")
        assert len(logs) == 1
        assert logs[0]["action"] == "user_login"

    def test_log_without_user(self):
        """ユーザーなしの監査ログ"""
        db = Database()
        db.log_audit(
            action="system_startup",
            details={"version": "1.0.0"}
        )

        logs = db.get_audit_logs()
        assert len(logs) >= 1

    def test_get_audit_logs_limit(self):
        """監査ログの件数制限"""
        db = Database()

        # 10件のログを記録
        for i in range(10):
            db.log_audit(
                action=f"action_{i}",
                user_id="limit-user"
            )

        logs = db.get_audit_logs("limit-user", limit=5)
        assert len(logs) == 5

    def test_audit_log_order(self):
        """監査ログの並び順（新しい順 = ID降順）"""
        db = Database()

        db.log_audit(action="first", user_id="order-user")
        db.log_audit(action="second", user_id="order-user")
        db.log_audit(action="third", user_id="order-user")

        logs = db.get_audit_logs("order-user")

        # 3件のログがあることを確認
        assert len(logs) == 3
        # IDが自動インクリメントなので、最新のIDが最大
        ids = [log["id"] for log in logs]
        # created_at DESCでソートされているので、IDが降順になる
        assert ids == sorted(ids, reverse=True)


class TestDatabasePersistence:
    """データベース永続性テスト"""

    def test_persistence_across_connections(self, tmp_path):
        """接続間のデータ永続性"""
        db_path = str(tmp_path / "persist.db")

        # 最初の接続でデータ作成
        db1 = Database(db_path)
        db1.create_user(
            user_id="persist-user",
            email="persist@example.com",
            password_hash="hash"
        )

        # 新しい接続でデータ確認
        db2 = Database(db_path)
        user = db2.get_user_by_id("persist-user")

        assert user is not None
        assert user.email == "persist@example.com"


class TestEdgeCases:
    """エッジケーステスト"""

    def test_special_characters_in_name(self):
        """名前に特殊文字"""
        db = Database()
        user = db.create_user(
            user_id="special-user",
            email="special@example.com",
            password_hash="hash",
            name="O'Brien \"Test\" <User>"
        )

        assert user.name == "O'Brien \"Test\" <User>"

        fetched = db.get_user_by_id("special-user")
        assert fetched.name == "O'Brien \"Test\" <User>"

    def test_unicode_in_details(self):
        """詳細に日本語"""
        db = Database()
        db.log_audit(
            action="test_action",
            details={"message": "日本語テスト", "emoji": "🎉"}
        )

        logs = db.get_audit_logs()
        assert logs[0]["details"]["message"] == "日本語テスト"
        assert logs[0]["details"]["emoji"] == "🎉"

    def test_empty_update(self):
        """空の更新"""
        db = Database()
        db.create_user(
            user_id="empty-upd-user",
            email="emptyupd@example.com",
            password_hash="hash"
        )

        result = db.update_user(user_id="empty-upd-user")
        assert result is False
