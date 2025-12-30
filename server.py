"""
Android YouTube Music Discord Rich Presence Server
YouTubeMusicの再生情報をDiscordに表示するサーバー
"""

import sys
import io

# Windows文字コード問題対策（UTF-8強制）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from flask import Flask, request, jsonify, abort
from pypresence import Presence
from ytmusicapi import YTMusic
from difflib import SequenceMatcher
from dotenv import load_dotenv
import os
import time
import threading
import atexit

# 本番用サーバー
from waitress import serve

# ========================================
#  設定
# ========================================

# .envファイルから環境変数を読み込み
load_dotenv()

# Discord Application ID
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID', '1442908216097767424')
SERVER_HOST = os.getenv('SERVER_HOST', '0.0.0.0')
SERVER_PORT = int(os.getenv('SERVER_PORT', '5000'))
AUTH_TOKEN = os.getenv('AUTH_TOKEN') # 設定されていない場合はNone

# ========================================
#  グローバル変数
# ========================================

app = Flask(__name__)

# Discord RPC関連
RPC = None
rpc_connected = False
rpc_lock = threading.Lock()

# YTMusic検索
yt = YTMusic()

# 状態保存用
last_title = ""
last_artist = ""
last_is_playing = True # 初期値
# 画像キャッシュ（同じ曲を何度も検索しないため）
# 形式: {"曲名 - アーティスト": "画像URL"}
image_cache = {}
CACHE_MAX_SIZE = 100  # キャッシュの最大数

# 自動クリア用（一定時間更新がなければPresenceを消す）
IDLE_TIMEOUT = 180  # 3分間更新がなければクリア
idle_timer = None

# ========================================
#  ユーティリティ関数
# ========================================

def check_auth():
    """認証トークンを確認"""
    if not AUTH_TOKEN:
        return True # トークン設定がなければ認証スキップ（警告推奨）
    
    auth_header = request.headers.get('Authorization')
    # "Bearer <token>" 形式または直接トークンを許容
    if auth_header and (auth_header == AUTH_TOKEN or auth_header == f"Bearer {AUTH_TOKEN}"):
        return True
    
    return False

def similar(a: str, b: str) -> float:
    """文字列の類似度を判定（0.0〜1.0）"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def get_cache_key(title: str, artist: str) -> str:
    """キャッシュ用のキーを生成"""
    return f"{title.lower()}|{artist.lower()}"


def connect_rpc() -> bool:
    """Discord RPCに接続を試みる"""
    global RPC, rpc_connected
    
    with rpc_lock:
        try:
            if RPC is None:
                RPC = Presence(CLIENT_ID)
            
            # 既に接続済みの場合はconnectしない
            # pypresenceの仕様上、closeせずにconnectはエラーになる場合があるため
            # ここではシンプルに再接続ロジックとする
            RPC.connect()
            rpc_connected = True
            print("✅ Discordに接続しました！")
            return True
        except Exception as e:
            rpc_connected = False
            # 頻繁に出るとうるさいので接続失敗ログは控えめに、あるいは初回のみ
            print(f"⚠️ Discord接続失敗: {e}")
            return False


def ensure_rpc_connection() -> bool:
    """RPC接続を確認し、必要なら再接続"""
    global rpc_connected
    
    if rpc_connected:
        return True
    
    print("🔄 Discord再接続を試みます...")
    return connect_rpc()


def clear_presence():
    """Presenceをクリアする"""
    global rpc_connected
    
    with rpc_lock:
        if rpc_connected and RPC:
            try:
                RPC.clear()
                print("🧹 Presenceをクリアしました")
            except Exception as e:
                print(f"⚠️ Presenceクリア失敗: {e}")
                rpc_connected = False


def reset_idle_timer():
    """アイドルタイマーをリセット"""
    global idle_timer
    
    if idle_timer:
        idle_timer.cancel()
    
    idle_timer = threading.Timer(IDLE_TIMEOUT, clear_presence)
    idle_timer.daemon = True
    idle_timer.start()


def search_album_art(title: str, artist: str) -> tuple[str, str | None]:
    """
    曲のアルバムアートを検索
    Returns: (image_url, video_id)
    """
    global image_cache
    
    cache_key = get_cache_key(title, artist)
    
    # キャッシュに存在すればそれを返す
    if cache_key in image_cache:
        cached = image_cache[cache_key]
        print(f"📦 キャッシュヒット: {title}")
        return cached['image'], cached.get('video_id')
    
    image_url = "youtube_music_icon"
    video_id = None
    
    try:
        # 検索処理（同期処理なので時間がかかる可能性がある）
        # 将来的には非同期化が望ましいが、簡易実装のためこのまま
        search_results = yt.search(f"{title} {artist}", filter="songs")
        
        if search_results:
            best_match = None
            highest_score = 0

            for item in search_results:
                res_title = item.get('title', "")
                res_artists = item.get('artists', [])
                res_artist_name = res_artists[0]['name'] if res_artists else ""

                title_score = similar(title, res_title)
                artist_score = similar(artist, res_artist_name)
                total_score = (title_score + artist_score) / 2

                if total_score > 0.5 and total_score > highest_score:
                    highest_score = total_score
                    best_match = item

            if best_match and highest_score > 0.5:
                # サムネイル取得
                thumbnails = best_match.get('thumbnails', [])
                if thumbnails:
                    image_url = thumbnails[-1]['url']
                
                video_id = best_match.get('videoId')
                print(f"✅ 画像特定 (信頼度: {highest_score:.2f}): {best_match['title']}")
            else:
                print(f"⚠️ 良い画像が見つかりませんでした (最高スコア: {highest_score:.2f})")

    except Exception as search_error:
        print(f"🔍 画像検索失敗: {search_error}")
    
    # キャッシュに保存（サイズ制限あり）
    if len(image_cache) >= CACHE_MAX_SIZE:
        # 古いエントリを削除（FIFOで先頭を削除）
        oldest_key = next(iter(image_cache))
        del image_cache[oldest_key]
    
    image_cache[cache_key] = {'image': image_url, 'video_id': video_id}
    
    return image_url, video_id


# ========================================
#  APIエンドポイント
# ========================================
last_update_time = 0
last_calc_start_time = 0

@app.before_request
def before_request():
    """リクエストごとの前処理（認証チェック）"""
    # health checkは認証不要でも良いが、念のためすべてに適用するか、
    # 公開しないなら全部にかける。今回は全てにかける。
    if request.endpoint == 'health_check':
        return # health checkは除外（死活監視のため）
    
    if not check_auth():
        print(f"⛔ 認証失敗: {request.remote_addr}")
        return jsonify({"error": "Unauthorized"}), 401


@app.route('/update', methods=['POST'])
def update_status():
    """再生情報を受け取りDiscord Presenceを更新"""
    global last_title, last_artist, last_is_playing, last_update_time, last_calc_start_time
    
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        # バリデーションと型変換
        title = str(data.get('title', 'Unknown Title'))
        artist = str(data.get('artist', 'Unknown Artist'))
        is_playing = bool(data.get('is_playing', True))
        
        try:
            duration = float(data.get('duration', 0))
            position = float(data.get('position', 0))
        except (ValueError, TypeError):
            duration = 0
            position = 0
        
        print(f"📩 受信: {title} - {artist} (Pos: {position}s)")
        
        # 一時停止中なら「Paused」表示にする
        small_image = "youtube_music_icon"
        small_text = "Playing on Android"
        
        if not is_playing:
            print("⏸️ 一時停止中")
            small_image = "https://img.icons8.com/ios-glyphs/60/ffffff/pause--v1.png"
            small_text = "⏸️ Paused"
        
        # 空文字チェックと最小長確保
        if not title.strip(): title = "Unknown Title"
        if not artist.strip(): artist = "Unknown Artist"
        if len(title) < 2: title += " "
        if len(artist) < 2: artist += " "

        # シーク検知ロジック
        current_time = time.time()
        calc_start_time = current_time - position # 今回の計算上の開始時間
        
        # 前回計算した開始時間とのズレが2秒以上あれば「シークされた」とみなす
        time_diff = abs(calc_start_time - last_calc_start_time)
        is_seeked = time_diff > 2 # 2秒以上のズレ
        
        # 同じ曲 かつ 状態変化なし かつ シークもしていない ならスキップ
        # ただし、再生位置が大きくずれていないかの確認なども含める
        if (title == last_title and 
            artist == last_artist and 
            is_playing == last_is_playing and 
            not is_seeked and
            current_time - last_update_time < 60):
            
            reset_idle_timer()
            return "Skipped", 200

        # 更新あり
        last_title = title
        last_artist = artist
        last_is_playing = is_playing
        last_update_time = current_time
        last_calc_start_time = calc_start_time # 基準時間を更新

        # Discord接続確認
        if not ensure_rpc_connection():
            return "Discord not connected", 503

        # 画像検索（キャッシュ対応）
        image_url, video_id = search_album_art(title, artist)

        # タイムスタンプ計算（再生中のみ表示）
        timestamps = {}
        if is_playing and duration > 0:
            start_time = int(current_time - position)
            end_time = int(start_time + duration)
            timestamps = {
                'start': start_time,
                'end': end_time
            }

        # ボタン設定（YouTube Musicで開くリンク）
        buttons = None
        if video_id:
            buttons = [
                {
                    "label": "🎵 Listen on YouTube Music",
                    "url": f"https://music.youtube.com/watch?v={video_id}"
                }
            ]

        # Discordのステータスを更新
        with rpc_lock:
            try:
                update_args = {
                    'details': title,
                    'state': artist,
                    'large_image': image_url,
                    'large_text': "YouTube Music",
                    'small_image': small_image,
                    'small_text': small_text
                }
                
                if timestamps:
                    update_args['start'] = timestamps.get('start')
                    update_args['end'] = timestamps.get('end')
                
                if buttons:
                    update_args['buttons'] = buttons
                
                result = RPC.update(**update_args)
                print(f"🎵 Presence更新: {title} - {artist}", flush=True)
                
            except Exception as rpc_error:
                global rpc_connected
                rpc_connected = False
                print(f"⚠️ Presence更新失敗: {rpc_error}")
                return "RPC Error", 500
        
        # アイドルタイマーリセット
        reset_idle_timer()
        
        return "OK", 200
        
    except Exception as e:
        print(f"❌ エラー: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/pause', methods=['POST'])
def pause_status():
    """一時停止時にPresenceをクリア"""
    clear_presence()
    return "Cleared", 200


@app.route('/health', methods=['GET'])
def health_check():
    """ヘルスチェック用エンドポイント"""
    return jsonify({
        "status": "running",
        "discord_connected": rpc_connected,
        "cache_size": len(image_cache),
        "auth_enabled": bool(AUTH_TOKEN)
    }), 200


# ========================================
#  クリーンアップ
# ========================================

def cleanup():
    """終了時のクリーンアップ"""
    global idle_timer
    
    print("🛑 サーバー終了処理中...")
    
    if idle_timer:
        idle_timer.cancel()
    
    clear_presence()
    
    with rpc_lock:
        if RPC:
            try:
                RPC.close()
            except:
                pass

atexit.register(cleanup)


# ========================================
#  メイン
# ========================================

if __name__ == '__main__':
    print("=" * 50)
    print("🎵 YouTube Music Discord Presence Server")
    print("=" * 50)
    
    if not AUTH_TOKEN:
        print("⚠️  警告: AUTH_TOKENが設定されていません。.envファイルの設定を推奨します。")
        print("    認証なしで誰でもリクエストを送信できる状態です。")
    else:
        print("🔒 認証: 有効 (Token設定済み)")
    
    print(f"📡 サーバー: http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"🔑 Client ID: {CLIENT_ID[:8]}...")
    print("=" * 50)
    
    # 初回接続
    connect_rpc()
    
    # Waitressサーバー起動
    print(f"🚀 サーバー稼働中... (Press CTRL+C to quit)")
    try:
        serve(app, host=SERVER_HOST, port=SERVER_PORT)
    except OSError as e:
        print(f"❌ 起動エラー: {e}")
        print("ポートが既に使用されている可能性があります。")