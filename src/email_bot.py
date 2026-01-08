"""
Email Bot Module - メール処理・要約機能

Gmail APIを使用してメールを取得し、LLMで要約を生成する
"""

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from pathlib import Path

from .llm import LLMService, create_llm_service
from .logging_config import get_logger, RequestContext, PerformanceTimer
from .errors import (
    EmailError,
    AuthError,
    LLMError,
    ErrorCode,
    ErrorContext,
    ErrorSeverity,
)

logger = get_logger(__name__, "email")


@dataclass
class Email:
    """メールデータ構造"""
    id: str
    thread_id: str
    subject: str
    sender: str
    recipient: str
    date: datetime
    body: str
    snippet: str
    is_unread: bool = True
    labels: list[str] | None = None


@dataclass
class EmailSummary:
    """メール要約結果"""
    email_id: str
    subject: str
    sender: str
    summary: str
    action_items: list[str]
    priority: str  # high, medium, low
    suggested_reply: Optional[str] = None


class EmailBot:
    """
    メール処理ボット

    Gmail APIを使用してメールを取得し、LLMで要約・分析を行う
    """

    def __init__(
        self,
        credentials_path: Optional[Path] = None,
        token_path: Optional[Path] = None,
        llm_service: Optional[LLMService] = None,
        draft_mode: bool = True
    ):
        """
        初期化

        Args:
            credentials_path: OAuth認証情報ファイルのパス
            token_path: アクセストークンファイルのパス
            llm_service: LLMサービスインスタンス
            draft_mode: True=下書きモード（送信しない）
        """
        self.credentials_path = credentials_path or Path("config/credentials/google_oauth.json")
        self.token_path = token_path or Path("config/credentials/token.json")
        self.llm_service = llm_service or create_llm_service(use_mock=True)
        self.draft_mode = draft_mode
        self._service = None

        logger.info("EmailBot初期化", data={"draft_mode": draft_mode})

    def authenticate(self) -> bool:
        """
        Gmail API認証を実行

        Returns:
            認証成功: True, 失敗: False

        Raises:
            AuthError: 認証に失敗した場合
        """
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            SCOPES = [
                'https://www.googleapis.com/auth/gmail.readonly',
                'https://www.googleapis.com/auth/gmail.compose',
            ]

            creds = None

            # 既存トークンの読み込み
            if self.token_path.exists():
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

            # トークンの更新または新規取得
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

                # トークンを保存
                self.token_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.token_path, 'w') as token:
                    token.write(creds.to_json())

            self._service = build('gmail', 'v1', credentials=creds)
            logger.info("Gmail API認証成功")
            return True

        except ImportError as e:
            error = AuthError(
                code=ErrorCode.AUTH_CREDENTIALS_MISSING,
                message="Gmail API認証ライブラリがインストールされていません",
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
                "Gmail API認証失敗",
                data={"error": str(e), "error_type": type(e).__name__}
            )
            return False

    def fetch_unread_emails(self, max_results: int = 10) -> list[Email]:
        """
        未読メールを取得

        Args:
            max_results: 最大取得件数

        Returns:
            Emailオブジェクトのリスト

        Raises:
            EmailError: 認証されていない場合やAPI呼び出しに失敗した場合
        """
        if not self._service:
            raise EmailError(
                code=ErrorCode.AUTH_FAILED,
                message="認証されていません。先にauthenticate()を呼び出してください",
                severity=ErrorSeverity.ERROR
            )

        try:
            with PerformanceTimer(logger, "fetch_unread_emails"):
                # 未読メールを検索
                results = self._service.users().messages().list(
                    userId='me',
                    q='is:unread',
                    maxResults=max_results
                ).execute()

                messages = results.get('messages', [])
                emails = []

                for msg_info in messages:
                    msg = self._service.users().messages().get(
                        userId='me',
                        id=msg_info['id'],
                        format='full'
                    ).execute()

                    email = self._parse_message(msg)
                    if email:
                        emails.append(email)

                logger.info(
                    "未読メールを取得",
                    data={"count": len(emails), "max_results": max_results}
                )
                return emails

        except EmailError:
            raise
        except Exception as e:
            error = EmailError(
                code=ErrorCode.EMAIL_FETCH_FAILED,
                message=f"メール取得エラー: {e}",
                cause=e
            )
            error.log()
            return []

    def _parse_message(self, msg: dict) -> Optional[Email]:
        """Gmail APIレスポンスをEmailオブジェクトに変換"""
        try:
            headers = {h['name']: h['value'] for h in msg['payload']['headers']}

            # 本文の取得
            body = self._extract_body(msg['payload'])

            # 日付のパース
            date_str = headers.get('Date', '')
            try:
                from email.utils import parsedate_to_datetime
                date = parsedate_to_datetime(date_str)
            except Exception:
                logger.debug(
                    "日付パース失敗、現在時刻を使用",
                    data={"date_str": date_str, "msg_id": msg.get('id')}
                )
                date = datetime.now()

            return Email(
                id=msg['id'],
                thread_id=msg['threadId'],
                subject=headers.get('Subject', '(件名なし)'),
                sender=headers.get('From', ''),
                recipient=headers.get('To', ''),
                date=date,
                body=body,
                snippet=msg.get('snippet', ''),
                is_unread='UNREAD' in msg.get('labelIds', []),
                labels=msg.get('labelIds', [])
            )
        except KeyError as e:
            logger.warning(
                "メールパースエラー: 必須フィールドが見つかりません",
                data={"missing_field": str(e), "msg_id": msg.get('id')}
            )
            return None
        except Exception as e:
            logger.warning(
                "メールパースエラー",
                data={"error": str(e), "msg_id": msg.get('id')}
            )
            return None

    def _extract_body(self, payload: dict) -> str:
        """メール本文を抽出"""
        body = ""

        if 'body' in payload and payload['body'].get('data'):
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        elif 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if part['body'].get('data'):
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        break

        return body

    def summarize_email(self, email: Email) -> EmailSummary:
        """
        メールをLLMで要約

        Args:
            email: 要約対象のメール

        Returns:
            EmailSummaryオブジェクト
        """
        # LLMサービスを使用してメール分析
        response = self.llm_service.analyze_email(
            subject=email.subject,
            sender=email.sender,
            body=email.body[:2000]
        )

        if not response.success:
            logger.warning(
                "LLM分析失敗",
                data={"email_id": email.id, "error": response.error_message}
            )
            return EmailSummary(
                email_id=email.id,
                subject=email.subject,
                sender=email.sender,
                summary="要約生成に失敗しました",
                action_items=[],
                priority='medium'
            )

        try:
            result = json.loads(response.content)
            logger.debug(
                "メール要約完了",
                data={"email_id": email.id, "priority": result.get('priority')}
            )
            return EmailSummary(
                email_id=email.id,
                subject=email.subject,
                sender=email.sender,
                summary=result.get('summary', ''),
                action_items=result.get('action_items', []),
                priority=result.get('priority', 'medium'),
                suggested_reply=result.get('suggested_reply')
            )
        except json.JSONDecodeError as e:
            # パース失敗時はデフォルト値で返す
            logger.warning(
                "LLM応答のJSONパース失敗",
                data={"email_id": email.id, "error": str(e)}
            )
            return EmailSummary(
                email_id=email.id,
                subject=email.subject,
                sender=email.sender,
                summary=response.content[:200],
                action_items=[],
                priority='medium'
            )

    def summarize_inbox(self, max_emails: int = 10) -> list[EmailSummary]:
        """
        受信トレイの未読メールを一括要約

        Args:
            max_emails: 最大処理件数

        Returns:
            EmailSummaryのリスト
        """
        with PerformanceTimer(logger, "summarize_inbox"):
            emails = self.fetch_unread_emails(max_results=max_emails)
            summaries = []

            for email in emails:
                summary = self.summarize_email(email)
                summaries.append(summary)
                logger.info(
                    "要約完了",
                    data={"subject": email.subject[:30], "priority": summary.priority}
                )

            # 優先度順にソート
            priority_order = {'high': 0, 'medium': 1, 'low': 2}
            summaries.sort(key=lambda s: priority_order.get(s.priority, 1))

            logger.info(
                "受信トレイ一括要約完了",
                data={"total": len(summaries)}
            )
            return summaries

    def create_draft(self, to: str, subject: str, body: str) -> Optional[str]:
        """
        メール下書きを作成

        Args:
            to: 宛先
            subject: 件名
            body: 本文

        Returns:
            作成された下書きのID（失敗時はNone）

        Raises:
            EmailError: 認証されていない場合やドラフト作成に失敗した場合
        """
        if not self._service:
            raise EmailError(
                code=ErrorCode.AUTH_FAILED,
                message="認証されていません",
                severity=ErrorSeverity.ERROR
            )

        if not self.draft_mode:
            logger.warning("Draft modeが無効です。下書きではなく送信が実行されます")

        try:
            from email.mime.text import MIMEText

            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

            draft = self._service.users().drafts().create(
                userId='me',
                body={'message': {'raw': raw}}
            ).execute()

            draft_id = draft.get('id')
            logger.info(
                "下書き作成完了",
                data={"draft_id": draft_id, "to": to, "subject": subject[:30]}
            )
            return draft_id

        except Exception as e:
            error = EmailError(
                code=ErrorCode.EMAIL_DRAFT_FAILED,
                message=f"下書き作成エラー: {e}",
                details={"to": to, "subject": subject},
                cause=e
            )
            error.log()
            return None


# オフラインテスト用のヘルパー関数
def summarize_text_offline(text: str, max_length: int = 200) -> str:
    """
    LLMなしでテキストを簡易要約（テスト用）

    Args:
        text: 要約対象のテキスト
        max_length: 最大文字数

    Returns:
        簡易要約文
    """
    # 改行や空白を正規化
    import re
    text = re.sub(r'\s+', ' ', text).strip()

    # 最初のmax_length文字を抽出
    if len(text) <= max_length:
        return text

    # 文の区切りで切る
    truncated = text[:max_length]
    last_period = max(
        truncated.rfind('。'),
        truncated.rfind('.'),
        truncated.rfind('！'),
        truncated.rfind('?')
    )

    if last_period > max_length // 2:
        return truncated[:last_period + 1]

    return truncated + "..."


if __name__ == "__main__":
    # テスト実行
    logging.basicConfig(level=logging.INFO)

    # オフラインテスト
    sample_text = """
    お世話になっております。

    先日ご相談させていただいた件について、ご報告いたします。
    プロジェクトの進捗は予定通りで、来週中には第一フェーズが完了する見込みです。

    つきましては、来週の水曜日または木曜日にミーティングを設定させていただければ幸いです。
    ご都合のよい日時をお知らせください。

    よろしくお願いいたします。
    """

    print("=== オフライン要約テスト ===")
    print(summarize_text_offline(sample_text))
