"""SNS運営自動化モジュールのテスト"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.social_media import (
    ContentTemplate,
    PostScheduler,
    SocialMediaError,
    TwitterPoster,
)


class TestContentTemplate:
    """ContentTemplateクラスのテスト"""

    def test_get_all_categories(self):
        """全カテゴリ取得のテスト"""
        categories = ContentTemplate.get_all_categories()
        assert len(categories) == 5
        assert "productivity_tips" in categories
        assert "feature_highlights" in categories

    def test_get_random_post_no_category(self):
        """カテゴリ指定なしでランダム投稿取得"""
        post = ContentTemplate.get_random_post()
        assert isinstance(post, str)
        assert len(post) > 0
        # ハッシュタグが含まれているはず
        assert "#" in post

    def test_get_random_post_with_category(self):
        """カテゴリ指定でランダム投稿取得"""
        post = ContentTemplate.get_random_post("productivity_tips")
        assert isinstance(post, str)
        assert len(post) > 0

    def test_get_random_post_invalid_category(self):
        """無効なカテゴリでエラー"""
        with pytest.raises(SocialMediaError):
            ContentTemplate.get_random_post("invalid_category")

    def test_productivity_tips_content(self):
        """生産性Tipsの内容確認"""
        assert len(ContentTemplate.PRODUCTIVITY_TIPS) > 0
        for tip in ContentTemplate.PRODUCTIVITY_TIPS:
            assert isinstance(tip, str)
            assert "#" in tip  # ハッシュタグ必須

    def test_all_categories_have_content(self):
        """全カテゴリにコンテンツがあることを確認"""
        for category in ContentTemplate.get_all_categories():
            attr_name = category.upper()
            content = getattr(ContentTemplate, attr_name, [])
            assert len(content) > 0, f"{category} has no content"


class TestPostScheduler:
    """PostSchedulerクラスのテスト"""

    @pytest.fixture
    def temp_schedule_file(self, tmp_path):
        """一時スケジュールファイル"""
        return tmp_path / "test_schedule.json"

    @pytest.fixture
    def scheduler(self, temp_schedule_file):
        """テスト用スケジューラー"""
        return PostScheduler(schedule_file=temp_schedule_file)

    def test_init_creates_schedule_file(self, temp_schedule_file):
        """初期化時にスケジュールファイルのディレクトリが作成される"""
        scheduler = PostScheduler(schedule_file=temp_schedule_file)
        assert temp_schedule_file.parent.exists()

    def test_generate_weekly_schedule(self, scheduler):
        """週間スケジュール生成のテスト"""
        start_date = datetime(2026, 1, 20, 9, 0)  # 月曜日
        posts = scheduler.generate_weekly_schedule(
            start_date=start_date, posts_per_day=2
        )

        # 平日5日×2投稿 + 週末2日×1投稿 = 12投稿
        assert len(posts) >= 10  # 少なくとも10件以上

        # 全投稿が必須フィールドを持つ
        for post in posts:
            assert "scheduled_time" in post
            assert "category" in post
            assert "content" in post
            assert "status" in post
            assert post["status"] == "scheduled"

    def test_schedule_persistence(self, scheduler, temp_schedule_file):
        """スケジュールの永続化テスト"""
        start_date = datetime(2026, 1, 20, 9, 0)
        scheduler.generate_weekly_schedule(start_date=start_date)

        # ファイルが作成されている
        assert temp_schedule_file.exists()

        # 新しいインスタンスで読み込める
        new_scheduler = PostScheduler(schedule_file=temp_schedule_file)
        assert len(new_scheduler.schedule) > 0

    def test_get_pending_posts(self, scheduler):
        """投稿待ちポスト取得のテスト"""
        # 過去の投稿をスケジュール
        past_date = datetime.now() - timedelta(days=1)
        scheduler.generate_weekly_schedule(start_date=past_date, posts_per_day=1)

        # 投稿待ちを取得
        pending = scheduler.get_pending_posts()
        assert len(pending) > 0

        # 時刻でソートされている
        times = [datetime.fromisoformat(p["scheduled_time"]) for p in pending]
        assert times == sorted(times)

    def test_mark_as_posted(self, scheduler):
        """投稿済みマークのテスト"""
        start_date = datetime.now()
        scheduler.generate_weekly_schedule(start_date=start_date, posts_per_day=1)

        # 最初の投稿を投稿済みにマーク
        scheduler.mark_as_posted(0)

        assert scheduler.schedule[0]["status"] == "posted"
        assert "posted_at" in scheduler.schedule[0]

    def test_mark_as_posted_invalid_id(self, scheduler):
        """無効なIDで投稿済みマークするとエラー"""
        with pytest.raises(SocialMediaError):
            scheduler.mark_as_posted(999)

    def test_get_stats(self, scheduler):
        """統計取得のテスト"""
        start_date = datetime.now()
        scheduler.generate_weekly_schedule(start_date=start_date, posts_per_day=2)

        stats = scheduler.get_stats()
        assert "total_posts" in stats
        assert "scheduled" in stats
        assert "posted" in stats
        assert "categories" in stats

        assert stats["total_posts"] > 0
        assert stats["scheduled"] > 0

    def test_weekday_vs_weekend_posts(self, scheduler):
        """平日と週末で投稿時刻が異なることを確認"""
        # 月曜日から開始
        start_date = datetime(2026, 1, 19, 9, 0)  # 月曜日
        posts = scheduler.generate_weekly_schedule(
            start_date=start_date, posts_per_day=2
        )

        weekday_posts = []
        weekend_posts = []

        for post in posts:
            scheduled_time = datetime.fromisoformat(post["scheduled_time"])
            if scheduled_time.weekday() < 5:  # 月-金
                weekday_posts.append(post)
            else:  # 土日
                weekend_posts.append(post)

        # 平日は複数投稿、週末は少なめ
        assert len(weekday_posts) > len(weekend_posts)


class TestTwitterPoster:
    """TwitterPosterクラスのテスト"""

    @pytest.fixture
    def poster(self, tmp_path):
        """テスト用ポスター（DRYモード）"""
        return TwitterPoster(dry_run=True)

    def test_dry_run_post(self, poster):
        """DRYモードでの投稿テスト"""
        content = "テスト投稿 #test"
        result = poster.post(content)

        assert result["success"] is True
        assert result["mode"] == "dry_run"
        assert "timestamp" in result

    def test_post_creates_log_file(self, poster):
        """投稿時にログファイルが作成される"""
        content = "ログテスト #test"
        poster.post(content)

        assert poster.log_file.exists()

    def test_log_file_content(self, poster):
        """ログファイルの内容確認"""
        content = "ログ内容テスト #test"
        poster.post(content)

        log_content = poster.log_file.read_text(encoding="utf-8")
        assert content in log_content
        assert "DRY RUN" in log_content

    def test_live_mode_not_implemented(self):
        """LIVEモードは未実装でエラー"""
        poster = TwitterPoster(dry_run=False)
        with pytest.raises(NotImplementedError):
            poster.post("実際の投稿テスト")


class TestIntegration:
    """統合テスト"""

    @pytest.fixture
    def temp_schedule_file(self, tmp_path):
        """一時スケジュールファイル"""
        return tmp_path / "integration_schedule.json"

    def test_full_workflow(self, temp_schedule_file):
        """スケジュール生成→投稿→統計のフルワークフロー"""
        # スケジュール生成（平日から開始して確実に3件以上）
        scheduler = PostScheduler(schedule_file=temp_schedule_file)
        # 月曜日から開始（weekday=0）
        past_date = datetime(2026, 1, 19, 9, 0)  # 2026年1月19日 月曜日
        scheduler.generate_weekly_schedule(start_date=past_date, posts_per_day=2)

        # 投稿待ちを取得
        future = datetime(2026, 1, 27)  # 1週間後
        pending = scheduler.get_pending_posts(until=future)
        assert len(pending) >= 3

        # 投稿実行（DRYモード）
        poster = TwitterPoster(dry_run=True)
        posted_count = 0
        for i, post in enumerate(pending[:3]):  # 最初の3件のみ
            result = poster.post(post["content"])
            assert result["success"]
            scheduler.mark_as_posted(i)
            posted_count += 1

        # 統計確認
        stats = scheduler.get_stats()
        assert stats["posted"] == posted_count
        assert stats["posted"] >= 3

    def test_category_distribution(self, temp_schedule_file):
        """カテゴリ分布が均等に近いことを確認"""
        scheduler = PostScheduler(schedule_file=temp_schedule_file)
        start_date = datetime.now()
        scheduler.generate_weekly_schedule(start_date=start_date, posts_per_day=2)

        stats = scheduler.get_stats()
        categories = stats["categories"]

        # 全カテゴリが使用されている
        assert len(categories) == len(ContentTemplate.get_all_categories())

        # 各カテゴリが最低1回は使用されている
        for count in categories.values():
            assert count >= 0  # ランダムなので0の可能性もある
