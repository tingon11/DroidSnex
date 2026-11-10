package com.droidsnex.agent

import android.util.Log
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketTimeoutException
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

/**
 * Server TCP su 127.0.0.1:8888 che invia gli eventi in formato JSON-lines
 * (un oggetto JSON per riga, terminato da '\n').
 *
 * Il PC lo raggiunge con:  adb forward tcp:8888 tcp:8888
 * adb inoltra le connessioni fatte al PC su localhost:8888 verso la porta
 * 8888 del loopback del telefono, attraverso il cavo USB. Per questo basta
 * ascoltare su 127.0.0.1: il server non è esposto al Wi-Fi.
 *
 * Gestione disconnessioni: gli ultimi eventi restano in un buffer circolare.
 * Appena connesso, il client può inviare {"cmd":"since","seq":N} e il server
 * gli rimanda tutto ciò che ha numero di sequenza > N, così staccare e
 * riattaccare il cavo non fa perdere nulla (entro la capienza del buffer).
 */
class EventServer(private val port: Int = 8888) {
    private val seq = AtomicLong(0)
    /** Identifica questa istanza: se cambia, il PC sa che la numerazione è ripartita. */
    private val instance = java.util.UUID.randomUUID().toString().substring(0, 8)
    private val history = ArrayDeque<String>()
    private val historySeq = ArrayDeque<Long>()
    private val clients = mutableListOf<Client>()
    private val lock = Object()
    @Volatile private var server: ServerSocket? = null
    @Volatile private var running = false

    val clientCount: Int get() = synchronized(lock) { clients.size }

    /**
     * Watchdog: il PC, collegandosi, può chiedere {"watchdog":N}. Da quel momento,
     * se per N secondi non c'è nessun PC "sorvegliante" collegato (programma PC
     * chiuso, crashato o cavo staccato), [watchdogExpired] diventa true e il
     * servizio si ferma da solo.
     */
    @Volatile var watchdogSec = 0
        private set
    private var watchers = 0
    @Volatile private var lastWatcherSeen = System.currentTimeMillis()

    val watchdogExpired: Boolean
        get() = synchronized(lock) {
            if (watchers > 0) lastWatcherSeen = System.currentTimeMillis()
            watchdogSec > 0 && watchers == 0 && System.currentTimeMillis() - lastWatcherSeen > watchdogSec * 1000L
        }
    val lastSeq: Long get() = seq.get()

    private class Client(val socket: Socket) {
        val queue = LinkedBlockingQueue<String>(QUEUE_MAX)
    }

    fun start() {
        running = true
        Thread({ acceptLoop() }, "EventServer-accept").apply { isDaemon = true; start() }
    }

    fun stop() {
        running = false
        try { server?.close() } catch (_: Exception) {}
        synchronized(lock) {
            clients.forEach { try { it.socket.close() } catch (_: Exception) {} }
            clients.clear()
        }
    }

    /** Assegna il numero di sequenza, salva nello storico e invia a tutti i client. */
    fun emit(obj: JSONObject, keepInHistory: Boolean = true) {
        synchronized(lock) {
            val s = seq.incrementAndGet()
            obj.put("seq", s)
            val line = obj.toString()
            if (keepInHistory) {
                history.addLast(line); historySeq.addLast(s)
                while (history.size > HISTORY_MAX) { history.removeFirst(); historySeq.removeFirst() }
            }
            for (c in clients) {
                // Client lento: se la coda è piena chiudiamo, si riconnetterà chiedendo "since"
                if (!c.queue.offer(line)) try { c.socket.close() } catch (_: Exception) {}
            }
        }
    }

    private fun acceptLoop() {
        while (running) {
            try {
                val ss = ServerSocket(port, 8, InetAddress.getByName("127.0.0.1")).apply { reuseAddress = true }
                server = ss
                while (running) {
                    val s = ss.accept()
                    Thread({ serve(s) }, "EventServer-client").apply { isDaemon = true; start() }
                }
            } catch (e: Exception) {
                if (running) {
                    Log.w(TAG, "server error, retry: $e")
                    Thread.sleep(1000)
                }
            }
        }
    }

    private fun serve(s: Socket) {
        val client = Client(s)
        var watchdog = 0
        var registered = false
        try {
            s.tcpNoDelay = true
            val out = OutputStreamWriter(s.getOutputStream(), Charsets.UTF_8)
            // Leggiamo un eventuale comando iniziale (max 700 ms di attesa)
            var since = 0L
            s.soTimeout = 700
            try {
                val line = BufferedReader(InputStreamReader(s.getInputStream(), Charsets.UTF_8)).readLine()
                if (line != null) {
                    val cmd = JSONObject(line)
                    if (cmd.optString("cmd") == "since") since = cmd.optLong("seq", 0)
                    watchdog = cmd.optInt("watchdog", 0)
                }
            } catch (_: SocketTimeoutException) {
            } catch (_: Exception) {}
            s.soTimeout = 0

            // Registrazione + snapshot dello storico in modo atomico: nessun buco né doppione
            val backlog: List<String>
            synchronized(lock) {
                backlog = history.zip(historySeq).filter { it.second > since }.map { it.first }
                clients.add(client)
                registered = true
                if (watchdog > 0) { watchdogSec = watchdog; watchers++; lastWatcherSeen = System.currentTimeMillis() }
            }
            val hello = JSONObject().put("ev", "hello").put("agent", "droidsnex").put("version", 1).put("instance", instance)
                .put("last_seq", lastSeq).put("replay", backlog.size).put("vpn", CaptureService.isRunning)
            out.write(hello.toString()); out.write("\n")
            for (l in backlog) { out.write(l); out.write("\n") }
            out.flush()

            while (running && !s.isClosed) {
                val line = client.queue.poll(5, TimeUnit.SECONDS)
                if (line == null) {
                    // Heartbeat: permette al PC di accorgersi di un collegamento morto
                    out.write(JSONObject().put("ev", "ping").put("ts", System.currentTimeMillis() / 1000)
                        .put("vpn", CaptureService.isRunning).toString())
                    out.write("\n")
                } else {
                    out.write(line); out.write("\n")
                    // svuotiamo quanto già in coda prima del flush
                    while (true) { val more = client.queue.poll() ?: break; out.write(more); out.write("\n") }
                }
                out.flush()
            }
        } catch (e: Exception) {
            Log.i(TAG, "client disconnected: $e")
        } finally {
            synchronized(lock) {
                clients.remove(client)
                if (registered && watchdog > 0) { watchers--; lastWatcherSeen = System.currentTimeMillis() }
            }
            try { s.close() } catch (_: Exception) {}
        }
    }

    companion object {
        private const val TAG = "DroidSnex"
        private const val HISTORY_MAX = 20000
        private const val QUEUE_MAX = 50000
    }
}
