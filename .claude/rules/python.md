---
paths:
  - "**/*.py"
  - "**/requirements.txt"
  - "**/pyproject.toml"
  - "**/setup.py"
---

# Pythonルール

## 必須チェック
- black: フォーマット
- isort: インポート整理
- mypy: 型チェック
- bandit: セキュリティスキャン
- pytest: テスト合格

## コーディング規約
- 型ヒント: 関数シグネチャ必須
- docstring: Google style
- 例外: 具体的な例外クラス使用
- パス: pathlib使用

## 禁止パターン
```python
# NG
def process(data):
    return data + 1

except Exception:
    pass

# OK
def process(data: int) -> int:
    """データを処理する。

    Args:
        data: 入力値

    Returns:
        処理結果
    """
    return data + 1

except ValueError as e:
    logger.error(f"処理エラー: {e}")
    raise
```

## インポート順序
1. 標準ライブラリ
2. サードパーティ
3. ローカル

## 仮想環境
- venv/poetry/uv使用
- requirements.txt固定
