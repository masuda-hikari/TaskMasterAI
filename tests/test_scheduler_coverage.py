"""
Scheduler カバレッジ向上テスト

未カバー箇所:
- 120-150: authenticate()内のGoogle Calendar API認証フロー
- 161-172: authenticate()の例外処理
- 201-241: get_events()のAPI呼び出し
- 281-286: _parse_event()の例外処理
- 316-338: find_free_slots()
- 353-355: _generate_candidate_slots()の現在時刻処理
- 412: propose_meeting()のスコア計算
- 476-526: create_event()
- 581: find_free_slots_offline()の終了時刻チェック
- 595-616: __main__ブロック
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from pathlib import Path
from zoneinfo import ZoneInfo

from src.scheduler import (
    Scheduler,
    TimeSlot,
    CalendarEvent,
    MeetingProposal,
    find_free_slots_offline,
)
from src.errors import ScheduleError


class TestTimeSlot:
    """TimeSlotデータクラスのテスト"""

    def test_duration_minutes(self):
        """duration_minutesプロパティ"""
        now = datetime.now()
        slot = TimeSlot(
            start=now,
            end=now + timedelta(minutes=90)
        )
        assert slot.duration_minutes == 90

    def test_overlaps_true(self):
        """重複する場合"""
        now = datetime.now()
        slot1 = TimeSlot(now, now + timedelta(hours=1))
        slot2 = TimeSlot(now + timedelta(minutes=30), now + timedelta(hours=2))
        assert slot1.overlaps(slot2) is True
        assert slot2.overlaps(slot1) is True

    def test_overlaps_false(self):
        """重複しない場合"""
        now = datetime.now()
        slot1 = TimeSlot(now, now + timedelta(hours=1))
        slot2 = TimeSlot(now + timedelta(hours=2), now + timedelta(hours=3))
        assert slot1.overlaps(slot2) is False

    def test_overlaps_adjacent(self):
        """隣接する場合（重複なし）"""
        now = datetime.now()
        slot1 = TimeSlot(now, now + timedelta(hours=1))
        slot2 = TimeSlot(now + timedelta(hours=1), now + timedelta(hours=2))
        assert slot1.overlaps(slot2) is False

    def test_str(self):
        """文字列表現"""
        slot = TimeSlot(
            start=datetime(2026, 1, 10, 10, 0),
            end=datetime(2026, 1, 10, 11, 30)
        )
        result = str(slot)
        assert "2026-01-10 10:00" in result
        assert "11:30" in result


class TestCalendarEvent:
    """CalendarEventデータクラスのテスト"""

    def test_event_creation(self):
        """イベント作成"""
        event = CalendarEvent(
            id='event1',
            summary='Test Meeting',
            start=datetime.now(),
            end=datetime.now() + timedelta(hours=1),
            location='Room A',
            attendees=['user1@example.com', 'user2@example.com'],
            description='Test description',
            is_all_day=False
        )

        assert event.id == 'event1'
        assert event.summary == 'Test Meeting'
        assert len(event.attendees) == 2

    def test_event_defaults(self):
        """デフォルト値"""
        event = CalendarEvent(
            id='event1',
            summary='Test',
            start=datetime.now(),
            end=datetime.now() + timedelta(hours=1)
        )

        assert event.location is None
        assert event.attendees == []
        assert event.is_all_day is False


class TestMeetingProposal:
    """MeetingProposalデータクラスのテスト"""

    def test_proposal_creation(self):
        """提案作成"""
        slot = TimeSlot(
            start=datetime(2026, 1, 10, 10, 0),
            end=datetime(2026, 1, 10, 11, 0)
        )
        proposal = MeetingProposal(
            slot=slot,
            attendees=['user1@example.com'],
            title='Weekly Meeting',
            score=0.9,
            conflicts=['conflict1']
        )

        assert proposal.title == 'Weekly Meeting'
        assert proposal.score == 0.9

    def test_proposal_str(self):
        """文字列表現"""
        slot = TimeSlot(
            start=datetime(2026, 1, 10, 10, 0),
            end=datetime(2026, 1, 10, 11, 0)
        )
        proposal = MeetingProposal(
            slot=slot,
            attendees=['user1@example.com', 'user2@example.com'],
            title='Team Sync'
        )

        result = str(proposal)
        assert 'Team Sync' in result
        assert 'user1@example.com' in result


class TestSchedulerAuthenticate:
    """authenticate()メソッドのテスト"""

    def test_authenticate_import_error(self):
        """認証ライブラリがない場合"""
        scheduler = Scheduler()

        with patch.dict('sys.modules', {'google': None}):
            with patch('builtins.__import__', side_effect=ImportError("No module named 'google'")):
                result = scheduler.authenticate()
                assert result is False

    def test_authenticate_file_not_found(self):
        """認証情報ファイルが見つからない場合"""
        scheduler = Scheduler(credentials_path=Path("/nonexistent/path.json"))

        with patch('src.scheduler.Path.exists', return_value=False):
            mock_creds_module = MagicMock()
            mock_flow_module = MagicMock()

            with patch.dict('sys.modules', {
                'google': MagicMock(),
                'google.oauth2': MagicMock(),
                'google.oauth2.credentials': mock_creds_module,
                'google_auth_oauthlib': MagicMock(),
                'google_auth_oauthlib.flow': mock_flow_module,
                'google.auth': MagicMock(),
                'google.auth.transport': MagicMock(),
                'google.auth.transport.requests': MagicMock(),
                'googleapiclient': MagicMock(),
                'googleapiclient.discovery': MagicMock(),
            }):
                mock_flow_module.InstalledAppFlow.from_client_secrets_file.side_effect = FileNotFoundError("File not found")
                result = scheduler.authenticate()
                assert result is False

    def test_authenticate_generic_exception(self):
        """予期しない例外"""
        scheduler = Scheduler()

        with patch('src.scheduler.Path.exists', return_value=True):
            mock_creds_module = MagicMock()

            with patch.dict('sys.modules', {
                'google': MagicMock(),
                'google.oauth2': MagicMock(),
                'google.oauth2.credentials': mock_creds_module,
            }):
                mock_creds_module.Credentials.from_authorized_user_file.side_effect = RuntimeError("Unexpected error")
                result = scheduler.authenticate()
                assert result is False


class TestSchedulerGetEvents:
    """get_events()メソッドのテスト"""

    def test_get_events_not_authenticated(self):
        """認証されていない場合"""
        scheduler = Scheduler()
        scheduler._service = None

        with pytest.raises(ScheduleError) as exc_info:
            scheduler.get_events()
        assert "認証されていません" in str(exc_info.value)

    def test_get_events_default_dates(self):
        """デフォルトの日付範囲"""
        scheduler = Scheduler()

        mock_service = MagicMock()
        scheduler._service = mock_service

        mock_service.events().list().execute.return_value = {'items': []}

        events = scheduler.get_events()
        assert events == []

    def test_get_events_success(self):
        """イベント取得成功"""
        scheduler = Scheduler()

        mock_service = MagicMock()
        scheduler._service = mock_service

        mock_service.events().list().execute.return_value = {
            'items': [
                {
                    'id': 'event1',
                    'summary': 'Test Event',
                    'start': {'dateTime': '2026-01-10T10:00:00+09:00'},
                    'end': {'dateTime': '2026-01-10T11:00:00+09:00'},
                }
            ]
        }

        events = scheduler.get_events()
        assert len(events) == 1
        assert events[0].summary == 'Test Event'

    def test_get_events_all_day_event(self):
        """終日イベント"""
        scheduler = Scheduler()

        mock_service = MagicMock()
        scheduler._service = mock_service

        mock_service.events().list().execute.return_value = {
            'items': [
                {
                    'id': 'event1',
                    'summary': 'All Day Event',
                    'start': {'date': '2026-01-10'},
                    'end': {'date': '2026-01-11'},
                }
            ]
        }

        events = scheduler.get_events()
        assert len(events) == 1
        assert events[0].is_all_day is True

    def test_get_events_api_error(self):
        """API呼び出しエラー"""
        scheduler = Scheduler()

        mock_service = MagicMock()
        scheduler._service = mock_service

        mock_service.events().list().execute.side_effect = Exception("API Error")

        events = scheduler.get_events()
        assert events == []


class TestSchedulerParseEvent:
    """_parse_event()メソッドのテスト"""

    def test_parse_event_key_error(self):
        """必須フィールドがない場合"""
        scheduler = Scheduler()

        item = {
            'id': 'event1',
            # start/endがない
        }

        result = scheduler._parse_event(item)
        assert result is None

    def test_parse_event_generic_exception(self):
        """予期しない例外"""
        scheduler = Scheduler()

        # 不正なstart/endデータで例外を発生させる
        item = {
            'id': 'event1',
            'start': {'dateTime': 'invalid-datetime-format'},  # 不正なフォーマット
            'end': {'dateTime': '2026-01-10T11:00:00+09:00'},
        }

        result = scheduler._parse_event(item)
        assert result is None

    def test_parse_event_with_attendees(self):
        """参加者付きイベント"""
        scheduler = Scheduler()

        item = {
            'id': 'event1',
            'summary': 'Meeting',
            'start': {'dateTime': '2026-01-10T10:00:00+09:00'},
            'end': {'dateTime': '2026-01-10T11:00:00+09:00'},
            'attendees': [
                {'email': 'user1@example.com'},
                {'email': 'user2@example.com'},
            ],
            'location': 'Room A',
            'description': 'Description'
        }

        result = scheduler._parse_event(item)
        assert result is not None
        assert len(result.attendees) == 2
        assert result.location == 'Room A'


class TestSchedulerFindFreeSlots:
    """find_free_slots()メソッドのテスト"""

    def test_find_free_slots_with_events(self):
        """既存イベントがある場合"""
        scheduler = Scheduler()
        scheduler._service = MagicMock()

        tz = ZoneInfo("Asia/Tokyo")
        now = datetime.now(tz).replace(hour=9, minute=0, second=0, microsecond=0)

        # 既存イベントをモック
        test_events = [
            CalendarEvent(
                id='event1',
                summary='Existing Meeting',
                start=now.replace(hour=10),
                end=now.replace(hour=11),
                is_all_day=False
            )
        ]

        with patch.object(scheduler, 'get_events', return_value=test_events):
            slots = scheduler.find_free_slots(
                duration_minutes=30,
                start_date=now,
                end_date=now + timedelta(hours=4)
            )

        # 10:00-11:00は除外される
        for slot in slots:
            assert not (slot.start.hour == 10 and slot.start.minute == 0)

    def test_find_free_slots_all_day_event_ignored(self):
        """終日イベントは無視"""
        scheduler = Scheduler()
        scheduler._service = MagicMock()

        tz = ZoneInfo("Asia/Tokyo")
        now = datetime.now(tz).replace(hour=9, minute=0, second=0, microsecond=0)

        test_events = [
            CalendarEvent(
                id='event1',
                summary='Holiday',
                start=now,
                end=now + timedelta(days=1),
                is_all_day=True
            )
        ]

        with patch.object(scheduler, 'get_events', return_value=test_events):
            slots = scheduler.find_free_slots(
                duration_minutes=30,
                start_date=now,
                end_date=now + timedelta(hours=4)
            )

        # 終日イベントは重複チェックに含まれないので、スロットは見つかる
        assert len(slots) > 0


class TestSchedulerGenerateCandidateSlots:
    """_generate_candidate_slots()メソッドのテスト"""

    def test_generate_slots_past_time_skipped(self):
        """過去の時刻はスキップ"""
        scheduler = Scheduler()

        tz = ZoneInfo("Asia/Tokyo")
        past = datetime.now(tz) - timedelta(hours=5)

        with patch('src.scheduler.datetime') as mock_dt:
            mock_dt.now.return_value = datetime.now(tz)
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            slots = scheduler._generate_candidate_slots(
                start_date=past,
                end_date=past + timedelta(hours=8),
                duration_minutes=30
            )

        # 過去のスロットは含まれない（現在時刻以降のみ）
        now = datetime.now(tz)
        for slot in slots:
            assert slot.start >= now.replace(second=0, microsecond=0) - timedelta(minutes=30)

    def test_generate_slots_weekend_skipped(self):
        """週末はスキップ"""
        scheduler = Scheduler()

        tz = ZoneInfo("Asia/Tokyo")
        # 土曜日を見つける
        today = datetime.now(tz)
        days_until_saturday = (5 - today.weekday()) % 7
        saturday = (today + timedelta(days=days_until_saturday)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )

        slots = scheduler._generate_candidate_slots(
            start_date=saturday,
            end_date=saturday + timedelta(hours=8),
            duration_minutes=30
        )

        # 土曜日（weekday=5）のスロットは含まれない
        for slot in slots:
            assert slot.start.weekday() != 5
            assert slot.start.weekday() != 6

    def test_generate_slots_outside_working_hours(self):
        """営業時間外はスキップ"""
        scheduler = Scheduler()
        scheduler.working_hours_start = 9
        scheduler.working_hours_end = 18

        tz = ZoneInfo("Asia/Tokyo")
        # 平日を見つける
        today = datetime.now(tz)
        if today.weekday() >= 5:
            today = today + timedelta(days=(7 - today.weekday()))

        morning = today.replace(hour=6, minute=0, second=0, microsecond=0)

        slots = scheduler._generate_candidate_slots(
            start_date=morning,
            end_date=morning + timedelta(hours=15),
            duration_minutes=30
        )

        # 9:00より前と18:00以降のスロットは含まれない
        for slot in slots:
            assert slot.start.hour >= 9
            assert slot.end.hour <= 18


class TestSchedulerProposeMeeting:
    """propose_meeting()メソッドのテスト"""

    def test_propose_meeting_scoring(self):
        """会議提案のスコアリング"""
        scheduler = Scheduler()
        scheduler._service = MagicMock()

        tz = ZoneInfo("Asia/Tokyo")
        today = datetime.now(tz)
        # 平日を見つける
        if today.weekday() >= 5:
            today = today + timedelta(days=(7 - today.weekday()))

        start = today.replace(hour=9, minute=0, second=0, microsecond=0)

        with patch.object(scheduler, 'get_events', return_value=[]):
            proposals = scheduler.propose_meeting(
                title='Test Meeting',
                duration_minutes=60,
                attendees=['user@example.com'],
                start_date=start,
                end_date=start + timedelta(hours=9),
                max_proposals=10
            )

        assert len(proposals) > 0

        # スコア順にソートされている
        for i in range(len(proposals) - 1):
            assert proposals[i].score >= proposals[i + 1].score

    def test_propose_meeting_preferred_times(self):
        """10-11時と14-15時は高スコア"""
        scheduler = Scheduler()
        scheduler._service = MagicMock()

        tz = ZoneInfo("Asia/Tokyo")
        today = datetime.now(tz)
        if today.weekday() >= 5:
            today = today + timedelta(days=(7 - today.weekday()))

        start = today.replace(hour=9, minute=0, second=0, microsecond=0)

        with patch.object(scheduler, 'get_events', return_value=[]):
            proposals = scheduler.propose_meeting(
                title='Test Meeting',
                duration_minutes=60,
                attendees=['user@example.com'],
                start_date=start,
                end_date=start + timedelta(hours=9),
                max_proposals=20
            )

        # 10-11時または14-15時のスロットを見つける
        preferred_slots = [
            p for p in proposals
            if p.slot.start.hour in [10, 14]
        ]

        for slot in preferred_slots:
            assert slot.score == 1.0


class TestSchedulerCreateEvent:
    """create_event()メソッドのテスト"""

    def test_create_event_not_authenticated(self):
        """認証されていない場合"""
        scheduler = Scheduler()
        scheduler._service = None

        with pytest.raises(ScheduleError) as exc_info:
            scheduler.create_event(
                title='Test',
                start=datetime.now(),
                end=datetime.now() + timedelta(hours=1)
            )
        assert "認証されていません" in str(exc_info.value)

    def test_create_event_confirmation_warning(self):
        """確認モードの警告"""
        scheduler = Scheduler(confirmation_required=True)

        mock_service = MagicMock()
        scheduler._service = mock_service

        mock_service.events().insert().execute.return_value = {'id': 'event123'}

        with patch('src.scheduler.logger') as mock_logger:
            result = scheduler.create_event(
                title='Test Event',
                start=datetime.now(),
                end=datetime.now() + timedelta(hours=1)
            )
            mock_logger.warning.assert_called()

        assert result == 'event123'

    def test_create_event_success(self):
        """イベント作成成功"""
        scheduler = Scheduler(confirmation_required=False)

        mock_service = MagicMock()
        scheduler._service = mock_service

        mock_service.events().insert().execute.return_value = {'id': 'event456'}

        result = scheduler.create_event(
            title='Test Event',
            start=datetime.now(),
            end=datetime.now() + timedelta(hours=1),
            attendees=['user@example.com'],
            location='Room A',
            description='Test description'
        )

        assert result == 'event456'

    def test_create_event_api_error(self):
        """API呼び出しエラー"""
        scheduler = Scheduler()

        mock_service = MagicMock()
        scheduler._service = mock_service

        mock_service.events().insert().execute.side_effect = Exception("API Error")

        result = scheduler.create_event(
            title='Test Event',
            start=datetime.now(),
            end=datetime.now() + timedelta(hours=1)
        )

        assert result is None


class TestSchedulerGetTodaySchedule:
    """get_today_schedule()メソッドのテスト"""

    def test_get_today_schedule(self):
        """今日のスケジュール取得"""
        scheduler = Scheduler()
        scheduler._service = MagicMock()

        test_events = [
            CalendarEvent(
                id='event1',
                summary='Today Meeting',
                start=datetime.now(),
                end=datetime.now() + timedelta(hours=1)
            )
        ]

        with patch.object(scheduler, 'get_events', return_value=test_events) as mock_get:
            events = scheduler.get_today_schedule()

            # get_eventsが今日の日付範囲で呼ばれた
            assert mock_get.called
            assert len(events) == 1


class TestSchedulerFormatSchedule:
    """format_schedule()メソッドのテスト"""

    def test_format_schedule_empty(self):
        """予定がない場合"""
        scheduler = Scheduler()

        result = scheduler.format_schedule([])
        assert "予定はありません" in result

    def test_format_schedule_with_events(self):
        """予定がある場合"""
        scheduler = Scheduler()

        events = [
            CalendarEvent(
                id='event1',
                summary='Morning Meeting',
                start=datetime(2026, 1, 10, 10, 0),
                end=datetime(2026, 1, 10, 11, 0),
                is_all_day=False
            ),
            CalendarEvent(
                id='event2',
                summary='Lunch',
                start=datetime(2026, 1, 10, 12, 0),
                end=datetime(2026, 1, 10, 13, 0),
                location='Cafeteria',
                is_all_day=False
            )
        ]

        result = scheduler.format_schedule(events)

        assert 'Morning Meeting' in result
        assert 'Lunch' in result
        assert '📍 Cafeteria' in result

    def test_format_schedule_all_day_event(self):
        """終日イベント"""
        scheduler = Scheduler()

        events = [
            CalendarEvent(
                id='event1',
                summary='Holiday',
                start=datetime(2026, 1, 10),
                end=datetime(2026, 1, 11),
                is_all_day=True
            )
        ]

        result = scheduler.format_schedule(events)

        assert '終日' in result
        assert 'Holiday' in result


class TestFindFreeSlotsOffline:
    """find_free_slots_offline()のテスト"""

    def test_find_free_slots_basic(self):
        """基本的な空き時間検索"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        busy_slots = [
            TimeSlot(today.replace(hour=10, minute=0), today.replace(hour=11, minute=0)),
            TimeSlot(today.replace(hour=14, minute=0), today.replace(hour=15, minute=30)),
        ]

        free_slots = find_free_slots_offline(busy_slots, duration_minutes=30)

        # 10:00-11:00と14:00-15:30は含まれない
        for slot in free_slots:
            assert not (slot.start.hour == 10 and slot.start.minute == 0)
            assert not (slot.start.hour == 14 and slot.start.minute == 0)

    def test_find_free_slots_custom_hours(self):
        """カスタム営業時間"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        busy_slots = []

        free_slots = find_free_slots_offline(
            busy_slots,
            duration_minutes=60,
            start_hour=10,
            end_hour=14
        )

        # 10:00-14:00の範囲のみ
        for slot in free_slots:
            assert slot.start.hour >= 10
            assert slot.end.hour <= 14

    def test_find_free_slots_no_space(self):
        """空きがない場合"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # 全時間を埋める
        busy_slots = [
            TimeSlot(today.replace(hour=9, minute=0), today.replace(hour=18, minute=0)),
        ]

        free_slots = find_free_slots_offline(busy_slots, duration_minutes=30)

        assert free_slots == []

    def test_find_free_slots_duration_too_long(self):
        """必要時間が営業時間より長い"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        busy_slots = []

        free_slots = find_free_slots_offline(
            busy_slots,
            duration_minutes=600,  # 10時間
            start_hour=9,
            end_hour=18  # 9時間
        )

        assert free_slots == []


class TestSchedulerInit:
    """Scheduler初期化のテスト"""

    def test_init_default_values(self):
        """デフォルト値"""
        scheduler = Scheduler()

        assert scheduler.working_hours_start == 9
        assert scheduler.working_hours_end == 18
        assert scheduler.working_days == [0, 1, 2, 3, 4]
        assert scheduler.confirmation_required is True

    def test_init_custom_timezone(self):
        """カスタムタイムゾーン"""
        scheduler = Scheduler(timezone="America/New_York")

        assert str(scheduler.timezone) == "America/New_York"

    def test_init_confirmation_disabled(self):
        """確認モード無効"""
        scheduler = Scheduler(confirmation_required=False)

        assert scheduler.confirmation_required is False
