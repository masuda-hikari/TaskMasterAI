# LLM API セットアップガイド

TaskMasterAIのメール要約・分析に使用するLLM APIの設定手順。

## 対応プロバイダー

| プロバイダー | 推奨モデル | 特徴 |
|------------|-----------|------|
| OpenAI | gpt-4o-mini | コスパ良好、高速 |
| Anthropic | claude-3-haiku | 高精度、日本語対応良好 |

どちらか一方でOK。両方設定すると自動フォールバック。

## OpenAI API

### 1. アカウント作成

1. [OpenAI Platform](https://platform.openai.com/)にアクセス
2. アカウント作成/ログイン
3. 支払い方法を設定（クレジットカード）

### 2. APIキー取得

1. 「API Keys」→「Create new secret key」
2. キー名: "TaskMasterAI"
3. キーをコピー（一度しか表示されない）

### 3. 環境変数設定

```bash
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 4. 使用量制限設定（推奨）

1. 「Usage」→「Limits」
2. 月額上限を設定（例: $10）
3. メール通知を有効化

## Anthropic API

### 1. アカウント作成

1. [Anthropic Console](https://console.anthropic.com/)にアクセス
2. アカウント作成/ログイン
3. 支払い方法を設定

### 2. APIキー取得

1. 「API Keys」→「Create Key」
2. キー名: "TaskMasterAI"
3. キーをコピー

### 3. 環境変数設定

```bash
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## 動作確認

### OpenAIテスト

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}]
)
print(response.choices[0].message.content)
```

### Anthropicテスト

```python
import os
import anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

message = client.messages.create(
    model="claude-3-haiku-20240307",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)
print(message.content[0].text)
```

## コスト見積もり

### 月間使用量予測（Personal Plan: 500メール/月）

| モデル | 入力/出力 | 単価 | 月額概算 |
|--------|----------|------|----------|
| gpt-4o-mini | ~1M tokens | $0.15/1M | ~$0.15 |
| claude-3-haiku | ~1M tokens | $0.25/1M | ~$0.25 |

> 実際のコストはメールの長さにより変動

## トラブルシューティング

### "Invalid API Key" エラー

- キーが正しくコピーされているか確認
- 環境変数が読み込まれているか確認

### "Rate limit exceeded" エラー

- 使用量制限に達している可能性
- リクエスト間隔を空ける

### "Insufficient quota" エラー

- クレジット残高を確認
- 支払い方法を確認

## セキュリティ注意事項

- APIキーをコードにハードコードしない
- `.env`ファイルは`.gitignore`に含める
- 本番環境ではSecret Managerを使用推奨
- 使用量制限を必ず設定
