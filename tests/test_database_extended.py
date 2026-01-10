# -*- coding: utf-8 -*-
"""
database.pyカバレッジ向上テスト

対象: 86% → 95%目標
未カバー行:
- 30, 33-34: _str_to_datetime エッジケース
- 188-191: close()メソッドのログ出力
- 355-357: create_subscription IntegrityError
- 391-392, 395: update_subscription period_end/空更新
- 569-608: __main__ブロック（テスト対象外）
"""

import pytest
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from src.database import (
    Database,
    DBUser,
    DBSubscription,
    DBUsageRecord,
    create_database,
    _str_to_datetime,
    _datetime_to_str,
)


class TestStrToDatetime:
    """_str_to_datetime関数のテスト"""

    def test_none_input_returns_current_datetime(self) -> None:
        """Noneが渡された場合、現在時刻を返す"""
        result = _str_to_datetime(None)
        # 現在時刻に近いかチェック
        now = datetime.now()
        assert abs((result - now).total_seconds()) < 5

    def test_valid_iso8601_string(self) -> None:
        """有効なISO8601文字列を変換"""
        dt_str = "2025-06-15T10:30:00"
        result = _str_to_datetime(dt_str)
        assert result.year == 2025
        assert result.month == 6
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_invalid_string_returns_current_datetime(self) -> None:
        """無効な文字列の場合、現在時刻を返す"""
        result = _str_to_datetime("invalid-date-string")
        now = datetime.now()
        assert abs((result - now).total_seconds()) < 5

    def test_empty_string_returns_current_datetime(self) -> None:
        """空文字列の場合、現在時刻を返す"""
        result = _str_to_datetime("")
        now = datetime.now()
        assert abs((result - now).total_seconds()) < 5


class TestDatabaseClose:
    """Database.close()メソッドのテスト"""

    def test_close_with_persistent_connection(self) -> None:
        """永続接続がある場合のclose()テスト"""
        db = Database(":memory:")
        # 接続を使用して永続接続を作成
        db.create_user("user1", "test@example.com", "hash", "Test User")
        # close()を呼び出し
        db.close()
        # _persistent_connがNoneになっているか確認
        assert db._persistent_conn is None

    def test_close_without_persistent_connection(self) -> None:
        """永続接続がない場合のclose()テスト"""
        db = Database(":memory:")
        # 明示的に永続接続がない状態を作る
        db._persistent_conn = None
        # close()を呼び出し（エラーが発生しないことを確認）
        db.close()
        assert db._persistent_conn is None

    def test_close_logs_debug_message(self) -> None:
        """close()がデバッグメッセージをログ出力することを確認"""
        db = Database(":memory:")
        db.create_user("user1", "test@example.com", "hash", "Test User")

        with patch('src.database.logger') as mock_logger:
            db.close()
            # debugメソッドが呼ばれたことを確認
            mock_logger.debug.assert_called()


class TestDatabaseCreateSubscriptionIntegrityError:
    """create_subscriptionのIntegrityErrorテスト"""

    def test_create_subscription_duplicate_id(self) -> None:
        """同一IDでのサブスクリプション作成がNoneを返す"""
        db = Database(":memory:")
        # ユーザー作成
        db.create_user("user1", "test@example.com", "hash", "Test User")

        # 最初のサブスクリプション作成
        sub1 = db.create_subscription("sub1", "user1", "personal")
        assert sub1 is not None

        # 同一IDで2回目の作成を試みる
        sub2 = db.create_subscription("sub1", "user1", "pro")
        # IntegrityErrorにより None が返る
        assert sub2 is None

    def test_create_subscription_integrity_error_logging(self) -> None:
        """IntegrityError時にwarningログが出力される"""
        db = Database(":memory:")
        db.create_user("user1", "test@example.com", "hash", "Test User")
        db.create_subscription("sub1", "user1", "personal")

        with patch('src.database.logger') as mock_logger:
            db.create_subscription("sub1", "user1", "pro")
            mock_logger.warning.assert_called()


class TestDatabaseUpdateSubscription:
    """update_subscriptionの追加テスト"""

    def test_update_subscription_with_period_end(self) -> None:
        """period_end更新のテスト"""
        db = Database(":memory:")
        db.create_user("user1", "test@example.com", "hash", "Test User")
        sub = db.create_subscription("sub1", "user1", "personal")
        assert sub is not None

        new_end = datetime.now() + timedelta(days=60)
        result = db.update_subscription("sub1", period_end=new_end)
        assert result is True

        # 更新されたか確認
        updated = db.get_subscription_by_user("user1")
        assert updated is not None
        # 日付が更新されている（タイムゾーンなし比較）
        assert updated.current_period_end.date() == new_end.date()

    def test_update_subscription_empty_updates(self) -> None:
        """更新項目がない場合Falseを返す"""
        db = Database(":memory:")
        db.create_user("user1", "test@example.com", "hash", "Test User")
        db.create_subscription("sub1", "user1", "personal")

        # 何も指定しない更新
        result = db.update_subscription("sub1")
        assert result is False

    def test_update_subscription_multiple_fields(self) -> None:
        """複数フィールドの同時更新"""
        db = Database(":memory:")
        db.create_user("user1", "test@example.com", "hash", "Test User")
        db.create_subscription("sub1", "user1", "personal")

        new_end = datetime.now() + timedelta(days=90)
        result = db.update_subscription(
            "sub1",
            plan="pro",
            status="active",
            period_end=new_end
        )
        assert result is True

        updated = db.get_subscription_by_user("user1")
        assert updated is not None
        assert updated.plan == "pro"
        assert updated.status == "active"

    def test_update_nonexistent_subscription(self) -> None:
        """存在しないサブスクリプションの更新"""
        db = Database(":memory:")
        result = db.update_subscription("nonexistent", plan="pro")
        assert result is False


class TestDatabaseEdgeCases:
    """その他のエッジケーステスト"""

    def test_get_user_by_id_not_found(self) -> None:
        """存在しないユーザーIDでの取得"""
        db = Database(":memory:")
        result = db.get_user_by_id("nonexistent")
        assert result is None

    def test_get_subscription_by_user_not_found(self) -> None:
        """サブスクリプションがないユーザーでの取得"""
        db = Database(":memory:")
        db.create_user("user1", "test@example.com", "hash", "Test User")
        result = db.get_subscription_by_user("user1")
        assert result is None

    def test_create_user_duplicate_email(self) -> None:
        """同一メールアドレスでのユーザー作成"""
        db = Database(":memory:")
        user1 = db.create_user("user1", "test@example.com", "hash", "User 1")
        assert user1 is not None

        user2 = db.create_user("user2", "test@example.com", "hash", "User 2")
        # IntegrityErrorによりNone
        assert user2 is None

    def test_update_user_plan(self) -> None:
        """ユーザープラン更新"""
        db = Database(":memory:")
        db.create_user("user1", "test@example.com", "hash", "Test User")

        result = db.update_user("user1", plan="pro")
        assert result is True

        user = db.get_user_by_id("user1")
        assert user is not None
        assert user.plan == "pro"

    def test_get_usage_no_records(self) -> None:
        """使用量レコードがない場合"""
        db = Database(":memory:")
        now = datetime.now()
        period_start = datetime(now.year, now.month, 1)

        count = db.get_usage("nonexistent", "email_summary", period_start)
        assert count == 0

    def test_record_usage_multiple_operations(self) -> None:
        """複数の操作タイプで使用量記録"""
        db = Database(":memory:")
        db.create_user("user1", "test@example.com", "hash", "Test User")

        now = datetime.now()
        period_start = datetime(now.year, now.month, 1)
        period_end = datetime(now.year, now.month + 1 if now.month < 12 else 1, 1)

        count1 = db.record_usage("user1", "email_summary", period_start, period_end)
        count2 = db.record_usage("user1", "schedule_proposal", period_start, period_end)
        count3 = db.record_usage("user1", "email_summary", period_start, period_end)

        assert count1 == 1
        assert count2 == 1
        assert count3 == 2  # email_summaryは2回目

    def test_get_audit_logs_empty(self) -> None:
        """監査ログが空の場合"""
        db = Database(":memory:")
        logs = db.get_audit_logs("nonexistent")
        assert logs == []

    def test_log_audit_with_metadata(self) -> None:
        """メタデータ付き監査ログ記録"""
        db = Database(":memory:")
        db.create_user("user1", "test@example.com", "hash", "Test User")

        db.log_audit(
            "user_login",
            user_id="user1",
            details={"ip": "192.168.1.1", "user_agent": "TestBrowser"}
        )

        logs = db.get_audit_logs("user1")
        assert len(logs) == 1
        assert logs[0]["action"] == "user_login"
        assert "ip" in logs[0]["details"]

    def test_get_audit_logs_with_limit(self) -> None:
        """監査ログの件数制限"""
        db = Database(":memory:")
        db.create_user("user1", "test@example.com", "hash", "Test User")

        # 複数のログを記録
        for i in range(10):
            db.log_audit(f"action_{i}", user_id="user1", details={"index": i})

        logs = db.get_audit_logs("user1", limit=5)
        assert len(logs) == 5


class TestDatabaseDataclasses:
    """データクラスのテスト"""

    def test_db_user_attributes(self) -> None:
        """DBUserのアトリビュート確認"""
        user = DBUser(
            id="user1",
            email="test@example.com",
            password_hash="hash",
            name="Test User",
            plan="personal",
            stripe_customer_id=None,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        assert user.id == "user1"
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.plan == "personal"

    def test_db_subscription_attributes(self) -> None:
        """DBSubscriptionのアトリビュート確認"""
        now = datetime.now()
        sub = DBSubscription(
            id="sub1",
            user_id="user1",
            plan="pro",
            status="active",
            stripe_subscription_id="stripe_123",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            created_at=now,
            updated_at=now
        )
        assert sub.id == "sub1"
        assert sub.plan == "pro"
        assert sub.status == "active"

    def test_db_usage_record_attributes(self) -> None:
        """DBUsageRecordのアトリビュート確認"""
        now = datetime.now()
        record = DBUsageRecord(
            id="usage1",
            user_id="user1",
            feature="email_summary",
            count=5,
            period_start=now,
            period_end=now + timedelta(days=30),
        )
        assert record.feature == "email_summary"
        assert record.count == 5


class TestCreateDatabaseFunction:
    """create_database関数のテスト"""

    def test_create_database_default(self) -> None:
        """デフォルト引数でのDatabase作成"""
        db = create_database()
        assert db is not None
        assert isinstance(db, Database)
        db.close()

    def test_create_database_custom_path(self, tmp_path) -> None:
        """カスタムパスでのDatabase作成"""
        db_path = str(tmp_path / "test.db")
        db = create_database(db_path)
        assert db is not None
        db.close()


class TestDatabaseIntegration:
    """統合テスト"""

    def test_full_user_lifecycle(self) -> None:
        """ユーザーの完全なライフサイクル"""
        db = Database(":memory:")

        # 1. ユーザー作成
        user = db.create_user("user1", "test@example.com", "hash", "Test User")
        assert user is not None

        # 2. サブスクリプション作成
        sub = db.create_subscription("sub1", "user1", "personal")
        assert sub is not None

        # 3. 使用量記録
        now = datetime.now()
        period_start = datetime(now.year, now.month, 1)
        period_end = datetime(now.year, now.month + 1 if now.month < 12 else 1, 1)

        for _ in range(5):
            db.record_usage("user1", "email_summary", period_start, period_end)

        count = db.get_usage("user1", "email_summary", period_start)
        assert count == 5

        # 4. プランアップグレード
        db.update_user("user1", plan="pro")
        db.update_subscription("sub1", plan="pro")

        # 5. 監査ログ記録
        db.log_audit("plan_upgraded", user_id="user1", details={"old_plan": "personal", "new_plan": "pro"})

        # 6. 確認
        updated_user = db.get_user_by_id("user1")
        assert updated_user is not None
        assert updated_user.plan == "pro"

        logs = db.get_audit_logs("user1")
        assert len(logs) == 1

        db.close()

    def test_multiple_users(self) -> None:
        """複数ユーザーのテスト"""
        db = Database(":memory:")

        # 複数ユーザー作成
        for i in range(3):
            db.create_user(f"user{i}", f"user{i}@example.com", "hash", f"User {i}")
            db.create_subscription(f"sub{i}", f"user{i}", "personal")

        # 各ユーザーの取得確認
        for i in range(3):
            user = db.get_user_by_email(f"user{i}@example.com")
            assert user is not None
            assert user.id == f"user{i}"

        db.close()
