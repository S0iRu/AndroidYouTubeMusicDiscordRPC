package com.example.youtubemusicrpc

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val etHost = findViewById<EditText>(R.id.et_host)
        val etPort = findViewById<EditText>(R.id.et_port)
        val etToken = findViewById<EditText>(R.id.et_token)
        val btnSave = findViewById<Button>(R.id.btn_save)
        val btnPermission = findViewById<Button>(R.id.btn_permission)

        // 設定読み込み
        val prefs = getSharedPreferences("rpc_settings", Context.MODE_PRIVATE)
        etHost.setText(prefs.getString("host", "100.125.20.126"))
        etPort.setText(prefs.getString("port", "5000"))
        etToken.setText(prefs.getString("token", ""))

        // 保存ボタン
        btnSave.setOnClickListener {
            val host = etHost.text.toString().trim()
            val port = etPort.text.toString().trim()
            val token = etToken.text.toString().trim()

            if (host.isEmpty() || port.isEmpty()) {
                Toast.makeText(this, "Please enter Host and Port", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            prefs.edit().apply {
                putString("host", host)
                putString("port", port)
                putString("token", token)
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
}