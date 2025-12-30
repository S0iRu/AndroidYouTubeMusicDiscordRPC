# 🎵 Android YouTube Music Discord Rich Presence

AndroidのYouTube Musicで再生中の曲をDiscordに表示するサーバーです。

![Discord Rich Presence Preview](https://i.imgur.com/example.png)

## ✨ 機能

- 🎵 **曲名・アーティスト名の表示** - 再生中の曲情報をリアルタイム表示
- 🖼️ **アルバムアート表示** - YouTube Music APIから自動取得
- ⏱️ **再生時間表示** - 曲の進行状況を表示（対応クライアント必要）
- 🔗 **YouTube Musicリンク** - ワンクリックで曲を開けるボタン
- 🔄 **自動再接続** - Discordとの接続が切れても自動復帰
- ⏸️ **一時停止検出** - 停止中は「Paused」ステータスを表示
- 📦 **画像キャッシュ** - 同じ曲の再検索を防止

## 📋 必要なもの

- Python 3.8以上
- Discord（PC版アプリ）
- Androidアプリ（Tasker等で曲情報を送信）

## 🚀 セットアップ

### 1. リポジトリをクローン

```bash
git clone https://github.com/yourusername/AndroidYouTubeMusicDiscordRPC.git
cd AndroidYouTubeMusicDiscordRPC
```

### 2. 依存関係をインストール

```bash
pip install -r requirements.txt
```

### 3. 環境変数を設定

```bash
# .env.exampleをコピー
cp .env.example .env

# .envを編集して設定を変更
# - DISCORD_CLIENT_ID: そのまま
# - AUTH_TOKEN: 安全なパスワードに変更してください（任意ですが推奨）
```

**Recommended:** セキュリティのため `AUTH_TOKEN` を設定することを強く推奨します。

### 4. サーバーを起動

```bash
python server.py
# Production server (waitress) on http://0.0.0.0:5000
```

## 📡 APIエンドポイント

### POST `/update`
曲情報を更新します。ヘッダーに `Authorization: Bearer <AUTH_TOKEN>` が必要です（トークン設定時）。

**リクエストボディ:**
```json
{
  "title": "曲名",
  "artist": "アーティスト名",
  "is_playing": true,
  "duration": 240,
  "position": 60
}
```

## 📱 Androidクライアントの設定

### 1. Android Studioでビルド
同梱の `AndroidStudio` フォルダを開き、アプリをビルドして端末にインストールします。

### 2. アプリ設定
アプリを起動すると設定画面が表示されます。以下の情報を入力して「Save Settings」を押してください。

- **PC IP Address**: サーバーを起動しているPCのIPアドレス（例: `192.168.1.10`）
- **Port**: `5000`（変更していなければそのまま）
- **Auth Token**: `.env` ファイルで設定したトークン（設定していなければ空欄）

### 3. 権限の許可
「Open Notification Settings」ボタンをタップし、「通知へのアクセス」をこのアプリに許可してください。

### 4. YouTube Musicで再生
設定完了後、YouTube Musicで音楽を再生するとPC側のDiscord Rich Presenceが更新されます。

---

### (代替手段) Taskerなどの自動化アプリを使用する場合
自作アプリを使用せず、TaskerなどのHTTPリクエスト送信機能を持つアプリを使用することも可能です。

**設定例:**
1. プロファイル: アプリ = YouTube Music
2. タスク: HTTP Request
   - Method: POST
   - URL: `http://YOUR_PC_IP:5000/update`
   - Headers: `Authorization: Bearer YOUR_TOKEN` (トークン設定時)
   - Body: `{"title": "%MTRACK", "artist": "%MARTIST"}`

## ⚙️ 環境変数

| 変数名 | 説明 | デフォルト |
|--------|------|----------|
| DISCORD_CLIENT_ID | Discord Application ID | (Default ID) |
| SERVER_HOST | サーバーホスト | 0.0.0.0 |
| SERVER_PORT | サーバーポート | 5000 |
| AUTH_TOKEN | API認証トークン（推奨） | None |

## 📝 ライセンス

MIT License
