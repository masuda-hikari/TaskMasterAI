"""
LLM Module - LLM API連携

OpenAI/Anthropicを抽象化したLLMインターフェース
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """LLMプロバイダー"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    OLLAMA = "ollama"
    MOCK = "mock"


@dataclass
class LLMConfig:
    """LLM設定"""
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1000


@dataclass
class LLMResponse:
    """LLM応答"""
    content: str
    provider: LLMProvider
    model: str
    tokens_used: int = 0
    success: bool = True
    error_message: Optional[str] = None


class BaseLLMClient(ABC):
    """LLMクライアント基底クラス"""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False
    ) -> LLMResponse:
        """
        テキスト生成

        Args:
            prompt: ユーザープロンプト
            system_prompt: システムプロンプト
            json_mode: JSON出力モード

        Returns:
            LLMResponse
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """利用可能かどうか"""
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI APIクライアント"""

    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, config: LLMConfig):
        self.config = config
        self.api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        self._client = None

        if self.api_key:
            try:
                import openai
                self._client = openai.OpenAI(api_key=self.api_key)
            except ImportError:
                logger.warning("openaiパッケージがインストールされていません")

    def is_available(self) -> bool:
        return self._client is not None and self.api_key is not None

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False
    ) -> LLMResponse:
        if not self.is_available():
            return LLMResponse(
                content="",
                provider=LLMProvider.OPENAI,
                model=self.config.model,
                success=False,
                error_message="OpenAI APIが利用できません"
            )

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            kwargs = {
                "model": self.config.model or self.DEFAULT_MODEL,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }

            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = self._client.chat.completions.create(**kwargs)

            content = response.choices[0].message.content
            tokens = response.usage.total_tokens if response.usage else 0

            return LLMResponse(
                content=content,
                provider=LLMProvider.OPENAI,
                model=self.config.model,
                tokens_used=tokens,
                success=True
            )

        except Exception as e:
            logger.error(f"OpenAI API呼び出しエラー: {e}")
            return LLMResponse(
                content="",
                provider=LLMProvider.OPENAI,
                model=self.config.model,
                success=False,
                error_message=str(e)
            )


class AnthropicClient(BaseLLMClient):
    """Anthropic APIクライアント"""

    DEFAULT_MODEL = "claude-3-5-haiku-latest"

    def __init__(self, config: LLMConfig):
        self.config = config
        self.api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
        self._client = None

        if self.api_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                logger.warning("anthropicパッケージがインストールされていません")

    def is_available(self) -> bool:
        return self._client is not None and self.api_key is not None

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False
    ) -> LLMResponse:
        if not self.is_available():
            return LLMResponse(
                content="",
                provider=LLMProvider.ANTHROPIC,
                model=self.config.model,
                success=False,
                error_message="Anthropic APIが利用できません"
            )

        try:
            kwargs = {
                "model": self.config.model or self.DEFAULT_MODEL,
                "max_tokens": self.config.max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }

            if system_prompt:
                kwargs["system"] = system_prompt

            response = self._client.messages.create(**kwargs)

            content = response.content[0].text
            tokens = response.usage.input_tokens + response.usage.output_tokens

            return LLMResponse(
                content=content,
                provider=LLMProvider.ANTHROPIC,
                model=self.config.model,
                tokens_used=tokens,
                success=True
            )

        except Exception as e:
            logger.error(f"Anthropic API呼び出しエラー: {e}")
            return LLMResponse(
                content="",
                provider=LLMProvider.ANTHROPIC,
                model=self.config.model,
                success=False,
                error_message=str(e)
            )


class GroqClient(BaseLLMClient):
    """Groq APIクライアント（無料枠あり、高速推論）"""

    DEFAULT_MODEL = "llama-3.1-8b-instant"

    def __init__(self, config: LLMConfig):
        self.config = config
        self.api_key = config.api_key or os.getenv("GROQ_API_KEY")
        self._client = None

        if self.api_key:
            try:
                from groq import Groq
                self._client = Groq(api_key=self.api_key)
            except ImportError:
                logger.warning("groqパッケージがインストールされていません: pip install groq")

    def is_available(self) -> bool:
        return self._client is not None and self.api_key is not None

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False
    ) -> LLMResponse:
        if not self.is_available():
            return LLMResponse(
                content="",
                provider=LLMProvider.GROQ,
                model=self.config.model,
                success=False,
                error_message="Groq APIが利用できません"
            )

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            kwargs = {
                "model": self.config.model or self.DEFAULT_MODEL,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }

            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = self._client.chat.completions.create(**kwargs)

            content = response.choices[0].message.content
            tokens = response.usage.total_tokens if response.usage else 0

            return LLMResponse(
                content=content,
                provider=LLMProvider.GROQ,
                model=self.config.model or self.DEFAULT_MODEL,
                tokens_used=tokens,
                success=True
            )

        except Exception as e:
            logger.error(f"Groq API呼び出しエラー: {e}")
            return LLMResponse(
                content="",
                provider=LLMProvider.GROQ,
                model=self.config.model,
                success=False,
                error_message=str(e)
            )


class OllamaClient(BaseLLMClient):
    """Ollama APIクライアント（ローカルLLM、完全無料）"""

    DEFAULT_MODEL = "llama3.2"
    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, config: LLMConfig, base_url: Optional[str] = None):
        self.config = config
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", self.DEFAULT_BASE_URL)
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Ollamaサーバーが起動しているか確認"""
        if self._available is not None:
            return self._available

        try:
            import urllib.request
            import urllib.error

            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as response:
                self._available = response.status == 200
        except Exception:
            self._available = False

        return self._available

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False
    ) -> LLMResponse:
        if not self.is_available():
            return LLMResponse(
                content="",
                provider=LLMProvider.OLLAMA,
                model=self.config.model,
                success=False,
                error_message="Ollamaサーバーが利用できません。ollama serveを実行してください"
            )

        try:
            import urllib.request
            import urllib.error

            model = self.config.model or self.DEFAULT_MODEL
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            payload = {
                "model": model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": self.config.temperature,
                    "num_predict": self.config.max_tokens,
                }
            }

            if json_mode:
                payload["format"] = "json"

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))

            content = result.get("response", "")
            tokens = result.get("eval_count", 0) + result.get("prompt_eval_count", 0)

            return LLMResponse(
                content=content,
                provider=LLMProvider.OLLAMA,
                model=model,
                tokens_used=tokens,
                success=True
            )

        except Exception as e:
            logger.error(f"Ollama API呼び出しエラー: {e}")
            return LLMResponse(
                content="",
                provider=LLMProvider.OLLAMA,
                model=self.config.model,
                success=False,
                error_message=str(e)
            )


class MockLLMClient(BaseLLMClient):
    """テスト用モックLLMクライアント"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig(
            provider=LLMProvider.MOCK,
            model="mock-model"
        )
        self._responses: dict[str, str] = {}

    def is_available(self) -> bool:
        return True

    def set_response(self, keyword: str, response: str):
        """特定キーワードに対する応答を設定"""
        self._responses[keyword] = response

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False
    ) -> LLMResponse:
        # キーワードマッチ
        for keyword, response in self._responses.items():
            if keyword.lower() in prompt.lower():
                return LLMResponse(
                    content=response,
                    provider=LLMProvider.MOCK,
                    model="mock-model",
                    tokens_used=len(response.split()),
                    success=True
                )

        # デフォルト応答
        if json_mode:
            content = json.dumps({
                "summary": "モックLLMによる要約です",
                "action_items": [],
                "priority": "medium",
                "suggested_reply": None
            })
        else:
            content = f"モックLLM応答: prompt長={len(prompt)}"

        return LLMResponse(
            content=content,
            provider=LLMProvider.MOCK,
            model="mock-model",
            tokens_used=10,
            success=True
        )


class LLMService:
    """
    LLMサービス

    複数プロバイダーを統合し、フォールバック機能を提供
    """

    def __init__(
        self,
        primary_provider: LLMProvider = LLMProvider.OPENAI,
        fallback_provider: Optional[LLMProvider] = LLMProvider.ANTHROPIC,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初期化

        Args:
            primary_provider: 優先プロバイダー
            fallback_provider: フォールバックプロバイダー
            openai_api_key: OpenAI APIキー
            anthropic_api_key: Anthropic APIキー
            groq_api_key: Groq APIキー（無料枠あり）
            ollama_base_url: OllamaサーバーURL（デフォルト: localhost:11434）
            model: 使用モデル名
        """
        self.primary_provider = primary_provider
        self.fallback_provider = fallback_provider

        self._clients: dict[LLMProvider, BaseLLMClient] = {}

        # OpenAIクライアント初期化
        if openai_api_key or os.getenv("OPENAI_API_KEY"):
            self._clients[LLMProvider.OPENAI] = OpenAIClient(LLMConfig(
                provider=LLMProvider.OPENAI,
                model=model or OpenAIClient.DEFAULT_MODEL,
                api_key=openai_api_key
            ))

        # Anthropicクライアント初期化
        if anthropic_api_key or os.getenv("ANTHROPIC_API_KEY"):
            self._clients[LLMProvider.ANTHROPIC] = AnthropicClient(LLMConfig(
                provider=LLMProvider.ANTHROPIC,
                model=model or AnthropicClient.DEFAULT_MODEL,
                api_key=anthropic_api_key
            ))

        # Groqクライアント初期化（無料枠あり、高速推論）
        if groq_api_key or os.getenv("GROQ_API_KEY"):
            self._clients[LLMProvider.GROQ] = GroqClient(LLMConfig(
                provider=LLMProvider.GROQ,
                model=model or GroqClient.DEFAULT_MODEL,
                api_key=groq_api_key
            ))

        # Ollamaクライアント初期化（ローカルLLM、完全無料）
        ollama_client = OllamaClient(
            LLMConfig(
                provider=LLMProvider.OLLAMA,
                model=model or OllamaClient.DEFAULT_MODEL
            ),
            base_url=ollama_base_url
        )
        if ollama_client.is_available():
            self._clients[LLMProvider.OLLAMA] = ollama_client

        # モッククライアント（常に利用可能）
        self._clients[LLMProvider.MOCK] = MockLLMClient()

        logger.info(f"LLMService初期化: primary={primary_provider.value}, "
                   f"available={[p.value for p in self._clients.keys()]}")

    def get_available_providers(self) -> list[LLMProvider]:
        """利用可能なプロバイダーを取得"""
        return [
            provider for provider, client in self._clients.items()
            if client.is_available()
        ]

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
        provider: Optional[LLMProvider] = None
    ) -> LLMResponse:
        """
        テキスト生成（フォールバック付き）

        Args:
            prompt: ユーザープロンプト
            system_prompt: システムプロンプト
            json_mode: JSON出力モード
            provider: 使用プロバイダー（指定時はフォールバックなし）

        Returns:
            LLMResponse
        """
        # 指定プロバイダー
        if provider:
            if provider in self._clients:
                return self._clients[provider].complete(
                    prompt, system_prompt, json_mode
                )
            else:
                return LLMResponse(
                    content="",
                    provider=provider,
                    model="",
                    success=False,
                    error_message=f"プロバイダー {provider.value} は利用できません"
                )

        # 優先プロバイダーを試行
        providers_to_try = [self.primary_provider]
        if self.fallback_provider:
            providers_to_try.append(self.fallback_provider)

        # モックは最後の手段
        if LLMProvider.MOCK not in providers_to_try:
            providers_to_try.append(LLMProvider.MOCK)

        for p in providers_to_try:
            if p in self._clients and self._clients[p].is_available():
                response = self._clients[p].complete(
                    prompt, system_prompt, json_mode
                )
                if response.success:
                    return response
                logger.warning(f"{p.value}での生成に失敗、次を試行")

        return LLMResponse(
            content="",
            provider=LLMProvider.MOCK,
            model="",
            success=False,
            error_message="利用可能なLLMプロバイダーがありません"
        )

    def summarize_text(
        self,
        text: str,
        max_length: int = 200,
        language: str = "ja"
    ) -> LLMResponse:
        """
        テキスト要約

        Args:
            text: 要約対象テキスト
            max_length: 最大文字数
            language: 出力言語

        Returns:
            LLMResponse
        """
        system_prompt = f"あなたはテキスト要約の専門家です。{max_length}文字以内で簡潔に要約してください。"

        prompt = f"以下のテキストを要約してください：\n\n{text}"

        return self.complete(prompt, system_prompt)

    def analyze_email(
        self,
        subject: str,
        sender: str,
        body: str
    ) -> LLMResponse:
        """
        メール分析

        Args:
            subject: 件名
            sender: 送信者
            body: 本文

        Returns:
            LLMResponse (JSON形式)
        """
        system_prompt = """あなたはメール分析の専門家です。
メールを分析し、以下のJSON形式で回答してください：
{
    "summary": "3文以内の要約",
    "action_items": ["必要なアクション1", "必要なアクション2"],
    "priority": "high/medium/low",
    "suggested_reply": "返信が必要な場合の提案（不要ならnull）"
}"""

        prompt = f"""件名: {subject}
送信者: {sender}

本文:
{body[:2000]}"""

        return self.complete(prompt, system_prompt, json_mode=True)


def create_llm_service(
    use_mock: bool = False,
    openai_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
    groq_key: Optional[str] = None,
    ollama_url: Optional[str] = None,
    prefer_local: bool = False
) -> LLMService:
    """
    LLMServiceファクトリ

    Args:
        use_mock: モックモードを使用
        openai_key: OpenAI APIキー
        anthropic_key: Anthropic APIキー
        groq_key: Groq APIキー（無料枠あり）
        ollama_url: OllamaサーバーURL
        prefer_local: ローカルLLM（Ollama）を優先

    Returns:
        LLMService
    """
    if use_mock:
        return LLMService(
            primary_provider=LLMProvider.MOCK,
            fallback_provider=None
        )

    # ローカルLLM優先モード
    if prefer_local:
        return LLMService(
            primary_provider=LLMProvider.OLLAMA,
            fallback_provider=LLMProvider.GROQ,
            groq_api_key=groq_key,
            ollama_base_url=ollama_url
        )

    return LLMService(
        openai_api_key=openai_key,
        anthropic_api_key=anthropic_key,
        groq_api_key=groq_key,
        ollama_base_url=ollama_url
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== LLMサービステスト ===")

    # モックモードでテスト
    service = create_llm_service(use_mock=True)

    print("\n利用可能なプロバイダー:")
    for p in service.get_available_providers():
        print(f"  - {p.value}")

    print("\nテキスト生成テスト:")
    response = service.complete("こんにちは、今日の天気は？")
    print(f"  成功: {response.success}")
    print(f"  内容: {response.content[:100]}...")

    print("\nメール分析テスト:")
    response = service.analyze_email(
        subject="プロジェクト進捗報告",
        sender="tanaka@example.com",
        body="お世話になっております。プロジェクトの進捗をご報告します。"
    )
    print(f"  成功: {response.success}")
    print(f"  内容: {response.content}")
