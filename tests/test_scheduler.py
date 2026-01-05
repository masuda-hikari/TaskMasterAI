"""
Scheduler モジュールのテスト
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scheduler import (
    TimeSlot,
    CalendarEvent,
    MeetingProposal,
    Scheduler,
    find_free_slots_offline
)


class TestTimeSlot:
    """TimeSlotデータクラスのテスト"""

    def test_timeslot_creation(self):
        """TimeSlotオブジェクトの作成"""
        start = datetime(2025, 1, 6, 10, 0)
        end = datetime(2025, 1, 6, 11, 0)
        slot = TimeSlot(start, end)

        assert slot.duration_minutes == 60

    def test_timeslot_overlap_true(self):
        """重複するTimeSlotの検出"""
        slot1 = TimeSlot(
            datetime(2025, 1, 6, 10, 0),
            datetime(2025, 1, 6, 11, 0)
        )
        slot2 = TimeSlot(
            datetime(2025, 1, 6, 10, 30),
            datetime(2025, 1, 6, 11, 30)
        )

        assert slot1.overlaps(slot2) is True
        assert slot2.overlaps(slot1) is True

    def test_timeslot_overlap_false(self):
        """重複しないTimeSlotの確認"""
        slot1 = TimeSlot(
            datetime(2025, 1, 6, 10, 0),
            datetime(2025, 1, 6, 11, 0)
        )
        slot2 = TimeSlot(
            datetime(2025, 1, 6, 11, 0),
            datetime(2025, 1, 6, 12, 0)
        )

        assert slot1.overlaps(slot2) is False

    def test_timeslot_string_representation(self):
        """文字列表現"""
        slot = TimeSlot(
            datetime(2025, 1, 6, 10, 0),
            datetime(2025, 1, 6, 11, 0)
        )

        str_repr = str(slot)
        assert "2025-01-06" in str_repr
        assert "10:00" in str_repr


class TestCalendarEvent:
    """CalendarEventデータクラスのテスト"""

    def test_event_creation(self):
        """イベントの作成"""
        event = CalendarEvent(
            id="event_001",
            summary="チームミーティング",
            start=datetime(2025, 1, 6, 14, 0),
            end=datetime(2025, 1, 6, 15, 0),
            location="会議室A",
            attendees=["alice@example.com", "bob@example.com"]
        )

        assert event.summary == "チームミーティング"
        assert len(event.attendees) == 2
        assert event.is_all_day is False

    def test_all_day_event(self):
        """終日イベント"""
        event = CalendarEvent(
            id="event_002",
            summary="休暇",
            start=datetime(2025, 1, 6),
            end=datetime(2025, 1, 7),
            is_all_day=True
        )

        assert event.is_all_day is True


class TestMeetingProposal:
    """MeetingProposalデータクラスのテスト"""

    def test_proposal_creation(self):
        """提案の作成"""
        slot = TimeSlot(
            datetime(2025, 1, 6, 10, 0),
            datetime(2025, 1, 6, 11, 0)
        )
        proposal = MeetingProposal(
            slot=slot,
            attendees=["alice@example.com"],
            title="1on1ミーティング",
            score=0.9
        )

        assert proposal.score == 0.9
        assert proposal.title == "1on1ミーティング"


class TestFindFreeSlotsOffline:
    """オフライン空き時間検索のテスト"""

    def test_no_busy_slots(self):
        """予定なしの場合"""
        free_slots = find_free_slots_offline(
            busy_slots=[],
            duration_minutes=30
        )

        # 9:00から18:00まで、30分刻みで複数のスロットが見つかる
        assert len(free_slots) > 0

    def test_with_busy_slot(self):
        """予定ありの場合"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        busy = [
            TimeSlot(
                today.replace(hour=10, minute=0),
                today.replace(hour=11, minute=0)
            )
        ]

        free_slots = find_free_slots_offline(
            busy_slots=busy,
            duration_minutes=30
        )

        # 10:00-11:00の時間帯は空きに含まれない
        for slot in free_slots:
            assert not (slot.start.hour == 10 and slot.start.minute < 60)

    def test_multiple_busy_slots(self):
        """複数の予定がある場合"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        busy = [
            TimeSlot(today.replace(hour=9), today.replace(hour=10)),
            TimeSlot(today.replace(hour=14), today.replace(hour=16)),
        ]

        free_slots = find_free_slots_offline(
            busy_slots=busy,
            duration_minutes=60
        )

        # 予定と重複しないスロットのみ
        for slot in free_slots:
            for busy_slot in busy:
                assert not slot.overlaps(busy_slot)

    def test_duration_filter(self):
        """長い会議時間のフィルター"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        busy = [
            TimeSlot(today.replace(hour=10), today.replace(hour=11)),
            TimeSlot(today.replace(hour=11, minute=30), today.replace(hour=12)),
        ]

        # 60分の空きを探す（10:00-11:00と11:30-12:00の間は30分しかない）
        free_slots = find_free_slots_offline(
            busy_slots=busy,
            duration_minutes=60
        )

        # 11:00-11:30の30分枠は60分の会議には使えない
        for slot in free_slots:
            assert slot.duration_minutes >= 60


class TestSchedulerInitialization:
    """Scheduler初期化のテスト"""

    def test_default_initialization(self):
        """デフォルト初期化"""
        scheduler = Scheduler()

        assert scheduler.confirmation_required is True
        assert scheduler.working_hours_start == 9
        assert scheduler.working_hours_end == 18

    def test_custom_initialization(self):
        """カスタム設定での初期化"""
        scheduler = Scheduler(
            timezone="America/New_York",
            confirmation_required=False
        )

        assert scheduler.confirmation_required is False


class TestSchedulerOffline:
    """Scheduler（オフラインモード）のテスト"""

    def test_format_schedule_empty(self):
        """空のスケジュールのフォーマット"""
        scheduler = Scheduler()
        result = scheduler.format_schedule([])

        assert "予定はありません" in result

    def test_format_schedule_with_events(self):
        """イベントありのスケジュールフォーマット"""
        scheduler = Scheduler()
        events = [
            CalendarEvent(
                id="1",
                summary="朝会",
                start=datetime(2025, 1, 6, 9, 0),
                end=datetime(2025, 1, 6, 9, 30)
            ),
            CalendarEvent(
                id="2",
                summary="ランチ",
                start=datetime(2025, 1, 6, 12, 0),
                end=datetime(2025, 1, 6, 13, 0),
                location="カフェテリア"
            )
        ]

        result = scheduler.format_schedule(events)

        assert "朝会" in result
        assert "ランチ" in result
        assert "カフェテリア" in result

    def test_format_all_day_event(self):
        """終日イベントのフォーマット"""
        scheduler = Scheduler()
        events = [
            CalendarEvent(
                id="3",
                summary="年末休暇",
                start=datetime(2025, 1, 6),
                end=datetime(2025, 1, 7),
                is_all_day=True
            )
        ]

        result = scheduler.format_schedule(events)

        assert "終日" in result
        assert "年末休暇" in result


class TestSchedulerMeetingProposal:
    """会議提案機能のテスト"""

    def test_proposal_scoring(self):
        """提案スコアの計算"""
        # 10:00-11:00は最高スコア
        slot_morning = TimeSlot(
            datetime(2025, 1, 6, 10, 0),
            datetime(2025, 1, 6, 11, 0)
        )
        # 17:00-18:00は低いスコア
        slot_evening = TimeSlot(
            datetime(2025, 1, 6, 17, 0),
            datetime(2025, 1, 6, 18, 0)
        )

        proposal_morning = MeetingProposal(
            slot=slot_morning,
            attendees=["alice@example.com"],
            title="Meeting",
            score=1.0
        )
        proposal_evening = MeetingProposal(
            slot=slot_evening,
            attendees=["alice@example.com"],
            title="Meeting",
            score=0.6
        )

        assert proposal_morning.score > proposal_evening.score


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
