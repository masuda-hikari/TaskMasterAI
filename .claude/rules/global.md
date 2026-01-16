---
paths:
  - "**/*"
---

# グローバルルール（O:\Dev配下全プロジェクト共通）

## 言語設定
- 応答・コメント・commit: 日本語必須
- 英語切替禁止

## パス指定
- Read/Edit/Write: Windowsフルパス（バックスラッシュ）必須
- 例: `O:\Dev\Project\file.rs`

## 基本原則
- DRY: 2箇所使用→即共通化
- 既存確認必須・改良優先
- 循環参照禁止

## 禁止事項
- 未テストコミット
- 認証情報ハードコード
- 脆弱性導入
- UTF-8以外のエンコーディング

## セッション開始
1. CLAUDE.md読込
2. DEVELOPMENT_LOG確認
3. TodoWrite計画作成

## セッション終了
1. テスト合格確認
2. DEVELOPMENT_LOG更新
