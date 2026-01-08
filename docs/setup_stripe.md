# Stripe API セットアップガイド

TaskMasterAIの課金システムに必要なStripe設定手順。

## 1. Stripeアカウント作成

1. [Stripe Dashboard](https://dashboard.stripe.com/)にアクセス
2. アカウント作成（ビジネス情報は後で設定可能）
3. ダッシュボードにログイン

## 2. APIキー取得

1. ダッシュボード右上「開発者」をクリック
2. 「APIキー」を選択
3. 以下をコピー:
   - **公開可能キー**: `pk_test_...`（フロントエンド用）
   - **シークレットキー**: `sk_test_...`（バックエンド用）

> ⚠️ 本番環境では`test`を`live`キーに置き換え

## 3. 製品・価格の作成

### ダッシュボードから作成

1. 「製品」→「製品を追加」
2. 製品情報を入力

| プラン | 名前 | 月額 | 説明 |
|--------|------|------|------|
| Personal | TaskMasterAI Personal | $10/月 | 500メール要約/月 |
| Pro | TaskMasterAI Pro | $25/月 | 2000メール要約/月 |
| Team | TaskMasterAI Team | $15/月/人 | 5000メール要約/月 |

3. 各製品で「価格を追加」→「繰り返し」を選択
4. 作成後、価格IDをコピー（`price_1xxx...`形式）

### CLIから作成（オプション）

```bash
# Stripe CLIインストール後
stripe products create --name="TaskMasterAI Personal" --description="500 email summaries/month"
stripe prices create --product=prod_xxx --unit-amount=1000 --currency=usd --recurring[interval]=month
```

## 4. 環境変数設定

`.env`ファイルに追加:

```bash
# Stripe API Keys
STRIPE_API_KEY=sk_test_xxxxxxxxxxxxxxxx

# Price IDs
STRIPE_PRICE_PERSONAL=price_xxxxxxxxxxxxxx
STRIPE_PRICE_PRO=price_xxxxxxxxxxxxxx
STRIPE_PRICE_TEAM=price_xxxxxxxxxxxxxx
```

## 5. Webhook設定（本番用）

1. 「開発者」→「Webhook」→「エンドポイントを追加」
2. エンドポイントURL: `https://your-domain.com/webhook/stripe`
3. イベント選択:
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
4. Webhook秘密鍵をコピー → `.env`に追加

```bash
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxx
```

## 6. テスト

### テストカード番号

| カード | 番号 | 結果 |
|--------|------|------|
| 成功 | 4242 4242 4242 4242 | 支払い成功 |
| 拒否 | 4000 0000 0000 0002 | カード拒否 |
| 認証必要 | 4000 0025 0000 3155 | 3D Secure |

すべてのテストカード: 有効期限は将来の日付、CVCは任意の3桁

### APIテスト

```python
import stripe
stripe.api_key = "sk_test_xxx"

# カスタマー作成テスト
customer = stripe.Customer.create(
    email="test@example.com",
    name="Test User"
)
print(f"Customer ID: {customer.id}")
```

## トラブルシューティング

### "Invalid API Key" エラー

- キーが正しくコピーされているか確認
- test/liveモードが一致しているか確認

### "No such price" エラー

- 価格IDが存在するか確認
- test/liveモードの価格IDが一致しているか確認

### Webhook署名検証エラー

- Webhook秘密鍵が正しいか確認
- ローカルテストの場合は`stripe listen`を使用

## 本番移行チェックリスト

- [ ] ビジネス情報を完全に入力
- [ ] 銀行口座を接続
- [ ] test→liveキーに切り替え
- [ ] 本番用Webhookエンドポイント設定
- [ ] 税務設定を確認
