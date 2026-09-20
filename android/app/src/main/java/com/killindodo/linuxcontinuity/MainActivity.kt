package com.killindodo.linuxcontinuity

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.KeyEvent
import android.media.Ringtone
import android.media.RingtoneManager
import android.media.AudioManager
import android.os.Vibrator
import android.os.VibrationEffect
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private lateinit var connectionLayout: ScrollView
    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var etHostIp: EditText
    private lateinit var etPort: EditText
    private lateinit var etPin: EditText
    private lateinit var btnConnect: Button
    private lateinit var tvStatus: TextView

    private val executor = Executors.newFixedThreadPool(2)
    private val mainHandler = Handler(Looper.getMainLooper())
    private var isPollingPairing = false
    private var fileUploadCallback: ValueCallback<Array<Uri>>? = null

    private val filePickerLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val uris = WebChromeClient.FileChooserParams.parseResult(result.resultCode, result.data)
            fileUploadCallback?.onReceiveValue(uris)
        } else {
            fileUploadCallback?.onReceiveValue(null)
        }
        fileUploadCallback = null
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        connectionLayout = findViewById(R.id.connectionLayout)
        webView = findViewById(R.id.webView)
        progressBar = findViewById(R.id.progressBar)
        etHostIp = findViewById(R.id.etHostIp)
        etPort = findViewById(R.id.etPort)
        etPin = findViewById(R.id.etPin)
        btnConnect = findViewById(R.id.btnConnect)
        tvStatus = findViewById(R.id.tvStatus)

        // Load saved preferences
        val prefs = getSharedPreferences("linux_continuity_prefs", Context.MODE_PRIVATE)
        val savedHost = prefs.getString("host_ip", "")
        val savedPort = prefs.getString("port", "8080")
        val savedPin = prefs.getString("pin", "2550")
        val savedToken = prefs.getString("token", "")

        etHostIp.setText(savedHost)
        etPort.setText(savedPort)
        etPin.setText(savedPin)

        setupWebView()

        btnConnect.setOnClickListener {
            startPairingHandshake()
        }

        // Back button navigation inside continuity app
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.visibility == View.VISIBLE && webView.canGoBack()) {
                    webView.goBack()
                } else if (webView.visibility == View.VISIBLE) {
                    // Return to connection settings screen
                    webView.visibility = View.GONE
                    connectionLayout.visibility = View.VISIBLE
                } else {
                    finish()
                }
            }
        })

        // Auto-connect if previous session was valid
        if (!savedToken.isNullOrEmpty() && !savedHost.isNullOrEmpty()) {
            validateStoredSession(savedHost, savedPort ?: "8080", savedToken)
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val s: WebSettings = webView.settings
        s.javaScriptEnabled = true
        s.domStorageEnabled = true
        s.allowFileAccess = true
        s.allowContentAccess = true
        s.useWideViewPort = true
        s.loadWithOverviewMode = true
        s.mediaPlaybackRequiresUserGesture = false
        s.cacheMode = WebSettings.LOAD_DEFAULT

        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                progressBar.visibility = View.GONE
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                if (newProgress < 100) {
                    progressBar.visibility = View.VISIBLE
                    progressBar.progress = newProgress
                } else {
                    progressBar.visibility = View.GONE
                }
            }

            override fun onPermissionRequest(request: PermissionRequest?) {
                // Grant camera & microphone permissions to Web app inside Continuity
                request?.grant(request.resources)
            }

            override fun onShowFileChooser(
                view: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                fileUploadCallback?.onReceiveValue(null)
                fileUploadCallback = filePathCallback
                val intent = fileChooserParams?.createIntent() ?: Intent(Intent.ACTION_GET_CONTENT).apply {
                    type = "*/*"
                    addCategory(Intent.CATEGORY_OPENABLE)
                }
                try {
                    filePickerLauncher.launch(intent)
                    return true
                } catch (e: Exception) {
                    fileUploadCallback = null
                    return false
                }
            }
        }

        webView.addJavascriptInterface(AndroidNativeBridge(this), "AndroidBridge")
    }

    inner class AndroidNativeBridge(private val context: Context) {
        private var ringtone: Ringtone? = null

        @JavascriptInterface
        fun ringPhone(enable: Boolean) {
            mainHandler.post {
                try {
                    if (enable) {
                        if (ringtone == null) {
                            val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
                                ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
                            ringtone = RingtoneManager.getRingtone(context, uri)
                        }
                        ringtone?.play()
                    } else {
                        ringtone?.stop()
                    }
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }
        }

        @JavascriptInterface
        fun vibratePhone(durationMs: Long) {
            mainHandler.post {
                try {
                    val v = context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        v?.vibrate(VibrationEffect.createOneShot(durationMs, VibrationEffect.DEFAULT_AMPLITUDE))
                    } else {
                        @Suppress("DEPRECATION")
                        v?.vibrate(durationMs)
                    }
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }
        }

        @JavascriptInterface
        fun setVolume(delta: Int) {
            mainHandler.post {
                try {
                    val am = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
                    val direction = if (delta > 0) AudioManager.ADJUST_RAISE else AudioManager.ADJUST_LOWER
                    am?.adjustStreamVolume(AudioManager.STREAM_MUSIC, direction, AudioManager.FLAG_SHOW_UI)
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }
        }

        @JavascriptInterface
        fun playMediaKey(key: String) {
            mainHandler.post {
                try {
                    val am = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
                    val code = when (key) {
                        "play_pause" -> KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE
                        "next" -> KeyEvent.KEYCODE_MEDIA_NEXT
                        "prev" -> KeyEvent.KEYCODE_MEDIA_PREVIOUS
                        else -> KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE
                    }
                    val eventDown = KeyEvent(KeyEvent.ACTION_DOWN, code)
                    val eventUp = KeyEvent(KeyEvent.ACTION_UP, code)
                    am?.dispatchMediaKeyEvent(eventDown)
                    am?.dispatchMediaKeyEvent(eventUp)
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }
        }

        @JavascriptInterface
        fun showToast(msg: String) {
            mainHandler.post {
                Toast.makeText(context, msg, Toast.LENGTH_LONG).show()
            }
        }

        @JavascriptInterface
        fun openUrl(url: String) {
            mainHandler.post {
                try {
                    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    context.startActivity(intent)
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            }
        }

        @JavascriptInterface
        fun getDeviceModel(): String {
            return getDeviceName()
        }

        @JavascriptInterface
        fun getBatteryLevel(): Int {
            return try {
                val bm = context.getSystemService(Context.BATTERY_SERVICE) as? android.os.BatteryManager
                if (bm != null) {
                    val cap = bm.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY)
                    if (cap in 0..100) return cap
                }
                val ifilter = android.content.IntentFilter(Intent.ACTION_BATTERY_CHANGED)
                val batteryStatus = context.registerReceiver(null, ifilter)
                val level = batteryStatus?.getIntExtra(android.os.BatteryManager.EXTRA_LEVEL, -1) ?: -1
                val scale = batteryStatus?.getIntExtra(android.os.BatteryManager.EXTRA_SCALE, -1) ?: -1
                if (level >= 0 && scale > 0) {
                    (level * 100 / scale)
                } else {
                    -1
                }
            } catch (e: Exception) {
                -1
            }
        }

        @JavascriptInterface
        fun isCharging(): Boolean {
            return try {
                val bm = context.getSystemService(Context.BATTERY_SERVICE) as? android.os.BatteryManager
                if (bm != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    return bm.isCharging
                }
                val ifilter = android.content.IntentFilter(Intent.ACTION_BATTERY_CHANGED)
                val batteryStatus = context.registerReceiver(null, ifilter)
                val status = batteryStatus?.getIntExtra(android.os.BatteryManager.EXTRA_STATUS, -1) ?: -1
                status == android.os.BatteryManager.BATTERY_STATUS_CHARGING || status == android.os.BatteryManager.BATTERY_STATUS_FULL
            } catch (e: Exception) {
                false
            }
        }
    }

    private fun getDeviceName(): String {
        val manufacturer = Build.MANUFACTURER.replaceFirstChar { it.uppercase() }
        val model = Build.MODEL
        return if (model.startsWith(manufacturer, ignoreCase = true)) model else "$manufacturer $model"
    }

    private fun startPairingHandshake() {
        val host = etHostIp.text.toString().trim()
        val port = etPort.text.toString().trim()
        val pin = etPin.text.toString().trim()

        if (host.isEmpty()) {
            Toast.makeText(this, "Please enter Tailscale IP", Toast.LENGTH_SHORT).show()
            return
        }

        btnConnect.isEnabled = false
        tvStatus.visibility = View.VISIBLE
        tvStatus.text = "⚡ Contacting Linux PC..."
        tvStatus.setTextColor(0xFF00D2FF.toInt())

        val deviceName = getDeviceName()

        executor.execute {
            try {
                val url = URL("http://$host:$port/api/auth")
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.connectTimeout = 4000
                conn.readTimeout = 4000
                conn.setRequestProperty("Content-Type", "application/json")
                conn.doOutput = true

                val payload = JSONObject().apply {
                    put("pin", pin)
                    put("device_name", deviceName)
                }

                OutputStreamWriter(conn.outputStream).use { it.write(payload.toString()) }

                val code = conn.responseCode
                val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                val responseText = BufferedReader(InputStreamReader(stream)).use { it.readText() }
                val json = JSONObject(responseText)

                mainHandler.post {
                    btnConnect.isEnabled = true
                    val status = json.optString("status")

                    if (status == "success" || status == "approved") {
                        val token = json.getString("token")
                        savePrefs(host, port, pin, token)
                        launchContinuity(host, port, token)
                    } else if (status == "pending") {
                        val reqId = json.getString("req_id")
                        tvStatus.text = "⏳ Request Sent! Please click [Approve] on your Linux PC desktop screen..."
                        tvStatus.setTextColor(0xFFFFCC00.toInt())
                        pollPairingApproval(host, port, pin, reqId)
                    } else if (status == "blocked") {
                        tvStatus.text = "⛔ Access Denied: This device is blocked by the PC administrator."
                        tvStatus.setTextColor(0xFFFF3B30.toInt())
                    } else {
                        val msg = json.optString("message", "Incorrect PIN")
                        tvStatus.text = "❌ $msg"
                        tvStatus.setTextColor(0xFFFF3B30.toInt())
                    }
                }
            } catch (e: Exception) {
                mainHandler.post {
                    btnConnect.isEnabled = true
                    tvStatus.text = "❌ Connection Failed: Check Tailscale VPN and PC server."
                    tvStatus.setTextColor(0xFFFF3B30.toInt())
                }
            }
        }
    }

    private fun pollPairingApproval(host: String, port: String, pin: String, reqId: String) {
        isPollingPairing = true

        val pollRunnable = object : Runnable {
            override fun run() {
                if (!isPollingPairing) return

                executor.execute {
                    try {
                        val url = URL("http://$host:$port/api/auth/pair_status?req_id=$reqId")
                        val conn = url.openConnection() as HttpURLConnection
                        conn.requestMethod = "GET"
                        conn.connectTimeout = 3000
                        conn.readTimeout = 3000

                        val responseText = BufferedReader(InputStreamReader(conn.inputStream)).use { it.readText() }
                        val json = JSONObject(responseText)
                        val status = json.optString("status")

                        mainHandler.post {
                            if (status == "approved") {
                                isPollingPairing = false
                                val token = json.getString("token")
                                savePrefs(host, port, pin, token)
                                tvStatus.text = "✓ Approved by PC Administrator!"
                                tvStatus.setTextColor(0xFF34C759.toInt())
                                launchContinuity(host, port, token)
                            } else if (status == "rejected") {
                                isPollingPairing = false
                                tvStatus.text = "❌ Connection rejected by PC administrator."
                                tvStatus.setTextColor(0xFFFF3B30.toInt())
                            } else if (status == "blocked") {
                                isPollingPairing = false
                                tvStatus.text = "⛔ This device has been permanently blocked by the PC."
                                tvStatus.setTextColor(0xFFFF3B30.toInt())
                            } else if (isPollingPairing) {
                                mainHandler.postDelayed(this, 1500)
                            }
                        }
                    } catch (e: Exception) {
                        if (isPollingPairing) {
                            mainHandler.postDelayed(this, 2000)
                        }
                    }
                }
            }
        }

        mainHandler.postDelayed(pollRunnable, 1500)
    }

    private fun validateStoredSession(host: String, port: String, token: String) {
        executor.execute {
            try {
                val url = URL("http://$host:$port/api/info?token=$token")
                val conn = url.openConnection() as HttpURLConnection
                conn.connectTimeout = 2500
                conn.readTimeout = 2500
                if (conn.responseCode == 200) {
                    mainHandler.post {
                        launchContinuity(host, port, token)
                    }
                }
            } catch (e: Exception) {}
        }
    }

    private fun savePrefs(host: String, port: String, pin: String, token: String) {
        val prefs = getSharedPreferences("linux_continuity_prefs", Context.MODE_PRIVATE)
        prefs.edit()
            .putString("host_ip", host)
            .putString("port", port)
            .putString("pin", pin)
            .putString("token", token)
            .apply()
    }

    private fun launchContinuity(host: String, port: String, token: String) {
        connectionLayout.visibility = View.GONE
        webView.visibility = View.VISIBLE
        val appUrl = "http://$host:$port/?token=$token"
        webView.loadUrl(appUrl)
    }

    override fun onDestroy() {
        isPollingPairing = false
        super.onDestroy()
    }
}
