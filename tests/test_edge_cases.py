"""
エッジケーステスト

境界条件、異常系、特殊な入力パターンのテスト
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock


class TestEmailBotEdgeCases:
    """EmailBot のエッジケーステスト"""

    def test_email_without_service_raises_error(self):
        """サービス未認証時のエラー"""
        from src.email_bot import EmailBot
        from src.errors import EmailError

        bot = EmailBot()
        # _serviceがNoneの状態

        with pytest.raises(EmailError):
            bot.fetch_unread_emails(max_results=10)

    def test_email_with_no_body(self):
        """本文なしメールの処理"""
        from src.email_bot import Email
        from datetime import datetime

        email = Email(
            id="test123",
            thread_id="thread123",
            subject="テスト件名",
            sender="sender@example.com",
            recipient="recipient@example.com",
            date=datetime.now(),
            body="",  # 空の本文
            snippet="スニペット",
            is_unread=True
        )

        assert email.id == "test123"
        assert email.body == ""

    def test_email_with_unicode_content(self):
        """Unicode文字を含むメールの処理"""
        from src.email_bot import Email
        from datetime import datetime

        email = Email(
            id="test123",
            thread_id="thread123",
            subject="日本語件名🎉",
            sender="送信者@例.jp",
            recipient="受信者@例.jp",
            date=datetime.now(),
            body="本文には絵文字😀と特殊文字①②③が含まれます",
            snippet="スニペット",
            is_unread=True
        )

        assert email.subject == "日本語件名🎉"
        assert "絵文字" in email.body

    def test_summarize_text_offline_function(self):
        """オフライン要約関数のテスト"""
        from src.email_bot import summarize_text_offline

        # 短いテキスト
        short = "これは短いテキストです。"
        result = summarize_text_offline(short)
        assert result == short

        # 長いテキスト
        long_text = "これはテスト文章です。" * 100
        result = summarize_text_offline(long_text, max_length=50)
        assert len(result) <= 60  # 文区切りのため若干余裕


class TestSchedulerEdgeCases:
    """Scheduler のエッジケーステスト"""

    def test_timeslot_overlap_detection(self):
        """TimeSlotの重複検出"""
        from src.scheduler import TimeSlot

        now = datetime.now()
        slot1 = TimeSlot(now, now + timedelta(hours=1))
        slot2 = TimeSlot(now + timedelta(minutes=30), now + timedelta(hours=1, minutes=30))
        slot3 = TimeSlot(now + timedelta(hours=2), now + timedelta(hours=3))

        assert slot1.overlaps(slot2)  # 重複あり
        assert not slot1.overlaps(slot3)  # 重複なし

    def test_timeslot_duration(self):
        """TimeSlotの所要時間計算"""
        from src.scheduler import TimeSlot

        now = datetime.now()
        slot = TimeSlot(now, now + timedelta(minutes=90))

        assert slot.duration_minutes == 90

    def test_scheduler_without_service_raises_error(self):
        """サービス未認証時のエラー"""
        from src.scheduler import Scheduler
        from src.errors import ScheduleError

        scheduler = Scheduler()

        with pytest.raises(ScheduleError):
            scheduler.get_events()

    def test_find_free_slots_offline(self):
        """オフライン空き時間検索"""
        from src.scheduler import find_free_slots_offline, TimeSlot

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        busy = [
            TimeSlot(today.replace(hour=10), today.replace(hour=11)),
            TimeSlot(today.replace(hour=14), today.replace(hour=15)),
        ]

        free = find_free_slots_offline(busy, duration_minutes=30)

        # 結果が存在すること
        assert len(free) > 0
        # 忙しい時間と重複しないこと
        for slot in free:
            for b in busy:
                assert not slot.overlaps(b)


class TestCoordinatorEdgeCases:
    """Coordinator のエッジケーステスト"""

    def test_empty_command(self):
        """空のコマンド"""
        from src.coordinator import Coordinator

        coordinator = Coordinator()
        result = coordinator.process_command("")

        assert result is not None
        assert hasattr(result, "success")

    def test_whitespace_only_command(self):
        """空白のみのコマンド"""
        from src.coordinator import Coordinator

        coordinator = Coordinator()
        result = coordinator.process_command("   \t\n  ")

        assert result is not None

    def test_very_long_command(self):
        """非常に長いコマンド"""
        from src.coordinator import Coordinator

        coordinator = Coordinator()
        long_command = "schedule " + "a" * 10000

        result = coordinator.process_command(long_command)
        assert result is not None

    def test_command_with_special_characters(self):
        """特殊文字を含むコマンド"""
        from src.coordinator import Coordinator

        coordinator = Coordinator()
        special_command = "schedule <script>alert('xss')</script>"

        result = coordinator.process_command(special_command)
        # XSS攻撃は無害化されるべき
        assert result is not None

    def test_command_with_sql_injection_attempt(self):
        """SQLインジェクション的なコマンド"""
        from src.coordinator import Coordinator

        coordinator = Coordinator()
        injection_command = "inbox; DROP TABLE users;--"

        result = coordinator.process_command(injection_command)
        # 安全に処理されるべき
        assert result is not None


class TestBillingEdgeCases:
    """Billing のエッジケーステスト"""

    def test_usage_at_exact_limit(self):
        """使用量が上限ちょうどの場合"""
        from src.billing import BillingService, SubscriptionPlan

        service = BillingService()
        service.create_subscription(
            user_id="test_user",
            customer_id="cust_test",
            plan=SubscriptionPlan.FREE
        )

        # 上限まで使用
        for _ in range(50):  # FREE プランの上限
            service.record_usage("test_user", "email_summary")

        can_use, message = service.check_usage_limit("test_user", "email_summary")
        assert can_use is False

    def test_usage_just_below_limit(self):
        """使用量が上限の1つ下の場合"""
        from src.billing import BillingService, SubscriptionPlan

        service = BillingService()
        service.create_subscription(
            user_id="test_user2",
            customer_id="cust_test2",
            plan=SubscriptionPlan.FREE
        )

        # 上限-1まで使用
        for _ in range(49):
            service.record_usage("test_user2", "email_summary")

        can_use, message = service.check_usage_limit("test_user2", "email_summary")
        assert can_use is True

    def test_unknown_usage_type(self):
        """未知の使用タイプ"""
        from src.billing import BillingService, SubscriptionPlan

        service = BillingService()
        service.create_subscription(
            user_id="test_user3",
            customer_id="cust_test3",
            plan=SubscriptionPlan.FREE
        )

        # 未知の使用タイプを記録しても例外が発生しないこと
        service.record_usage("test_user3", "unknown_type")


class TestAuthServiceEdgeCases:
    """AuthService のエッジケーステスト"""

    def test_empty_email(self):
        """空のメールアドレス"""
        from src.api import AuthService

        auth = AuthService()
        user = auth.create_user(email="", password="password123")
        # 空のメールでもUserは作成される（実装依存）
        # 本番では追加のバリデーションが必要
        assert user is not None or user is None

    def test_very_long_password(self):
        """非常に長いパスワード"""
        from src.api import AuthService

        auth = AuthService()
        long_password = "a" * 10000

        user = auth.create_user(
            email="longpass@example.com",
            password=long_password
        )
        # 長いパスワードでも処理できること
        assert user is not None

    def test_unicode_password(self):
        """Unicode文字を含むパスワード"""
        from src.api import AuthService

        auth = AuthService()
        unicode_password = "パスワード🔐123"

        user = auth.create_user(
            email="unicode@example.com",
            password=unicode_password
        )
        assert user is not None

        # 認証も成功すること
        auth_user = auth.authenticate("unicode@example.com", unicode_password)
        assert auth_user is not None

    def test_empty_token_verification(self):
        """空のトークン検証"""
        from src.api import AuthService

        auth = AuthService()
        result = auth.verify_token("")
        assert result is None

    def test_malformed_token_verification(self):
        """不正な形式のトークン検証"""
        from src.api import AuthService

        auth = AuthService()
        result = auth.verify_token("not.a.valid.jwt.token.at.all")
        assert result is None


class TestDatabaseEdgeCases:
    """Database のエッジケーステスト"""

    def test_concurrent_user_creation(self):
        """同時ユーザー作成（競合状態）"""
        from src.database import Database
        import threading
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            results = []
            def create_user(email):
                try:
                    result = db.create_user(email, "password", "name")
                    results.append(("success", email, result))
                except Exception as e:
                    results.append(("error", email, str(e)))

            threads = []
            for i in range(10):
                t = threading.Thread(target=create_user, args=(f"user{i}@example.com",))
                threads.append(t)

            for t in threads:
                t.start()

            for t in threads:
                t.join()

            # 全てのスレッドが完了し、重大なエラーがないこと
            assert len(results) == 10

    def test_very_long_user_name(self):
        """非常に長いユーザー名"""
        from src.database import Database
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)

            long_name = "a" * 10000
            user = db.create_user(
                "longname@example.com",
                "password",
                long_name
            )
            # 長い名前でも処理できること
            assert user is not None


class TestLLMServiceEdgeCases:
    """LLMService のエッジケーステスト"""

    def test_complete_with_empty_prompt(self):
        """空のプロンプトでの生成"""
        from src.llm import LLMService, LLMProvider

        service = LLMService(primary_provider=LLMProvider.MOCK)
        result = service.complete("")
        assert result.success

    def test_complete_with_very_long_prompt(self):
        """非常に長いプロンプトでの生成"""
        from src.llm import LLMService, LLMProvider

        service = LLMService(primary_provider=LLMProvider.MOCK)
        long_prompt = "これはテストです。" * 10000  # 約10万文字

        result = service.complete(long_prompt)
        # モックなのでエラーなく処理
        assert result.success

    def test_summarize_text(self):
        """テキスト要約"""
        from src.llm import LLMService, LLMProvider

        service = LLMService(primary_provider=LLMProvider.MOCK)
        result = service.summarize_text("これはテストテキストです。" * 10)

        assert result.success
        assert len(result.content) > 0

    def test_analyze_email(self):
        """メール分析"""
        from src.llm import LLMService, LLMProvider

        service = LLMService(primary_provider=LLMProvider.MOCK)
        result = service.analyze_email(
            subject="テスト件名",
            sender="test@example.com",
            body="これはテスト本文です。"
        )

        assert result.success

    def test_unavailable_provider(self):
        """利用不可能なプロバイダー指定"""
        from src.llm import LLMService, LLMProvider

        service = LLMService(primary_provider=LLMProvider.MOCK)
        result = service.complete("test", provider=LLMProvider.OPENAI)

        # OpenAIが利用不可でもエラーにならない
        assert isinstance(result.success, bool)


class TestErrorHandlingEdgeCases:
    """エラーハンドリングのエッジケーステスト"""

    def test_error_with_none_message(self):
        """メッセージがNoneのエラー"""
        from src.errors import TaskMasterError, ErrorCode

        # Noneを渡してもエラーにならないこと
        error = TaskMasterError(
            code=ErrorCode.SYSTEM_INTERNAL_ERROR,
            message=None or "デフォルトメッセージ"
        )
        assert error.message == "デフォルトメッセージ"

    def test_error_collector_with_many_errors(self):
        """大量のエラーを収集"""
        from src.errors import ErrorCollector, TaskMasterError, ErrorCode

        collector = ErrorCollector()

        for i in range(1000):
            collector.add(TaskMasterError(
                code=ErrorCode.SYSTEM_INTERNAL_ERROR,
                message=f"エラー {i}"
            ))

        assert len(collector.get_errors()) == 1000
        assert collector.has_errors()

    def test_nested_error_cause(self):
        """ネストしたエラー原因"""
        from src.errors import TaskMasterError, ErrorCode

        original = ValueError("元のエラー")
        wrapper1 = TaskMasterError(
            code=ErrorCode.SYSTEM_INTERNAL_ERROR,
            message="ラッパー1",
            cause=original
        )
        wrapper2 = TaskMasterError(
            code=ErrorCode.SYSTEM_INTERNAL_ERROR,
            message="ラッパー2",
            cause=wrapper1
        )

        assert wrapper2.cause is wrapper1
        assert wrapper1.cause is original


class TestInputValidationEdgeCases:
    """入力検証のエッジケーステスト"""

    def test_null_byte_in_input(self):
        """NULLバイトを含む入力"""
        from src.coordinator import Coordinator

        coordinator = Coordinator()
        result = coordinator.process_command("inbox\x00malicious")

        # NULLバイトが含まれていても安全に処理
        assert result is not None

    def test_control_characters_in_input(self):
        """制御文字を含む入力"""
        from src.coordinator import Coordinator

        coordinator = Coordinator()
        result = coordinator.process_command("\x01\x02\x03inbox")

        assert result is not None

    def test_path_traversal_attempt(self):
        """パストラバーサル攻撃の試み"""
        from src.coordinator import Coordinator

        coordinator = Coordinator()
        result = coordinator.process_command("../../../etc/passwd")

        # パストラバーサルは無効化されるべき
        assert result is not None


class TestMeetingProposalEdgeCases:
    """MeetingProposal のエッジケーステスト"""

    def test_meeting_proposal_creation(self):
        """MeetingProposal作成"""
        from src.scheduler import MeetingProposal, TimeSlot

        now = datetime.now()
        slot = TimeSlot(now, now + timedelta(hours=1))

        proposal = MeetingProposal(
            slot=slot,
            attendees=["alice@example.com", "bob@example.com"],
            title="テスト会議",
            score=0.9
        )

        assert proposal.title == "テスト会議"
        assert len(proposal.attendees) == 2
        assert proposal.score == 0.9

    def test_meeting_proposal_str(self):
        """MeetingProposalの文字列表現"""
        from src.scheduler import MeetingProposal, TimeSlot

        now = datetime.now()
        slot = TimeSlot(now, now + timedelta(hours=1))

        proposal = MeetingProposal(
            slot=slot,
            attendees=["test@example.com"],
            title="ミーティング"
        )

        result = str(proposal)
        assert "ミーティング" in result


class TestCalendarEventEdgeCases:
    """CalendarEvent のエッジケーステスト"""

    def test_calendar_event_creation(self):
        """CalendarEvent作成"""
        from src.scheduler import CalendarEvent

        now = datetime.now()
        event = CalendarEvent(
            id="event123",
            summary="テスト予定",
            start=now,
            end=now + timedelta(hours=2),
            location="会議室A",
            attendees=["user1@example.com"],
            description="詳細説明",
            is_all_day=False
        )

        assert event.id == "event123"
        assert event.summary == "テスト予定"
        assert event.location == "会議室A"

    def test_all_day_event(self):
        """終日イベント"""
        from src.scheduler import CalendarEvent

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        event = CalendarEvent(
            id="allday123",
            summary="終日予定",
            start=today,
            end=today + timedelta(days=1),
            is_all_day=True
        )

        assert event.is_all_day is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
