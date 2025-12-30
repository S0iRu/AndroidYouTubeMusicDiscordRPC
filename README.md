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

# .envを編集してDiscord Application IDを設定
```

**Discord Application IDの取得方法:**
1. [Discord Developer Portal](https://discord.com/developers/applications)にアクセス
2. 「New Application」でアプリを作成
3. 「Application ID」をコピー

### 4. サーバーを起動

```bash
python server.py
```

## 📡 APIエンドポイント

### POST `/update`
曲情報を更新します。

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

| フィールド | 型 | 説明 |
|----------|------|------|
| title | string | 曲名（必須） |
| artist | string | アーティスト名（必須） |
| is_playing | boolean | 再生中かどうか（オプション、デフォルト: true） |
| duration | number | 曲の長さ（秒）（オプション） |
| position | number | 現在の再生位置（秒）（オプション） |

### POST `/pause`
Presenceをクリアします。

### GET `/health`
サーバーの状態を確認します。

**レスポンス:**
```json
{
  "status": "running",
  "discord_connected": true,
  "cache_size": 10
}
```

## 📱 Androidクライアントの設定

### 1. Android Studioを開く
同梱の `AndroidStudio` フォルダをAndroid Studioで開きます。

### 2. IPアドレスの設定
`app/src/main/java/com/example/youtubemusicrpc/MyNotificationListener.kt` を開き、`SERVER_URL` をあなたのPCのIPアドレスに変更してください。

```kotlin
// Before
private val SERVER_URL = "http://100.125.20.126:5000/update"

// After (例: PCのIPが 192.168.1.10 の場合)
private val SERVER_URL = "http://192.168.1.10:5000/update"
```

### 3. ビルドとインストール
アプリをビルドし、Android端末にインストールします。

### 4. 権限の許可
1. アプリを起動し、画面上のボタンをタップします。
2. 「通知へのアクセス」設定画面が開くので、このアプリ（YouTube Music RPC Listener）をONにします。

### 5. YouTube Musicで再生
YouTube Musicアプリで音楽を再生すると、自動的にDiscord Rich Presenceが更新されます。

---

### (代替手段) Taskerなどの自動化アプリを使用する場合
自作アプリを使用せず、TaskerなどのHTTPリクエスト送信機能を持つアプリを使用することも可能です。

**設定例:**
1. プロファイル: アプリ = YouTube Music
2. タスク: HTTP Request
   - Method: POST
   - URL: `http://YOUR_PC_IP:5000/update`
   - Body: `{"title": "%MTRACK", "artist": "%MARTIST"}`

## ⚙️ 環境変数

| 変数名 | 説明 | デフォルト |
|--------|------|----------|
| DISCORD_CLIENT_ID | Discord Application ID | - |
| SERVER_HOST | サーバーホスト | 0.0.0.0 |
| SERVER_PORT | サーバーポート | 5000 |

## 📝 ライセンス

MIT License
