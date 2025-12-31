package com.example.youtubemusicrpc

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys

class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val etHost = findViewById<EditText>(R.id.et_host)
        val etPort = findViewById<EditText>(R.id.et_port)
        val etToken = findViewById<EditText>(R.id.et_token)
        val cbHttps = findViewById<CheckBox>(R.id.cb_https)
        val btnSave = findViewById<Button>(R.id.btn_save)
        val btnPermission = findViewById<Button>(R.id.btn_permission)

        // 暗号化SharedPreferencesの取得
        val prefs = getEncryptedPrefs(this)
        
        // 設定読み込み（デフォルトは空文字 - ユーザーに入力を促す）
        // 設定読み込み（デフォルトは空文字 - ユーザーに入力を促す）
        etHost.setText(prefs.getString("host", ""))
        etPort.setText(prefs.getString("port", "5000"))
        etToken.setText(prefs.getString("token", ""))
        cbHttps.isChecked = prefs.getBoolean("use_https", false)

        // 保存ボタン
        btnSave.setOnClickListener {
            val host = etHost.text.toString().trim()
            val port = etPort.text.toString().trim()
            val token = etToken.text.toString().trim()
            val useHttps = cbHttps.isChecked

            // バリデーション
            if (host.isEmpty()) {
                Toast.makeText(this, "Please enter Server Host (IP or domain)", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            
            if (port.isEmpty()) {
                Toast.makeText(this, "Please enter Server Port", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            
            // ポート番号の範囲チェック
            val portNum = port.toIntOrNull()
            if (portNum == null || portNum < 1 || portNum > 65535) {
                Toast.makeText(this, "Port must be between 1 and 65535", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            
            // ホスト名の簡易バリデーション（IPアドレスまたはドメイン形式）
            if (!isValidHost(host)) {
                Toast.makeText(this, "Invalid host format", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            prefs.edit().apply {
                putString("host", host)
                putString("port", port)
                putString("token", token)
                putBoolean("use_https", useHttps)
                apply()
            }
            
            Toast.makeText(this, "Settings Saved!", Toast.LENGTH_SHORT).show()
        }

        // 権限設定ボタン
        btnPermission.setOnClickListener {
            val intent = Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
            startActivity(intent)
        }
    }

    companion object {
        /**
         * 暗号化されたSharedPreferencesを取得
         * トークンなどの機密情報を安全に保存
         */
        fun getEncryptedPrefs(context: Context): android.content.SharedPreferences {
            return try {
                // security-crypto:1.0.0 互換の書き方
                val masterKeyAlias = MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC)
                
                EncryptedSharedPreferences.create(
                    "rpc_settings_encrypted",
                    masterKeyAlias,
                    context,
                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
                )
            } catch (e: Exception) {
                // フォールバック: 通常のSharedPreferences（古いデバイスやエラー時）
                context.getSharedPreferences("rpc_settings", Context.MODE_PRIVATE)
            }
        }
        
        // ... (省略) ...
        
        /**
         * ホスト名のバリデーション
         */
        fun isValidHost(host: String): Boolean {
            // IPv4アドレス
            val ipv4Regex = Regex("""^(\d{1,3}\.){3}\d{1,3}$""")
            if (ipv4Regex.matches(host)) {
                val parts = host.split(".")
                return parts.all { it.toIntOrNull()?.let { n -> n in 0..255 } ?: false }
            }
            
            // ドメイン名（簡易チェック）
            val domainRegex = Regex("""^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*$""")
            if (domainRegex.matches(host)) {
                return true
            }
            
            // localhost
            if (host == "localhost") {
                return true
            }
            
            return false
        }
    }
}