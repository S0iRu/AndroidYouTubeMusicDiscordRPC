"""
Android YouTube Music Discord Rich Presence Server
YouTubeMusicの再生情報をDiscordに表示するサーバー

外部公開対応版 - セキュリティ強化済み
"""

import sys
import io
import re
import secrets
import logging

# Windows文字コード問題対策（UTF-8強制）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ファイルログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.FileHandler('server_debug.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

from flask import Flask, request, jsonify, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from pypresence import Presence
from ytmusicapi import YTMusic
from difflib import SequenceMatcher
from dotenv import load_dotenv
import os
import time
import threading
import atexit
import hashlib
import hmac

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
AUTH_TOKEN = os.getenv('AUTH_TOKEN')  # 設定されていない場合はNone

# セキュリティ設定
ALLOWED_IPS = os.getenv('ALLOWED_IPS', '')  # カンマ区切りで許可IP指定 (空なら全許可)
RATE_LIMIT_UPDATE = os.getenv('RATE_LIMIT_UPDATE', '60/minute')  # /update のレート制限
RATE_LIMIT_DEFAULT = os.getenv('RATE_LIMIT_DEFAULT', '120/minute')  # デフォルトのレート制限
MAX_CONTENT_LENGTH = 10 * 1024  # 10KB（リクエストボディの最大サイズ）

# リバースプロキシ設定（X-Forwarded-Forを信頼するか）
# Nginx等のリバースプロキシ経由でアクセスする場合のみtrueに設定
TRUST_PROXY = os.getenv('TRUST_PROXY', 'false').lower() == 'true'

# 許可IPリストをパース
ALLOWED_IP_LIST = [ip.strip() for ip in ALLOWED_IPS.split(',') if ip.strip()]

# ========================================
#  Flaskアプリ初期化
# ========================================

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# CORS設定（必要に応じてoriginsを制限）
CORS(app, resources={
    r"/*": {
        "origins": "*",  # 本番環境では特定のオリジンに制限推奨
        "methods": ["GET", "POST"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# レート制限設定
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[RATE_LIMIT_DEFAULT],
    storage_uri="memory://",
    strategy="fixed-window"
)

# ========================================
#  グローバル変数
# ========================================

# Discord RPC関連
RPC = None
rpc_connected = False
rpc_lock = threading.Lock()

# YTMusic検索
yt = YTMusic()

# 状態保存用
last_title = ""
last_artist = ""
last_is_playing = True
# 画像キャッシュ
image_cache = {}
CACHE_MAX_SIZE = 100

# 自動クリア用
IDLE_TIMEOUT = 180
idle_timer = None

# 認証失敗ログ用（ブルートフォース対策）
auth_failures = {}
AUTH_FAILURE_THRESHOLD = 10  # 10回失敗でブロック
AUTH_FAILURE_WINDOW = 300    # 5分間
MAX_AUTH_FAILURE_ENTRIES = 1000  # メモリ保護: 最大追跡IP数

# ========================================
#  セキュリティ関数
# ========================================

def get_client_ip():
    """クライアントIPを取得（プロキシ対応）"""
    # TRUST_PROXYが有効な場合のみX-Forwarded-Forを信頼
    # 直接接続時にこれを信頼すると、攻撃者がIPを偽装できる
    if TRUST_PROXY and request.headers.get('X-Forwarded-For'):
        # 最初のIPが元のクライアント
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'


def is_ip_allowed(ip: str) -> bool:
    """IPアドレスが許可リストにあるか確認"""
    if not ALLOWED_IP_LIST:
        return True  # 許可リストが空なら全許可
    
    # CIDR表記やワイルドカードにも対応可能だが、簡易実装として完全一致のみ
    return ip in ALLOWED_IP_LIST


def is_ip_blocked(ip: str) -> bool:
    """IPがブルートフォース対策でブロックされているか"""
    if ip not in auth_failures:
        return False
    
    failures = auth_failures[ip]
    current_time = time.time()
    
    # ウィンドウ外の古い失敗を削除
    failures = [t for t in failures if current_time - t < AUTH_FAILURE_WINDOW]
    auth_failures[ip] = failures
    
    return len(failures) >= AUTH_FAILURE_THRESHOLD


def record_auth_failure(ip: str):
    """認証失敗を記録（メモリ制限付き）"""
    if ip not in auth_failures:
        # メモリ保護: エントリ数が上限に達したら最も古いものを削除
        if len(auth_failures) >= MAX_AUTH_FAILURE_ENTRIES:
            # 最も古い失敗記録を持つIPを削除
            oldest_ip = min(auth_failures.keys(), key=lambda k: min(auth_failures[k]) if auth_failures[k] else float('inf'))
            del auth_failures[oldest_ip]
        auth_failures[ip] = []
    auth_failures[ip].append(time.time())


def check_auth() -> bool:
    """認証トークンを確認（タイミング攻撃対策付き）"""
    if not AUTH_TOKEN:
        return True  # トークン設定がなければ認証スキップ
    
    auth_header = request.headers.get('Authorization', '')
    
    # Bearer プレフィックスを除去
    token = auth_header
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    
    # タイミング攻撃対策: 固定時間比較
    return hmac.compare_digest(token, AUTH_TOKEN)


def sanitize_string(s: str, max_length: int = 200) -> str:
    """文字列をサニタイズ（長さ制限、危険な文字除去）"""
    if not isinstance(s, str):
        s = str(s)
    
    # 長さ制限
    s = s[:max_length]
    
    # 制御文字を除去（改行・タブは許容）
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s)
    
    return s.strip()


def validate_number(value, default: float = 0, min_val: float = 0, max_val: float = float('inf')) -> float:
    """数値をバリデーション"""
    try:
        num = float(value)
        if num < min_val:
            return min_val
        if num > max_val:
            return max_val
        return num
    except (ValueError, TypeError):
        return default


# ========================================
#  ユーティリティ関数
# ========================================

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
            
            RPC.connect()
            rpc_connected = True
            print("✅ Discordに接続しました！")
            return True
        except Exception as e:
            rpc_connected = False
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
    """曲のアルバムアートを検索"""
    global image_cache
    
    cache_key = get_cache_key(title, artist)
    
    if cache_key in image_cache:
        cached = image_cache[cache_key]
        print(f"📦 キャッシュヒット: {title}")
        return cached['image'], cached.get('video_id')
    
    image_url = "youtube_music_icon"
    video_id = None
    
    try:
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
                thumbnails = best_match.get('thumbnails', [])
                if thumbnails:
                    image_url = thumbnails[-1]['url']
                video_id = best_match.get('videoId')
                print(f"✅ 画像特定 (信頼度: {highest_score:.2f}): {best_match['title']}")
            else:
                print(f"⚠️ 良い画像が見つかりませんでした (最高スコア: {highest_score:.2f})")

    except Exception as search_error:
        print(f"🔍 画像検索失敗: {search_error}")
    
    # キャッシュに保存
    if len(image_cache) >= CACHE_MAX_SIZE:
        oldest_key = next(iter(image_cache))
        del image_cache[oldest_key]
    
    image_cache[cache_key] = {'image': image_url, 'video_id': video_id}
    
    return image_url, video_id


# ========================================
#  ミドルウェア
# ========================================

@app.before_request
def before_request():
    """リクエストごとの前処理"""
    client_ip = get_client_ip()
    g.client_ip = client_ip
    
    # IP制限チェック
    if not is_ip_allowed(client_ip):
        print(f"⛔ IP制限: {client_ip}")
        return jsonify({"error": "Forbidden"}), 403
    
    # ブルートフォース対策
    if is_ip_blocked(client_ip):
        print(f"🚫 ブロック中: {client_ip}")
        return jsonify({"error": "Too many failed attempts"}), 429
    
    # health checkは認証不要
    if request.endpoint == 'health_check':
        return
    
    # 認証チェック
    if not check_auth():
        record_auth_failure(client_ip)
        print(f"⛔ 認証失敗: {client_ip}")
        return jsonify({"error": "Unauthorized"}), 401


@app.after_request
def after_request(response):
    """レスポンスにセキュリティヘッダーを追加"""
    # セキュリティヘッダー
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    
    # サーバー情報を隠す
    response.headers['Server'] = 'YTM-RPC'
    
    return response


# ========================================
#  エラーハンドラ
# ========================================

@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": "Bad Request"}), 400


@app.errorhandler(401)
def unauthorized(e):
    return jsonify({"error": "Unauthorized"}), 401


@app.errorhandler(403)
def forbidden(e):
    return jsonify({"error": "Forbidden"}), 403


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not Found"}), 404


@app.errorhandler(413)
def request_entity_too_large(e):
    return jsonify({"error": "Request too large"}), 413


@app.errorhandler(429)
def rate_limit_exceeded(e):
    return jsonify({"error": "Rate limit exceeded"}), 429


@app.errorhandler(500)
def internal_error(e):
    # 内部エラーの詳細は隠す
    return jsonify({"error": "Internal server error"}), 500


# ========================================
#  APIエンドポイント
# ========================================

last_update_time = 0
last_calc_start_time = 0


@app.route('/update', methods=['POST'])
@limiter.limit(RATE_LIMIT_UPDATE)
def update_status():
    """再生情報を受け取りDiscord Presenceを更新"""
    global last_title, last_artist, last_is_playing, last_update_time, last_calc_start_time
    
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        # 入力のバリデーションとサニタイズ
        title = sanitize_string(data.get('title', 'Unknown Title'), max_length=100)
        artist = sanitize_string(data.get('artist', 'Unknown Artist'), max_length=100)
        is_playing = bool(data.get('is_playing', True))
        duration = validate_number(data.get('duration', 0), min_val=0, max_val=86400)  # 最大24時間
        position = validate_number(data.get('position', 0), min_val=0, max_val=86400)
        
        print(f"📩 受信: {title} - {artist} (Pos: {position}s)")
        
        # 一時停止中の表示設定
        small_image = "youtube_music_icon"
        small_text = "Playing on Android"
        
        if not is_playing:
            print("⏸️ 一時停止中")
            small_image = "https://img.icons8.com/ios-glyphs/60/ffffff/pause--v1.png"
            small_text = "⏸️ Paused"
        
        # 空文字チェック
        if not title.strip():
            title = "Unknown Title"
        if not artist.strip():
            artist = "Unknown Artist"
        if len(title) < 2:
            title += " "
        if len(artist) < 2:
            artist += " "

        # シーク検知ロジック
        current_time = time.time()
        calc_start_time = current_time - position
        
        time_diff = abs(calc_start_time - last_calc_start_time)
        is_seeked = time_diff > 2
        
        # 曲が変わったかどうか
        is_new_song = (title != last_title or artist != last_artist)
        
        # デバッグログ
        if is_new_song:
            logger.info(f"🆕 新しい曲検出: {last_title} → {title}")
        
        # 重複更新スキップ（同じ曲・同じ状態・シークなし・60秒以内）
        if (not is_new_song and 
            is_playing == last_is_playing and 
            not is_seeked and
            current_time - last_update_time < 60):
            
            reset_idle_timer()
            return jsonify({"status": "skipped"}), 200

        # 曲が変わった場合は必ずタイムスタンプをリセット（position=0から開始）
        if is_new_song:
            # 新しい曲はposition=0として扱う（Android側から古いpositionが送られることがあるため）
            last_calc_start_time = current_time
            logger.info(f"⏱️ タイムスタンプリセット: start={int(last_calc_start_time)} (pos={position}s→0s に強制)")
        # シークした場合もタイムスタンプを更新
        elif is_seeked:
            last_calc_start_time = calc_start_time
            logger.info(f"⏩ シーク検出: タイムスタンプ更新")
        
        # 状態更新
        last_title = title
        last_artist = artist
        last_is_playing = is_playing
        last_update_time = current_time

        # Discord接続確認
        if not ensure_rpc_connection():
            return jsonify({"error": "Discord not connected"}), 503

        # 画像検索
        image_url, video_id = search_album_art(title, artist)

        # タイムスタンプ計算（保存したstart_timeを使用して時間が進むようにする）
        timestamps = {}
        logger.info(f"📊 is_playing={is_playing}, duration={duration}, last_calc_start_time={int(last_calc_start_time)}")
        if is_playing and duration > 0:
            # 保存されたstart_timeを使用（曲変更/シーク時のみ更新される）
            timestamps = {'start': int(last_calc_start_time)}
            logger.info(f"⏰ Discord送信: start={timestamps['start']}")

        # ボタン設定
        buttons = None
        if video_id:
            buttons = [{
                "label": "🎵 Listen on YouTube Music",
                "url": f"https://music.youtube.com/watch?v={video_id}"
            }]

        # Discord Presence更新
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
                
                if buttons:
                    update_args['buttons'] = buttons
                
                RPC.update(**update_args)
                print(f"🎵 Presence更新: {title} - {artist}")
                
            except Exception as rpc_error:
                global rpc_connected
                rpc_connected = False
                print(f"⚠️ Presence更新失敗: {rpc_error}")
                return jsonify({"error": "RPC error"}), 500
        
        reset_idle_timer()
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        print(f"❌ エラー: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route('/pause', methods=['POST'])
@limiter.limit("30/minute")
def pause_status():
    """一時停止時にPresenceをクリア"""
    clear_presence()
    return jsonify({"status": "cleared"}), 200


@app.route('/health', methods=['GET'])
@limiter.limit("10/minute")
def health_check():
    """ヘルスチェック用エンドポイント"""
    return jsonify({
        "status": "running",
        "discord_connected": rpc_connected,
        "cache_size": len(image_cache),
        "auth_enabled": bool(AUTH_TOKEN),
        "ip_restriction": bool(ALLOWED_IP_LIST)
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
    print("=" * 60)
    print("🎵 YouTube Music Discord Presence Server")
    print("   セキュリティ強化版 (外部公開対応)")
    print("=" * 60)
    
    # セキュリティ警告
    if not AUTH_TOKEN:
        print("⚠️  警告: AUTH_TOKENが設定されていません！")
        print("    外部公開時は必ず設定してください: AUTH_TOKEN=<secure-random-token>")
        print("    トークン生成例: python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
    else:
        print("🔒 認証: 有効")
    
    if ALLOWED_IP_LIST:
        print(f"🌐 IP制限: 有効 ({len(ALLOWED_IP_LIST)} IPs)")
    else:
        print("🌐 IP制限: 無効 (全IP許可)")
    
    print(f"⏱️  レート制限: {RATE_LIMIT_UPDATE} (update)")
    print(f"📡 サーバー: http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"🔑 Client ID: {CLIENT_ID[:8]}...")
    print("=" * 60)
    
    # 初回接続
    connect_rpc()
    
    # Waitressサーバー起動
    print("🚀 サーバー稼働中... (Press CTRL+C to quit)")
    try:
        serve(app, host=SERVER_HOST, port=SERVER_PORT)
    except OSError as e:
        print(f"❌ 起動エラー: {e}")
        print("ポートが既に使用されている可能性があります。")