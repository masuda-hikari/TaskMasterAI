"""
Database Module - データベース永続化層

SQLiteによるデータ永続化を提供
"""

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Generator
import json

logger = logging.getLogger(__name__)


@dataclass
class DBUser:
    """データベースユーザーモデル"""
    id: str
    email: str
    password_hash: str
    name: Optional[str]
    plan: str
    stripe_customer_id: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class DBSubscription:
    """データベースサブスクリプションモデル"""
    id: str
    user_id: str
    plan: str
    status: str
    stripe_subscription_id: Optional[str]
    current_period_start: datetime
    current_period_end: datetime
    created_at: datetime
    updated_at: datetime


@dataclass
class DBUsageRecord:
    """使用量レコード"""
    id: str
    user_id: str
    feature: str
    count: int
    period_start: datetime
    period_end: datetime


class Database:
    """
    SQLiteデータベース管理クラス

    ユーザー、サブスクリプション、使用量の永続化を提供
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        初期化

        Args:
            db_path: データベースファイルパス（Noneの場合はインメモリ）
        """
        self.db_path = db_path or ":memory:"
        # インメモリDBの場合は接続を保持（閉じるとデータが消える）
        self._persistent_conn: Optional[sqlite3.Connection] = None
        if self.db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:")
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_database()
        logger.info(f"データベース初期化完了: {self.db_path}")

    def _init_database(self) -> None:
        """データベーススキーマを初期化"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # ユーザーテーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT,
                    plan TEXT DEFAULT 'free',
                    stripe_customer_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # サブスクリプションテーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    stripe_subscription_id TEXT,
                    current_period_start TIMESTAMP,
                    current_period_end TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            # 使用量テーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usage_records (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    feature TEXT NOT NULL,
                    count INTEGER DEFAULT 0,
                    period_start TIMESTAMP NOT NULL,
                    period_end TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    UNIQUE(user_id, feature, period_start)
                )
            """)

            # 監査ログテーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    action TEXT NOT NULL,
                    details TEXT,
                    ip_address TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # インデックス作成
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_user_feature ON usage_records(user_id, feature)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_logs(user_id)")

            conn.commit()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """データベース接続を取得"""
        # インメモリDBの場合は永続接続を使用
        if self._persistent_conn is not None:
            yield self._persistent_conn
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    # ユーザー関連
    def create_user(
        self,
        user_id: str,
        email: str,
        password_hash: str,
        name: Optional[str] = None,
        plan: str = "free"
    ) -> Optional[DBUser]:
        """
        ユーザーを作成

        Args:
            user_id: ユーザーID
            email: メールアドレス
            password_hash: パスワードハッシュ
            name: 名前
            plan: プラン

        Returns:
            作成されたユーザー（失敗時はNone）
        """
        now = datetime.now()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO users (id, email, password_hash, name, plan, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, email, password_hash, name, plan, now, now))
                conn.commit()

                return DBUser(
                    id=user_id,
                    email=email,
                    password_hash=password_hash,
                    name=name,
                    plan=plan,
                    stripe_customer_id=None,
                    created_at=now,
                    updated_at=now
                )
        except sqlite3.IntegrityError as e:
            logger.warning(f"ユーザー作成エラー（重複）: {e}")
            return None

    def get_user_by_id(self, user_id: str) -> Optional[DBUser]:
        """IDでユーザーを取得"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_user(row)
            return None

    def get_user_by_email(self, email: str) -> Optional[DBUser]:
        """メールアドレスでユーザーを取得"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()

            if row:
                return self._row_to_user(row)
            return None

    def update_user(
        self,
        user_id: str,
        name: Optional[str] = None,
        plan: Optional[str] = None,
        stripe_customer_id: Optional[str] = None
    ) -> bool:
        """ユーザー情報を更新"""
        updates = []
        values = []

        if name is not None:
            updates.append("name = ?")
            values.append(name)
        if plan is not None:
            updates.append("plan = ?")
            values.append(plan)
        if stripe_customer_id is not None:
            updates.append("stripe_customer_id = ?")
            values.append(stripe_customer_id)

        if not updates:
            return False

        updates.append("updated_at = ?")
        values.append(datetime.now())
        values.append(user_id)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                values
            )
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_user(self, row: sqlite3.Row) -> DBUser:
        """行データをDBUserに変換"""
        return DBUser(
            id=row["id"],
            email=row["email"],
            password_hash=row["password_hash"],
            name=row["name"],
            plan=row["plan"],
            stripe_customer_id=row["stripe_customer_id"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now()
        )

    # サブスクリプション関連
    def create_subscription(
        self,
        subscription_id: str,
        user_id: str,
        plan: str,
        status: str = "active",
        stripe_subscription_id: Optional[str] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None
    ) -> Optional[DBSubscription]:
        """サブスクリプションを作成"""
        now = datetime.now()
        period_start = period_start or now
        period_end = period_end or datetime(now.year, now.month + 1 if now.month < 12 else 1, 1)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO subscriptions
                    (id, user_id, plan, status, stripe_subscription_id,
                     current_period_start, current_period_end, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (subscription_id, user_id, plan, status, stripe_subscription_id,
                      period_start, period_end, now, now))
                conn.commit()

                return DBSubscription(
                    id=subscription_id,
                    user_id=user_id,
                    plan=plan,
                    status=status,
                    stripe_subscription_id=stripe_subscription_id,
                    current_period_start=period_start,
                    current_period_end=period_end,
                    created_at=now,
                    updated_at=now
                )
        except sqlite3.IntegrityError as e:
            logger.warning(f"サブスクリプション作成エラー: {e}")
            return None

    def get_subscription_by_user(self, user_id: str) -> Optional[DBSubscription]:
        """ユーザーIDでサブスクリプションを取得"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                (user_id,)
            )
            row = cursor.fetchone()

            if row:
                return self._row_to_subscription(row)
            return None

    def update_subscription(
        self,
        subscription_id: str,
        plan: Optional[str] = None,
        status: Optional[str] = None,
        period_end: Optional[datetime] = None
    ) -> bool:
        """サブスクリプションを更新"""
        updates = []
        values = []

        if plan is not None:
            updates.append("plan = ?")
            values.append(plan)
        if status is not None:
            updates.append("status = ?")
            values.append(status)
        if period_end is not None:
            updates.append("current_period_end = ?")
            values.append(period_end)

        if not updates:
            return False

        updates.append("updated_at = ?")
        values.append(datetime.now())
        values.append(subscription_id)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE subscriptions SET {', '.join(updates)} WHERE id = ?",
                values
            )
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_subscription(self, row: sqlite3.Row) -> DBSubscription:
        """行データをDBSubscriptionに変換"""
        return DBSubscription(
            id=row["id"],
            user_id=row["user_id"],
            plan=row["plan"],
            status=row["status"],
            stripe_subscription_id=row["stripe_subscription_id"],
            current_period_start=datetime.fromisoformat(row["current_period_start"]) if row["current_period_start"] else datetime.now(),
            current_period_end=datetime.fromisoformat(row["current_period_end"]) if row["current_period_end"] else datetime.now(),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now()
        )

    # 使用量関連
    def record_usage(
        self,
        user_id: str,
        feature: str,
        period_start: datetime,
        period_end: datetime
    ) -> int:
        """
        使用量を記録

        Args:
            user_id: ユーザーID
            feature: 機能名
            period_start: 期間開始
            period_end: 期間終了

        Returns:
            更新後のカウント
        """
        import uuid

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 既存レコードを確認
            cursor.execute("""
                SELECT id, count FROM usage_records
                WHERE user_id = ? AND feature = ? AND period_start = ?
            """, (user_id, feature, period_start))
            row = cursor.fetchone()

            if row:
                # 既存レコードを更新
                new_count = row["count"] + 1
                cursor.execute("""
                    UPDATE usage_records SET count = ? WHERE id = ?
                """, (new_count, row["id"]))
            else:
                # 新規レコードを作成
                new_count = 1
                cursor.execute("""
                    INSERT INTO usage_records (id, user_id, feature, count, period_start, period_end)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (str(uuid.uuid4()), user_id, feature, new_count, period_start, period_end))

            conn.commit()
            return new_count

    def get_usage(
        self,
        user_id: str,
        feature: str,
        period_start: datetime
    ) -> int:
        """使用量を取得"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT count FROM usage_records
                WHERE user_id = ? AND feature = ? AND period_start = ?
            """, (user_id, feature, period_start))
            row = cursor.fetchone()

            return row["count"] if row else 0

    def get_all_usage(self, user_id: str, period_start: datetime) -> dict[str, int]:
        """全機能の使用量を取得"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT feature, count FROM usage_records
                WHERE user_id = ? AND period_start = ?
            """, (user_id, period_start))

            return {row["feature"]: row["count"] for row in cursor.fetchall()}

    # 監査ログ関連
    def log_audit(
        self,
        action: str,
        user_id: Optional[str] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """監査ログを記録"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_logs (user_id, action, details, ip_address)
                VALUES (?, ?, ?, ?)
            """, (user_id, action, json.dumps(details) if details else None, ip_address))
            conn.commit()

    def get_audit_logs(
        self,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> list[dict]:
        """監査ログを取得"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if user_id:
                cursor.execute("""
                    SELECT * FROM audit_logs WHERE user_id = ?
                    ORDER BY id DESC LIMIT ?
                """, (user_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?
                """, (limit,))

            return [
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "action": row["action"],
                    "details": json.loads(row["details"]) if row["details"] else None,
                    "ip_address": row["ip_address"],
                    "created_at": row["created_at"]
                }
                for row in cursor.fetchall()
            ]


def create_database(db_path: Optional[str] = None) -> Database:
    """
    データベースインスタンスを作成

    Args:
        db_path: データベースファイルパス

    Returns:
        Databaseインスタンス
    """
    return Database(db_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # テスト実行
    print("=== Database テスト ===")

    db = create_database()

    # ユーザー作成
    user = db.create_user(
        user_id="test-user-1",
        email="test@example.com",
        password_hash="hashed_password",
        name="Test User"
    )
    print(f"ユーザー作成: {user}")

    # ユーザー取得
    fetched = db.get_user_by_email("test@example.com")
    print(f"ユーザー取得: {fetched}")

    # サブスクリプション作成
    sub = db.create_subscription(
        subscription_id="sub-1",
        user_id="test-user-1",
        plan="personal"
    )
    print(f"サブスクリプション作成: {sub}")

    # 使用量記録
    now = datetime.now()
    period_start = datetime(now.year, now.month, 1)
    period_end = datetime(now.year, now.month + 1 if now.month < 12 else 1, 1)

    count = db.record_usage("test-user-1", "email_summary", period_start, period_end)
    print(f"使用量記録: {count}")

    # 監査ログ
    db.log_audit("user_created", "test-user-1", {"email": "test@example.com"})
    logs = db.get_audit_logs("test-user-1")
    print(f"監査ログ: {logs}")
