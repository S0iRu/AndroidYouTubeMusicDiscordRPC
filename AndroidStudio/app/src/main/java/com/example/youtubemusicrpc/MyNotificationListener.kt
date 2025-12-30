package com.example.youtubemusicrpc

import android.content.Context
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.app.Notification
import android.util.Log
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

    // 通信クライアント
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

            // 再生状態の判定ロジック
            var isPlaying = true 
            val actions = notification.actions
            if (actions != null) {
                for (action in actions) {
                    val description = action.title?.toString() ?: ""
                    // 「再生」ボタンが表示されている = 現在は止まっている
                    if (description.contains("Play", ignoreCase = true) || 
                        description.contains("再生", ignoreCase = true) ||
                        description.contains("Resume", ignoreCase = true)) {
                        isPlaying = false
                        break 
                    }
                }
            }
            
            Log.d("YoutubeMusicRPC", "🎵 $title - $artist (再生中: $isPlaying)")

            // MediaSessionから詳細情報を取得
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
            }

            // 送信
            sendToDiscord(title, artist, isPlaying, duration, position)
        }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        if (sbn.packageName == "com.google.android.apps.youtube.music") {
            Log.d("MusicRPC", "再生停止（通知削除）")
            sendPauseToDiscord()
        }
    }
    
    // 設定を取得するヘルパー関数
    private fun getSettings(): Triple<String, String, String> {
        val prefs = getSharedPreferences("rpc_settings", Context.MODE_PRIVATE)
        val host = prefs.getString("host", "100.125.20.126") ?: "100.125.20.126"
        val port = prefs.getString("port", "5000") ?: "5000"
        val token = prefs.getString("token", "") ?: ""
        return Triple(host, port, token)
    }
    
    private fun sendPauseToDiscord() {
        val (host, port, token) = getSettings()
        val url = "http://$host:$port/pause"
        
        val builder = Request.Builder()
            .url(url)
            .post("".toRequestBody(JSON_TYPE))
            
        if (token.isNotEmpty()) {
            builder.addHeader("Authorization", "Bearer $token")
        }
        
        val request = builder.build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {}
            override fun onResponse(call: Call, response: Response) { response.close() }
        })
    }

    private fun sendToDiscord(title: String, artist: String, isPlaying: Boolean, duration: Long, position: Long) {
        val (host, port, token) = getSettings()
        val url = "http://$host:$port/update"

        val jsonBody = JSONObject()
        jsonBody.put("title", title)
        jsonBody.put("artist", artist)
        jsonBody.put("is_playing", isPlaying)
        jsonBody.put("duration", duration / 1000)
        jsonBody.put("position", position / 1000)

        val requestBody = jsonBody.toString().toRequestBody(JSON_TYPE)
        
        val builder = Request.Builder()
            .url(url)
            .post(requestBody)
            
        if (token.isNotEmpty()) {
            builder.addHeader("Authorization", "Bearer $token")
        }
        
        val request = builder.build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e("YoutubeMusicRPC", "❌ 送信失敗: ${e.message}")
            }

            override fun onResponse(call: Call, response: Response) {
                if (response.isSuccessful) {
                    Log.d("YoutubeMusicRPC", "✅ 送信成功")
                } else {
                    Log.e("YoutubeMusicRPC", "⚠️ サーバーエラー: ${response.code}")
                }
                response.close()
            }
        })
    }
}