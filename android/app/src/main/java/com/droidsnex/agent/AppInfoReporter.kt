package com.droidsnex.agent

import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.Drawable
import android.os.Build
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors

/**
 * Scheda di ogni app vista nel traffico, inviata al PC una volta sola (evento "app"):
 * nome leggibile, versione, icona (PNG 64x64 in base64, ~3 KB), permessi richiesti
 * e concessi, se è un'app di sistema. Il PC la usa per il profilo dell'app, per i
 * nomi nelle liste e per le icone nel grafo.
 *
 * Il lavoro (PackageManager + disegno dell'icona) va su un thread a parte per non
 * rallentare il Forwarder.
 */
class AppInfoReporter(private val ctx: Context, private val emit: (JSONObject) -> Unit) {
    private val pm = ctx.packageManager
    private val done = HashSet<String>()
    private val exec = Executors.newSingleThreadExecutor { r -> Thread(r, "AppInfo").apply { isDaemon = true } }

    fun report(app: String, uid: Int) {
        // più pacchetti con lo stesso UID arrivano come "a|b"
        for (pkg in app.split('|')) {
            if (pkg.isEmpty() || !pkg.contains('.') || !synchronized(done) { done.add(pkg) }) continue
            exec.execute { try { send(pkg, uid) } catch (e: Exception) { /* app rimossa, ecc. */ } }
        }
    }

    fun stop() = exec.shutdownNow()

    private fun send(pkg: String, uid: Int) {
        val o = JSONObject().put("ev", "app").put("pkg", pkg).put("uid", uid)
        val pi: PackageInfo? = try {
            if (Build.VERSION.SDK_INT >= 33)
                pm.getPackageInfo(pkg, PackageManager.PackageInfoFlags.of(PackageManager.GET_PERMISSIONS.toLong()))
            else @Suppress("DEPRECATION") pm.getPackageInfo(pkg, PackageManager.GET_PERMISSIONS)
        } catch (e: PackageManager.NameNotFoundException) { null }
        if (pi == null) { emit(o.put("label", pkg)); return }
        val ai = pi.applicationInfo
        o.put("label", ai?.let { pm.getApplicationLabel(it).toString() } ?: pkg)
        o.put("version", pi.versionName ?: "")
        o.put("system", ai != null && (ai.flags and android.content.pm.ApplicationInfo.FLAG_SYSTEM) != 0)
        o.put("installed", pi.firstInstallTime / 1000).put("updated", pi.lastUpdateTime / 1000)
        o.put("target_sdk", ai?.targetSdkVersion ?: 0)
        val perms = JSONArray()
        val req = pi.requestedPermissions
        val flags = pi.requestedPermissionsFlags
        if (req != null) for (i in req.indices) {
            val granted = flags != null && i < flags.size &&
                (flags[i] and PackageInfo.REQUESTED_PERMISSION_GRANTED) != 0
            perms.put(JSONObject().put("name", req[i]).put("granted", granted))
        }
        o.put("perms", perms)
        ai?.let { info ->
            try {
                val icon = pm.getApplicationIcon(info)
                o.put("icon", Base64.encodeToString(toPng(icon, 64), Base64.NO_WRAP))
            } catch (e: Exception) { /* senza icona */ }
        }
        emit(o)
    }

    private fun toPng(d: Drawable, size: Int): ByteArray {
        val bmp = if (d is BitmapDrawable && d.bitmap != null) Bitmap.createScaledBitmap(d.bitmap, size, size, true)
        else Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888).also {
            val c = Canvas(it)
            d.setBounds(0, 0, size, size)
            d.draw(c)
        }
        val out = ByteArrayOutputStream()
        bmp.compress(Bitmap.CompressFormat.PNG, 90, out)
        return out.toByteArray()
    }
}
