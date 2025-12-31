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
import java.util.concurrent.TimeUnit

data class ServerSettings(val host: String, val port: String, val token: String, val useHttps: Boolean)

class MyNotificationListener : NotificationListenerService() {

    companion object {
        private const val TAG = "YoutubeMusicRPC"
        private const val CONNECT_TIMEOUT_SEC = 10L
        private const val READ_TIMEOUT_SEC = 15L
        private const val WRITE_TIMEOUT_SEC = 15L
    }

    // 通信クライアント（タイムアウト設定付き）
    private val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(CONNECT_TIMEOUT_SEC, TimeUnit.SECONDS)
            .readTimeout(READ_TIMEOUT_SEC, TimeUnit.SECONDS)
            .writeTimeout(WRITE_TIMEOUT_SEC, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }
    
    private val JSON_TYPE = "application/json; charset=utf-8".toMediaType()

    override fun onListenerConnected() {
        super.onListenerConnected()
        Log.d(TAG, "サービスが接続されました")
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
            
            Log.d(TAG, "🎵 $title - $artist (再生中: $isPlaying)")

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
            Log.d(TAG, "再生停止（通知削除）")
            sendPauseToDiscord()
        }
    }
    
    /**
     * 設定を取得するヘルパー関数
     * EncryptedSharedPreferencesから安全に取得
     */
    private fun getSettings(): ServerSettings? {
        return try {
            val prefs = MainActivity.getEncryptedPrefs(this)
            val host = prefs.getString("host", "") ?: ""
            val port = prefs.getString("port", "5000") ?: "5000"
            val token = prefs.getString("token", "") ?: ""
            val useHttps = prefs.getBoolean("use_https", false)
            
            // ホストが設定されていない場合はnullを返す
            if (host.isEmpty()) {
                Log.w(TAG, "⚠️ サーバーホストが設定されていません")
                return null
            }
            
            ServerSettings(host, port, token, useHttps)
        } catch (e: Exception) {
            Log.e(TAG, "設定取得エラー: ${e.message}")
            null
        }
    }
    
    private fun sendPauseToDiscord() {
        val settings = getSettings() ?: return
        val scheme = if (settings.useHttps) "https" else "http"
        val url = "$scheme://${settings.host}:${settings.port}/pause"
        
        val builder = Request.Builder()
            .url(url)
            .post("".toRequestBody(JSON_TYPE))
            
        if (settings.token.isNotEmpty()) {
            builder.addHeader("Authorization", "Bearer ${settings.token}")
        }
        
        val request = builder.build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e(TAG, "❌ Pause送信失敗: ${e.message}")
            }
            override fun onResponse(call: Call, response: Response) {
                response.use {
                    if (!it.isSuccessful) {
                        Log.w(TAG, "⚠️ Pauseレスポンス: ${it.code}")
                    }
                }
            }
        })
    }

    private fun sendToDiscord(title: String, artist: String, isPlaying: Boolean, duration: Long, position: Long) {
        val settings = getSettings() ?: return
        val scheme = if (settings.useHttps) "https" else "http"
        val url = "$scheme://${settings.host}:${settings.port}/update"

        val jsonBody = JSONObject().apply {
            put("title", title)
            put("artist", artist)
            put("is_playing", isPlaying)
            put("duration", duration / 1000)
            put("position", position / 1000)
        }

        val requestBody = jsonBody.toString().toRequestBody(JSON_TYPE)
        
        val builder = Request.Builder()
            .url(url)
            .post(requestBody)
            
        if (settings.token.isNotEmpty()) {
            builder.addHeader("Authorization", "Bearer ${settings.token}")
        }
        
        val request = builder.build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e(TAG, "❌ 送信失敗: ${e.message}")
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    when {
                        it.isSuccessful -> Log.d(TAG, "✅ 送信成功")
                        it.code == 401 -> Log.e(TAG, "⛔ 認証失敗: トークンを確認してください")
                        it.code == 429 -> Log.w(TAG, "⏳ レート制限中")
                        else -> Log.e(TAG, "⚠️ サーバーエラー: ${it.code}")
                    }
                }
            }
        })
    }
}