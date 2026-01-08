"""
LLM モジュールのテスト
"""

import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm import (
    LLMProvider,
    LLMConfig,
    LLMResponse,
    MockLLMClient,
    LLMService,
    create_llm_service
)


class TestLLMConfig:
    """LLMConfigのテスト"""

    def test_config_creation(self):
        """設定の作成テスト"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini",
            api_key="test_key",
            temperature=0.5
        )

        assert config.provider == LLMProvider.OPENAI
        assert config.model == "gpt-4o-mini"
        assert config.temperature == 0.5

    def test_config_defaults(self):
        """デフォルト値のテスト"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini"
        )

        assert config.api_key is None
        assert config.temperature == 0.7
        assert config.max_tokens == 1000


class TestLLMResponse:
    """LLMResponseのテスト"""

    def test_response_creation(self):
        """応答の作成テスト"""
        response = LLMResponse(
            content="テスト応答",
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini",
            tokens_used=10
        )

        assert response.content == "テスト応答"
        assert response.success is True

    def test_error_response(self):
        """エラー応答のテスト"""
        response = LLMResponse(
            content="",
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini",
            success=False,
            error_message="API呼び出し失敗"
        )

        assert response.success is False
        assert response.error_message == "API呼び出し失敗"


class TestMockLLMClient:
    """MockLLMClientのテスト"""

    def test_is_available(self):
        """利用可能性のテスト"""
        client = MockLLMClient()
        assert client.is_available() is True

    def test_complete_default(self):
        """デフォルト応答のテスト"""
        client = MockLLMClient()
        response = client.complete("テストプロンプト")

        assert response.success is True
        assert response.provider == LLMProvider.MOCK
        assert "モックLLM" in response.content

    def test_complete_json_mode(self):
        """JSON出力モードのテスト"""
        client = MockLLMClient()
        response = client.complete("テスト", json_mode=True)

        assert response.success is True

        # JSONとしてパース可能か確認
        data = json.loads(response.content)
        assert "summary" in data
        assert "priority" in data

    def test_set_custom_response(self):
        """カスタム応答の設定テスト"""
        client = MockLLMClient()
        client.set_response("天気", "今日は晴れです")

        response = client.complete("今日の天気は？")

        assert response.content == "今日は晴れです"

    def test_keyword_matching(self):
        """キーワードマッチングのテスト"""
        client = MockLLMClient()
        client.set_response("プロジェクト", "プロジェクト関連の応答")
        client.set_response("会議", "会議関連の応答")

        response1 = client.complete("プロジェクトの進捗について")
        assert "プロジェクト関連" in response1.content

        response2 = client.complete("明日の会議について")
        assert "会議関連" in response2.content


class TestLLMService:
    """LLMServiceのテスト"""

    def test_create_with_mock(self):
        """モックモードでの作成テスト"""
        service = create_llm_service(use_mock=True)

        assert LLMProvider.MOCK in service.get_available_providers()

    def test_get_available_providers(self):
        """利用可能プロバイダー取得のテスト"""
        service = create_llm_service(use_mock=True)
        providers = service.get_available_providers()

        assert isinstance(providers, list)
        assert len(providers) >= 1  # 最低でもモックは利用可能

    def test_complete_with_mock(self):
        """モックでのテキスト生成テスト"""
        service = create_llm_service(use_mock=True)
        response = service.complete("テストプロンプト")

        assert response.success is True
        assert response.provider == LLMProvider.MOCK

    def test_complete_with_system_prompt(self):
        """システムプロンプト付きテスト"""
        service = create_llm_service(use_mock=True)
        response = service.complete(
            "質問です",
            system_prompt="あなたはアシスタントです"
        )

        assert response.success is True

    def test_complete_json_mode(self):
        """JSON出力モードのテスト"""
        service = create_llm_service(use_mock=True)
        response = service.complete("分析してください", json_mode=True)

        assert response.success is True

        # JSONパース可能
        data = json.loads(response.content)
        assert isinstance(data, dict)

    def test_summarize_text(self):
        """テキスト要約のテスト"""
        service = create_llm_service(use_mock=True)

        long_text = "これは長いテキストです。" * 100
        response = service.summarize_text(long_text, max_length=200)

        assert response.success is True

    def test_analyze_email(self):
        """メール分析のテスト"""
        service = create_llm_service(use_mock=True)

        response = service.analyze_email(
            subject="プロジェクト進捗報告",
            sender="tanaka@example.com",
            body="お世話になっております。進捗をご報告します。"
        )

        assert response.success is True

        # JSON応答を検証
        data = json.loads(response.content)
        assert "summary" in data
        assert "action_items" in data
        assert "priority" in data

    def test_fallback_to_mock(self):
        """フォールバックのテスト"""
        # APIキーなしで作成（モックにフォールバック）
        service = LLMService(
            primary_provider=LLMProvider.OPENAI,
            fallback_provider=LLMProvider.MOCK
        )

        response = service.complete("テスト")

        # OpenAI利用不可なのでモックにフォールバック
        assert response.success is True

    def test_specified_provider(self):
        """プロバイダー指定のテスト"""
        service = create_llm_service(use_mock=True)

        # 存在するプロバイダーを指定
        response = service.complete(
            "テスト",
            provider=LLMProvider.MOCK
        )

        assert response.success is True
        assert response.provider == LLMProvider.MOCK

    def test_unavailable_provider(self):
        """利用不可プロバイダー指定のテスト"""
        service = create_llm_service(use_mock=True)

        # 利用不可なプロバイダーを明示的に指定
        response = service.complete(
            "テスト",
            provider=LLMProvider.OPENAI  # APIキーなしなので利用不可
        )

        # OpenAIクライアントが存在しないためエラー
        # ただしMockのみの場合はクライアントが存在しない
        assert response.success is False or response.provider == LLMProvider.MOCK


class TestLLMProvider:
    """LLMProviderのテスト"""

    def test_provider_values(self):
        """プロバイダー値のテスト"""
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.ANTHROPIC.value == "anthropic"
        assert LLMProvider.MOCK.value == "mock"


class TestEmailAnalysisIntegration:
    """メール分析統合テスト"""

    @pytest.fixture
    def llm_service(self):
        """LLMサービスフィクスチャ"""
        return create_llm_service(use_mock=True)

    def test_analyze_urgent_email(self, llm_service):
        """緊急メール分析"""
        response = llm_service.analyze_email(
            subject="【緊急】サーバー障害発生",
            sender="admin@example.com",
            body="本番サーバーでエラーが発生しています。至急対応をお願いします。"
        )

        assert response.success is True

        data = json.loads(response.content)
        assert data["priority"] in ["high", "medium", "low"]

    def test_analyze_newsletter(self, llm_service):
        """ニュースレター分析"""
        response = llm_service.analyze_email(
            subject="週刊テックニュース",
            sender="newsletter@tech.com",
            body="今週のテクノロジーニュースをお届けします。AI、クラウド、セキュリティの最新動向..."
        )

        assert response.success is True

        data = json.loads(response.content)
        assert "summary" in data

    def test_analyze_meeting_request(self, llm_service):
        """会議依頼メール分析"""
        response = llm_service.analyze_email(
            subject="来週のミーティングについて",
            sender="suzuki@example.com",
            body="来週水曜日の15時からミーティングを設定したいのですが、ご都合いかがでしょうか？"
        )

        assert response.success is True

        data = json.loads(response.content)
        assert "action_items" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
