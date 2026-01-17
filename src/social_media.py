"""SNS運営自動化モジュール

X/Twitter自動投稿・スケジューリング機能を提供
"""

import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from .errors import ErrorCode, TaskMasterError
from .logging_config import get_logger

logger = get_logger(__name__)


class SocialMediaError(TaskMasterError):
    """SNS関連のエラー"""

    def __init__(self, message: str, **kwargs):
        """初期化

        Args:
            message: エラーメッセージ
            **kwargs: TaskMasterErrorへの追加引数
        """
        # デフォルトでSYSTEM_INTERNAL_ERRORコードを使用
        code = kwargs.pop("code", ErrorCode.SYSTEM_INTERNAL_ERROR)
        super().__init__(code=code, message=message, **kwargs)


class ContentTemplate:
    """投稿コンテンツテンプレート"""

    # 生産性Tips
    PRODUCTIVITY_TIPS = [
        "📧 メール処理に1日4時間使っていませんか？TaskMasterAIなら、AIが自動要約・返信ドラフト作成で週5時間を節約できます。\n\n#生産性向上 #AI #時間管理",
        "⏰ 会議のスケジュール調整、往復メールで15分かかっていませんか？TaskMasterAIは参加者全員の空き時間を10秒で検索します。\n\n#スケジュール管理 #効率化 #AI",
        "🎯 タスクの優先順位付けに迷っていませんか？TaskMasterAIはAIがあなたの仕事パターンを学習し、最適なスケジュールを提案します。\n\n#タスク管理 #AI #仕事術",
        "💰 時給5,000円のあなたが週5時間節約すると、月間10万円の価値。TaskMasterAIの月額¥1,480で、ROI 70倍の投資効果。\n\n#ROI #生産性 #コスパ",
        "📊 日本企業の導入事例：日程調整時間を月間60時間削減、生産性30%向上を実現。AIスケジューリングの威力を体験してみませんか？\n\n#事例紹介 #AI #業務効率化",
    ]

    # 機能紹介
    FEATURE_HIGHLIGHTS = [
        "✨ TaskMasterAI 主な機能\n\n📧 メール自動要約\n📅 空き時間自動検索\n✍️ 返信ドラフト作成\n🔔 スマートリマインダー\n\n無料プラン（月50件）でお試しいただけます！\n\n#TaskMasterAI #AI #生産性",
        "🔒 安全性重視の設計\n\nTaskMasterAIは確認モードがデフォルト。AIは勝手にメール送信や予定変更を行いません。全アクションに明示的な承認が必要です。\n\n#セキュリティ #プライバシー #安心",
        "🌐 Gmail & Googleカレンダー対応\n\nTaskMasterAIはOAuth 2.0で安全に連携。メール内容はサーバーに保存せず、リアルタイム処理のみ。\n\n#Gmail #Google #API連携",
        "📱 いつでもどこでも\n\nCLI、Web API、Python SDKの3つのインターフェース。あなたの作業スタイルに合わせて利用可能。\n\n#開発者向け #API #CLI",
    ]

    # 時間管理Tips
    TIME_MANAGEMENT = [
        "⏱️ 時間管理のコツ：メールチェックは1日3回（朝・昼・夕）に限定。TaskMasterAIの要約機能で優先度の高いものだけ即座に把握できます。\n\n#時間管理術 #メール #集中力",
        "🧘 集中時間の確保：TaskMasterAIはあなたの生産性が高い時間帯を学習。その時間は会議を入れず、重要タスクに集中できるよう自動ブロック。\n\n#集中力 #フロー状態 #AI",
        "🗓️ ダブルブッキング防止：複数カレンダーを統合管理。TaskMasterAIが自動でコンフリクトを検出し、警告します。\n\n#スケジュール #ミス防止 #カレンダー",
    ]

    # 市場データ・統計
    MARKET_INSIGHTS = [
        "📈 AI仮想アシスタント市場は2026年に約3,000億円規模、2030年には8,000億円超に成長見込み（CAGR 30%超）。生産性革命が始まっています。\n\n#市場動向 #AI #未来",
        "🌏 世界のビジネスパーソンは平均1日4.1時間をメール管理に費やしています。AIアシスタントで週3-5時間の節約が標準的に。\n\n#統計 #メール #生産性",
        "🇯🇵 日本市場の特徴：企業の業務効率化ニーズが特に高く、AIスケジュール管理ツールの導入が加速。国産・日本語対応が重視されます。\n\n#日本市場 #AI #ローカライズ",
    ]

    # ユーザー向けメッセージ
    USER_ENGAGEMENT = [
        "🙋 こんな方におすすめ\n\n✅ メール処理に追われている\n✅ 会議調整で時間を無駄にしている\n✅ タスクの優先順位がわからない\n✅ ワークライフバランスを改善したい\n\n#ターゲット #おすすめ",
        "💬 ベータテスター募集中！\n\nTaskMasterAIを無料で試して、フィードバックをお寄せください。あなたの声がプロダクトを進化させます。\n\n#ベータ版 #募集 #フィードバック",
        "🎁 紹介プログラム\n\n友達を紹介すると、あなたは1ヶ月無料！友達も初月50%オフ。上限なしで何人でも紹介可能です。\n\n#紹介特典 #キャンペーン #お得",
    ]

    @classmethod
    def get_random_post(cls, category: Optional[str] = None) -> str:
        """ランダムに投稿を取得

        Args:
            category: カテゴリ名（指定なしで全カテゴリからランダム）

        Returns:
            投稿テキスト
        """
        if category:
            posts = getattr(cls, category.upper(), [])
            if not posts:
                raise SocialMediaError(f"Unknown category: {category}")
        else:
            # 全カテゴリから選択
            all_posts = (
                cls.PRODUCTIVITY_TIPS
                + cls.FEATURE_HIGHLIGHTS
                + cls.TIME_MANAGEMENT
                + cls.MARKET_INSIGHTS
                + cls.USER_ENGAGEMENT
            )
            posts = all_posts

        return random.choice(posts)

    @classmethod
    def get_all_categories(cls) -> List[str]:
        """全カテゴリ名を取得

        Returns:
            カテゴリ名のリスト
        """
        return [
            "productivity_tips",
            "feature_highlights",
            "time_management",
            "market_insights",
            "user_engagement",
        ]


class PostScheduler:
    """投稿スケジューラー"""

    def __init__(self, schedule_file: Optional[Path] = None):
        """初期化

        Args:
            schedule_file: スケジュールファイルのパス
        """
        self.schedule_file = schedule_file or Path("data/social_schedule.json")
        self.schedule_file.parent.mkdir(parents=True, exist_ok=True)
        self.schedule: List[Dict] = self._load_schedule()

    def _load_schedule(self) -> List[Dict]:
        """スケジュールを読み込み

        Returns:
            スケジュールリスト
        """
        if self.schedule_file.exists():
            try:
                with open(self.schedule_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"スケジュール読み込みエラー: {e}")
                return []
        return []

    def _save_schedule(self) -> None:
        """スケジュールを保存"""
        try:
            with open(self.schedule_file, "w", encoding="utf-8") as f:
                json.dump(self.schedule, f, ensure_ascii=False, indent=2)
            logger.info(f"スケジュール保存: {len(self.schedule)}件")
        except Exception as e:
            logger.error(f"スケジュール保存エラー: {e}")
            raise SocialMediaError(f"Failed to save schedule: {e}")

    def generate_weekly_schedule(
        self,
        start_date: Optional[datetime] = None,
        posts_per_day: int = 2,
    ) -> List[Dict]:
        """週間スケジュールを生成

        Args:
            start_date: 開始日（デフォルトは明日）
            posts_per_day: 1日あたりの投稿数

        Returns:
            生成されたスケジュールリスト
        """
        if start_date is None:
            start_date = datetime.now() + timedelta(days=1)
            start_date = start_date.replace(hour=9, minute=0, second=0, microsecond=0)

        categories = ContentTemplate.get_all_categories()
        new_posts = []

        for day in range(7):
            current_date = start_date + timedelta(days=day)

            # 平日は朝9時・夕方18時、週末は昼12時のみ
            if current_date.weekday() < 5:  # 月-金
                times = [
                    current_date.replace(hour=9, minute=0),
                    current_date.replace(hour=18, minute=0),
                ]
            else:  # 土日
                times = [current_date.replace(hour=12, minute=0)]

            for post_time in times[:posts_per_day]:
                category = random.choice(categories)
                content = ContentTemplate.get_random_post(category)

                post = {
                    "scheduled_time": post_time.isoformat(),
                    "category": category,
                    "content": content,
                    "status": "scheduled",
                    "created_at": datetime.now().isoformat(),
                }
                new_posts.append(post)

        self.schedule.extend(new_posts)
        self._save_schedule()

        logger.info(f"週間スケジュール生成: {len(new_posts)}件")
        return new_posts

    def get_pending_posts(self, until: Optional[datetime] = None) -> List[Dict]:
        """投稿待ちのポストを取得

        Args:
            until: この時刻までの投稿を取得（デフォルトは現在時刻）

        Returns:
            投稿待ちポストのリスト
        """
        if until is None:
            until = datetime.now()

        pending = []
        for post in self.schedule:
            if post["status"] != "scheduled":
                continue

            scheduled_time = datetime.fromisoformat(post["scheduled_time"])
            if scheduled_time <= until:
                pending.append(post)

        return sorted(pending, key=lambda x: x["scheduled_time"])

    def mark_as_posted(self, post_id: int) -> None:
        """投稿済みとしてマーク

        Args:
            post_id: 投稿のインデックス
        """
        if 0 <= post_id < len(self.schedule):
            self.schedule[post_id]["status"] = "posted"
            self.schedule[post_id]["posted_at"] = datetime.now().isoformat()
            self._save_schedule()
            logger.info(f"投稿完了マーク: {post_id}")
        else:
            raise SocialMediaError(f"Invalid post ID: {post_id}")

    def get_stats(self) -> Dict:
        """投稿統計を取得

        Returns:
            統計情報
        """
        total = len(self.schedule)
        scheduled = sum(1 for p in self.schedule if p["status"] == "scheduled")
        posted = sum(1 for p in self.schedule if p["status"] == "posted")

        return {
            "total_posts": total,
            "scheduled": scheduled,
            "posted": posted,
            "categories": {
                cat: sum(1 for p in self.schedule if p.get("category") == cat)
                for cat in ContentTemplate.get_all_categories()
            },
        }


class TwitterPoster:
    """Twitter投稿クライアント（モック）

    実際のAPI連携は外部認証情報が必要なため、
    現時点ではモック実装として投稿予定を記録
    """

    def __init__(self, dry_run: bool = True):
        """初期化

        Args:
            dry_run: Trueの場合は実際に投稿せず、ログのみ
        """
        self.dry_run = dry_run
        self.log_file = Path("data/twitter_posts.log")
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def post(self, content: str) -> Dict:
        """投稿を実行

        Args:
            content: 投稿内容

        Returns:
            投稿結果
        """
        if self.dry_run:
            logger.info(f"[DRY RUN] Twitter投稿:\n{content}")

            # ログファイルに記録
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"時刻: {datetime.now().isoformat()}\n")
                f.write(f"モード: DRY RUN\n")
                f.write(f"内容:\n{content}\n")

            return {
                "success": True,
                "mode": "dry_run",
                "timestamp": datetime.now().isoformat(),
            }
        else:
            # 実際のAPI連携はここに実装
            # Twitter API v2を使用する場合:
            # import tweepy
            # client = tweepy.Client(bearer_token=...)
            # response = client.create_tweet(text=content)
            raise NotImplementedError(
                "実際のTwitter API連携は外部認証情報設定後に実装"
            )


def main():
    """メイン関数（テスト用）"""
    # スケジューラーのテスト
    scheduler = PostScheduler()

    print("=== 週間スケジュール生成 ===")
    posts = scheduler.generate_weekly_schedule()
    print(f"生成: {len(posts)}件")

    print("\n=== 投稿統計 ===")
    stats = scheduler.get_stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    print("\n=== 投稿待ち（テスト）===")
    # 未来の時刻で取得（テスト用）
    future = datetime.now() + timedelta(days=7)
    pending = scheduler.get_pending_posts(until=future)
    print(f"投稿待ち: {len(pending)}件")

    if pending:
        print("\n最初の3件:")
        for i, post in enumerate(pending[:3], 1):
            print(f"\n[{i}] {post['scheduled_time']}")
            print(f"カテゴリ: {post['category']}")
            print(f"内容:\n{post['content']}")

    print("\n=== Twitterモック投稿 ===")
    poster = TwitterPoster(dry_run=True)
    test_content = ContentTemplate.get_random_post()
    result = poster.post(test_content)
    print(f"結果: {result}")


if __name__ == "__main__":
    main()
