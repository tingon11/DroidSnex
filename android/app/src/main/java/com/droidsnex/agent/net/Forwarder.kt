package com.droidsnex.agent.net

import com.droidsnex.agent.inspect.Dns
import com.droidsnex.agent.inspect.HostSniffer
import java.io.IOException
import java.net.InetAddress
import java.net.InetSocketAddress
import java.nio.ByteBuffer
import java.nio.channels.DatagramChannel
import java.nio.channels.SelectionKey
import java.nio.channels.Selector
import java.nio.channels.SocketChannel
import java.util.concurrent.ConcurrentLinkedQueue
import kotlin.random.Random

/** Una connessione (flusso) osservata: è ciò che finisce nello stream JSON. */
class Flow(
    val id: Long,
    val proto: Int,
    val ipVersion: Int,
    val src: ByteArray, val srcPort: Int,
    val dst: ByteArray, val dstPort: Int,
    val startMs: Long,
) {
    var uid: Int = -1
    var app: String = "unknown"
    var host: String? = null
    var hostSource: String? = null
    // scritti dal thread del Forwarder, letti ogni secondo dal thread delle statistiche
    @Volatile var bytesOut = 0L
    @Volatile var bytesIn = 0L
    var error: String? = null
    /** UDP/53: quando è partita l'ultima query (per il tempo di risposta). */
    @Volatile var queryMs = 0L
}

interface FlowListener {
    /** Nuovo flusso: qui si risolvono UID/app e l'host dalla cache DNS. */
    fun onNewFlow(f: Flow)
    /** Host scoperto dopo l'apertura (SNI/HTTP Host). */
    fun onHostFound(f: Flow)
    fun onClosed(f: Flow)
    /** Coppie IP->nome viste nelle risposte DNS. */
    fun onDnsAnswers(answers: List<Pair<String, String>>)
    /** Una risposta DNS completa (per il tab DNS del PC). */
    fun onDnsResponse(f: Flow, r: Dns.Response, rttMs: Long)
}

/**
 * Il "pass-through": un mini stack TCP/UDP in user space.
 *
 * Senza root non possiamo semplicemente "rilanciare" i pacchetti IP grezzi
 * letti dal TUN: possiamo solo aprire normali socket. Quindi:
 *
 *  - per ogni flusso UDP apriamo un DatagramChannel verso la stessa
 *    destinazione, inviamo il payload e rimettiamo nel TUN le risposte
 *    impacchettate come UDP/IP provenienti dal server;
 *  - per ogni connessione TCP ci comportiamo da "server" verso l'app
 *    (rispondiamo al SYN con un SYN-ACK, gestiamo seq/ack, finestre, FIN/RST)
 *    e da "client" verso il server reale tramite un SocketChannel. I byte
 *    vengono copiati da un lato all'altro.
 *
 * Tutti i socket verso l'esterno sono "protetti" con VpnService.protect():
 * così escono dalla rete reale e non rientrano nella nostra VPN (loop).
 *
 * Threading: un solo thread (run()) possiede tutto lo stato. Il thread che
 * legge il TUN accoda i pacchetti in [inbound] e sveglia il selector.
 */
class Forwarder(
    /** VpnService.protect(): il socket esce dalla rete reale e non rientra nella VPN. */
    private val protect: (java.net.Socket) -> Boolean,
    private val protectUdp: (java.net.DatagramSocket) -> Boolean,
    /** Scrive un pacchetto IP completo nel TUN (una write = un pacchetto). */
    private val tunWrite: (ByteArray) -> Unit,
    private val listener: FlowListener,
    /** Indirizzo DNS virtuale annunciato dalla VPN: lo rigiriamo al DNS reale. */
    private val virtualDns: ByteArray,
    private val upstreamDns: () -> InetAddress,
) {
    private val selector: Selector = Selector.open()
    private val inbound = ConcurrentLinkedQueue<ByteArray>()
    @Volatile private var running = true
    private var nextId = 1L

    private val tcp = HashMap<String, TcpSession>()
    private val udp = HashMap<String, UdpSession>()
    private val readBuf = ByteBuffer.allocate(65536)

    val activeCount: Int get() = tcp.size + udp.size

    /** Chiamato dal thread lettore del TUN. */
    fun submit(packet: ByteArray) {
        inbound.offer(packet)
        selector.wakeup()
    }

    fun stop() {
        running = false
        selector.wakeup()
    }

    fun run() {
        var lastHousekeeping = 0L
        try {
            while (running) {
                selector.select(500)
                while (true) {
                    val p = inbound.poll() ?: break
                    try { handlePacket(p) } catch (e: Exception) { Log.w(TAG, "packet error", e) }
                }
                val it = selector.selectedKeys().iterator()
                while (it.hasNext()) {
                    val key = it.next(); it.remove()
                    try {
                        when (val s = key.attachment()) {
                            is TcpSession -> s.onSocketEvent(key)
                            is UdpSession -> s.onReadable()
                        }
                    } catch (e: Exception) {
                        Log.w(TAG, "socket error", e)
                        (key.attachment() as? TcpSession)?.abort("io: ${e.message}")
                        (key.attachment() as? UdpSession)?.close()
                    }
                }
                val now = System.currentTimeMillis()
                if (now - lastHousekeeping > 500) { housekeeping(now); lastHousekeeping = now }
            }
        } finally {
            tcp.values.toList().forEach { it.abort("stopped") }
            udp.values.toList().forEach { it.close() }
            try { selector.close() } catch (_: Exception) {}
        }
    }

    // ------------------------------------------------------------------ ingresso

    private fun handlePacket(raw: ByteArray) {
        val p = PacketParser.parse(raw, raw.size) ?: return   // ICMP & co.: scartati
        when (p.protocol) {
            Proto.TCP -> handleTcp(p)
            Proto.UDP -> handleUdp(p)
        }
    }

    private fun key(p: ParsedPacket) =
        "${p.protocol}|${hex(p.src)}:${p.srcPort}|${hex(p.dst)}:${p.dstPort}"

    /** Destinazione reale del socket: il DNS virtuale viene rediretto al DNS della rete. */
    private fun realDestination(p: ParsedPacket): InetSocketAddress =
        if (p.dst.contentEquals(virtualDns)) InetSocketAddress(upstreamDns(), p.dstPort)
        else InetSocketAddress(p.dstAddr(), p.dstPort)

    private fun isDns(port: Int, dst: ByteArray) = port == 53 || dst.contentEquals(virtualDns)

    private fun newFlow(p: ParsedPacket): Flow =
        Flow(nextId++, p.protocol, p.ipVersion, p.src, p.srcPort, p.dst, p.dstPort, System.currentTimeMillis())

    private fun writeTun(pkt: ByteArray) {
        try { tunWrite(pkt) } catch (e: IOException) { Log.w(TAG, "tun write: $e") }
    }

    // ------------------------------------------------------------------ UDP

    private fun handleUdp(p: ParsedPacket) {
        val k = key(p)
        var s = udp[k]
        if (s == null) {
            val flow = newFlow(p)
            if (isDns(p.dstPort, p.dst)) {
                Dns.queryName(p.raw, p.payloadOffset, p.payloadLength)?.let { flow.host = it; flow.hostSource = "dns-query" }
            }
            listener.onNewFlow(flow)
            val ch = DatagramChannel.open()
            protectUdp(ch.socket())                 // <- fondamentale: esce dalla rete reale
            ch.configureBlocking(false)
            try {
                ch.connect(realDestination(p))
            } catch (e: IOException) {
                flow.error = e.message; listener.onClosed(flow); ch.close(); return
            }
            s = UdpSession(k, flow, ch)
            s.selKey = ch.register(selector, SelectionKey.OP_READ, s)
            udp[k] = s
        }
        s.send(p)
    }

    private inner class UdpSession(val k: String, val flow: Flow, val ch: DatagramChannel) {
        var selKey: SelectionKey? = null
        var lastActivity = System.currentTimeMillis()

        fun send(p: ParsedPacket) {
            lastActivity = System.currentTimeMillis()
            if (isDns(flow.dstPort, flow.dst)) flow.queryMs = lastActivity
            flow.bytesOut += p.payloadLength
            try {
                ch.write(ByteBuffer.wrap(p.raw, p.payloadOffset, p.payloadLength))
            } catch (e: IOException) {
                flow.error = e.message; close()
            }
        }

        fun onReadable() {
            while (true) {
                readBuf.clear()
                val n = try { ch.read(readBuf) } catch (e: IOException) { flow.error = e.message; close(); return }
                if (n <= 0) return
                lastActivity = System.currentTimeMillis()
                flow.bytesIn += n
                val data = readBuf.array()
                if (isDns(flow.dstPort, flow.dst)) {
                    val ans = Dns.answers(data, 0, n)
                    if (ans.isNotEmpty()) listener.onDnsAnswers(ans)
                    Dns.response(data, 0, n)?.let {
                        listener.onDnsResponse(flow, it, if (flow.queryMs > 0) lastActivity - flow.queryMs else -1)
                    }
                }
                val max = (if (flow.ipVersion == 4) MTU - 28 else MTU - 48)
                if (n > max) continue   // non frammentiamo: datagramma troppo grande, scartato
                // Risposta: src = destinazione originale (anche se era il DNS virtuale)
                writeTun(PacketBuilder.udp(flow.dst, flow.src, flow.dstPort, flow.srcPort, data, 0, n))
            }
        }

        fun close() {
            if (udp.remove(k) == null) return
            try { ch.close() } catch (_: Exception) {}
            listener.onClosed(flow)
        }
    }

    // ------------------------------------------------------------------ TCP

    private fun handleTcp(p: ParsedPacket) {
        val k = key(p)
        val s = tcp[k]
        if (s != null) { s.onClientPacket(p); return }

        if (p.has(TcpFlags.RST)) return
        if (!p.has(TcpFlags.SYN) || p.has(TcpFlags.ACK)) {
            // Pacchetto di una connessione che non conosciamo (es. dopo un riavvio
            // della VPN): rispondiamo RST così l'app la chiude subito.
            val ackNo = p.seq + p.payloadLength + (if (p.has(TcpFlags.FIN)) 1 else 0)
            writeTun(PacketBuilder.tcp(p.dst, p.src, p.dstPort, p.srcPort,
                if (p.has(TcpFlags.ACK)) p.ack else 0, ackNo, TcpFlags.RST or TcpFlags.ACK, 0))
            return
        }

        // Nuovo SYN: apriamo il socket reale in modo non bloccante.
        val flow = newFlow(p)
        listener.onNewFlow(flow)
        val ch = SocketChannel.open()
        protect(ch.socket())
        ch.configureBlocking(false)
        ch.socket().tcpNoDelay = true
        val session = TcpSession(k, flow, ch, p)
        tcp[k] = session
        try {
            if (ch.connect(realDestination(p))) session.onConnected()
            else session.selKey = ch.register(selector, SelectionKey.OP_CONNECT, session)
        } catch (e: IOException) {
            session.abort("connect: ${e.message}")
        }
    }

    private enum class TcpState { CONNECTING, ESTABLISHED, CLOSED }

    /**
     * Stato di una connessione TCP lato app (l'app crede di parlare col server).
     *
     * Numeri di sequenza (Int con aritmetica modulo 2^32):
     *  - clientNext: prossimo byte atteso dall'app (= ACK che le mandiamo)
     *  - mySeq:      prossimo numero di sequenza che useremo verso l'app
     *  - clientAcked: fin dove l'app ha confermato i nostri dati
     * I byte inviati ma non confermati restano in [unacked] per la ritrasmissione.
     */
    private inner class TcpSession(val k: String, val flow: Flow, val ch: SocketChannel, syn: ParsedPacket) {
        var selKey: SelectionKey? = null
        var state = TcpState.CONNECTING
        val myIsn = Random.nextInt()
        var mySeq = myIsn
        var clientNext = syn.seq + 1
        var clientAcked = myIsn
        var clientWindow = syn.window
        val mss = minOf(if (flow.ipVersion == 4) MTU - 40 else MTU - 60, if (syn.mss > 0) syn.mss else 536)

        val toRemote = ArrayDeque<ByteBuffer>()
        var toRemoteBytes = 0
        var unacked = ByteArray(0)
        var unackedLen = 0

        var clientFin = false        // l'app ha chiuso il suo lato
        var remoteEof = false        // il server ha chiuso il suo lato
        var finSent = false
        var finAcked = false
        var lastActivity = System.currentTimeMillis()
        var lastSend = 0L
        var sniffer: HostSniffer? = HostSniffer()

        fun onSocketEvent(key: SelectionKey) {
            if (!key.isValid) return
            if (key.isConnectable) {
                try {
                    if (ch.finishConnect()) onConnected()
                } catch (e: IOException) {
                    abort("connect: ${e.message}"); return
                }
            }
            if (key.isValid && key.isWritable) flushToRemote()
            if (key.isValid && key.isReadable) readFromRemote()
        }

        /** Il server reale ha accettato: ora completiamo l'handshake con l'app. */
        fun onConnected() {
            state = TcpState.ESTABLISHED
            sendToClient(TcpFlags.SYN or TcpFlags.ACK, seq = myIsn, mssOpt = mss)
            mySeq = myIsn + 1
            clientAcked = mySeq
            updateInterest()
        }

        fun onClientPacket(p: ParsedPacket) {
            lastActivity = System.currentTimeMillis()
            if (p.has(TcpFlags.RST)) { close(sendRst = false); return }
            if (p.has(TcpFlags.SYN)) {
                // SYN ritrasmesso: se siamo già connessi rimandiamo il SYN-ACK
                if (state == TcpState.ESTABLISHED && mySeq == myIsn + 1)
                    sendToClient(TcpFlags.SYN or TcpFlags.ACK, seq = myIsn, mssOpt = mss)
                return
            }
            if (state != TcpState.ESTABLISHED) return

            if (p.has(TcpFlags.ACK)) onClientAck(p.ack, p.window)

            // Dati dall'app verso il server
            if (p.payloadLength > 0) {
                val d = p.seq - clientNext
                if (d != 0) {
                    // Duplicato o fuori ordine: ri-confermiamo ciò che abbiamo
                    sendAck(); return
                }
                if (toRemoteBytes > MAX_PENDING) return   // backpressure: non confermiamo, l'app ritrasmetterà
                inspect(p)
                val copy = ByteBuffer.wrap(p.raw.copyOfRange(p.payloadOffset, p.payloadOffset + p.payloadLength))
                toRemote.addLast(copy); toRemoteBytes += p.payloadLength
                flow.bytesOut += p.payloadLength
                clientNext += p.payloadLength
                flushToRemote()
                if (!p.has(TcpFlags.FIN)) sendAck()
            }

            if (p.has(TcpFlags.FIN) && p.seq + p.payloadLength == clientNext && !clientFin) {
                clientFin = true
                clientNext += 1
                sendAck()
                if (toRemote.isEmpty()) shutdownRemoteOutput()
            } else if (p.has(TcpFlags.FIN) && clientFin) {
                sendAck()   // FIN ritrasmesso: il nostro ACK era andato perso
            }
            maybeFinish()
        }

        private fun onClientAck(ack: Int, window: Int) {
            clientWindow = window
            val acked = ack - clientAcked
            val inFlight = mySeq - clientAcked
            if (acked in 1..inFlight) {
                var dataAcked = acked
                if (finSent && ack == mySeq) { finAcked = true; dataAcked -= 1 }
                dataAcked = minOf(dataAcked, unackedLen)
                System.arraycopy(unacked, dataAcked, unacked, 0, unackedLen - dataAcked)
                unackedLen -= dataAcked
                clientAcked = ack
                lastSend = System.currentTimeMillis()
            }
            updateInterest()
        }

        /** Ispezione dei primi byte: TLS SNI o HTTP Host. Solo metadati, nessuna decifratura. */
        private fun inspect(p: ParsedPacket) {
            val sn = sniffer ?: return
            when (val r = sn.feed(p.raw, p.payloadOffset, p.payloadLength)) {
                is HostSniffer.Result.Found -> {
                    sniffer = null
                    if (flow.host != r.host) {
                        flow.host = r.host; flow.hostSource = r.source
                        listener.onHostFound(flow)
                    }
                }
                HostSniffer.Result.NotFound -> sniffer = null
                HostSniffer.Result.NeedMore -> {}
            }
        }

        private fun flushToRemote() {
            try {
                while (toRemote.isNotEmpty()) {
                    val b = toRemote.first()
                    val n = ch.write(b)
                    toRemoteBytes -= n
                    if (b.hasRemaining()) break
                    toRemote.removeFirst()
                }
            } catch (e: IOException) {
                abort("write: ${e.message}"); return
            }
            if (toRemote.isEmpty() && clientFin) shutdownRemoteOutput()
            updateInterest()
        }

        private fun shutdownRemoteOutput() {
            try { ch.shutdownOutput() } catch (_: Exception) {}
        }

        /** Legge dal server solo quanto entra nella finestra annunciata dall'app. */
        private fun readFromRemote() {
            while (state == TcpState.ESTABLISHED && !remoteEof) {
                val room = minOf(clientWindow - (mySeq - clientAcked), 65535 - unackedLen)
                if (room <= 0) break
                readBuf.clear()
                readBuf.limit(minOf(room, readBuf.capacity()))
                val n = try { ch.read(readBuf) } catch (e: IOException) { abort("read: ${e.message}"); return }
                if (n == 0) break
                if (n < 0) {
                    remoteEof = true
                    sendToClient(TcpFlags.FIN or TcpFlags.ACK, seq = mySeq)
                    mySeq += 1; finSent = true
                    break
                }
                flow.bytesIn += n
                appendUnacked(readBuf.array(), n)
                // Segmentazione in pacchetti da MSS byte
                var off = 0
                while (off < n) {
                    val len = minOf(mss, n - off)
                    sendToClient(TcpFlags.ACK or TcpFlags.PSH, seq = mySeq, data = readBuf.array(), off = off, len = len)
                    mySeq += len; off += len
                }
            }
            updateInterest()
            maybeFinish()
        }

        private fun appendUnacked(src: ByteArray, n: Int) {
            if (unackedLen + n > unacked.size) unacked = unacked.copyOf(maxOf(unacked.size * 2, unackedLen + n, 4096))
            System.arraycopy(src, 0, unacked, unackedLen, n)
            unackedLen += n
        }

        /** Ritrasmissione semplice: se l'app non conferma da 1 s, rimandiamo dal primo byte non confermato. */
        fun retransmitIfNeeded(now: Long) {
            if (state != TcpState.ESTABLISHED || now - lastSend < RTO_MS) return
            if (unackedLen > 0) {
                var off = 0
                var seq = clientAcked
                val limit = minOf(unackedLen, maxOf(clientWindow, mss))
                while (off < limit) {
                    val len = minOf(mss, limit - off)
                    sendToClient(TcpFlags.ACK or TcpFlags.PSH, seq = seq, data = unacked, off = off, len = len)
                    seq += len; off += len
                }
            } else if (finSent && !finAcked) {
                sendToClient(TcpFlags.FIN or TcpFlags.ACK, seq = mySeq - 1)
            }
        }

        private fun sendAck() = sendToClient(TcpFlags.ACK, seq = mySeq)

        private fun sendToClient(flags: Int, seq: Int, data: ByteArray? = null, off: Int = 0, len: Int = 0, mssOpt: Int = 0) {
            // Pacchetto "dal server all'app": invertiamo indirizzi e porte
            writeTun(PacketBuilder.tcp(flow.dst, flow.src, flow.dstPort, flow.srcPort,
                seq, clientNext, flags, RCV_WINDOW, data, off, len, mssOpt))
            // Il timer di ritrasmissione riparte solo per dati/FIN, non per i semplici ACK
            if (len > 0 || (flags and TcpFlags.FIN) != 0) lastSend = System.currentTimeMillis()
        }

        private fun updateInterest() {
            val key = selKey ?: ch.register(selector, 0, this).also { selKey = it }
            if (!key.isValid) return
            var ops = 0
            if (state == TcpState.CONNECTING) ops = ops or SelectionKey.OP_CONNECT
            if (state == TcpState.ESTABLISHED) {
                if (!remoteEof && clientWindow - (mySeq - clientAcked) > 0 && unackedLen < 65535) ops = ops or SelectionKey.OP_READ
                if (toRemote.isNotEmpty()) ops = ops or SelectionKey.OP_WRITE
            }
            key.interestOps(ops)
        }

        private fun maybeFinish() {
            // Chiusura pulita: entrambi i lati chiusi e il nostro FIN confermato
            if (clientFin && remoteEof && finAcked && toRemote.isEmpty()) close(sendRst = false)
        }

        fun abort(reason: String) {
            if (flow.error == null) flow.error = reason
            close(sendRst = true)
        }

        fun close(sendRst: Boolean) {
            if (state == TcpState.CLOSED) return
            if (sendRst) sendToClient(TcpFlags.RST or TcpFlags.ACK, seq = mySeq)
            state = TcpState.CLOSED
            tcp.remove(k)
            try { selKey?.cancel() } catch (_: Exception) {}
            try { ch.close() } catch (_: Exception) {}
            listener.onClosed(flow)
        }
    }

    // ------------------------------------------------------------------ manutenzione

    private fun housekeeping(now: Long) {
        for (s in tcp.values.toList()) {
            s.retransmitIfNeeded(now)
            val idle = now - s.lastActivity
            val timeout = when {
                s.state == TcpState.CONNECTING -> 30_000L
                s.clientFin || s.remoteEof -> 60_000L
                else -> TCP_IDLE_MS
            }
            if (idle > timeout) s.abort("timeout")
        }
        for (s in udp.values.toList()) {
            val timeout = if (s.flow.dstPort == 53) 10_000L else UDP_IDLE_MS
            if (now - s.lastActivity > timeout) s.close()
        }
    }

    companion object {
        private const val TAG = "DroidSnex"
        const val MTU = 1500
        private const val RCV_WINDOW = 65535
        private const val MAX_PENDING = 1 shl 20
        private const val RTO_MS = 1000L
        private const val TCP_IDLE_MS = 15 * 60_000L
        private const val UDP_IDLE_MS = 2 * 60_000L

        private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }
    }
}
