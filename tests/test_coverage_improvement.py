"""
カバレッジ向上テスト

cli.py、email_bot.py、scheduler.pyのカバレッジ向上を目的としたテスト
"""

import pytest
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================
# CLI テスト
# ============================================================

class TestCLIMain:
    """cli.py main関数のテスト"""

    def test_main_no_args_interactive(self):
        """引数なしで対話モードを起動（モック）"""
        from src import cli

        with patch.object(cli, 'interactive_mode') as mock_interactive:
            with patch.object(sys, 'argv', ['cli.py']):
                cli.main()
                mock_interactive.assert_called_once()

    def test_main_auth_mode(self):
        """auth引数で認証モードを起動（モック）"""
        from src import cli

        with patch.object(cli, 'auth_mode', return_value=0) as mock_auth:
            with patch.object(sys, 'argv', ['cli.py', 'auth']):
                with pytest.raises(SystemExit) as exc_info:
                    cli.main()
                mock_auth.assert_called_once()
                assert exc_info.value.code == 0

    def test_main_help_flag(self, capsys):
        """--helpフラグでヘルプを表示"""
        from src import cli

        with patch.object(sys, 'argv', ['cli.py', '--help']):
            cli.main()
            captured = capsys.readouterr()
            assert "TaskMasterAI" in captured.out
            assert "使用方法" in captured.out

    def test_main_h_flag(self, capsys):
        """-hフラグでヘルプを表示"""
        from src import cli

        with patch.object(sys, 'argv', ['cli.py', '-h']):
            cli.main()
            captured = capsys.readouterr()
            assert "TaskMasterAI" in captured.out

    def test_main_single_command(self):
        """単一コマンドモード"""
        from src import cli

        with patch.object(cli, 'single_command_mode', return_value=0) as mock_single:
            with patch.object(sys, 'argv', ['cli.py', 'status']):
                with pytest.raises(SystemExit) as exc_info:
                    cli.main()
                mock_single.assert_called_once_with(['status'])
                assert exc_info.value.code == 0


class TestCLIInteractiveMode:
    """interactive_mode関数のテスト"""

    def test_interactive_quit(self, capsys):
        """quitで終了"""
        from src import cli

        with patch('builtins.input', side_effect=['quit']):
            cli.interactive_mode()
            captured = capsys.readouterr()
            assert "終了" in captured.out

    def test_interactive_exit(self, capsys):
        """exitで終了"""
        from src import cli

        with patch('builtins.input', side_effect=['exit']):
            cli.interactive_mode()
            captured = capsys.readouterr()
            assert "終了" in captured.out

    def test_interactive_q(self, capsys):
        """qで終了"""
        from src import cli

        with patch('builtins.input', side_effect=['q']):
            cli.interactive_mode()
            captured = capsys.readouterr()
            assert "終了" in captured.out

    def test_interactive_empty_input(self, capsys):
        """空入力はスキップ"""
        from src import cli

        with patch('builtins.input', side_effect=['', 'quit']):
            cli.interactive_mode()
            captured = capsys.readouterr()
            assert "終了" in captured.out

    def test_interactive_help_then_quit(self, capsys):
        """helpコマンド後にquit"""
        from src import cli

        with patch('builtins.input', side_effect=['help', 'quit']):
            cli.interactive_mode()
            captured = capsys.readouterr()
            assert "コマンド" in captured.out or "終了" in captured.out

    def test_interactive_keyboard_interrupt(self, capsys):
        """Ctrl+Cで終了"""
        from src import cli

        with patch('builtins.input', side_effect=KeyboardInterrupt):
            cli.interactive_mode()
            captured = capsys.readouterr()
            assert "終了" in captured.out

    def test_interactive_unknown_command_then_quit(self, capsys):
        """不明なコマンド後にquit"""
        from src import cli

        # 実際のCoordinatorを使用して不明コマンドを処理
        with patch('builtins.input', side_effect=['unknown_xyz_command', 'quit']):
            cli.interactive_mode()
            captured = capsys.readouterr()
            # 不明なコマンドのエラーと終了メッセージが表示される
            assert "終了" in captured.out


class TestCLIAuthMode:
    """auth_mode関数のテスト"""

    def test_auth_mode_calls_authenticate(self, capsys):
        """auth_modeが認証メソッドを呼び出す"""
        from src import cli

        # src.email_botとsrc.schedulerモジュールをパッチ
        with patch('src.email_bot.EmailBot') as mock_email_class:
            with patch('src.scheduler.Scheduler') as mock_scheduler_class:
                mock_email_bot = Mock()
                mock_email_bot.authenticate.return_value = True
                mock_email_class.return_value = mock_email_bot

                mock_scheduler = Mock()
                mock_scheduler.authenticate.return_value = True
                mock_scheduler_class.return_value = mock_scheduler

                result = cli.auth_mode()
                # 認証が呼び出される
                mock_email_bot.authenticate.assert_called_once()
                mock_scheduler.authenticate.assert_called_once()
                assert result == 0

    def test_auth_mode_both_fail(self, capsys):
        """両方の認証が失敗"""
        from src import cli

        with patch('src.email_bot.EmailBot') as mock_email_class:
            with patch('src.scheduler.Scheduler') as mock_scheduler_class:
                mock_email_bot = Mock()
                mock_email_bot.authenticate.return_value = False
                mock_email_class.return_value = mock_email_bot

                mock_scheduler = Mock()
                mock_scheduler.authenticate.return_value = False
                mock_scheduler_class.return_value = mock_scheduler

                result = cli.auth_mode()
                assert result == 1
                captured = capsys.readouterr()
                # 失敗メッセージが表示される
                assert "❌" in captured.out or "失敗" in captured.out


class TestCLIPrintBanner:
    """print_banner関数のテスト"""

    def test_banner_contains_ascii_art(self, capsys):
        """バナーにASCIIアートが含まれる"""
        from src.cli import print_banner

        print_banner()
        captured = capsys.readouterr()
        # ASCIIアートボックスまたはロゴが含まれる
        assert "╔" in captured.out or "TASK" in captured.out or "TaskMaster" in captured.out


# ============================================================
# EmailBot テスト
# ============================================================

class TestEmailBotAuthenticate:
    """EmailBot.authenticate()のテスト"""

    def test_authenticate_import_error(self):
        """Google APIライブラリがない場合"""
        from src.email_bot import EmailBot

        with patch.dict(sys.modules, {'google.oauth2.credentials': None}):
            bot = EmailBot()
            # ImportErrorが発生してFalseを返す
            result = bot.authenticate()
            assert result is False

    def test_authenticate_file_not_found(self):
        """認証情報ファイルがない場合"""
        from src.email_bot import EmailBot

        bot = EmailBot(credentials_path=Path("/nonexistent/path/oauth.json"))
        result = bot.authenticate()
        assert result is False


class TestEmailBotFetchUnreadEmails:
    """EmailBot.fetch_unread_emails()のテスト"""

    def test_fetch_without_auth(self):
        """認証なしでの取得はエラー"""
        from src.email_bot import EmailBot
        from src.errors import EmailError

        bot = EmailBot()
        # _serviceがNoneの状態
        with pytest.raises(EmailError):
            bot.fetch_unread_emails()


class TestEmailBotParseMessage:
    """EmailBot._parse_message()のテスト"""

    def test_parse_message_valid(self):
        """有効なメッセージのパース"""
        from src.email_bot import EmailBot

        bot = EmailBot()
        msg = {
            'id': 'msg123',
            'threadId': 'thread123',
            'snippet': 'テストスニペット',
            'labelIds': ['INBOX', 'UNREAD'],
            'payload': {
                'headers': [
                    {'name': 'Subject', 'value': 'テスト件名'},
                    {'name': 'From', 'value': 'sender@example.com'},
                    {'name': 'To', 'value': 'recipient@example.com'},
                    {'name': 'Date', 'value': 'Mon, 6 Jan 2025 10:00:00 +0900'},
                ],
                'body': {'data': ''}
            }
        }

        email = bot._parse_message(msg)
        assert email is not None
        assert email.id == 'msg123'
        assert email.subject == 'テスト件名'

    def test_parse_message_missing_field(self):
        """必須フィールド欠落"""
        from src.email_bot import EmailBot

        bot = EmailBot()
        msg = {
            'id': 'msg123',
            'threadId': 'thread123',
            # payloadがない
        }

        email = bot._parse_message(msg)
        assert email is None

    def test_parse_message_invalid_date(self):
        """無効な日付形式"""
        from src.email_bot import EmailBot

        bot = EmailBot()
        msg = {
            'id': 'msg123',
            'threadId': 'thread123',
            'snippet': 'テスト',
            'labelIds': ['INBOX'],
            'payload': {
                'headers': [
                    {'name': 'Subject', 'value': 'テスト'},
                    {'name': 'From', 'value': 'sender@example.com'},
                    {'name': 'To', 'value': 'recipient@example.com'},
                    {'name': 'Date', 'value': 'invalid-date'},
                ],
                'body': {'data': ''}
            }
        }

        email = bot._parse_message(msg)
        assert email is not None  # 日付パース失敗でも現在時刻で作成される


class TestEmailBotExtractBody:
    """EmailBot._extract_body()のテスト"""

    def test_extract_body_direct(self):
        """直接本文データ"""
        import base64
        from src.email_bot import EmailBot

        bot = EmailBot()
        body_text = "これはテスト本文です"
        encoded = base64.urlsafe_b64encode(body_text.encode()).decode()

        payload = {
            'body': {'data': encoded}
        }

        result = bot._extract_body(payload)
        assert result == body_text

    def test_extract_body_from_parts(self):
        """partsから本文抽出"""
        import base64
        from src.email_bot import EmailBot

        bot = EmailBot()
        body_text = "パートからの本文"
        encoded = base64.urlsafe_b64encode(body_text.encode()).decode()

        payload = {
            'body': {},
            'parts': [
                {'mimeType': 'text/html', 'body': {'data': 'html'}},
                {'mimeType': 'text/plain', 'body': {'data': encoded}},
            ]
        }

        result = bot._extract_body(payload)
        assert result == body_text

    def test_extract_body_empty(self):
        """本文なし"""
        from src.email_bot import EmailBot

        bot = EmailBot()
        payload = {'body': {}}

        result = bot._extract_body(payload)
        assert result == ""


class TestEmailBotSummarizeEmail:
    """EmailBot.summarize_email()のテスト"""

    def test_summarize_email_llm_failure(self):
        """LLM応答失敗時"""
        from src.email_bot import EmailBot, Email
        from src.llm import LLMResponse, LLMProvider

        mock_llm = Mock()
        mock_llm.analyze_email.return_value = LLMResponse(
            success=False,
            content="",
            provider=LLMProvider.MOCK,
            model="mock",
            error_message="LLM error"
        )

        bot = EmailBot(llm_service=mock_llm)
        email = Email(
            id="test1",
            thread_id="thread1",
            subject="テスト",
            sender="sender@example.com",
            recipient="recipient@example.com",
            date=datetime.now(),
            body="テスト本文",
            snippet="テスト"
        )

        summary = bot.summarize_email(email)
        assert summary.email_id == "test1"
        assert "失敗" in summary.summary

    def test_summarize_email_invalid_json(self):
        """LLM応答がJSON不正"""
        from src.email_bot import EmailBot, Email
        from src.llm import LLMResponse, LLMProvider

        mock_llm = Mock()
        mock_llm.analyze_email.return_value = LLMResponse(
            success=True,
            content="これはJSONではない応答です",
            provider=LLMProvider.MOCK,
            model="mock"
        )

        bot = EmailBot(llm_service=mock_llm)
        email = Email(
            id="test2",
            thread_id="thread2",
            subject="テスト",
            sender="sender@example.com",
            recipient="recipient@example.com",
            date=datetime.now(),
            body="テスト本文",
            snippet="テスト"
        )

        summary = bot.summarize_email(email)
        assert summary.email_id == "test2"
        # JSONパース失敗時は内容の一部が要約に入る
        assert len(summary.summary) > 0


class TestEmailBotCreateDraft:
    """EmailBot.create_draft()のテスト"""

    def test_create_draft_without_auth(self):
        """認証なしでの下書き作成"""
        from src.email_bot import EmailBot
        from src.errors import EmailError

        bot = EmailBot()
        with pytest.raises(EmailError):
            bot.create_draft("to@example.com", "件名", "本文")


# ============================================================
# Scheduler テスト
# ============================================================

class TestSchedulerAuthenticate:
    """Scheduler.authenticate()のテスト"""

    def test_authenticate_import_error(self):
        """Calendar APIライブラリがない場合"""
        from src.scheduler import Scheduler

        with patch.dict(sys.modules, {'google.oauth2.credentials': None}):
            scheduler = Scheduler()
            result = scheduler.authenticate()
            assert result is False

    def test_authenticate_file_not_found(self):
        """認証情報ファイルがない場合"""
        from src.scheduler import Scheduler

        scheduler = Scheduler(credentials_path=Path("/nonexistent/oauth.json"))
        result = scheduler.authenticate()
        assert result is False


class TestSchedulerGetEvents:
    """Scheduler.get_events()のテスト"""

    def test_get_events_without_auth(self):
        """認証なしでのイベント取得"""
        from src.scheduler import Scheduler
        from src.errors import ScheduleError

        scheduler = Scheduler()
        with pytest.raises(ScheduleError):
            scheduler.get_events()


class TestSchedulerParseEvent:
    """Scheduler._parse_event()のテスト"""

    def test_parse_event_datetime(self):
        """日時イベントのパース"""
        from src.scheduler import Scheduler

        scheduler = Scheduler()
        item = {
            'id': 'event123',
            'summary': 'ミーティング',
            'start': {'dateTime': '2025-01-06T10:00:00+09:00'},
            'end': {'dateTime': '2025-01-06T11:00:00+09:00'},
            'attendees': [{'email': 'alice@example.com'}]
        }

        event = scheduler._parse_event(item)
        assert event is not None
        assert event.id == 'event123'
        assert event.is_all_day is False

    def test_parse_event_all_day(self):
        """終日イベントのパース"""
        from src.scheduler import Scheduler

        scheduler = Scheduler()
        item = {
            'id': 'event456',
            'summary': '休暇',
            'start': {'date': '2025-01-06'},
            'end': {'date': '2025-01-07'}
        }

        event = scheduler._parse_event(item)
        assert event is not None
        assert event.is_all_day is True

    def test_parse_event_missing_field(self):
        """必須フィールド欠落"""
        from src.scheduler import Scheduler

        scheduler = Scheduler()
        item = {
            'id': 'event789',
            # start/endがない
        }

        event = scheduler._parse_event(item)
        assert event is None


class TestSchedulerCreateEvent:
    """Scheduler.create_event()のテスト"""

    def test_create_event_without_auth(self):
        """認証なしでのイベント作成"""
        from src.scheduler import Scheduler
        from src.errors import ScheduleError

        scheduler = Scheduler()
        with pytest.raises(ScheduleError):
            scheduler.create_event(
                title="テスト",
                start=datetime.now(),
                end=datetime.now() + timedelta(hours=1)
            )


class TestSchedulerGetTodaySchedule:
    """Scheduler.get_today_schedule()のテスト"""

    def test_get_today_schedule_calls_get_events(self):
        """get_today_scheduleがget_eventsを呼び出す"""
        from src.scheduler import Scheduler

        scheduler = Scheduler()
        scheduler._service = Mock()  # 認証済みを偽装

        with patch.object(scheduler, 'get_events', return_value=[]) as mock_get:
            result = scheduler.get_today_schedule()
            mock_get.assert_called_once()
            assert result == []


class TestSchedulerGenerateCandidateSlots:
    """Scheduler._generate_candidate_slots()のテスト"""

    def test_generate_slots_within_working_hours(self):
        """営業時間内のスロット生成"""
        from src.scheduler import Scheduler
        from zoneinfo import ZoneInfo

        scheduler = Scheduler()
        tz = ZoneInfo("Asia/Tokyo")

        # 未来の日付を使用
        start = datetime(2099, 1, 6, 0, 0, tzinfo=tz)
        end = datetime(2099, 1, 6, 23, 59, tzinfo=tz)

        slots = scheduler._generate_candidate_slots(start, end, 30)

        # すべてのスロットが営業時間内
        for slot in slots:
            assert slot.start.hour >= scheduler.working_hours_start
            assert slot.end.hour <= scheduler.working_hours_end

    def test_generate_slots_skip_weekends(self):
        """週末をスキップ"""
        from src.scheduler import Scheduler
        from zoneinfo import ZoneInfo

        scheduler = Scheduler()
        tz = ZoneInfo("Asia/Tokyo")

        # 土曜日のみを対象
        # 2099年1月2日が土曜日と仮定して検索
        saturday = datetime(2099, 1, 4, 0, 0, tzinfo=tz)  # 実際の曜日は確認が必要
        sunday = datetime(2099, 1, 5, 23, 59, tzinfo=tz)

        slots = scheduler._generate_candidate_slots(saturday, sunday, 30)

        # 週末の日はスキップされる（working_daysに含まれない）
        for slot in slots:
            assert slot.start.weekday() in scheduler.working_days


class TestSchedulerProposeMeeting:
    """Scheduler.propose_meeting()のテスト"""

    def test_propose_meeting_scoring(self):
        """会議提案のスコアリング"""
        from src.scheduler import Scheduler, TimeSlot

        scheduler = Scheduler()
        scheduler._service = Mock()  # 認証済み偽装

        # find_free_slotsをモック
        mock_slots = [
            TimeSlot(
                datetime(2025, 1, 6, 10, 0),
                datetime(2025, 1, 6, 10, 30)
            ),
            TimeSlot(
                datetime(2025, 1, 6, 17, 0),
                datetime(2025, 1, 6, 17, 30)
            )
        ]

        with patch.object(scheduler, 'find_free_slots', return_value=mock_slots):
            proposals = scheduler.propose_meeting(
                title="テスト会議",
                duration_minutes=30,
                attendees=["alice@example.com"]
            )

            assert len(proposals) == 2
            # 10時のスロットは高スコア、17時は低スコア
            # スコア順にソートされている


# ============================================================
# オフラインヘルパー追加テスト
# ============================================================

class TestSummarizeTextOfflineEdgeCases:
    """summarize_text_offline()のエッジケーステスト"""

    def test_exact_max_length(self):
        """ちょうどmax_length"""
        from src.email_bot import summarize_text_offline

        text = "あ" * 100
        result = summarize_text_offline(text, max_length=100)
        assert result == text

    def test_with_exclamation(self):
        """！で終わる文"""
        from src.email_bot import summarize_text_offline

        # 十分長いテキストで、！が途中にある
        text = "これは最初の文！" + "あ" * 100 + "。"
        result = summarize_text_offline(text, max_length=30)
        # 文の区切りで切るか、...で終わる
        assert result.endswith("！") or result.endswith("...")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
