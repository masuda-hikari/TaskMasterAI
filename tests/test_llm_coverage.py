"""
LLM モジュールのカバレッジ向上テスト

カバレッジ目標: 56% → 70%+
未カバー領域:
- 81-90, 101-141: OpenAIClient実装
- 156-165, 176-210: AnthropicClient実装
- 305, 313, 373, 382-384, 472, 479-502: 各種分岐
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm import (
    LLMProvider,
    LLMConfig,
    LLMResponse,
    OpenAIClient,
    AnthropicClient,
    MockLLMClient,
    LLMService,
    BaseLLMClient,
    create_llm_service
)


class TestOpenAIClient:
    """OpenAIClientのテスト"""

    def test_init_without_api_key(self):
        """APIキーなしでの初期化"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini",
            api_key=None
        )

        # 環境変数もクリア
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict(os.environ, {'OPENAI_API_KEY': ''}, clear=False):
                os.environ.pop('OPENAI_API_KEY', None)
                client = OpenAIClient(config)

        assert client.is_available() is False

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test_key'})
    @patch('openai.OpenAI')
    def test_init_with_env_api_key(self, mock_openai):
        """環境変数APIキーでの初期化"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini"
        )

        client = OpenAIClient(config)

        assert client.api_key == 'test_key'

    def test_init_import_error(self):
        """openaiパッケージがない場合"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini",
            api_key="test_key"
        )

        with patch.dict('sys.modules', {'openai': None}):
            with patch('builtins.__import__', side_effect=ImportError):
                # インポートエラーはcreate時に発生
                client = OpenAIClient(config)

        assert client._client is None

    @patch('openai.OpenAI')
    def test_complete_not_available(self, mock_openai):
        """利用不可時のcomplete"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini"
        )

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('OPENAI_API_KEY', None)
            client = OpenAIClient(config)
            client._client = None

        response = client.complete("テスト")

        assert response.success is False
        assert "利用できません" in response.error_message

    @patch('openai.OpenAI')
    def test_complete_success(self, mock_openai_class):
        """正常なcomplete"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini",
            api_key="test_key"
        )

        # モッククライアント設定
        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "テスト応答"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_usage = Mock()
        mock_usage.total_tokens = 100
        mock_response.usage = mock_usage
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        client = OpenAIClient(config)
        response = client.complete("テストプロンプト")

        assert response.success is True
        assert response.content == "テスト応答"
        assert response.tokens_used == 100

    @patch('openai.OpenAI')
    def test_complete_with_system_prompt(self, mock_openai_class):
        """システムプロンプト付きcomplete"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini",
            api_key="test_key"
        )

        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "応答"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock(total_tokens=50)
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        client = OpenAIClient(config)
        response = client.complete("質問", system_prompt="あなたはアシスタントです")

        assert response.success is True
        # システムプロンプトがmessagesに含まれることを確認
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs['messages']
        assert messages[0]['role'] == 'system'

    @patch('openai.OpenAI')
    def test_complete_json_mode(self, mock_openai_class):
        """JSON出力モードのcomplete"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini",
            api_key="test_key"
        )

        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = '{"key": "value"}'
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock(total_tokens=30)
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        client = OpenAIClient(config)
        response = client.complete("JSON生成", json_mode=True)

        assert response.success is True
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs.get('response_format') == {"type": "json_object"}

    @patch('openai.OpenAI')
    def test_complete_no_usage(self, mock_openai_class):
        """usageがない応答"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini",
            api_key="test_key"
        )

        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "応答"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = None  # usageなし
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        client = OpenAIClient(config)
        response = client.complete("テスト")

        assert response.success is True
        assert response.tokens_used == 0

    @patch('openai.OpenAI')
    def test_complete_api_error(self, mock_openai_class):
        """API呼び出しエラー"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o-mini",
            api_key="test_key"
        )

        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("APIエラー")
        mock_openai_class.return_value = mock_client

        client = OpenAIClient(config)
        response = client.complete("テスト")

        assert response.success is False
        assert "APIエラー" in response.error_message

    @patch('openai.OpenAI')
    def test_complete_default_model(self, mock_openai_class):
        """デフォルトモデル使用"""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model=None,  # モデル指定なし
            api_key="test_key"
        )

        mock_client = Mock()
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "応答"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock(total_tokens=10)
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        client = OpenAIClient(config)
        response = client.complete("テスト")

        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs['model'] == OpenAIClient.DEFAULT_MODEL


class TestAnthropicClient:
    """AnthropicClientのテスト"""

    def test_init_without_api_key(self):
        """APIキーなしでの初期化"""
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-haiku-latest"
        )

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('ANTHROPIC_API_KEY', None)
            client = AnthropicClient(config)

        assert client.is_available() is False

    @patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test_key'})
    @patch('anthropic.Anthropic')
    def test_init_with_env_api_key(self, mock_anthropic):
        """環境変数APIキーでの初期化"""
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-haiku-latest"
        )

        client = AnthropicClient(config)

        assert client.api_key == 'test_key'

    def test_init_import_error(self):
        """anthropicパッケージがない場合"""
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-haiku-latest",
            api_key="test_key"
        )

        with patch.dict('sys.modules', {'anthropic': None}):
            with patch('builtins.__import__', side_effect=ImportError):
                client = AnthropicClient(config)

        assert client._client is None

    @patch('anthropic.Anthropic')
    def test_complete_not_available(self, mock_anthropic):
        """利用不可時のcomplete"""
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-haiku-latest"
        )

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('ANTHROPIC_API_KEY', None)
            client = AnthropicClient(config)
            client._client = None

        response = client.complete("テスト")

        assert response.success is False
        assert "利用できません" in response.error_message

    @patch('anthropic.Anthropic')
    def test_complete_success(self, mock_anthropic_class):
        """正常なcomplete"""
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-haiku-latest",
            api_key="test_key"
        )

        # モッククライアント設定
        mock_client = Mock()
        mock_response = Mock()
        mock_content = Mock()
        mock_content.text = "テスト応答"
        mock_response.content = [mock_content]
        mock_usage = Mock()
        mock_usage.input_tokens = 50
        mock_usage.output_tokens = 50
        mock_response.usage = mock_usage
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        client = AnthropicClient(config)
        response = client.complete("テストプロンプト")

        assert response.success is True
        assert response.content == "テスト応答"
        assert response.tokens_used == 100

    @patch('anthropic.Anthropic')
    def test_complete_with_system_prompt(self, mock_anthropic_class):
        """システムプロンプト付きcomplete"""
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-haiku-latest",
            api_key="test_key"
        )

        mock_client = Mock()
        mock_response = Mock()
        mock_content = Mock()
        mock_content.text = "応答"
        mock_response.content = [mock_content]
        mock_response.usage = Mock(input_tokens=30, output_tokens=20)
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        client = AnthropicClient(config)
        response = client.complete("質問", system_prompt="アシスタント")

        assert response.success is True
        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs.get('system') == "アシスタント"

    @patch('anthropic.Anthropic')
    def test_complete_api_error(self, mock_anthropic_class):
        """API呼び出しエラー"""
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-haiku-latest",
            api_key="test_key"
        )

        mock_client = Mock()
        mock_client.messages.create.side_effect = Exception("APIエラー")
        mock_anthropic_class.return_value = mock_client

        client = AnthropicClient(config)
        response = client.complete("テスト")

        assert response.success is False
        assert "APIエラー" in response.error_message

    @patch('anthropic.Anthropic')
    def test_complete_default_model(self, mock_anthropic_class):
        """デフォルトモデル使用"""
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model=None,
            api_key="test_key"
        )

        mock_client = Mock()
        mock_response = Mock()
        mock_content = Mock()
        mock_content.text = "応答"
        mock_response.content = [mock_content]
        mock_response.usage = Mock(input_tokens=10, output_tokens=10)
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        client = AnthropicClient(config)
        response = client.complete("テスト")

        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs['model'] == AnthropicClient.DEFAULT_MODEL


class TestLLMServiceAdvanced:
    """LLMServiceの高度なテスト"""

    def test_init_with_openai_key(self):
        """OpenAI APIキーでの初期化"""
        with patch('openai.OpenAI'):
            service = LLMService(
                openai_api_key="test_openai_key"
            )

        assert LLMProvider.OPENAI in service._clients

    def test_init_with_anthropic_key(self):
        """Anthropic APIキーでの初期化"""
        with patch('anthropic.Anthropic'):
            service = LLMService(
                anthropic_api_key="test_anthropic_key"
            )

        assert LLMProvider.ANTHROPIC in service._clients

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'env_key'})
    @patch('openai.OpenAI')
    def test_init_with_env_openai_key(self, mock_openai):
        """環境変数OpenAIキーでの初期化"""
        service = LLMService()

        assert LLMProvider.OPENAI in service._clients

    @patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'env_key'})
    @patch('anthropic.Anthropic')
    def test_init_with_env_anthropic_key(self, mock_anthropic):
        """環境変数Anthropicキーでの初期化"""
        service = LLMService()

        assert LLMProvider.ANTHROPIC in service._clients

    def test_complete_with_specified_provider_not_in_clients(self):
        """存在しないプロバイダー指定"""
        service = create_llm_service(use_mock=True)

        # クライアントを削除
        if LLMProvider.OPENAI in service._clients:
            del service._clients[LLMProvider.OPENAI]

        response = service.complete("テスト", provider=LLMProvider.OPENAI)

        assert response.success is False
        assert "利用できません" in response.error_message

    def test_complete_all_providers_fail(self):
        """全プロバイダーが失敗"""
        service = LLMService(
            primary_provider=LLMProvider.MOCK,
            fallback_provider=None
        )

        # Mockクライアントを失敗させる
        mock_client = Mock()
        mock_client.is_available.return_value = False
        service._clients[LLMProvider.MOCK] = mock_client

        response = service.complete("テスト")

        assert response.success is False

    def test_fallback_chain(self):
        """フォールバックチェーンのテスト"""
        service = LLMService(
            primary_provider=LLMProvider.OPENAI,
            fallback_provider=LLMProvider.ANTHROPIC
        )

        # 両方とも利用不可だがMockにフォールバック
        response = service.complete("テスト")

        # Mockが最後に追加されるので成功する
        assert response.success is True
        assert response.provider == LLMProvider.MOCK

    @patch('openai.OpenAI')
    def test_complete_primary_fails_then_fallback(self, mock_openai_class):
        """プライマリ失敗後フォールバック"""
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("APIエラー")
        mock_openai_class.return_value = mock_client

        service = LLMService(
            openai_api_key="test_key",
            primary_provider=LLMProvider.OPENAI,
            fallback_provider=LLMProvider.MOCK
        )

        response = service.complete("テスト")

        # Mockにフォールバックして成功
        assert response.success is True
        assert response.provider == LLMProvider.MOCK


class TestCreateLLMServiceFactory:
    """create_llm_serviceファクトリのテスト"""

    def test_create_mock_service(self):
        """モックサービス作成"""
        service = create_llm_service(use_mock=True)

        assert service.primary_provider == LLMProvider.MOCK
        assert service.fallback_provider is None

    @patch('openai.OpenAI')
    def test_create_with_openai_key(self, mock_openai):
        """OpenAIキー指定で作成"""
        service = create_llm_service(openai_key="test_key")

        assert LLMProvider.OPENAI in service._clients

    @patch('anthropic.Anthropic')
    def test_create_with_anthropic_key(self, mock_anthropic):
        """Anthropicキー指定で作成"""
        service = create_llm_service(anthropic_key="test_key")

        assert LLMProvider.ANTHROPIC in service._clients


class TestMockLLMClientAdvanced:
    """MockLLMClientの高度なテスト"""

    def test_multiple_keyword_responses(self):
        """複数キーワード応答"""
        client = MockLLMClient()
        client.set_response("天気", "晴れ")
        client.set_response("時間", "12時")
        client.set_response("場所", "東京")

        assert client.complete("天気").content == "晴れ"
        assert client.complete("時間").content == "12時"
        assert client.complete("場所").content == "東京"

    def test_case_insensitive_matching(self):
        """大文字小文字を区別しないマッチング"""
        client = MockLLMClient()
        client.set_response("HELLO", "こんにちは")

        response = client.complete("hello world")

        assert response.content == "こんにちは"

    def test_custom_config(self):
        """カスタム設定"""
        config = LLMConfig(
            provider=LLMProvider.MOCK,
            model="custom-mock",
            temperature=0.5
        )

        client = MockLLMClient(config)

        assert client.config.model == "custom-mock"
        assert client.config.temperature == 0.5

    def test_tokens_used_calculation(self):
        """トークン使用量計算"""
        client = MockLLMClient()
        client.set_response("test", "one two three four five")

        response = client.complete("test")

        assert response.tokens_used == 5  # 5単語


class TestBaseLLMClient:
    """BaseLLMClient抽象クラスのテスト"""

    def test_cannot_instantiate(self):
        """直接インスタンス化できない"""
        with pytest.raises(TypeError):
            BaseLLMClient()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
