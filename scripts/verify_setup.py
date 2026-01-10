#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
環境設定検証スクリプト

本番デプロイ前に必要な設定が揃っているか確認します。
"""

import os
import sys
import io
from pathlib import Path

# Windows環境でUTF-8出力を強制
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# .envファイルを読み込む
try:
    from dotenv import load_dotenv
    env_path = project_root / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ .envファイルを読み込みました: {env_path}")
    else:
        print(f"⚠ .envファイルが見つかりません: {env_path}")
        print("  → config/.env.example をコピーして .env を作成してください")
except ImportError:
    print("⚠ python-dotenv がインストールされていません")
    print("  → pip install python-dotenv")


class SetupVerifier:
    """環境設定検証クラス"""

    def __init__(self):
        self.errors = []
        self.warnings = []
        self.success = []

    def check_env_var(self, name: str, required: bool = True, is_secret: bool = True):
        """環境変数の存在確認"""
        value = os.getenv(name)
        if value:
            if is_secret:
                masked = value[:8] + "..." if len(value) > 8 else "***"
                self.success.append(f"{name} = {masked}")
            else:
                self.success.append(f"{name} = {value}")
            return True
        else:
            if required:
                self.errors.append(f"{name} が設定されていません")
            else:
                self.warnings.append(f"{name} が設定されていません（オプション）")
            return False

    def check_google(self):
        """Google API設定確認"""
        print("\n" + "=" * 50)
        print("🔍 Google API 設定確認")
        print("=" * 50)

        client_id = self.check_env_var("GOOGLE_CLIENT_ID")
        client_secret = self.check_env_var("GOOGLE_CLIENT_SECRET")

        # 認証情報ファイル確認
        creds_path = project_root / "config" / "credentials" / "google_oauth.json"
        if creds_path.exists():
            self.success.append(f"OAuth JSONファイル存在: {creds_path.name}")
        else:
            self.warnings.append(f"OAuth JSONファイルなし: {creds_path}")

        return client_id and client_secret

    def check_stripe(self):
        """Stripe設定確認"""
        print("\n" + "=" * 50)
        print("💳 Stripe 設定確認")
        print("=" * 50)

        api_key = self.check_env_var("STRIPE_API_KEY")
        self.check_env_var("STRIPE_WEBHOOK_SECRET", required=False)
        price_personal = self.check_env_var("STRIPE_PRICE_PERSONAL")
        price_pro = self.check_env_var("STRIPE_PRICE_PRO")
        price_team = self.check_env_var("STRIPE_PRICE_TEAM")

        # テストモードか本番モードか確認
        stripe_key = os.getenv("STRIPE_API_KEY", "")
        if stripe_key.startswith("sk_test_"):
            self.warnings.append("Stripeはテストモードです（本番用はsk_live_...）")
        elif stripe_key.startswith("sk_live_"):
            self.success.append("Stripeは本番モードです")

        return api_key and price_personal and price_pro and price_team

    def check_llm(self):
        """LLM API設定確認"""
        print("\n" + "=" * 50)
        print("🤖 LLM API 設定確認")
        print("=" * 50)

        openai = self.check_env_var("OPENAI_API_KEY", required=False)
        anthropic = self.check_env_var("ANTHROPIC_API_KEY", required=False)

        if not openai and not anthropic:
            self.errors.append("OPENAI_API_KEY または ANTHROPIC_API_KEY が必要です")
            return False

        return True

    def check_jwt(self):
        """JWT設定確認"""
        print("\n" + "=" * 50)
        print("🔐 JWT 設定確認")
        print("=" * 50)

        jwt_secret = os.getenv("JWT_SECRET_KEY", "")
        if not jwt_secret:
            self.errors.append("JWT_SECRET_KEY が設定されていません")
            return False

        if jwt_secret == "your-secret-key-change-in-production":
            self.errors.append("JWT_SECRET_KEY がデフォルト値のままです！本番用に変更してください")
            return False

        if len(jwt_secret) < 32:
            self.warnings.append("JWT_SECRET_KEY は32文字以上推奨です")

        self.success.append(f"JWT_SECRET_KEY = {jwt_secret[:8]}...")
        return True

    def check_admin(self):
        """管理者設定確認"""
        print("\n" + "=" * 50)
        print("👤 管理者 設定確認")
        print("=" * 50)

        admin_emails = os.getenv("ADMIN_EMAILS", "")
        if admin_emails:
            self.success.append(f"ADMIN_EMAILS = {admin_emails}")
        else:
            self.warnings.append("ADMIN_EMAILS が設定されていません（管理ダッシュボードアクセス不可）")

        return True

    def check_dependencies(self):
        """依存関係確認"""
        print("\n" + "=" * 50)
        print("📦 依存関係 確認")
        print("=" * 50)

        deps = [
            ("fastapi", "FastAPI"),
            ("uvicorn", "Uvicorn"),
            ("pydantic", "Pydantic"),
            ("jwt", "PyJWT"),
            ("stripe", "Stripe"),
            ("anthropic", "Anthropic SDK"),
            ("openai", "OpenAI SDK"),
        ]

        all_ok = True
        for module, name in deps:
            try:
                __import__(module)
                self.success.append(f"{name} インストール済み")
            except ImportError:
                self.errors.append(f"{name} ({module}) がインストールされていません")
                all_ok = False

        return all_ok

    def print_results(self):
        """結果表示"""
        print("\n" + "=" * 50)
        print("📊 検証結果")
        print("=" * 50)

        if self.success:
            print("\n✅ 成功:")
            for msg in self.success:
                print(f"   • {msg}")

        if self.warnings:
            print("\n⚠️  警告:")
            for msg in self.warnings:
                print(f"   • {msg}")

        if self.errors:
            print("\n❌ エラー:")
            for msg in self.errors:
                print(f"   • {msg}")

        print("\n" + "-" * 50)
        if not self.errors:
            print("🎉 すべての必須設定が完了しています！")
            return True
        else:
            print(f"⚠️  {len(self.errors)} 件のエラーがあります。修正してください。")
            return False

    def run(self):
        """全チェック実行"""
        print("=" * 50)
        print("TaskMasterAI 環境設定検証")
        print("=" * 50)

        self.check_google()
        self.check_stripe()
        self.check_llm()
        self.check_jwt()
        self.check_admin()
        self.check_dependencies()

        return self.print_results()


def main():
    """メイン関数"""
    verifier = SetupVerifier()
    success = verifier.run()

    print("\n" + "=" * 50)
    print("📋 次のステップ")
    print("=" * 50)

    if success:
        print("""
1. テスト実行:
   pytest tests/ -v

2. サーバー起動:
   uvicorn src.api:app --reload

3. ヘルスチェック:
   ブラウザで http://localhost:8000/health にアクセス

4. 管理ダッシュボード:
   http://localhost:8000/admin.html
""")
    else:
        print("""
エラーを修正してから再度実行してください:
   python scripts/verify_setup.py

設定手順は以下を参照:
   docs/SETUP_CHECKLIST.md
""")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
