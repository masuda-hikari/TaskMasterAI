"""
EmailBot カバレッジ向上テスト

未カバー箇所:
- 99-132: authenticate()内のGmail API認証フロー
- 143-154: authenticate()の例外処理
- 176-214: fetch_unread_emails()のAPI呼び出し
- 254-259: _parse_message()の例外処理
- 349-367: summarize_inbox()
- 391-423: create_draft()
- 463-479: __main__ブロック
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import json
import base64

from src.email_bot import (
    EmailBot,
    Email,
    EmailSummary,
    summarize_text_offline,
)
from src.errors import EmailError


class TestEmailBotAuthenticate:
    """authenticate()メソッドのテスト"""

    @patch("src.email_bot.Path.exists")
    def test_authenticate_import_error(self, mock_exists):
        """認証ライブラリがない場合"""
        mock_exists.return_value = False
        bot = EmailBot()

        # google モジュールのインポートエラーをシミュレート
        with patch.dict('sys.modules', {'google': None, 'google.oauth2': None, 'google.oauth2.credentials': None}):
            with patch('builtins.__import__', side_effect=ImportError("No module named 'google'")):
                result = bot.authenticate()
                assert result is False

    def test_authenticate_credentials_file_not_found(self):
        """認証情報ファイルが見つからない場合"""
        bot = EmailBot(credentials_path=Path("/nonexistent/path.json"))

        # FileNotFoundError をシミュレート
        with patch('src.email_bot.Path.exists', return_value=False):
            # インポートをモック
            mock_creds_module = MagicMock()
            mock_flow_module = MagicMock()
            mock_request_module = MagicMock()
            mock_build_module = MagicMock()

            with patch.dict('sys.modules', {
                'google': MagicMock(),
                'google.oauth2': MagicMock(),
                'google.oauth2.credentials': mock_creds_module,
                'google_auth_oauthlib': MagicMock(),
                'google_auth_oauthlib.flow': mock_flow_module,
                'google.auth': MagicMock(),
                'google.auth.transport': MagicMock(),
                'google.auth.transport.requests': mock_request_module,
                'googleapiclient': MagicMock(),
                'googleapiclient.discovery': mock_build_module,
            }):
                # flow.run_local_server でFileNotFoundError
                mock_flow_module.InstalledAppFlow.from_client_secrets_file.side_effect = FileNotFoundError("File not found")
                result = bot.authenticate()
                assert result is False

    def test_authenticate_generic_exception(self):
        """予期しない例外の場合"""
        bot = EmailBot()

        with patch('src.email_bot.Path.exists', return_value=True):
            mock_creds_module = MagicMock()

            with patch.dict('sys.modules', {
                'google': MagicMock(),
                'google.oauth2': MagicMock(),
                'google.oauth2.credentials': mock_creds_module,
            }):
                mock_creds_module.Credentials.from_authorized_user_file.side_effect = RuntimeError("Unexpected error")
                result = bot.authenticate()
                assert result is False


class TestEmailBotFetchUnreadEmails:
    """fetch_unread_emails()メソッドのテスト"""

    def test_fetch_unread_not_authenticated(self):
        """認証されていない場合"""
        bot = EmailBot()
        bot._service = None

        with pytest.raises(EmailError) as exc_info:
            bot.fetch_unread_emails()
        assert "認証されていません" in str(exc_info.value)

    def test_fetch_unread_success(self):
        """正常にメールを取得"""
        bot = EmailBot()

        # モックサービス
        mock_service = MagicMock()
        bot._service = mock_service

        # APIレスポンスをモック
        mock_service.users().messages().list().execute.return_value = {
            'messages': [
                {'id': 'msg1', 'threadId': 'thread1'},
                {'id': 'msg2', 'threadId': 'thread2'},
            ]
        }

        # 個別メッセージ取得をモック
        test_date = "Fri, 10 Jan 2026 10:00:00 +0900"
        mock_service.users().messages().get().execute.return_value = {
            'id': 'msg1',
            'threadId': 'thread1',
            'snippet': 'Test snippet',
            'labelIds': ['UNREAD', 'INBOX'],
            'payload': {
                'headers': [
                    {'name': 'Subject', 'value': 'Test Subject'},
                    {'name': 'From', 'value': 'sender@example.com'},
                    {'name': 'To', 'value': 'recipient@example.com'},
                    {'name': 'Date', 'value': test_date},
                ],
                'body': {
                    'data': base64.urlsafe_b64encode(b'Test body content').decode()
                }
            }
        }

        emails = bot.fetch_unread_emails(max_results=5)
        assert len(emails) == 2  # 2メッセージ
        assert emails[0].id == 'msg1'

    def test_fetch_unread_api_error(self):
        """API呼び出しエラー"""
        bot = EmailBot()

        mock_service = MagicMock()
        bot._service = mock_service

        # API例外をシミュレート
        mock_service.users().messages().list().execute.side_effect = Exception("API Error")

        # エラーは空リストを返す
        emails = bot.fetch_unread_emails()
        assert emails == []

    def test_fetch_unread_empty_result(self):
        """未読メールがない場合"""
        bot = EmailBot()

        mock_service = MagicMock()
        bot._service = mock_service

        mock_service.users().messages().list().execute.return_value = {
            'messages': []
        }

        emails = bot.fetch_unread_emails()
        assert emails == []


class TestEmailBotParseMessage:
    """_parse_message()メソッドのテスト"""

    def test_parse_message_key_error(self):
        """必須フィールドがない場合"""
        bot = EmailBot()

        # payloadがない不正なメッセージ
        msg = {
            'id': 'msg1',
            'threadId': 'thread1',
        }

        result = bot._parse_message(msg)
        assert result is None

    def test_parse_message_headers_missing(self):
        """headersがない場合"""
        bot = EmailBot()

        msg = {
            'id': 'msg1',
            'threadId': 'thread1',
            'payload': {},  # headersなし
        }

        result = bot._parse_message(msg)
        assert result is None

    def test_parse_message_invalid_date(self):
        """日付パースに失敗する場合"""
        bot = EmailBot()

        msg = {
            'id': 'msg1',
            'threadId': 'thread1',
            'snippet': 'Test',
            'labelIds': ['INBOX'],
            'payload': {
                'headers': [
                    {'name': 'Subject', 'value': 'Test'},
                    {'name': 'From', 'value': 'test@example.com'},
                    {'name': 'To', 'value': 'to@example.com'},
                    {'name': 'Date', 'value': 'invalid-date-format'},
                ],
                'body': {'data': ''}
            }
        }

        result = bot._parse_message(msg)
        assert result is not None
        # 現在時刻が使用される（日付パース失敗時）
        assert isinstance(result.date, datetime)

    def test_parse_message_generic_exception(self):
        """予期しない例外"""
        bot = EmailBot()

        # __getitem__で例外を発生させる
        msg = MagicMock()
        msg.__getitem__ = MagicMock(side_effect=RuntimeError("Unexpected"))
        msg.get = MagicMock(return_value='msg1')

        result = bot._parse_message(msg)
        assert result is None


class TestEmailBotExtractBody:
    """_extract_body()メソッドのテスト"""

    def test_extract_body_from_payload(self):
        """payloadから直接本文を取得"""
        bot = EmailBot()

        payload = {
            'body': {
                'data': base64.urlsafe_b64encode(b'Direct body').decode()
            }
        }

        result = bot._extract_body(payload)
        assert result == 'Direct body'

    def test_extract_body_from_parts(self):
        """partsから本文を取得"""
        bot = EmailBot()

        payload = {
            'parts': [
                {
                    'mimeType': 'text/html',
                    'body': {'data': base64.urlsafe_b64encode(b'HTML content').decode()}
                },
                {
                    'mimeType': 'text/plain',
                    'body': {'data': base64.urlsafe_b64encode(b'Plain text content').decode()}
                },
            ]
        }

        result = bot._extract_body(payload)
        assert result == 'Plain text content'

    def test_extract_body_empty(self):
        """本文がない場合"""
        bot = EmailBot()

        payload = {}

        result = bot._extract_body(payload)
        assert result == ""

    def test_extract_body_parts_no_text_plain(self):
        """partsにtext/plainがない場合"""
        bot = EmailBot()

        payload = {
            'parts': [
                {
                    'mimeType': 'text/html',
                    'body': {'data': base64.urlsafe_b64encode(b'HTML only').decode()}
                },
            ]
        }

        result = bot._extract_body(payload)
        assert result == ""


class TestEmailBotSummarizeEmail:
    """summarize_email()メソッドのテスト"""

    def test_summarize_email_llm_failure(self):
        """LLM応答が失敗した場合"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.error_message = "LLM error"
        mock_llm.analyze_email.return_value = mock_response

        bot = EmailBot(llm_service=mock_llm)

        email = Email(
            id='test1',
            thread_id='thread1',
            subject='Test Subject',
            sender='sender@example.com',
            recipient='recipient@example.com',
            date=datetime.now(),
            body='Test body',
            snippet='Test snippet'
        )

        summary = bot.summarize_email(email)

        assert summary.email_id == 'test1'
        assert summary.summary == "要約生成に失敗しました"
        assert summary.priority == 'medium'

    def test_summarize_email_json_decode_error(self):
        """LLM応答のJSONパースに失敗した場合"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = "Not a valid JSON response"
        mock_llm.analyze_email.return_value = mock_response

        bot = EmailBot(llm_service=mock_llm)

        email = Email(
            id='test1',
            thread_id='thread1',
            subject='Test Subject',
            sender='sender@example.com',
            recipient='recipient@example.com',
            date=datetime.now(),
            body='Test body',
            snippet='Test snippet'
        )

        summary = bot.summarize_email(email)

        assert summary.email_id == 'test1'
        # 最初の200文字が使用される
        assert summary.summary == "Not a valid JSON response"
        assert summary.priority == 'medium'

    def test_summarize_email_success(self):
        """正常に要約を生成"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = json.dumps({
            'summary': 'This is a summary',
            'action_items': ['Reply to the email'],
            'priority': 'high',
            'suggested_reply': 'Thank you for your email.'
        })
        mock_llm.analyze_email.return_value = mock_response

        bot = EmailBot(llm_service=mock_llm)

        email = Email(
            id='test1',
            thread_id='thread1',
            subject='Test Subject',
            sender='sender@example.com',
            recipient='recipient@example.com',
            date=datetime.now(),
            body='Test body',
            snippet='Test snippet'
        )

        summary = bot.summarize_email(email)

        assert summary.email_id == 'test1'
        assert summary.summary == 'This is a summary'
        assert summary.priority == 'high'
        assert summary.action_items == ['Reply to the email']
        assert summary.suggested_reply == 'Thank you for your email.'


class TestEmailBotSummarizeInbox:
    """summarize_inbox()メソッドのテスト"""

    def test_summarize_inbox_success(self):
        """受信トレイ一括要約"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = json.dumps({
            'summary': 'Summary',
            'action_items': [],
            'priority': 'medium'
        })
        mock_llm.analyze_email.return_value = mock_response

        bot = EmailBot(llm_service=mock_llm)

        # fetch_unread_emailsをモック
        test_emails = [
            Email(
                id=f'test{i}',
                thread_id=f'thread{i}',
                subject=f'Subject {i}',
                sender='sender@example.com',
                recipient='recipient@example.com',
                date=datetime.now(),
                body='Body',
                snippet='Snippet'
            )
            for i in range(3)
        ]

        with patch.object(bot, 'fetch_unread_emails', return_value=test_emails):
            summaries = bot.summarize_inbox(max_emails=5)

        assert len(summaries) == 3
        for summary in summaries:
            assert summary.priority == 'medium'

    def test_summarize_inbox_priority_sort(self):
        """優先度順にソート"""
        mock_llm = MagicMock()

        # 異なる優先度を返す
        priorities = ['low', 'high', 'medium']
        mock_responses = []
        for p in priorities:
            resp = MagicMock()
            resp.success = True
            resp.content = json.dumps({
                'summary': f'Summary {p}',
                'action_items': [],
                'priority': p
            })
            mock_responses.append(resp)

        mock_llm.analyze_email.side_effect = mock_responses

        bot = EmailBot(llm_service=mock_llm)

        test_emails = [
            Email(
                id=f'test{i}',
                thread_id=f'thread{i}',
                subject=f'Subject {i}',
                sender='sender@example.com',
                recipient='recipient@example.com',
                date=datetime.now(),
                body='Body',
                snippet='Snippet'
            )
            for i in range(3)
        ]

        with patch.object(bot, 'fetch_unread_emails', return_value=test_emails):
            summaries = bot.summarize_inbox(max_emails=5)

        # high, medium, low の順
        assert summaries[0].priority == 'high'
        assert summaries[1].priority == 'medium'
        assert summaries[2].priority == 'low'


class TestEmailBotCreateDraft:
    """create_draft()メソッドのテスト"""

    def test_create_draft_not_authenticated(self):
        """認証されていない場合"""
        bot = EmailBot()
        bot._service = None

        with pytest.raises(EmailError) as exc_info:
            bot.create_draft("to@example.com", "Subject", "Body")
        assert "認証されていません" in str(exc_info.value)

    def test_create_draft_draft_mode_off_warning(self):
        """draft_modeが無効の場合に警告"""
        bot = EmailBot(draft_mode=False)

        mock_service = MagicMock()
        bot._service = mock_service

        mock_service.users().drafts().create().execute.return_value = {
            'id': 'draft123'
        }

        with patch('src.email_bot.logger') as mock_logger:
            result = bot.create_draft("to@example.com", "Subject", "Body")
            mock_logger.warning.assert_called()

        assert result == 'draft123'

    def test_create_draft_success(self):
        """下書き作成成功"""
        bot = EmailBot(draft_mode=True)

        mock_service = MagicMock()
        bot._service = mock_service

        mock_service.users().drafts().create().execute.return_value = {
            'id': 'draft456'
        }

        result = bot.create_draft("to@example.com", "Subject", "Body content")

        assert result == 'draft456'

    def test_create_draft_api_error(self):
        """API呼び出しエラー"""
        bot = EmailBot()

        mock_service = MagicMock()
        bot._service = mock_service

        mock_service.users().drafts().create().execute.side_effect = Exception("API Error")

        result = bot.create_draft("to@example.com", "Subject", "Body")

        assert result is None


class TestSummarizeTextOffline:
    """summarize_text_offline()のテスト"""

    def test_short_text(self):
        """短いテキストはそのまま返す"""
        text = "Short text."
        result = summarize_text_offline(text, max_length=200)
        assert result == "Short text."

    def test_long_text_cut_at_period(self):
        """長いテキストは文の区切りで切る"""
        text = "First sentence. Second sentence is here. Third sentence is very long and continues for a while."
        result = summarize_text_offline(text, max_length=60)
        assert result.endswith('.') or result.endswith('...')

    def test_long_text_with_japanese(self):
        """日本語の句点で切る"""
        text = "これは最初の文です。これは二つ目の文です。これは三つ目の文です。"
        result = summarize_text_offline(text, max_length=30)
        assert '。' in result or '...' in result

    def test_normalize_whitespace(self):
        """空白・改行を正規化"""
        text = "Text   with\n\nmultiple   spaces\n\nand newlines."
        result = summarize_text_offline(text, max_length=100)
        assert '\n' not in result
        assert '   ' not in result

    def test_truncate_without_period(self):
        """句点がない場合は...で終わる"""
        text = "This is a very long text without any period or sentence break that continues indefinitely"
        result = summarize_text_offline(text, max_length=40)
        assert result.endswith('...')

    def test_exclamation_mark(self):
        """感嘆符で区切る"""
        text = "Great news! This is amazing! And it continues."
        result = summarize_text_offline(text, max_length=25)
        assert '!' in result or '...' in result


class TestEmailDataclass:
    """Emailデータクラスのテスト"""

    def test_email_creation(self):
        """Email作成"""
        email = Email(
            id='test1',
            thread_id='thread1',
            subject='Subject',
            sender='sender@example.com',
            recipient='recipient@example.com',
            date=datetime.now(),
            body='Body',
            snippet='Snippet',
            is_unread=True,
            labels=['INBOX', 'UNREAD']
        )

        assert email.id == 'test1'
        assert email.is_unread is True
        assert 'INBOX' in email.labels

    def test_email_default_values(self):
        """デフォルト値"""
        email = Email(
            id='test1',
            thread_id='thread1',
            subject='Subject',
            sender='sender@example.com',
            recipient='recipient@example.com',
            date=datetime.now(),
            body='Body',
            snippet='Snippet'
        )

        assert email.is_unread is True
        assert email.labels is None


class TestEmailSummaryDataclass:
    """EmailSummaryデータクラスのテスト"""

    def test_email_summary_creation(self):
        """EmailSummary作成"""
        summary = EmailSummary(
            email_id='test1',
            subject='Subject',
            sender='sender@example.com',
            summary='This is the summary',
            action_items=['Item 1', 'Item 2'],
            priority='high',
            suggested_reply='Thank you.'
        )

        assert summary.email_id == 'test1'
        assert summary.priority == 'high'
        assert len(summary.action_items) == 2

    def test_email_summary_optional_reply(self):
        """suggested_replyはオプション"""
        summary = EmailSummary(
            email_id='test1',
            subject='Subject',
            sender='sender@example.com',
            summary='Summary',
            action_items=[],
            priority='medium'
        )

        assert summary.suggested_reply is None
