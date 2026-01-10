# -*- coding: utf-8 -*-
"""
ベータ登録DB永続化テスト

ベータ登録機能のDB永続化に関するテストを提供
"""

import pytest
from src.database import Database, create_database


class TestBetaSignupDatabase:
    """ベータ登録データベース機能テスト"""

    @pytest.fixture
    def db(self):
        """テスト用インメモリDB"""
        database = create_database(":memory:")
        yield database
        database.close()

    def test_add_beta_signup_success(self, db):
        """ベータ登録成功テスト"""
        success, message = db.add_beta_signup("test@example.com")
        assert success is True
        assert "登録ありがとうございます" in message

    def test_add_beta_signup_duplicate(self, db):
        """ベータ登録重複テスト"""
        # 初回登録
        db.add_beta_signup("test@example.com")
        # 重複登録
        success, message = db.add_beta_signup("test@example.com")
        assert success is True
        assert "既に登録済み" in message

    def test_add_beta_signup_case_insensitive(self, db):
        """ベータ登録大文字小文字無視テスト"""
        db.add_beta_signup("Test@Example.com")
        success, message = db.add_beta_signup("test@example.com")
        assert success is True
        assert "既に登録済み" in message

    def test_add_beta_signup_with_source(self, db):
        """ベータ登録ソース指定テスト"""
        success, message = db.add_beta_signup("api@example.com", source="api")
        assert success is True
        signups = db.get_beta_signups()
        assert len(signups) == 1
        assert signups[0]["source"] == "api"

    def test_get_beta_signup_count_empty(self, db):
        """ベータ登録数取得（空）テスト"""
        count = db.get_beta_signup_count()
        assert count == 0

    def test_get_beta_signup_count(self, db):
        """ベータ登録数取得テスト"""
        db.add_beta_signup("test1@example.com")
        db.add_beta_signup("test2@example.com")
        db.add_beta_signup("test3@example.com")
        count = db.get_beta_signup_count()
        assert count == 3

    def test_get_beta_signups_empty(self, db):
        """ベータ登録一覧取得（空）テスト"""
        signups = db.get_beta_signups()
        assert signups == []

    def test_get_beta_signups(self, db):
        """ベータ登録一覧取得テスト"""
        db.add_beta_signup("test1@example.com", source="landing_page")
        db.add_beta_signup("test2@example.com", source="api")
        signups = db.get_beta_signups()
        assert len(signups) == 2
        assert all("email" in s for s in signups)
        assert all("created_at" in s for s in signups)
        assert all("source" in s for s in signups)
        assert all("status" in s for s in signups)

    def test_get_beta_signups_pagination(self, db):
        """ベータ登録一覧ページネーションテスト"""
        for i in range(10):
            db.add_beta_signup(f"test{i}@example.com")

        # 最初の3件
        signups = db.get_beta_signups(limit=3, offset=0)
        assert len(signups) == 3

        # 次の3件
        signups = db.get_beta_signups(limit=3, offset=3)
        assert len(signups) == 3

        # 全件数確認
        assert db.get_beta_signup_count() == 10

    def test_get_beta_emails_empty(self, db):
        """ベータ登録メール一覧取得（空）テスト"""
        emails = db.get_beta_emails()
        assert emails == []

    def test_get_beta_emails(self, db):
        """ベータ登録メール一覧取得テスト"""
        db.add_beta_signup("test1@example.com")
        db.add_beta_signup("test2@example.com")
        emails = db.get_beta_emails()
        assert len(emails) == 2
        assert "test1@example.com" in emails
        assert "test2@example.com" in emails

    def test_is_beta_registered_false(self, db):
        """ベータ登録確認（未登録）テスト"""
        assert db.is_beta_registered("notregistered@example.com") is False

    def test_is_beta_registered_true(self, db):
        """ベータ登録確認（登録済み）テスト"""
        db.add_beta_signup("registered@example.com")
        assert db.is_beta_registered("registered@example.com") is True

    def test_is_beta_registered_case_insensitive(self, db):
        """ベータ登録確認大文字小文字無視テスト"""
        db.add_beta_signup("Test@Example.com")
        assert db.is_beta_registered("test@example.com") is True
        assert db.is_beta_registered("TEST@EXAMPLE.COM") is True

    def test_email_normalization_whitespace(self, db):
        """メールアドレス正規化（空白）テスト"""
        db.add_beta_signup("  test@example.com  ")
        assert db.is_beta_registered("test@example.com") is True

    def test_beta_signup_status_default(self, db):
        """ベータ登録ステータスデフォルト値テスト"""
        db.add_beta_signup("test@example.com")
        signups = db.get_beta_signups()
        assert signups[0]["status"] == "pending"


class TestBetaSignupPersistence:
    """ベータ登録永続化テスト"""

    def test_file_persistence(self, tmp_path):
        """ファイル永続化テスト"""
        db_path = str(tmp_path / "test_beta.db")

        # DB作成・登録
        db1 = create_database(db_path)
        db1.add_beta_signup("persist@example.com")
        count1 = db1.get_beta_signup_count()
        db1.close()

        # 再接続・確認
        db2 = create_database(db_path)
        count2 = db2.get_beta_signup_count()
        assert count2 == count1
        assert db2.is_beta_registered("persist@example.com") is True
        db2.close()
