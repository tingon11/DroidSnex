package com.droidsnex.agent

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.LinkProperties
import android.net.Network
import android.net.VpnService
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.system.ErrnoException
import android.system.Os
import android.system.OsConstants
import android.system.StructPollfd
import android.util.Log
import com.droidsnex.agent.inspect.Dns
import com.droidsnex.agent.net.Flow
import com.droidsnex.agent.net.FlowListener
import com.droidsnex.agent.net.Forwarder
import com.droidsnex.agent.net.Proto
import org.json.JSONArray
import org.json.JSONObject
import java.io.FileOutputStream
import java.net.Inet4Address
import java.net.Inet6Address
import java.net.InetAddress
import java.util.concurrent.atomic.AtomicLong

/**
 * Servizio VPN locale.
 *
 * La VPN non ha un server remoto: l'interfaccia TUN creata con
 * VpnService.Builder riceve *tutti* i pacchetti IP delle app (route 0.0.0.0/0
 * e ::/0). Noi li leggiamo, registriamo i metadati di destinazione e li
 * inoltriamo con socket normali (vedi [Forwarder]). Nessun root necessario:
 * l'utente concede una volta il permesso VPN (o il PC lo pre-autorizza con
 * "appops set ... ACTIVATE_VPN allow").
 */
class CaptureService : VpnService(), FlowListener {

    private var tun: ParcelFileDescriptor? = null
    private var forwarder: Forwarder? = null
    /** Connessioni aperte, per i contatori di traffico live (evento "bytes"). */
    private val liveFlows = java.util.concurrent.ConcurrentHashMap<Long, Flow>()
    private var server: EventServer? = null
    private lateinit var apps: AppResolver
    private var appInfo: AppInfoReporter? = null
    private var netCallback: ConnectivityManager.NetworkCallback? = null
    @Volatile private var upstreamDns: InetAddress = InetAddress.getByName(FALLBACK_DNS)

    // Cache IP -> nome di dominio, alimentata dalle risposte DNS (solo thread del Forwarder)
    private val dnsCache = object : LinkedHashMap<String, String>(1024, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, String>?) = size > 20000
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Strings.load(this)
        if (intent?.action == ACTION_STOP) {
            stopCapture()
            return START_NOT_STICKY
        }
        if (!isRunning) startCapture()
        return START_STICKY
    }

    override fun onRevoke() {
        // Un'altra VPN ha preso il posto o l'utente ha revocato il permesso
        stopCapture()
        super.onRevoke()
    }

    override fun onDestroy() {
        stopCapture()
        super.onDestroy()
    }

    private fun startCapture() {
        goForeground()
        apps = AppResolver(this)
        val cm = getSystemService(ConnectivityManager::class.java)

        // Prima di attivare la VPN leggiamo i DNS e l'IPv6 della rete reale
        val lp = cm.activeNetwork?.let { cm.getLinkProperties(it) }
        lp?.let { updateUpstreamDns(it) }
        val hasIpv6 = lp?.linkAddresses?.any {
            val a = it.address
            a is Inet6Address && !a.isLinkLocalAddress && !a.isSiteLocalAddress && !a.isLoopbackAddress
        } ?: false

        // --- Configurazione dell'interfaccia TUN ---------------------------------
        val builder = Builder()
            .setSession("DroidSnex")
            .setMtu(Forwarder.MTU)
            .addAddress(VPN_ADDR4, 30)
            .addRoute("0.0.0.0", 0)        // tutto il traffico IPv4 passa da noi
            .addDnsServer(VIRTUAL_DNS4)    // DNS "finto": lo intercettiamo e rigiriamo al DNS reale
            .setBlocking(false)            // fd non bloccante: il lettore usa poll()
        if (hasIpv6) {
            builder.addAddress(VPN_ADDR6, 128).addRoute("::", 0)
        }
        // La nostra app resta fuori dalla VPN: i suoi socket (server 8888 e
        // inoltro) vanno direttamente in rete. In più usiamo protect() sui socket.
        try { builder.addDisallowedApplication(packageName) } catch (e: Exception) {}
        if (Build.VERSION.SDK_INT >= 29) builder.setMetered(false)

        val pfd = try { builder.establish() } catch (e: Exception) { null }
        if (pfd == null) {
            // establish() ritorna null se il permesso VPN non è stato concesso
            lastError = Strings.t("err_no_permission")
            Log.e(TAG, lastError!!)
            stopSelf()
            return
        }
        tun = pfd
        lastError = null

        server = EventServer(PORT).also { it.start(); currentServer = it }
        appInfo = AppInfoReporter(this) { server?.emit(it) }
        val tunOut = FileOutputStream(pfd.fileDescriptor)
        val fwd = Forwarder({ protect(it) }, { protect(it) }, { tunOut.write(it) }, this,
            InetAddress.getByName(VIRTUAL_DNS4).address) { upstreamDns }
        forwarder = fwd
        isRunning = true
        startedAt = System.currentTimeMillis()

        Thread({ fwd.run() }, "Forwarder").start()

        // Thread lettore: ogni read() sul TUN restituisce esattamente un pacchetto IP.
        // Usiamo poll() con timeout invece di una read() bloccante: così il thread
        // si accorge dello stop anche se non arrivano pacchetti (chiudere un fd
        // mentre un altro thread è bloccato in read() non è affidabile).
        Thread({
            val fd = pfd.fileDescriptor
            val buf = ByteArray(Forwarder.MTU + 100)
            val pollFd = StructPollfd().apply { this.fd = fd; events = OsConstants.POLLIN.toShort() }
            try {
                while (isRunning) {
                    if (Os.poll(arrayOf(pollFd), 500) <= 0) continue
                    val n = try { Os.read(fd, buf, 0, buf.size) } catch (e: ErrnoException) {
                        if (e.errno == OsConstants.EAGAIN || e.errno == OsConstants.EINTR) continue else throw e
                    }
                    if (n > 0) fwd.submit(buf.copyOf(n))
                }
            } catch (e: Exception) {
                Log.i(TAG, "tun reader stopped: $e")
            }
        }, "TunReader").start()

        // Se cambia rete (Wi-Fi <-> mobile) aggiorniamo il DNS di upstream
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onLinkPropertiesChanged(network: Network, linkProperties: LinkProperties) {
                updateUpstreamDns(linkProperties)
            }
        }
        try { cm.registerDefaultNetworkCallback(cb); netCallback = cb } catch (e: Exception) {}

        server?.emit(JSONObject().put("ev", "status").put("vpn", true).put("ipv6", hasIpv6)
            .put("dns_upstream", upstreamDns.hostAddress).put("ts", System.currentTimeMillis() / 1000))
        Log.i(TAG, "capture started (ipv6=$hasIpv6, dns=${upstreamDns.hostAddress})")

        // Watchdog: se il programma PC che ha chiesto la sorveglianza sparisce
        // (chiuso, crashato, cavo staccato oltre il tempo di grazia) ci fermiamo.
        val main = Handler(Looper.getMainLooper())
        Thread({
            while (isRunning) {
                try { Thread.sleep(2000) } catch (_: InterruptedException) { break }
                if (isRunning && server?.watchdogExpired == true) {
                    main.post { onPcLost() }
                    break
                }
            }
        }, "Watchdog").apply { isDaemon = true; start() }

        // Traffico live: ogni secondo inviamo i contatori di byte delle connessioni
        // aperte che sono cambiati. Il PC ne ricava la velocità (mappa, spessore delle linee).
        // Non finiscono nello storico: sono tanti e ne conta solo l'ultimo valore.
        Thread({
            val reported = HashMap<Long, Long>()
            while (isRunning) {
                try { Thread.sleep(1000) } catch (_: InterruptedException) { break }
                val arr = JSONArray()
                for (f in liveFlows.values) {
                    val out = f.bytesOut; val inb = f.bytesIn
                    if (reported.put(f.id, out + inb) != out + inb) arr.put(JSONArray().put(f.id).put(out).put(inb))
                }
                reported.keys.retainAll(liveFlows.keys)
                if (arr.length() > 0) server?.emit(JSONObject().put("ev", "bytes")
                    .put("ts", System.currentTimeMillis() / 1000).put("flows", arr), keepInHistory = false)
            }
        }, "TrafficStats").apply { isDaemon = true; start() }
    }

    /**
     * Il PC non c'è più: fermiamo la VPN e chiediamo la disinstallazione.
     * Senza root un'app non può disinstallarsi in silenzio: Android mostra la
     * conferma di sistema. Se il PC torna, la disinstallazione la fa lui con adb.
     */
    private fun onPcLost() {
        Log.i(TAG, "PC scollegato oltre il tempo di grazia: stop + richiesta di disinstallazione")
        lastError = Strings.t("err_pc_lost")
        stopCapture()
        val del = Intent(Intent.ACTION_DELETE, Uri.parse("package:$packageName"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val nm = getSystemService(NotificationManager::class.java)
        val pi = PendingIntent.getActivity(this, 1, del, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val b = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, CHANNEL)
        else @Suppress("DEPRECATION") Notification.Builder(this)
        nm.notify(NOTIF_UNINSTALL, b.setContentTitle(Strings.t("notif_stopped_title"))
            .setContentText(Strings.t("notif_stopped_text"))
            .setSmallIcon(android.R.drawable.ic_menu_delete)
            .setContentIntent(pi).setAutoCancel(true).build())
        // Tentativo diretto (riesce se l'app è in primo piano; altrimenti resta la notifica)
        try { startActivity(del) } catch (e: Exception) { Log.i(TAG, "uninstall prompt: $e") }
    }

    private fun updateUpstreamDns(lp: LinkProperties) {
        val servers = lp.dnsServers.filter { it.hostAddress != VIRTUAL_DNS4 }
        val pick = servers.firstOrNull { it is Inet4Address } ?: servers.firstOrNull()
        if (pick != null) upstreamDns = pick
    }

    private fun stopCapture() {
        if (!isRunning && tun == null) { stopForegroundCompat(); stopSelf(); return }
        isRunning = false
        server?.emit(JSONObject().put("ev", "status").put("vpn", false).put("ts", System.currentTimeMillis() / 1000))
        forwarder?.stop(); forwarder = null
        appInfo?.stop(); appInfo = null
        try { tun?.close() } catch (_: Exception) {}   // sblocca il thread lettore
        tun = null
        netCallback?.let { try { getSystemService(ConnectivityManager::class.java).unregisterNetworkCallback(it) } catch (_: Exception) {} }
        netCallback = null
        // piccolo ritardo per lasciar arrivare l'evento "vpn:false" al PC
        val srv = server; server = null; currentServer = null
        Thread({ Thread.sleep(300); srv?.stop() }, "EventServer-stop").start()
        activeConnections = 0
        liveFlows.clear()
        stopForegroundCompat()
        stopSelf()
    }

    // ------------------------------------------------------------- FlowListener

    override fun onNewFlow(f: Flow) {
        val src = InetAddress.getByAddress(f.src)
        val dst = InetAddress.getByAddress(f.dst)
        f.uid = apps.uidFor(f.proto, src, f.srcPort, dst, f.dstPort)
        f.app = apps.nameFor(f.uid)
        appInfo?.report(f.app, f.uid)
        if (f.host == null) {
            dnsCache[dst.hostAddress]?.let { f.host = it; f.hostSource = "dns" }
        }
        totalConnections.incrementAndGet()
        liveFlows[f.id] = f
        activeConnections = (forwarder?.activeCount ?: 0) + 1
        server?.emit(flowJson("conn", f))
    }

    override fun onHostFound(f: Flow) {
        server?.emit(JSONObject().put("ev", "update").put("id", f.id)
            .put("ts", System.currentTimeMillis() / 1000).put("host", f.host).put("host_src", f.hostSource))
    }

    override fun onClosed(f: Flow) {
        liveFlows.remove(f.id)
        activeConnections = forwarder?.activeCount ?: 0
        val now = System.currentTimeMillis()
        val o = JSONObject().put("ev", "close").put("id", f.id).put("ts", now / 1000)
            .put("bytes_out", f.bytesOut).put("bytes_in", f.bytesIn).put("duration_ms", now - f.startMs)
        f.error?.let { o.put("error", it) }
        server?.emit(o)
    }

    override fun onDnsAnswers(answers: List<Pair<String, String>>) {
        for ((ip, name) in answers) dnsCache[ip] = name
    }

    override fun onDnsResponse(f: Flow, r: Dns.Response, rttMs: Long) {
        var server = InetAddress.getByAddress(f.dst).hostAddress
        if (server == VIRTUAL_DNS4) server = upstreamDns.hostAddress
        val o = JSONObject().put("ev", "dns").put("ts", System.currentTimeMillis() / 1000)
            .put("app", f.app).put("uid", f.uid).put("qname", r.qname).put("qtype", Dns.typeName(r.qtype))
            .put("rcode", r.rcode).put("answers", JSONArray(r.answers)).put("cnames", JSONArray(r.cnames))
            .put("server", server).put("rtt_ms", rttMs).put("ttl", r.ttl).put("conn", f.id)
        this.server?.emit(o)
    }

    private fun flowJson(ev: String, f: Flow): JSONObject {
        var dstIp = InetAddress.getByAddress(f.dst).hostAddress
        if (dstIp == VIRTUAL_DNS4) dstIp = upstreamDns.hostAddress   // mostriamo il DNS reale
        return JSONObject()
            .put("ev", ev)
            .put("id", f.id)
            .put("ts", f.startMs / 1000)
            .put("ts_ms", f.startMs)
            .put("app", f.app)
            .put("uid", f.uid)
            .put("proto", if (f.proto == Proto.TCP) "TCP" else "UDP")
            .put("ipver", f.ipVersion)
            .put("src_ip", InetAddress.getByAddress(f.src).hostAddress)
            .put("src_port", f.srcPort)
            .put("dst_ip", dstIp)
            .put("dst_port", f.dstPort)
            .put("host", f.host ?: JSONObject.NULL)
            .put("host_src", f.hostSource ?: JSONObject.NULL)
    }

    // ------------------------------------------------------------- notifica

    private fun goForeground() {
        val nm = getSystemService(NotificationManager::class.java)
        val pi = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val b = if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(NotificationChannel(CHANNEL, Strings.t("notif_channel"), NotificationManager.IMPORTANCE_LOW))
            Notification.Builder(this, CHANNEL)
        } else {
            @Suppress("DEPRECATION") Notification.Builder(this)
        }
        val n = b.setContentTitle(Strings.t("notif_title"))
            .setContentText(Strings.t("notif_text", PORT))
            .setSmallIcon(android.R.drawable.ic_menu_view)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 34) startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        else startForeground(NOTIF_ID, n)
    }

    private fun stopForegroundCompat() {
        if (Build.VERSION.SDK_INT >= 24) stopForeground(STOP_FOREGROUND_REMOVE)
        else @Suppress("DEPRECATION") stopForeground(true)
    }

    companion object {
        private const val TAG = "DroidSnex"
        const val ACTION_START = "com.droidsnex.agent.START"
        const val ACTION_STOP = "com.droidsnex.agent.STOP"
        const val PORT = 8888
        private const val CHANNEL = "capture"
        private const val NOTIF_ID = 1
        private const val NOTIF_UNINSTALL = 2
        private const val VPN_ADDR4 = "10.215.173.1"
        private const val VIRTUAL_DNS4 = "10.215.173.2"
        private const val VPN_ADDR6 = "fd00:d501:5e00::1"
        private const val FALLBACK_DNS = "1.1.1.1"

        // Stato letto dalla UI
        @Volatile var isRunning = false
        @Volatile var activeConnections = 0
        @Volatile var lastError: String? = null
        @Volatile var startedAt = 0L
        val totalConnections = AtomicLong(0)
        @Volatile var currentServer: EventServer? = null
    }
}
