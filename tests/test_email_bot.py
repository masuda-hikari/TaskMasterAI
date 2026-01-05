"""
EmailBot モジュールのテスト
"""

import json
import pytest
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.email_bot import (
    Email,
    EmailSummary,
    EmailBot,
    summarize_text_offline
)


class TestEmail:
    """Emailデータクラスのテスト"""

    def test_email_creation(self):
        """Emailオブジェクトの作成テスト"""
        email = Email(
            id="test_001",
            thread_id="thread_001",
            subject="テストメール",
            sender="sender@example.com",
            recipient="recipient@example.com",
            date=datetime.now(),
            body="テスト本文です。",
            snippet="テスト本文です。"
        )

        assert email.id == "test_001"
        assert email.subject == "テストメール"
        assert email.is_unread is True

    def test_email_with_labels(self):
        """ラベル付きEmailのテスト"""
        email = Email(
            id="test_002",
            thread_id="thread_002",
            subject="重要メール",
            sender="boss@example.com",
            recipient="me@example.com",
            date=datetime.now(),
            body="重要な内容です。",
            snippet="重要な内容です。",
            labels=["IMPORTANT", "INBOX"]
        )

        assert "IMPORTANT" in email.labels


class TestEmailSummary:
    """EmailSummaryデータクラスのテスト"""

    def test_summary_creation(self):
        """EmailSummaryオブジェクトの作成テスト"""
        summary = EmailSummary(
            email_id="email_001",
            subject="プロジェクト報告",
            sender="tanaka@example.com",
            summary="Q4プロジェクトの進捗報告。API実装完了、来週ミーティング希望。",
            action_items=["ミーティング日程調整", "進捗確認"],
            priority="medium"
        )

        assert summary.priority == "medium"
        assert len(summary.action_items) == 2

    def test_summary_with_suggested_reply(self):
        """返信提案付きSummaryのテスト"""
        summary = EmailSummary(
            email_id="email_002",
            subject="日程調整",
            sender="suzuki@example.com",
            summary="ランチミーティングの誘い",
            action_items=["日程を返信"],
            priority="low",
            suggested_reply="火曜日12時でいかがでしょうか。"
        )

        assert summary.suggested_reply is not None


class TestSummarizeTextOffline:
    """オフライン要約関数のテスト"""

    def test_short_text(self):
        """短いテキストはそのまま返す"""
        text = "これは短いテストです。"
        result = summarize_text_offline(text)
        assert result == text

    def test_long_text_truncation(self):
        """長いテキストは切り詰められる"""
        long_text = "あ" * 500
        result = summarize_text_offline(long_text, max_length=100)
        assert len(result) <= 103  # max_length + "..."

    def test_sentence_boundary(self):
        """文の区切りで切り詰められる"""
        text = "これは最初の文です。これは二番目の文です。これは三番目の文です。これは四番目の文です。"
        result = summarize_text_offline(text, max_length=50)

        # 文の区切りで終わっているか確認
        assert result.endswith("。") or result.endswith("...")

    def test_whitespace_normalization(self):
        """空白が正規化される"""
        text = "これは   複数の\n\n空白を    含むテストです。"
        result = summarize_text_offline(text)
        assert "   " not in result
        assert "\n" not in result


class TestEmailBotOffline:
    """EmailBot（オフラインモード）のテスト"""

    @pytest.fixture
    def sample_emails(self):
        """サンプルメールデータの読み込み"""
        fixtures_path = Path(__file__).parent / "fixtures" / "sample_emails.json"
        with open(fixtures_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def test_email_parsing_from_fixture(self, sample_emails):
        """フィクスチャからのメールパース"""
        email_data = sample_emails[0]

        email = Email(
            id=email_data["id"],
            thread_id=email_data["thread_id"],
            subject=email_data["subject"],
            sender=email_data["sender"],
            recipient=email_data["recipient"],
            date=datetime.fromisoformat(email_data["date"]),
            body=email_data["body"],
            snippet=email_data["snippet"],
            is_unread=email_data["is_unread"],
            labels=email_data["labels"]
        )

        assert email.subject == "プロジェクト進捗報告 - Q4レビュー"
        assert email.sender == "tanaka@company.com"

    def test_priority_email_detection(self, sample_emails):
        """優先度の高いメール検出"""
        urgent_email = sample_emails[1]

        # 緊急を示すキーワードが件名に含まれているか
        assert "緊急" in urgent_email["subject"]
        assert "IMPORTANT" in urgent_email["labels"]

    def test_email_body_summarization(self, sample_emails):
        """メール本文の要約"""
        email_data = sample_emails[0]
        body = email_data["body"]

        summary = summarize_text_offline(body, max_length=100)

        # 要約が適切な長さか
        assert len(summary) <= 103

        # 主要な内容が含まれているか
        assert "田中" in summary or "Q4" in summary or "進捗" in summary

    def test_action_item_extraction_pattern(self, sample_emails):
        """アクションアイテムのパターン検出"""
        email_data = sample_emails[0]
        body = email_data["body"]

        # アクションを示すキーワードの検出
        action_keywords = ["ミーティング", "設定", "ご都合"]
        has_action = any(keyword in body for keyword in action_keywords)

        assert has_action

    def test_newsletter_categorization(self, sample_emails):
        """ニュースレターの分類"""
        newsletter = sample_emails[3]

        assert "CATEGORY_PROMOTIONS" in newsletter["labels"]
        assert "newsletter" in newsletter["sender"]


class TestEmailBotInitialization:
    """EmailBot初期化のテスト"""

    def test_default_initialization(self):
        """デフォルト初期化"""
        bot = EmailBot()

        assert bot.draft_mode is True
        assert bot._service is None

    def test_custom_initialization(self):
        """カスタム設定での初期化"""
        bot = EmailBot(
            credentials_path=Path("/custom/path"),
            draft_mode=False
        )

        assert bot.draft_mode is False
        assert bot.credentials_path == Path("/custom/path")


# 統合テスト（APIモック使用時）
class TestEmailBotIntegration:
    """EmailBot統合テスト（オフライン）"""

    @pytest.fixture
    def mock_emails(self):
        """モックメールデータ"""
        return [
            Email(
                id="mock_001",
                thread_id="thread_mock",
                subject="統合テストメール",
                sender="test@example.com",
                recipient="user@example.com",
                date=datetime.now(),
                body="これは統合テスト用のメール本文です。重要な情報が含まれています。",
                snippet="これは統合テスト用..."
            )
        ]

    def test_summarize_email_without_api(self, mock_emails):
        """API無しでの要約テスト"""
        bot = EmailBot()
        email = mock_emails[0]

        # LLM APIキーなしで実行
        summary = bot.summarize_email(email)

        # 基本情報は設定される
        assert summary.email_id == email.id
        assert summary.subject == email.subject
        assert summary.sender == email.sender

    def test_batch_summarization_simulation(self, mock_emails):
        """バッチ要約のシミュレーション"""
        # 複数メールの要約をシミュレート
        summaries = []
        for email in mock_emails:
            summary = EmailSummary(
                email_id=email.id,
                subject=email.subject,
                sender=email.sender,
                summary=summarize_text_offline(email.body, max_length=100),
                action_items=[],
                priority="medium"
            )
            summaries.append(summary)

        assert len(summaries) == len(mock_emails)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
