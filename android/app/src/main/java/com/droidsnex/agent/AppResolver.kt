package com.droidsnex.agent

import android.content.Context
import android.net.ConnectivityManager
import android.os.Build
import android.os.Process
import java.io.File
import java.net.InetAddress
import java.net.InetSocketAddress

/**
 * Risale all'app che ha aperto una connessione.
 *
 * Android 10+ (API 29): ConnectivityManager.getConnectionOwnerUid() — funziona
 * SOLO se chiamato dall'app VPN attiva, che è esattamente il nostro caso.
 * Android 7-9: fallback su /proc/net/{tcp,udp}[6], che lì è ancora leggibile.
 *
 * Poi UID -> nome pacchetto con PackageManager (serve QUERY_ALL_PACKAGES su 11+).
 */
class AppResolver(private val ctx: Context) {
    private val cm = ctx.getSystemService(ConnectivityManager::class.java)
    private val names = HashMap<Int, String>()

    fun uidFor(proto: Int, src: InetAddress, sport: Int, dst: InetAddress, dport: Int): Int {
        if (Build.VERSION.SDK_INT >= 29) {
            return try {
                cm.getConnectionOwnerUid(proto, InetSocketAddress(src, sport), InetSocketAddress(dst, dport))
            } catch (e: Exception) {
                Process.INVALID_UID
            }
        }
        return procUid(proto, sport)
    }

    fun nameFor(uid: Int): String = names.getOrPut(uid) {
        when (uid) {
            Process.INVALID_UID -> "unknown"
            0 -> "root"
            1000 -> "android.system"
            1051 -> "android.dns"   // AID_DNS: il resolver di sistema
            else -> ctx.packageManager.getPackagesForUid(uid)?.let { pkgs ->
                // Più pacchetti possono condividere un UID (sharedUserId): li elenchiamo tutti
                if (pkgs.size == 1) pkgs[0] else pkgs.sorted().joinToString("|")
            } ?: "uid:$uid"
        }
    }

    private fun procUid(proto: Int, sport: Int): Int {
        val files = if (proto == 6) listOf("/proc/net/tcp6", "/proc/net/tcp") else listOf("/proc/net/udp6", "/proc/net/udp")
        val portHex = ":%04X".format(sport)
        for (f in files) {
            try {
                File(f).useLines { lines ->
                    for (line in lines.drop(1)) {
                        val cols = line.trim().split(Regex("\\s+"))
                        if (cols.size > 7 && cols[1].endsWith(portHex)) return cols[7].toIntOrNull() ?: Process.INVALID_UID
                    }
                }
            } catch (e: Exception) { /* non leggibile */ }
        }
        return Process.INVALID_UID
    }
}
