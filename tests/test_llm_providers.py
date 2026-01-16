"""
Groq/Ollama LLMプロバイダーのテスト
"""

import json
import pytest
from unittest.mock import MagicMock, patch, Mock
import urllib.request
import urllib.error

from src.llm import (
    LLMProvider,
    LLMConfig,
    LLMResponse,
    GroqClient,
    OllamaClient,
    LLMService,
    create_llm_service,
)


class TestGroqClient:
    """Groqクライアントのテスト"""

    def test_groq_client_without_api_key(self):
        """APIキーなしの場合は利用不可"""
        with patch.dict('os.environ', {}, clear=True):
            config = LLMConfig(provider=LLMProvider.GROQ, model="llama-3.1-8b-instant")
            client = GroqClient(config)
            assert client.is_available() is False

    def test_groq_client_without_package(self):
        """groqパッケージがない場合"""
        config = LLMConfig(
            provider=LLMProvider.GROQ,
            model="llama-3.1-8b-instant",
            api_key="test-key"
        )
        with patch.dict('sys.modules', {'groq': None}):
            client = GroqClient(config)
            # パッケージがない場合でもエラーにならない
            assert True

    def test_groq_client_complete_unavailable(self):
        """利用不可時のcomplete"""
        with patch.dict('os.environ', {}, clear=True):
            config = LLMConfig(provider=LLMProvider.GROQ, model="test")
            client = GroqClient(config)
            response = client.complete("test prompt")
            assert response.success is False
            assert "利用できません" in response.error_message

    def test_groq_client_complete_success(self):
        """Groq APIが正常に応答する場合"""
        config = LLMConfig(
            provider=LLMProvider.GROQ,
            model="llama-3.1-8b-instant",
            api_key="test-key"
        )
        client = GroqClient(config)

        # モッククライアントを設定
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "テスト応答"
        mock_response.usage.total_tokens = 100

        client._client = MagicMock()
        client._client.chat.completions.create.return_value = mock_response

        response = client.complete("テストプロンプト", system_prompt="システム")
        assert response.success is True
        assert response.content == "テスト応答"
        assert response.tokens_used == 100
        assert response.provider == LLMProvider.GROQ

    def test_groq_client_complete_json_mode(self):
        """JSON出力モード"""
        config = LLMConfig(
            provider=LLMProvider.GROQ,
            model="llama-3.1-8b-instant",
            api_key="test-key"
        )
        client = GroqClient(config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"key": "value"}'
        mock_response.usage.total_tokens = 50

        client._client = MagicMock()
        client._client.chat.completions.create.return_value = mock_response

        response = client.complete("テスト", json_mode=True)
        assert response.success is True
        # JSONモードでresponse_formatが設定されているか確認
        call_kwargs = client._client.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("response_format") == {"type": "json_object"}

    def test_groq_client_complete_error(self):
        """API呼び出しエラー"""
        config = LLMConfig(
            provider=LLMProvider.GROQ,
            model="llama-3.1-8b-instant",
            api_key="test-key"
        )
        client = GroqClient(config)
        client._client = MagicMock()
        client._client.chat.completions.create.side_effect = Exception("API Error")

        response = client.complete("テスト")
        assert response.success is False
        assert "API Error" in response.error_message


class TestOllamaClient:
    """Ollamaクライアントのテスト"""

    def test_ollama_client_default_url(self):
        """デフォルトURLの確認"""
        config = LLMConfig(provider=LLMProvider.OLLAMA, model="llama3.2")
        client = OllamaClient(config)
        assert client.base_url == "http://localhost:11434"

    def test_ollama_client_custom_url(self):
        """カスタムURLの指定"""
        config = LLMConfig(provider=LLMProvider.OLLAMA, model="llama3.2")
        client = OllamaClient(config, base_url="http://custom:8080")
        assert client.base_url == "http://custom:8080"

    def test_ollama_client_url_from_env(self):
        """環境変数からURLを取得"""
        with patch.dict('os.environ', {'OLLAMA_BASE_URL': 'http://env:9999'}):
            config = LLMConfig(provider=LLMProvider.OLLAMA, model="llama3.2")
            client = OllamaClient(config)
            assert client.base_url == "http://env:9999"

    @patch('urllib.request.urlopen')
    def test_ollama_is_available_true(self, mock_urlopen):
        """Ollamaサーバーが起動している場合"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = LLMConfig(provider=LLMProvider.OLLAMA, model="llama3.2")
        client = OllamaClient(config)
        assert client.is_available() is True

    @patch('urllib.request.urlopen')
    def test_ollama_is_available_false(self, mock_urlopen):
        """Ollamaサーバーが起動していない場合"""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        config = LLMConfig(provider=LLMProvider.OLLAMA, model="llama3.2")
        client = OllamaClient(config)
        assert client.is_available() is False

    def test_ollama_complete_unavailable(self):
        """サーバーが利用不可の場合"""
        config = LLMConfig(provider=LLMProvider.OLLAMA, model="llama3.2")
        client = OllamaClient(config)
        client._available = False

        response = client.complete("テスト")
        assert response.success is False
        assert "利用できません" in response.error_message

    @patch('urllib.request.urlopen')
    def test_ollama_complete_success(self, mock_urlopen):
        """正常なAPI応答"""
        config = LLMConfig(provider=LLMProvider.OLLAMA, model="llama3.2")
        client = OllamaClient(config)
        client._available = True

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "response": "Ollamaの応答です",
            "eval_count": 50,
            "prompt_eval_count": 30
        }).encode('utf-8')
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        response = client.complete("テスト", system_prompt="システム")
        assert response.success is True
        assert response.content == "Ollamaの応答です"
        assert response.tokens_used == 80
        assert response.provider == LLMProvider.OLLAMA

    @patch('urllib.request.urlopen')
    def test_ollama_complete_json_mode(self, mock_urlopen):
        """JSON出力モード"""
        config = LLMConfig(provider=LLMProvider.OLLAMA, model="llama3.2")
        client = OllamaClient(config)
        client._available = True

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "response": '{"result": "ok"}',
            "eval_count": 20,
            "prompt_eval_count": 10
        }).encode('utf-8')
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        response = client.complete("テスト", json_mode=True)
        assert response.success is True

    @patch('urllib.request.urlopen')
    def test_ollama_complete_error(self, mock_urlopen):
        """API呼び出しエラー"""
        config = LLMConfig(provider=LLMProvider.OLLAMA, model="llama3.2")
        client = OllamaClient(config)
        client._available = True

        mock_urlopen.side_effect = Exception("Network error")

        response = client.complete("テスト")
        assert response.success is False
        assert "Network error" in response.error_message


class TestLLMServiceWithNewProviders:
    """新プロバイダーを含むLLMServiceのテスト"""

    def test_service_with_groq(self):
        """Groqを含むサービス初期化"""
        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-groq-key'}, clear=True):
            with patch('src.llm.GroqClient') as MockGroq:
                mock_client = MagicMock()
                mock_client.is_available.return_value = True
                MockGroq.return_value = mock_client

                service = LLMService(groq_api_key='test-key')
                assert LLMProvider.GROQ in service._clients

    @patch('urllib.request.urlopen')
    def test_service_with_ollama(self, mock_urlopen):
        """Ollamaを含むサービス初期化"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        service = LLMService(ollama_base_url='http://localhost:11434')
        assert LLMProvider.OLLAMA in service._clients

    def test_create_llm_service_prefer_local(self):
        """ローカルLLM優先モード"""
        service = create_llm_service(prefer_local=True)
        assert service.primary_provider == LLMProvider.OLLAMA
        assert service.fallback_provider == LLMProvider.GROQ


class TestLLMProviderEnum:
    """LLMProvider Enumのテスト"""

    def test_groq_provider_value(self):
        """Groqプロバイダーの値"""
        assert LLMProvider.GROQ.value == "groq"

    def test_ollama_provider_value(self):
        """Ollamaプロバイダーの値"""
        assert LLMProvider.OLLAMA.value == "ollama"

    def test_all_providers(self):
        """全プロバイダーが定義されている"""
        providers = [p.value for p in LLMProvider]
        assert "openai" in providers
        assert "anthropic" in providers
        assert "groq" in providers
        assert "ollama" in providers
        assert "mock" in providers
