package com.example.youtubemusicrpc

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.app.Notification
import android.util.Log
// ▼追加1：通信とJSONに必要なインポート
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Call
import okhttp3.Callback
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException

class MyNotificationListener : NotificationListenerService() {

    // ▼追加2：PCサーバーの設定
    // ★重要：VS Codeのターミナルに表示された「http://192...」のアドレスに書き換えてください！
//    private val SERVER_URL = "http://192.168.1.3:5000/update"
    private val SERVER_URL = "http://100.125.20.126:5000/update"

    // 通信クライアントの準備
    private val client = OkHttpClient()
    private val JSON_TYPE = "application/json; charset=utf-8".toMediaType()

    override fun onListenerConnected() {
        super.onListenerConnected()
        Log.d("YoutubeMusicRPC", "サービスが接続されました")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName == "com.google.android.apps.youtube.music") {
            val notification = sbn.notification
            val extras = notification.extras

            val title = extras.getString(Notification.EXTRA_TITLE) ?: "不明な曲"
            val artist = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: "不明なアーティスト"

            // ▼再生状態の判定ロジック
            var isPlaying = true // デフォルトは再生中とする
            val actions = notification.actions
            if (actions != null) {
                for (action in actions) {
                    // アクションボタンの説明文（"Pause", "Play"など）を取得
                    val description = action.title?.toString() ?: ""
                    Log.d("YoutubeMusicRPC", "Action: $description") // デバッグ用ログ
                    
                    // 「再生」ボタンが表示されている = 現在は止まっている
                    // 多言語対応なども考慮してキーワードを広めに
                    if (description.contains("Play", ignoreCase = true) || 
                        description.contains("再生", ignoreCase = true) ||
                        description.contains("Resume", ignoreCase = true)) {
                        isPlaying = false
                        // 見つかったらループを抜ける
                        break 
                    }
                }
            }
            
            Log.d("YoutubeMusicRPC", "🎵 $title - $artist (再生中: $isPlaying)")

            // ▼MediaSessionから詳細情報を取得
            var duration = 0L
            var position = 0L
            
            val token = extras.getParcelable<android.media.session.MediaSession.Token>(Notification.EXTRA_MEDIA_SESSION)
            if (token != null) {
                val controller = android.media.session.MediaController(this, token)
                val metadata = controller.metadata
                val playbackState = controller.playbackState
                
                if (metadata != null) {
                    duration = metadata.getLong(android.media.MediaMetadata.METADATA_KEY_DURATION)
                }
                if (playbackState != null) {
                    position = playbackState.position
                }
                
                Log.d("YoutubeMusicRPC", "⏱️ ${position / 1000}s / ${duration / 1000}s")
            }

            if (isPlaying) {
                // 再生中なら更新
                sendToDiscord(title, artist, isPlaying, duration, position)
            } else {
                // 一時停止中
                sendToDiscord(title, artist, isPlaying, duration, position)
            }
        }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        if (sbn.packageName == "com.google.android.apps.youtube.music") {
            Log.d("MusicRPC", "再生停止（通知削除）")
            sendPauseToDiscord()
        }
    }
    
    private fun sendPauseToDiscord() {
        val pauseUrl = SERVER_URL.replace("/update", "/pause")
        val request = Request.Builder()
            .url(pauseUrl)
            .post("".toRequestBody(JSON_TYPE))
            .build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {}
            override fun onResponse(call: Call, response: Response) { response.close() }
        })
    }

    // ▼引数に duration, position を追加 (単位: ミリ秒)
    private fun sendToDiscord(title: String, artist: String, isPlaying: Boolean, duration: Long, position: Long) {
        val jsonBody = JSONObject()
        jsonBody.put("title", title)
        jsonBody.put("artist", artist)
        jsonBody.put("is_playing", isPlaying)
        // サーバーは秒単位で期待しているので / 1000 する
        jsonBody.put("duration", duration / 1000)
        jsonBody.put("position", position / 1000)

        // 2. リクエストを作成
        val requestBody = jsonBody.toString().toRequestBody(JSON_TYPE)
        val request = Request.Builder()
            .url(SERVER_URL) // 上で設定したURLへ送る
            .post(requestBody)
            .build()

        // 3. 非同期で送信実行
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                // 送信失敗時（PCが起動していない、IPが違うなど）
                Log.e("YoutubeMusicRPC", "❌ 送信失敗: ${e.message}")
            }

            override fun onResponse(call: Call, response: Response) {
                // 送信成功時
                if (response.isSuccessful) {
                    Log.d("YoutubeMusicRPC", "✅ 送信成功")
                } else {
                    Log.e("YoutubeMusicRPC", "⚠️ サーバーエラー: ${response.code}")
                }
                response.close() // 必ず閉じる
            }
        })
    }
}


//package com.example.youtubemusicrpc
//
//import android.service.notification.NotificationListenerService
//import android.service.notification.StatusBarNotification
//import android.util.Log
//import android.app.Notification
//
//class MyNotificationListener : NotificationListenerService() {
//
//    override fun onListenerConnected() {
//        super.onListenerConnected()
//        Log.d("YoutubeMusicRPC", "サービスが接続されました")
//    }
//
//    // 通知が来た（更新された）時に呼ばれる関数
//    override fun onNotificationPosted(sbn: StatusBarNotification) {
//        // YouTube MusicのパッケージIDのみを対象にする
//        // YouTube Music: "com.google.android.apps.youtube.music"
//        // 普通のYouTube: "com.google.android.youtube"
//
//        if (sbn.packageName == "com.google.android.apps.youtube.music") {
//            val notification = sbn.notification
//            val extras = notification.extras
//
//            // 通知から情報を抜き出す
//            // android.title : 曲名
//            // android.text  : アーティスト名
//            val title = extras.getString(Notification.EXTRA_TITLE) ?: "不明な曲"
//            val artist = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: "不明なアーティスト"
//
//            Log.d("YoutubeMusicRPC", "🎵 現在再生中: $title / $artist")
//
//            // ★ここでDiscordに送信する処理を行う
//            sendToDiscord(title, artist)
//        }
//    }
//
//    override fun onNotificationRemoved(sbn: StatusBarNotification) {
//        // 通知が消えた（再生停止など）時の処理
//        if (sbn.packageName == "com.google.android.apps.youtube.music") {
//            Log.d("MusicRPC", "再生停止")
//            // Discordのステータスをクリアする処理などを書く
//        }
//    }
//
//    // 送信用の仮関数
//    private fun sendToDiscord(title: String, artist: String) {
//        // ここにHTTPリクエストやWebSocket通信のコードを書く
//        // 例: OkHttpを使って自作サーバーへPOSTするなど
//    }
//}