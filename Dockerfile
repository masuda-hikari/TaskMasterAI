# TaskMasterAI - Production Dockerfile
# Python 3.11ベースのマルチステージビルド

# ビルドステージ
FROM python:3.14-slim as builder

WORKDIR /app

# 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# 本番ステージ
FROM python:3.14-slim

WORKDIR /app

# セキュリティ: 非rootユーザーで実行
RUN useradd --create-home --shell /bin/bash appuser

# ビルドステージから依存関係をコピー
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# アプリケーションコードをコピー
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser config/.env.example ./config/.env.example

# ランディングページをコピー（静的ファイルサーバー用）
COPY --chown=appuser:appuser landing/ ./landing/

# 環境変数
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV APP_ENV=production

# ユーザー切り替え
USER appuser

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ポート公開
EXPOSE 8000

# アプリケーション起動
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
