"""
Scheduler Module - カレンダー管理・スケジューリング機能

Google Calendar APIを使用して空き時間検索・会議スケジュールを行う
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from zoneinfo import ZoneInfo

from .logging_config import get_logger, PerformanceTimer
from .errors import (
    ScheduleError,
    AuthError,
    ErrorCode,
    ErrorSeverity,
)

logger = get_logger(__name__, "scheduler")


@dataclass
class TimeSlot:
    """時間枠"""
    start: datetime
    end: datetime

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)

    def overlaps(self, other: "TimeSlot") -> bool:
        """他のTimeSlotと重複するか判定"""
        return self.start < other.end and other.start < self.end

    def __str__(self) -> str:
        return f"{self.start.strftime('%Y-%m-%d %H:%M')} - {self.end.strftime('%H:%M')}"


@dataclass
class CalendarEvent:
    """カレンダーイベント"""
    id: str
    summary: str
    start: datetime
    end: datetime
    location: Optional[str] = None
    attendees: list[str] = field(default_factory=list)
    description: Optional[str] = None
    is_all_day: bool = False


@dataclass
class MeetingProposal:
    """会議提案"""
    slot: TimeSlot
    attendees: list[str]
    title: str
    score: float = 1.0  # 適合度スコア（1.0が最高）
    conflicts: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return f"{self.title}: {self.slot} (参加者: {', '.join(self.attendees)})"


class Scheduler:
    """
    カレンダー管理・スケジューリングボット

    Google Calendar APIを使用して:
    - カレンダーイベントの取得
    - 空き時間の検索
    - 会議のスケジュール提案
    """

    def __init__(
        self,
        credentials_path: Optional[Path] = None,
        token_path: Optional[Path] = None,
        timezone: str = "Asia/Tokyo",
        confirmation_required: bool = True
    ):
        """
        初期化

        Args:
            credentials_path: OAuth認証情報ファイルのパス
            token_path: アクセストークンファイルのパス
            timezone: デフォルトタイムゾーン
            confirmation_required: 予定作成前に確認が必要か
        """
        self.credentials_path = credentials_path or Path("config/credentials/google_oauth.json")
        self.token_path = token_path or Path("config/credentials/token.json")
        self.timezone = ZoneInfo(timezone)
        self.confirmation_required = confirmation_required
        self._service = None

        # 営業時間設定（デフォルト）
        self.working_hours_start = 9  # 9:00
        self.working_hours_end = 18   # 18:00
        self.working_days = [0, 1, 2, 3, 4]  # 月〜金

        logger.info(
            "Scheduler初期化",
            data={"timezone": timezone, "confirmation_required": confirmation_required}
        )

    def authenticate(self) -> bool:
        """
        Google Calendar API認証を実行

        Returns:
            認証成功: True, 失敗: False
        """
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            SCOPES = [
                'https://www.googleapis.com/auth/calendar.readonly',
                'https://www.googleapis.com/auth/calendar.events',
            ]

            creds = None

            if self.token_path.exists():
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("トークンを更新中")
                    creds.refresh(Request())
                else:
                    logger.info("新規認証フローを開始")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.credentials_path), SCOPES
                    )
                    creds = flow.run_local_server(port=0)

                self.token_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.token_path, 'w') as token:
                    token.write(creds.to_json())

            self._service = build('calendar', 'v3', credentials=creds)
            logger.info("Google Calendar API認証成功")
            return True

        except ImportError as e:
            error = AuthError(
                code=ErrorCode.AUTH_CREDENTIALS_MISSING,
                message="Calendar API認証ライブラリがインストールされていません",
                details={"missing_package": str(e)},
                cause=e
            )
            error.log()
            return False
        except FileNotFoundError as e:
            logger.error(
                "認証情報ファイルが見つかりません",
                data={"credentials_path": str(self.credentials_path), "error": str(e)}
            )
            return False
        except Exception as e:
            logger.error(
                "Google Calendar API認証失敗",
                data={"error": str(e), "error_type": type(e).__name__}
            )
            return False

    def get_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        calendar_id: str = 'primary'
    ) -> list[CalendarEvent]:
        """
        指定期間のイベントを取得

        Args:
            start_date: 開始日時（デフォルト: 今日）
            end_date: 終了日時（デフォルト: 7日後）
            calendar_id: カレンダーID

        Returns:
            CalendarEventのリスト

        Raises:
            ScheduleError: 認証されていない場合
        """
        if not self._service:
            raise ScheduleError(
                code=ErrorCode.AUTH_FAILED,
                message="認証されていません。先にauthenticate()を呼び出してください",
                severity=ErrorSeverity.ERROR
            )

        if start_date is None:
            start_date = datetime.now(self.timezone).replace(hour=0, minute=0, second=0, microsecond=0)
        if end_date is None:
            end_date = start_date + timedelta(days=7)

        try:
            with PerformanceTimer(logger, "get_events"):
                events_result = self._service.events().list(
                    calendarId=calendar_id,
                    timeMin=start_date.isoformat(),
                    timeMax=end_date.isoformat(),
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()

                events = []
                for item in events_result.get('items', []):
                    event = self._parse_event(item)
                    if event:
                        events.append(event)

                logger.info(
                    "イベントを取得",
                    data={
                        "count": len(events),
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat()
                    }
                )
                return events

        except ScheduleError:
            raise
        except Exception as e:
            error = ScheduleError(
                code=ErrorCode.SCHEDULE_FETCH_FAILED,
                message=f"イベント取得エラー: {e}",
                cause=e
            )
            error.log()
            return []

    def _parse_event(self, item: dict) -> Optional[CalendarEvent]:
        """APIレスポンスをCalendarEventに変換"""
        try:
            start_data = item.get('start', {})
            end_data = item.get('end', {})

            is_all_day = 'date' in start_data

            if is_all_day:
                start = datetime.strptime(start_data['date'], '%Y-%m-%d')
                start = start.replace(tzinfo=self.timezone)
                end = datetime.strptime(end_data['date'], '%Y-%m-%d')
                end = end.replace(tzinfo=self.timezone)
            else:
                start = datetime.fromisoformat(start_data['dateTime'])
                end = datetime.fromisoformat(end_data['dateTime'])

            attendees = [
                a.get('email', '')
                for a in item.get('attendees', [])
            ]

            return CalendarEvent(
                id=item['id'],
                summary=item.get('summary', '(タイトルなし)'),
                start=start,
                end=end,
                location=item.get('location'),
                attendees=attendees,
                description=item.get('description'),
                is_all_day=is_all_day
            )
        except KeyError as e:
            logger.warning(
                "イベントパースエラー: 必須フィールドが見つかりません",
                data={"missing_field": str(e), "event_id": item.get('id')}
            )
            return None
        except Exception as e:
            logger.warning(
                "イベントパースエラー",
                data={"error": str(e), "event_id": item.get('id')}
            )
            return None

    def find_free_slots(
        self,
        duration_minutes: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        attendee_emails: Optional[list[str]] = None
    ) -> list[TimeSlot]:
        """
        空き時間枠を検索

        Args:
            duration_minutes: 必要な時間（分）
            start_date: 検索開始日時
            end_date: 検索終了日時
            attendee_emails: 参加者のメールアドレス（freebusyチェック用）

        Returns:
            利用可能なTimeSlotのリスト
        """
        if start_date is None:
            start_date = datetime.now(self.timezone)
        if end_date is None:
            end_date = start_date + timedelta(days=7)

        # 既存イベントを取得
        events = self.get_events(start_date, end_date)

        # 営業時間内の候補スロットを生成
        candidate_slots = self._generate_candidate_slots(
            start_date, end_date, duration_minutes
        )

        # イベントと重複するスロットを除外
        free_slots = []
        for slot in candidate_slots:
            is_free = True
            for event in events:
                if not event.is_all_day:
                    event_slot = TimeSlot(event.start, event.end)
                    if slot.overlaps(event_slot):
                        is_free = False
                        break

            if is_free:
                free_slots.append(slot)

        logger.info(
            "空き時間を検出",
            data={"count": len(free_slots), "duration_minutes": duration_minutes}
        )
        return free_slots

    def _generate_candidate_slots(
        self,
        start_date: datetime,
        end_date: datetime,
        duration_minutes: int
    ) -> list[TimeSlot]:
        """営業時間内の候補スロットを生成"""
        slots = []
        current = start_date.replace(minute=0, second=0, microsecond=0)

        # 現在時刻より前は除外
        now = datetime.now(self.timezone)
        if current < now:
            current = now.replace(minute=(now.minute // 30) * 30, second=0, microsecond=0)
            if current < now:
                current += timedelta(minutes=30)

        while current < end_date:
            # 営業日かチェック
            if current.weekday() in self.working_days:
                # 営業時間内かチェック
                if self.working_hours_start <= current.hour < self.working_hours_end:
                    slot_end = current + timedelta(minutes=duration_minutes)

                    # 終了時刻も営業時間内かチェック
                    if slot_end.hour <= self.working_hours_end:
                        slots.append(TimeSlot(current, slot_end))

            # 30分刻みで次へ
            current += timedelta(minutes=30)

            # 営業時間外なら翌日の営業開始時刻へ
            if current.hour >= self.working_hours_end:
                current = current.replace(hour=self.working_hours_start, minute=0)
                current += timedelta(days=1)

        return slots

    def propose_meeting(
        self,
        title: str,
        duration_minutes: int,
        attendees: list[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_proposals: int = 5
    ) -> list[MeetingProposal]:
        """
        会議時間を提案

        Args:
            title: 会議タイトル
            duration_minutes: 会議時間（分）
            attendees: 参加者メールアドレス
            start_date: 検索開始日時
            end_date: 検索終了日時
            max_proposals: 最大提案数

        Returns:
            MeetingProposalのリスト（スコア順）
        """
        free_slots = self.find_free_slots(
            duration_minutes, start_date, end_date, attendees
        )

        proposals = []
        for slot in free_slots[:max_proposals]:
            # スコア計算（朝・昼過ぎを優先）
            hour = slot.start.hour
            if 10 <= hour <= 11 or 14 <= hour <= 15:
                score = 1.0
            elif 9 <= hour <= 12 or 13 <= hour <= 16:
                score = 0.8
            else:
                score = 0.6

            proposals.append(MeetingProposal(
                slot=slot,
                attendees=attendees,
                title=title,
                score=score
            ))

        # スコア順にソート
        proposals.sort(key=lambda p: p.score, reverse=True)

        logger.info(
            "会議提案を生成",
            data={
                "count": len(proposals),
                "title": title,
                "duration": duration_minutes,
                "attendees_count": len(attendees)
            }
        )
        return proposals

    def create_event(
        self,
        title: str,
        start: datetime,
        end: datetime,
        attendees: Optional[list[str]] = None,
        location: Optional[str] = None,
        description: Optional[str] = None,
        calendar_id: str = 'primary',
        send_notifications: bool = True
    ) -> Optional[str]:
        """
        カレンダーイベントを作成

        確認が必要な場合は確認済みフラグが必要

        Args:
            title: イベントタイトル
            start: 開始日時
            end: 終了日時
            attendees: 参加者メールアドレス
            location: 場所
            description: 説明
            calendar_id: カレンダーID
            send_notifications: 参加者に通知を送るか

        Returns:
            作成されたイベントのID（失敗時はNone）

        Raises:
            ScheduleError: 認証されていない場合やイベント作成に失敗した場合
        """
        if not self._service:
            raise ScheduleError(
                code=ErrorCode.AUTH_FAILED,
                message="認証されていません",
                severity=ErrorSeverity.ERROR
            )

        if self.confirmation_required:
            logger.warning("確認モードが有効です。イベント作成には明示的な確認が必要です")
            # 実際の実装では確認フローを挟む

        try:
            event = {
                'summary': title,
                'start': {
                    'dateTime': start.isoformat(),
                    'timeZone': str(self.timezone),
                },
                'end': {
                    'dateTime': end.isoformat(),
                    'timeZone': str(self.timezone),
                },
            }

            if location:
                event['location'] = location
            if description:
                event['description'] = description
            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]

            result = self._service.events().insert(
                calendarId=calendar_id,
                body=event,
                sendNotifications=send_notifications
            ).execute()

            event_id = result.get('id')
            logger.info(
                "イベント作成完了",
                data={
                    "event_id": event_id,
                    "title": title,
                    "start": start.isoformat(),
                    "attendees_count": len(attendees) if attendees else 0
                }
            )
            return event_id

        except Exception as e:
            error = ScheduleError(
                code=ErrorCode.SCHEDULE_CREATE_FAILED,
                message=f"イベント作成エラー: {e}",
                details={"title": title, "start": start.isoformat()},
                cause=e
            )
            error.log()
            return None

    def get_today_schedule(self) -> list[CalendarEvent]:
        """今日のスケジュールを取得"""
        today = datetime.now(self.timezone).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        return self.get_events(today, tomorrow)

    def format_schedule(self, events: list[CalendarEvent]) -> str:
        """スケジュールを読みやすい形式で出力"""
        if not events:
            return "予定はありません。"

        lines = []
        for event in events:
            if event.is_all_day:
                time_str = "終日"
            else:
                time_str = f"{event.start.strftime('%H:%M')}-{event.end.strftime('%H:%M')}"

            lines.append(f"  {time_str}: {event.summary}")
            if event.location:
                lines.append(f"           📍 {event.location}")

        return "\n".join(lines)


# オフラインテスト用のヘルパー
def find_free_slots_offline(
    busy_slots: list[TimeSlot],
    duration_minutes: int,
    start_hour: int = 9,
    end_hour: int = 18
) -> list[TimeSlot]:
    """
    オフラインで空き時間を計算（テスト用）

    Args:
        busy_slots: 予約済みの時間枠
        duration_minutes: 必要な時間（分）
        start_hour: 営業開始時刻
        end_hour: 営業終了時刻

    Returns:
        利用可能なTimeSlotのリスト
    """
    today = datetime.now().replace(hour=start_hour, minute=0, second=0, microsecond=0)

    free_slots = []
    current = today

    while current.hour < end_hour:
        slot_end = current + timedelta(minutes=duration_minutes)

        if slot_end.hour > end_hour:
            break

        candidate = TimeSlot(current, slot_end)
        is_free = all(not candidate.overlaps(busy) for busy in busy_slots)

        if is_free:
            free_slots.append(candidate)

        current += timedelta(minutes=30)

    return free_slots


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # オフラインテスト
    print("=== オフライン空き時間検索テスト ===")

    # 既存の予定をシミュレート
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    busy = [
        TimeSlot(today.replace(hour=10, minute=0), today.replace(hour=11, minute=0)),
        TimeSlot(today.replace(hour=14, minute=0), today.replace(hour=15, minute=30)),
    ]

    print("予約済み:")
    for slot in busy:
        print(f"  {slot}")

    # 30分の空き時間を検索
    free = find_free_slots_offline(busy, duration_minutes=30)

    print("\n空き時間（30分）:")
    for slot in free[:5]:
        print(f"  {slot}")
