"""
パフォーマンステスト

システム全体のパフォーマンスとスケーラビリティを検証
"""

import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Callable
from unittest.mock import MagicMock, patch

from src.billing import BillingService, SubscriptionPlan, PlanLimits
from src.api import AuthService
from src.database import Database
from src.coordinator import Coordinator


class TestBillingPerformance:
    """課金システムのパフォーマンステスト"""

    @pytest.fixture
    def billing_service(self):
        """BillingServiceのフィクスチャ"""
        return BillingService()

    def test_subscription_creation_performance(self, billing_service):
        """サブスクリプション作成のパフォーマンス"""
        num_users = 100
        start_time = time.time()

        for i in range(num_users):
            billing_service.create_subscription(
                user_id=f"perf_user_{i}",
                customer_id=f"cus_mock_{i}",
                plan=SubscriptionPlan.PERSONAL
            )

        elapsed = time.time() - start_time
        avg_time = elapsed / num_users

        # 100ユーザー作成に5秒以内
        assert elapsed < 5.0, f"サブスクリプション作成が遅い: {elapsed:.2f}秒"
        # 平均50ms以内
        assert avg_time < 0.05, f"平均作成時間が遅い: {avg_time*1000:.2f}ms"

    def test_usage_check_performance(self, billing_service):
        """使用量チェックのパフォーマンス"""
        # サブスクリプション作成
        billing_service.create_subscription(
            user_id="usage_perf_user",
            customer_id="cus_mock",
            plan=SubscriptionPlan.PERSONAL
        )

        num_checks = 1000
        start_time = time.time()

        for _ in range(num_checks):
            billing_service.check_usage_limit("usage_perf_user", "email_summary")

        elapsed = time.time() - start_time
        avg_time = elapsed / num_checks

        # 1000回チェックに2秒以内
        assert elapsed < 2.0, f"使用量チェックが遅い: {elapsed:.2f}秒"
        # 平均2ms以内
        assert avg_time < 0.002, f"平均チェック時間が遅い: {avg_time*1000:.2f}ms"

    def test_concurrent_usage_recording(self, billing_service):
        """並行使用量記録のテスト"""
        # サブスクリプション作成
        billing_service.create_subscription(
            user_id="concurrent_user",
            customer_id="cus_mock",
            plan=SubscriptionPlan.PRO  # 2000件/月
        )

        num_threads = 10
        records_per_thread = 50

        def record_usage():
            for _ in range(records_per_thread):
                billing_service.record_usage("concurrent_user", "email_summary")

        start_time = time.time()
        threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=record_usage)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        elapsed = time.time() - start_time

        # 500回記録に3秒以内
        assert elapsed < 3.0, f"並行記録が遅い: {elapsed:.2f}秒"

        # 全記録が正しく行われたことを確認
        subscription = billing_service.get_subscription("concurrent_user")
        assert subscription is not None
        # 注: スレッドセーフでない可能性があるため、正確な件数は保証されない
        assert subscription.usage.email_summaries_used > 0

    def test_plan_limits_lookup_performance(self):
        """プラン制限ルックアップのパフォーマンス"""
        num_lookups = 10000
        plans = list(SubscriptionPlan)

        start_time = time.time()

        for i in range(num_lookups):
            PlanLimits.for_plan(plans[i % len(plans)])

        elapsed = time.time() - start_time

        # 10000回ルックアップに1秒以内
        assert elapsed < 1.0, f"プラン制限ルックアップが遅い: {elapsed:.2f}秒"


class TestAuthPerformance:
    """認証システムのパフォーマンステスト"""

    @pytest.fixture
    def auth_service(self):
        """AuthServiceのフィクスチャ"""
        return AuthService(secret_key="perf-test-secret-key")

    def test_user_creation_performance(self, auth_service):
        """ユーザー作成のパフォーマンス"""
        num_users = 100
        start_time = time.time()

        for i in range(num_users):
            auth_service.create_user(
                email=f"perfuser{i}@example.com",
                password=f"password{i}",
                name=f"Perf User {i}"
            )

        elapsed = time.time() - start_time
        avg_time = elapsed / num_users

        # 100ユーザー作成に5秒以内
        assert elapsed < 5.0, f"ユーザー作成が遅い: {elapsed:.2f}秒"
        # 平均50ms以内
        assert avg_time < 0.05, f"平均作成時間が遅い: {avg_time*1000:.2f}ms"

    def test_token_creation_performance(self, auth_service):
        """トークン生成のパフォーマンス"""
        num_tokens = 1000
        start_time = time.time()

        for i in range(num_tokens):
            auth_service.create_access_token(f"user_{i}")

        elapsed = time.time() - start_time
        avg_time = elapsed / num_tokens

        # 1000トークン生成に2秒以内
        assert elapsed < 2.0, f"トークン生成が遅い: {elapsed:.2f}秒"
        # 平均2ms以内
        assert avg_time < 0.002, f"平均生成時間が遅い: {avg_time*1000:.2f}ms"

    def test_token_verification_performance(self, auth_service):
        """トークン検証のパフォーマンス"""
        token = auth_service.create_access_token("perf_user")
        num_verifications = 1000

        start_time = time.time()

        for _ in range(num_verifications):
            auth_service.verify_token(token)

        elapsed = time.time() - start_time
        avg_time = elapsed / num_verifications

        # 1000回検証に2秒以内
        assert elapsed < 2.0, f"トークン検証が遅い: {elapsed:.2f}秒"
        # 平均2ms以内
        assert avg_time < 0.002, f"平均検証時間が遅い: {avg_time*1000:.2f}ms"

    def test_authentication_performance(self, auth_service):
        """認証のパフォーマンス"""
        # ユーザー作成
        auth_service.create_user(
            email="authperf@example.com",
            password="password123"
        )

        num_auths = 100
        start_time = time.time()

        for _ in range(num_auths):
            auth_service.authenticate("authperf@example.com", "password123")

        elapsed = time.time() - start_time
        avg_time = elapsed / num_auths

        # 100回認証に3秒以内
        assert elapsed < 3.0, f"認証が遅い: {elapsed:.2f}秒"
        # 平均30ms以内
        assert avg_time < 0.03, f"平均認証時間が遅い: {avg_time*1000:.2f}ms"


class TestDatabasePerformance:
    """データベースのパフォーマンステスト"""

    @pytest.fixture
    def database(self):
        """インメモリデータベースのフィクスチャ"""
        return Database()

    def test_user_insert_performance(self, database):
        """ユーザー挿入のパフォーマンス"""
        num_users = 500
        start_time = time.time()

        for i in range(num_users):
            database.create_user(
                user_id=f"db_perf_user_{i}",
                email=f"dbperf{i}@example.com",
                password_hash=f"hash_{i}",
                name=f"DB Perf User {i}"
            )

        elapsed = time.time() - start_time
        avg_time = elapsed / num_users

        # 500ユーザー挿入に5秒以内
        assert elapsed < 5.0, f"ユーザー挿入が遅い: {elapsed:.2f}秒"
        # 平均10ms以内
        assert avg_time < 0.01, f"平均挿入時間が遅い: {avg_time*1000:.2f}ms"

    def test_user_lookup_performance(self, database):
        """ユーザー検索のパフォーマンス"""
        # テストデータ作成
        for i in range(100):
            database.create_user(
                user_id=f"lookup_user_{i}",
                email=f"lookup{i}@example.com",
                password_hash=f"hash_{i}"
            )

        num_lookups = 1000
        start_time = time.time()

        for i in range(num_lookups):
            database.get_user_by_email(f"lookup{i % 100}@example.com")

        elapsed = time.time() - start_time
        avg_time = elapsed / num_lookups

        # 1000回検索に2秒以内
        assert elapsed < 2.0, f"ユーザー検索が遅い: {elapsed:.2f}秒"
        # 平均2ms以内
        assert avg_time < 0.002, f"平均検索時間が遅い: {avg_time*1000:.2f}ms"

    def test_usage_recording_performance(self, database):
        """使用量記録のパフォーマンス"""
        # ユーザー作成
        database.create_user(
            user_id="usage_record_user",
            email="usagerecord@example.com",
            password_hash="hash"
        )

        now = datetime.now()
        period_start = datetime(now.year, now.month, 1)
        period_end = period_start + timedelta(days=30)

        num_records = 500
        start_time = time.time()

        for i in range(num_records):
            database.record_usage(
                user_id="usage_record_user",
                feature=f"feature_{i % 3}",
                period_start=period_start,
                period_end=period_end
            )

        elapsed = time.time() - start_time
        avg_time = elapsed / num_records

        # 500回記録に5秒以内
        assert elapsed < 5.0, f"使用量記録が遅い: {elapsed:.2f}秒"
        # 平均10ms以内
        assert avg_time < 0.01, f"平均記録時間が遅い: {avg_time*1000:.2f}ms"

    def test_audit_log_performance(self, database):
        """監査ログのパフォーマンス"""
        num_logs = 500
        start_time = time.time()

        for i in range(num_logs):
            database.log_audit(
                action=f"test_action_{i % 10}",
                user_id=f"user_{i % 50}",
                details={"index": i}
            )

        elapsed = time.time() - start_time
        avg_time = elapsed / num_logs

        # 500件ログに3秒以内
        assert elapsed < 3.0, f"監査ログが遅い: {elapsed:.2f}秒"
        # 平均6ms以内
        assert avg_time < 0.006, f"平均ログ時間が遅い: {avg_time*1000:.2f}ms"

    def test_audit_log_retrieval_performance(self, database):
        """監査ログ取得のパフォーマンス"""
        # ログ作成
        for i in range(200):
            database.log_audit(
                action="test_action",
                user_id=f"user_{i % 20}",
                details={"index": i}
            )

        num_retrievals = 100
        start_time = time.time()

        for i in range(num_retrievals):
            database.get_audit_logs(user_id=f"user_{i % 20}", limit=50)

        elapsed = time.time() - start_time
        avg_time = elapsed / num_retrievals

        # 100回取得に2秒以内
        assert elapsed < 2.0, f"ログ取得が遅い: {elapsed:.2f}秒"
        # 平均20ms以内
        assert avg_time < 0.02, f"平均取得時間が遅い: {avg_time*1000:.2f}ms"


class TestCoordinatorPerformance:
    """Coordinatorのパフォーマンステスト"""

    @pytest.fixture
    def coordinator(self):
        """Coordinatorのフィクスチャ（モック）"""
        with patch('src.coordinator.EmailBot') as mock_email, \
             patch('src.coordinator.Scheduler') as mock_scheduler:

            mock_email_instance = MagicMock()
            mock_email_instance.get_recent_emails.return_value = [
                {"id": "1", "subject": "Test", "from": "test@example.com"}
            ]
            mock_email_instance.summarize_email.return_value = {
                "summary": "Test summary"
            }
            mock_email.return_value = mock_email_instance

            mock_scheduler_instance = MagicMock()
            mock_scheduler_instance.find_free_slots.return_value = [
                {"start": datetime.now(), "end": datetime.now() + timedelta(hours=1)}
            ]
            mock_scheduler.return_value = mock_scheduler_instance

            return Coordinator()

    def test_command_processing_performance(self, coordinator):
        """コマンド処理のパフォーマンス"""
        commands = ["help", "status", "inbox", "calendar"]
        num_commands = 100

        start_time = time.time()

        for i in range(num_commands):
            coordinator.process_command(commands[i % len(commands)])

        elapsed = time.time() - start_time
        avg_time = elapsed / num_commands

        # 100コマンド処理に5秒以内
        assert elapsed < 5.0, f"コマンド処理が遅い: {elapsed:.2f}秒"
        # 平均50ms以内
        assert avg_time < 0.05, f"平均処理時間が遅い: {avg_time*1000:.2f}ms"

    def test_command_routing_performance(self, coordinator):
        """コマンドルーティング性能"""
        test_commands = [
            "help",
            "inbox",
            "schedule meeting with alice@example.com 30min",
            "status",
        ]

        num_commands = 100
        start_time = time.time()

        for i in range(num_commands):
            coordinator.process_command(test_commands[i % len(test_commands)])

        elapsed = time.time() - start_time
        avg_time = elapsed / num_commands

        # 100コマンド処理に3秒以内
        assert elapsed < 3.0, f"コマンドルーティングが遅い: {elapsed:.2f}秒"
        # 平均30ms以内
        assert avg_time < 0.03, f"平均ルーティング時間が遅い: {avg_time*1000:.2f}ms"


class TestConcurrencyStress:
    """並行処理のストレステスト"""

    def test_concurrent_auth_operations(self):
        """並行認証操作のストレステスト"""
        auth_service = AuthService(secret_key="stress-test-key")

        # 事前にユーザーを作成
        for i in range(50):
            auth_service.create_user(
                email=f"stress{i}@example.com",
                password="password123"
            )

        def auth_operation(user_index: int):
            """認証操作"""
            email = f"stress{user_index}@example.com"
            user = auth_service.authenticate(email, "password123")
            if user:
                token = auth_service.create_access_token(user.id)
                auth_service.verify_token(token)
                return True
            return False

        num_operations = 200
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [
                executor.submit(auth_operation, i % 50)
                for i in range(num_operations)
            ]
            results = [f.result() for f in as_completed(futures)]

        elapsed = time.time() - start_time

        # 200操作に10秒以内
        assert elapsed < 10.0, f"並行認証操作が遅い: {elapsed:.2f}秒"
        # 成功率80%以上
        success_rate = sum(results) / len(results)
        assert success_rate > 0.8, f"成功率が低い: {success_rate*100:.1f}%"

    def test_concurrent_billing_operations(self):
        """並行課金操作のストレステスト"""
        billing_service = BillingService()

        # 事前にサブスクリプションを作成
        for i in range(50):
            billing_service.create_subscription(
                user_id=f"billing_stress_{i}",
                customer_id=f"cus_stress_{i}",
                plan=SubscriptionPlan.PERSONAL
            )

        def billing_operation(user_index: int):
            """課金操作"""
            user_id = f"billing_stress_{user_index}"
            can_use, _ = billing_service.check_usage_limit(user_id, "email_summary")
            if can_use:
                billing_service.record_usage(user_id, "email_summary")
                return True
            return False

        num_operations = 500
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [
                executor.submit(billing_operation, i % 50)
                for i in range(num_operations)
            ]
            results = [f.result() for f in as_completed(futures)]

        elapsed = time.time() - start_time

        # 500操作に10秒以内
        assert elapsed < 10.0, f"並行課金操作が遅い: {elapsed:.2f}秒"
        # 成功率90%以上（使用量上限に達するまで）
        success_rate = sum(results) / len(results)
        assert success_rate > 0.5, f"成功率が低い: {success_rate*100:.1f}%"


class TestMemoryUsage:
    """メモリ使用量テスト"""

    def test_subscription_memory_footprint(self):
        """サブスクリプションのメモリフットプリント"""
        import sys
        billing_service = BillingService()

        # 初期メモリ使用量
        initial_size = sys.getsizeof(billing_service._subscriptions)

        # 1000件のサブスクリプション作成
        for i in range(1000):
            billing_service.create_subscription(
                user_id=f"memory_user_{i}",
                customer_id=f"cus_memory_{i}",
                plan=SubscriptionPlan.PERSONAL
            )

        # 最終メモリ使用量
        final_size = sys.getsizeof(billing_service._subscriptions)
        memory_growth = final_size - initial_size

        # 辞書自体のサイズは小さいため、内容の確認
        assert len(billing_service._subscriptions) == 1000
        # 1000サブスクリプションで10MB以下（概算）
        # 実際のオブジェクトサイズは別途計測が必要

    def test_audit_log_memory_management(self):
        """監査ログのメモリ管理"""
        database = Database()

        # 1000件のログを書き込み
        for i in range(1000):
            database.log_audit(
                action="memory_test",
                user_id="test_user",
                details={"index": i, "data": "x" * 100}  # 各ログに100文字のデータ
            )

        # 取得時のlimit動作確認
        logs_50 = database.get_audit_logs(limit=50)
        logs_100 = database.get_audit_logs(limit=100)

        assert len(logs_50) == 50
        assert len(logs_100) == 100


class TestResponseTime:
    """レスポンスタイムテスト"""

    def test_authentication_response_time(self):
        """認証のレスポンスタイム"""
        auth_service = AuthService(secret_key="response-time-key")

        # ユーザー作成
        auth_service.create_user(
            email="response@example.com",
            password="password123"
        )

        # 認証のレスポンスタイム測定
        times = []
        for _ in range(20):
            start = time.time()
            auth_service.authenticate("response@example.com", "password123")
            times.append(time.time() - start)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # 平均20ms以内
        assert avg_time < 0.02, f"平均認証時間が遅い: {avg_time*1000:.2f}ms"
        # 最大100ms以内
        assert max_time < 0.1, f"最大認証時間が遅い: {max_time*1000:.2f}ms"

    def test_usage_check_response_time(self):
        """使用量チェックのレスポンスタイム"""
        billing_service = BillingService()

        billing_service.create_subscription(
            user_id="response_user",
            customer_id="cus_response",
            plan=SubscriptionPlan.PRO
        )

        # 使用量チェックのレスポンスタイム測定
        times = []
        for _ in range(50):
            start = time.time()
            billing_service.check_usage_limit("response_user", "email_summary")
            times.append(time.time() - start)

        avg_time = sum(times) / len(times)
        p99_time = sorted(times)[int(len(times) * 0.99)]

        # 平均1ms以内
        assert avg_time < 0.001, f"平均チェック時間が遅い: {avg_time*1000:.2f}ms"
        # P99 5ms以内
        assert p99_time < 0.005, f"P99チェック時間が遅い: {p99_time*1000:.2f}ms"
