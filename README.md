# 🎵 Android YouTube Music Discord Rich Presence

AndroidのYouTube Musicで再生中の曲をDiscordに表示するサーバーです。

![Discord Rich Presence Preview](https://i.imgur.com/example.png)

## ✨ 機能

- 🎵 **曲名・アーティスト名の表示** - 再生中の曲情報をリアルタイム表示
- 🖼️ **アルバムアート表示** - YouTube Music APIから自動取得
- ⏱️ **再生時間表示** - 曲の進行状況を表示
- 🔗 **YouTube Musicリンク** - ワンクリックで曲を開けるボタン
- 🔄 **自動再接続** - Discordとの接続が切れても自動復帰
- ⏸️ **一時停止検出** - 停止中は「Paused」ステータスを表示
- 🔒 **セキュリティ強化** - 外部公開対応（レート制限、IP制限、認証機能）

## 📋 必要なもの

- Python 3.8以上
- Discord（PC版アプリ）
- Android端末（専用アプリをインストールまたはTasker等を使用）

## 🚀 セットアップ（サーバー側）

### 1. リポジトリをクローン

```bash
git clone https://github.com/S0iRu/AndroidYouTubeMusicDiscordRPC.git
cd AndroidYouTubeMusicDiscordRPC
```

### 2. 依存関係をインストール

```bash
pip install -r requirements.txt
```

### 3. 環境変数を設定

`.env.example` を `.env` にコピーして編集します。

```bash
cp .env.example .env
```

`.env`ファイルを編集し、**必ず** `AUTH_TOKEN` を設定してください。

```bash
# セキュアなトークンを生成して設定（例）
AUTH_TOKEN=your-secure-random-token
```

### 4. サーバーを起動

```bash
python server.py
# Production server (waitress) running on http://0.0.0.0:5000
```

## 📱 セットアップ（Androidクライアント）

### 1. アプリをビルド & インストール
同梱の `AndroidStudio` フォルダを開き、アプリをビルドして端末にインストールします。

### 2. アプリ設定
アプリを起動し、以下の情報を設定します：

- **Server Host**: サーバーのIPアドレス（例: `192.168.1.100` やドメイン）
- **Server Port**: `5000`
- **Auth Token**: サーバーの `.env` で設定したトークン

### 3. 権限許可
「Open Notification Settings」をタップし、通知へのアクセスを許可してください。

## ⚙️ 詳細設定（環境変数）

`.env` ファイルで以下の設定が可能です。

| 変数名 | 説明 | デフォルト |
|--------|------|----------|
| `DISCORD_CLIENT_ID` | Discord Application ID | (Default ID) |
| `SERVER_HOST` | サーバーホスト | 0.0.0.0 |
| `SERVER_PORT` | サーバーポート | 5000 |
| `AUTH_TOKEN` | **[必須]** API認証トークン | None |
| `ALLOWED_IPS` | 許可するIPアドレス（カンマ区切り）。空なら全許可 | (空) |
| `TRUST_PROXY` | リバースプロキシ使用時は `true` に設定 | false |
| `RATE_LIMIT_*` | レート制限の設定 | 60/min |

## 🛡️ セキュリティ機能

本サーバーは外部公開を想定していくつかのセキュリティ機能を備えています。

1. **認証機能**: `AUTH_TOKEN` によるBearer認証（タイミング攻撃対策済み）。
2. **レート制限**: DoS攻撃対策としてリクエスト頻度を制限。
3. **IP制限**: `ALLOWED_IPS` でアクセス元のIPを制限可能。
4. **ブルートフォース対策**: 認証失敗が続くとIPを一時的にブロック。
5. **暗号化保存**: Androidアプリ側でトークンを暗号化して保存。

> [!WARNING]
> 外部サーバーに公開する場合は、必ず **HTTPS (SSL/TLS)** を使用してください。Nginx等のリバースプロキシでSSL終端を行うことを強く推奨します。

## 📡 APIエンドポイント

### POST `/update`
曲情報を更新します。

**ヘッダー:** `Authorization: Bearer <AUTH_TOKEN>`

**ボディ:**
```json
{
  "title": "曲名",
  "artist": "アーティスト名",
  "is_playing": true,
  "duration": 240,
  "position": 60
}
```

<!--
## 📝 ライセンス

MIT License
-->
