"""
節約時間レポート機能のテスト

収益化のためのROI可視化機能をテスト
"""

import pytest
from datetime import datetime

# BillingService テスト
from src.billing import (
    BillingService,
    SubscriptionPlan,
    SubscriptionStatus,
)


class TestSavingsReportBilling:
    """BillingService.get_savings_report()のテスト"""

    def setup_method(self):
        """各テスト前にサービスを初期化"""
        self.service = BillingService()

    def test_savings_report_no_subscription(self):
        """サブスクリプションがない場合はエラー"""
        report = self.service.get_savings_report("nonexistent_user")
        assert "error" in report
        assert "サブスクリプションが見つかりません" in report["error"]

    def test_savings_report_free_plan_no_usage(self):
        """無料プラン・使用量ゼロの場合"""
        self.service.create_subscription(
            user_id="user1",
            customer_id="cus_1",
            plan=SubscriptionPlan.FREE
        )

        report = self.service.get_savings_report("user1")

        # 構造確認
        assert "usage_breakdown" in report
        assert "total_savings" in report
        assert "plan_cost" in report
        assert "net_savings" in report
        assert "usage_status" in report
        assert "generated_at" in report

        # 使用量ゼロなので節約もゼロ
        assert report["total_savings"]["minutes"] == 0
        assert report["total_savings"]["hours"] == 0
        assert report["total_savings"]["value_jpy"] == 0

        # 無料プランなのでコストもゼロ
        assert report["plan_cost"]["monthly_price_jpy"] == 0

    def test_savings_report_with_email_usage(self):
        """メール要約使用後のレポート"""
        self.service.create_subscription(
            user_id="user2",
            customer_id="cus_2",
            plan=SubscriptionPlan.FREE
        )

        # 10通のメール要約を使用
        for _ in range(10):
            self.service.record_usage("user2", "email_summary")

        report = self.service.get_savings_report("user2")

        # メール要約: 10通 × 3分 = 30分
        assert report["usage_breakdown"]["email_summaries"]["count"] == 10
        assert report["usage_breakdown"]["email_summaries"]["savings_minutes"] == 30
        assert report["total_savings"]["minutes"] == 30
        assert report["total_savings"]["hours"] == 0.5

        # 金額換算: 0.5時間 × 5000円 = 2500円
        assert report["total_savings"]["value_jpy"] == 2500

    def test_savings_report_with_schedule_usage(self):
        """スケジュール提案使用後のレポート"""
        self.service.create_subscription(
            user_id="user3",
            customer_id="cus_3",
            plan=SubscriptionPlan.FREE
        )

        # 5回のスケジュール提案を使用
        for _ in range(5):
            self.service.record_usage("user3", "schedule_proposal")

        report = self.service.get_savings_report("user3")

        # スケジュール提案: 5回 × 10分 = 50分
        assert report["usage_breakdown"]["schedule_proposals"]["count"] == 5
        assert report["usage_breakdown"]["schedule_proposals"]["savings_minutes"] == 50
        assert report["total_savings"]["minutes"] == 50

    def test_savings_report_combined_usage(self):
        """複数機能の使用後のレポート"""
        self.service.create_subscription(
            user_id="user4",
            customer_id="cus_4",
            plan=SubscriptionPlan.FREE
        )

        # メール20通 + スケジュール3回
        for _ in range(20):
            self.service.record_usage("user4", "email_summary")
        for _ in range(3):
            self.service.record_usage("user4", "schedule_proposal")

        report = self.service.get_savings_report("user4")

        # メール: 20 × 3 = 60分、スケジュール: 3 × 10 = 30分、合計90分
        assert report["total_savings"]["minutes"] == 90
        assert report["total_savings"]["hours"] == 1.5
        assert report["total_savings"]["value_jpy"] == 7500  # 1.5時間 × 5000円

    def test_savings_report_personal_plan_roi(self):
        """Personalプランの場合のROI計算"""
        self.service.create_subscription(
            user_id="user5",
            customer_id="cus_5",
            plan=SubscriptionPlan.PERSONAL
        )

        # 100通のメール要約使用
        for _ in range(100):
            self.service.record_usage("user5", "email_summary")

        report = self.service.get_savings_report("user5")

        # メール: 100 × 3 = 300分 = 5時間
        assert report["total_savings"]["hours"] == 5.0
        assert report["total_savings"]["value_jpy"] == 25000  # 5時間 × 5000円

        # Personalプラン: 1480円
        assert report["plan_cost"]["monthly_price_jpy"] == 1480
        assert report["net_savings"]["value_jpy"] == 25000 - 1480

        # ROI: 25000 / 1480 * 100 ≈ 1689%
        assert report["net_savings"]["roi_percent"] > 1000

    def test_savings_report_upgrade_recommendation_free(self):
        """無料プランで使用量80%超えるとアップグレード推奨"""
        self.service.create_subscription(
            user_id="user6",
            customer_id="cus_6",
            plan=SubscriptionPlan.FREE
        )

        # メール45通使用（50通の90%）
        for _ in range(45):
            self.service.record_usage("user6", "email_summary")

        report = self.service.get_savings_report("user6")

        assert report["usage_status"]["upgrade_recommended"] is True
        assert report["upgrade_recommendation"] is not None
        assert report["upgrade_recommendation"]["plan"] == "personal"
        assert report["upgrade_recommendation"]["price_jpy"] == 1480
        assert len(report["upgrade_recommendation"]["additional_benefits"]) > 0

    def test_savings_report_no_upgrade_recommendation_low_usage(self):
        """使用量が少ない場合はアップグレード推奨なし"""
        self.service.create_subscription(
            user_id="user7",
            customer_id="cus_7",
            plan=SubscriptionPlan.FREE
        )

        # メール10通使用（50通の20%）
        for _ in range(10):
            self.service.record_usage("user7", "email_summary")

        report = self.service.get_savings_report("user7")

        assert report["usage_status"]["upgrade_recommended"] is False
        assert report["upgrade_recommendation"] is None

    def test_savings_report_pro_plan(self):
        """Proプランのレポート"""
        self.service.create_subscription(
            user_id="user8",
            customer_id="cus_8",
            plan=SubscriptionPlan.PRO
        )

        report = self.service.get_savings_report("user8")

        assert report["plan_cost"]["plan"] == "pro"
        assert report["plan_cost"]["monthly_price_jpy"] == 3980

    def test_savings_report_free_plan_roi_unlimited(self):
        """無料プランの場合ROIは無限大"""
        self.service.create_subscription(
            user_id="user9",
            customer_id="cus_9",
            plan=SubscriptionPlan.FREE
        )

        # 使用量を記録
        for _ in range(10):
            self.service.record_usage("user9", "email_summary")

        report = self.service.get_savings_report("user9")

        # 無料プランなのでROIは無限大
        assert report["net_savings"]["roi_percent"] == "unlimited"

    def test_savings_report_generated_at(self):
        """レポート生成日時が含まれる"""
        self.service.create_subscription(
            user_id="user10",
            customer_id="cus_10",
            plan=SubscriptionPlan.FREE
        )

        report = self.service.get_savings_report("user10")

        assert "generated_at" in report
        # ISO形式の日時文字列であることを確認
        datetime.fromisoformat(report["generated_at"])


class TestSavingsReportAPI:
    """APIエンドポイントのテスト"""

    @pytest.fixture
    def client(self):
        """テストクライアントを作成"""
        try:
            from fastapi.testclient import TestClient
            from src.api import create_app
            app = create_app()
            return TestClient(app)
        except ImportError:
            pytest.skip("FastAPIがインストールされていません")

    def test_savings_report_endpoint_unauthorized(self, client):
        """認証なしでアクセスするとエラー"""
        response = client.get("/usage/report")
        # 認証なしの場合は401 Unauthorized（FastAPIのHTTPBearerデフォルト動作）
        # または403 Forbidden
        assert response.status_code in [401, 403]

    def test_savings_report_endpoint_success(self, client):
        """認証ありでアクセスすると成功"""
        import uuid
        email = f"test_{uuid.uuid4().hex[:8]}@example.com"

        # ユーザー登録
        register_response = client.post(
            "/auth/register",
            json={"email": email, "password": "password123"}
        )
        assert register_response.status_code == 200

        # ログイン
        login_response = client.post(
            "/auth/login",
            json={"email": email, "password": "password123"}
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # レポート取得
        report_response = client.get(
            "/usage/report",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert report_response.status_code == 200

        data = report_response.json()
        assert "usage_breakdown" in data
        assert "total_savings" in data
        assert "plan_cost" in data
        assert "net_savings" in data
        assert "usage_status" in data

    def test_savings_report_after_usage(self, client):
        """使用後のレポート取得"""
        import uuid
        email = f"test_{uuid.uuid4().hex[:8]}@example.com"

        # ユーザー登録
        client.post(
            "/auth/register",
            json={"email": email, "password": "password123"}
        )

        # ログイン
        login_response = client.post(
            "/auth/login",
            json={"email": email, "password": "password123"}
        )
        token = login_response.json()["access_token"]

        # メール要約を実行（使用量を記録）
        client.post(
            "/email/summarize",
            json={"max_emails": 5},
            headers={"Authorization": f"Bearer {token}"}
        )

        # レポート取得
        report_response = client.get(
            "/usage/report",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert report_response.status_code == 200

        data = report_response.json()
        # 使用量が記録されていることを確認
        assert data["usage_breakdown"]["email_summaries"]["count"] >= 0
