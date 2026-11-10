package com.droidsnex.agent

import android.app.Activity
import android.content.Intent
import android.graphics.BitmapFactory
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * UI minimale con la stessa grafica del programma PC (tema scuro di AndrOsint):
 * logo DroidSnex, stato VPN, contatore connessioni, pulsante avvia/ferma.
 * Costruita da codice (niente layout XML). Il logo è in assets/logo.png.
 *
 * Dal PC si pilota con:
 *   adb shell am start -n com.droidsnex.agent/.MainActivity -a com.droidsnex.agent.START --es lang en
 *   adb shell am start -n com.droidsnex.agent/.MainActivity -a com.droidsnex.agent.STOP
 */
class MainActivity : Activity() {
    private lateinit var stateDot: TextView
    private lateinit var stateText: TextView
    private lateinit var counter: TextView
    private lateinit var active: TextView
    private lateinit var pc: TextView
    private lateinit var error: TextView
    private lateinit var toggle: Button
    private val ui = Handler(Looper.getMainLooper())
    private val refresher = object : Runnable {
        override fun run() { refresh(); ui.postDelayed(this, 500) }
    }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun box(fill: Int, stroke: Int = Theme.BORDER, radius: Int = 4) = GradientDrawable().apply {
        setColor(fill); cornerRadius = dp(radius).toFloat(); setStroke(dp(1), stroke)
    }

    private fun label(text: String, size: Float, color: Int, mono: Boolean = false, bold: Boolean = false) =
        TextView(this).apply {
            this.text = text; textSize = size; setTextColor(color)
            typeface = Typeface.create(if (mono) Typeface.MONOSPACE else Typeface.SANS_SERIF,
                if (bold) Typeface.BOLD else Typeface.NORMAL)
        }

    /** Riquadro come le Card del PC: bordo sottile, barretta d'accento e titolo maiuscolo. */
    private fun card(title: String): LinearLayout {
        val c = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = box(Theme.PANEL)
            setPadding(dp(14), dp(12), dp(14), dp(14))
        }
        val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        head.addView(View(this).apply { setBackgroundColor(Theme.ACCENT) }, LinearLayout.LayoutParams(dp(2), dp(11)).apply { rightMargin = dp(7) })
        head.addView(label(title.uppercase(), 10f, Theme.TEXT_DIM, mono = true, bold = true))
        c.addView(head)
        return c
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Theme.BG
        window.navigationBarColor = Theme.BG
        Strings.load(this)
        Strings.set(this, intent?.getStringExtra(EXTRA_LANG))
        buildUi()
        if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf("android.permission.POST_NOTIFICATIONS"), 2)
        handleIntent(intent)
    }

    /** Costruisce la schermata nella lingua corrente (rifatta se il PC cambia lingua). */
    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Theme.BG)
            setPadding(dp(18), dp(22), dp(18), dp(18))
        }

        // --- intestazione: logo + versione
        val header = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        val logo = ImageView(this).apply {
            adjustViewBounds = true
            try { setImageBitmap(assets.open("logo.png").use { BitmapFactory.decodeStream(it) }) } catch (_: Exception) {}
        }
        header.addView(logo, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, dp(20)))
        header.addView(label("   v1.0  ·  " + Strings.t("subtitle"), 11f, Theme.TEXT_FAINT, mono = true))
        root.addView(header)
        root.addView(View(this).apply { setBackgroundColor(Theme.BORDER) },
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(1)).apply { topMargin = dp(16); bottomMargin = dp(16) })

        // --- stato
        val st = card(Strings.t("status"))
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(10), 0, 0) }
        stateDot = label("●", 14f, Theme.TEXT_FAINT)
        stateText = label("", 18f, Theme.TEXT, bold = true)
        row.addView(stateDot); row.addView(stateText, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { leftMargin = dp(8) })
        st.addView(row)
        pc = label("", 12f, Theme.TEXT_SOFT, mono = true).apply { setPadding(0, dp(8), 0, 0) }
        st.addView(pc)
        error = label("", 12f, Theme.ERR).apply { setPadding(0, dp(6), 0, 0) }
        st.addView(error)
        root.addView(st)

        // --- contatori
        val cnt = card(Strings.t("connections"))
        counter = label("0", 34f, Theme.TEXT, mono = true, bold = true).apply { setPadding(0, dp(6), 0, 0) }
        active = label("", 12f, Theme.TEXT_DIM, mono = true)
        cnt.addView(counter); cnt.addView(active)
        root.addView(cnt, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(8) })

        // --- pulsante
        toggle = Button(this).apply {
            isAllCaps = false; textSize = 14f; typeface = Typeface.DEFAULT_BOLD
            stateListAnimator = null
            setOnClickListener { if (CaptureService.isRunning) stopCapture() else startCapture() }
        }
        root.addView(toggle, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(46)).apply { topMargin = dp(14) })

        root.addView(label(
            Strings.t("info"),
            12f, Theme.TEXT_DIM).apply { setPadding(0, dp(16), 0, 0); setLineSpacing(0f, 1.15f) })

        root.addView(View(this), LinearLayout.LayoutParams(1, 0, 1f))
        root.addView(label("Andrea Cumini · www.osintinfo.net", 10f, Theme.TEXT_FAINT, mono = true).apply { gravity = Gravity.CENTER })

        setContentView(ScrollView(this).apply { setBackgroundColor(Theme.BG); isFillViewport = true; addView(root) })
        refresh()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (Strings.set(this, intent.getStringExtra(EXTRA_LANG))) buildUi()
        handleIntent(intent)
    }

    private fun handleIntent(i: Intent?) {
        when (i?.action) {
            CaptureService.ACTION_START -> if (!CaptureService.isRunning) startCapture()
            CaptureService.ACTION_STOP -> stopCapture()
        }
    }

    override fun onResume() { super.onResume(); ui.post(refresher) }
    override fun onPause() { super.onPause(); ui.removeCallbacks(refresher) }

    /**
     * VpnService.prepare() ritorna un Intent se serve il consenso dell'utente
     * (il dialog di sistema "Richiesta di connessione"), null se è già concesso.
     */
    private fun startCapture() {
        val consent = VpnService.prepare(this)
        if (consent != null) {
            try {
                @Suppress("DEPRECATION") startActivityForResult(consent, REQ_VPN)
            } catch (e: Exception) {
                CaptureService.lastError = Strings.t("err_consent_show", e)
            }
        } else {
            onVpnResult(RESULT_OK)
        }
    }

    @Deprecated("API Activity classica")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == REQ_VPN) onVpnResult(resultCode)
    }

    private fun onVpnResult(resultCode: Int) {
        if (resultCode == RESULT_OK) {
            CaptureService.lastError = null
            val svc = Intent(this, CaptureService::class.java).setAction(CaptureService.ACTION_START)
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(svc) else startService(svc)
        } else {
            CaptureService.lastError = Strings.t("err_consent_denied")
        }
        refresh()
    }

    private fun stopCapture() {
        if (!CaptureService.isRunning) return
        startService(Intent(this, CaptureService::class.java).setAction(CaptureService.ACTION_STOP))
    }

    private fun refresh() {
        val running = CaptureService.isRunning
        stateDot.setTextColor(if (running) Theme.OK else Theme.TEXT_FAINT)
        stateText.text = Strings.t(if (running) "running" else "stopped")
        counter.text = "${CaptureService.totalConnections.get()}"
        active.text = Strings.t("open_now", CaptureService.activeConnections)
        val clients = CaptureService.currentServer?.clientCount ?: 0
        pc.text = Strings.t(if (clients > 0) "pc_on" else "pc_off") + "  ·  127.0.0.1:${CaptureService.PORT}"
        pc.setTextColor(if (clients > 0) Theme.OK else Theme.TEXT_SOFT)
        error.text = CaptureService.lastError ?: ""
        error.visibility = if (CaptureService.lastError == null) View.GONE else View.VISIBLE
        toggle.text = Strings.t(if (running) "stop" else "start")
        toggle.setTextColor(if (running) Theme.ERR else Theme.BTN_TEXT)
        toggle.background = if (running) box(Theme.BG, Theme.ERR) else box(Theme.BTN, Theme.BTN)
    }

    companion object {
        private const val REQ_VPN = 1
        /** Lingua scelta sul PC: am start ... --es lang en */
        const val EXTRA_LANG = "lang"
    }
}

/** Palette identica a quella del programma PC (tema di AndrOsint). */
object Theme {
    const val BG = 0xFF07090C.toInt()
    const val PANEL = 0xFF0D1117.toInt()
    const val BORDER = 0xFF1C2530.toInt()
    const val TEXT = 0xFFD5DDE6.toInt()
    const val TEXT_SOFT = 0xFFAAB6C3.toInt()
    const val TEXT_DIM = 0xFF6E7B89.toInt()
    const val TEXT_FAINT = 0xFF3E4955.toInt()
    const val ACCENT = 0xFF7B95DD.toInt()
    const val BTN = 0xFF4A63B5.toInt()
    const val BTN_TEXT = 0xFFF1F4FD.toInt()
    const val OK = 0xFF34D399.toInt()
    const val ERR = 0xFFF87171.toInt()
}
