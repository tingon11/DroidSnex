package com.droidsnex.agent

import com.droidsnex.agent.inspect.Dns
import com.droidsnex.agent.inspect.HostSniffer
import com.droidsnex.agent.net.Flow
import com.droidsnex.agent.net.FlowListener
import com.droidsnex.agent.net.Forwarder
import com.droidsnex.agent.net.PacketBuilder
import com.droidsnex.agent.net.PacketParser
import com.droidsnex.agent.net.ParsedPacket
import com.droidsnex.agent.net.TcpFlags
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.ServerSocket
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import kotlin.random.Random

/**
 * Test JVM (senza telefono) dello stack in user space: simuliamo l'app che
 * scrive pacchetti nel TUN e verifichiamo che il Forwarder li inoltri su
 * socket reali verso server locali e risponda con pacchetti corretti.
 */
class NetStackTest {
    private val client = byteArrayOf(10, 215.toByte(), 173.toByte(), 1)
    private val loop = byteArrayOf(127, 0, 0, 1)

    // ------------------------------------------------------------ helper
    private class Harness {
        val out = LinkedBlockingQueue<ByteArray>()
        val flows = CopyOnWriteArrayList<Flow>()
        val closed = CopyOnWriteArrayList<Flow>()
        val dns = CopyOnWriteArrayList<Pair<String, String>>()
        val fwd = Forwarder({ true }, { true }, { out.put(it) }, object : FlowListener {
            override fun onNewFlow(f: Flow) { flows.add(f) }
            override fun onHostFound(f: Flow) {}
            override fun onClosed(f: Flow) { closed.add(f) }
            override fun onDnsAnswers(answers: List<Pair<String, String>>) { dns.addAll(answers) }
        }, byteArrayOf(10, 215.toByte(), 173.toByte(), 2)) { InetAddress.getByName("127.0.0.1") }
        val thread = Thread { fwd.run() }.apply { isDaemon = true; start() }
        fun recv(): ParsedPacket {
            val b = out.poll(5, TimeUnit.SECONDS) ?: error("nessun pacchetto dal Forwarder")
            return PacketParser.parse(b, b.size)!!
        }
        fun stop() = fwd.stop()
    }

    private fun tcp(h: Harness, sport: Int, dport: Int, flags: Int, seq: Int, ack: Int, data: ByteArray = ByteArray(0), win: Int = 65535) =
        h.fwd.submit(PacketBuilder.tcp(client, loop, sport, dport, seq, ack, flags, win, data, 0, data.size, if (flags == TcpFlags.SYN) 1460 else 0))

    private fun clientHello(host: String): ByteArray {
        val name = host.toByteArray()
        val sni = ByteArrayOutputStream().apply {
            write(0); write(0)                                  // ext type server_name
            val l = name.size + 5
            write(l ushr 8); write(l)
            write((name.size + 3) ushr 8); write(name.size + 3)
            write(0); write(name.size ushr 8); write(name.size); write(name)
        }.toByteArray()
        val body = ByteArrayOutputStream().apply {
            write(3); write(3); write(ByteArray(32)); write(0)   // version, random, session id
            write(0); write(2); write(0x13); write(0x01)         // cipher suites
            write(1); write(0)                                  // compression
            write(sni.size ushr 8); write(sni.size); write(sni)
        }.toByteArray()
        val hs = byteArrayOf(1, 0, (body.size ushr 8).toByte(), body.size.toByte()) + body
        return byteArrayOf(0x16, 3, 1, (hs.size ushr 8).toByte(), hs.size.toByte()) + hs
    }

    // ------------------------------------------------------------ test

    @Test fun packetRoundTripAndChecksum() {
        val data = "ciao".toByteArray()
        val raw = PacketBuilder.tcp(client, loop, 1234, 443, 100, 200, TcpFlags.ACK or TcpFlags.PSH, 1000, data, 0, data.size)
        val p = PacketParser.parse(raw, raw.size)!!
        assertEquals(1234, p.srcPort); assertEquals(443, p.dstPort); assertEquals(100, p.seq); assertEquals(200, p.ack)
        assertEquals("ciao", String(raw, p.payloadOffset, p.payloadLength))
        // checksum IPv4 header: la somma su tutto l'header deve dare 0xffff
        var sum = 0
        for (i in 0 until 20 step 2) sum += ((raw[i].toInt() and 0xff) shl 8) or (raw[i + 1].toInt() and 0xff)
        while (sum ushr 16 != 0) sum = (sum and 0xffff) + (sum ushr 16)
        assertEquals(0xffff, sum)
        val v6 = PacketBuilder.udp(ByteArray(16).also { it[15] = 1 }, ByteArray(16).also { it[15] = 2 }, 5, 53, data, 0, data.size)
        val p6 = PacketParser.parse(v6, v6.size)!!
        assertEquals(6, p6.ipVersion); assertEquals(53, p6.dstPort); assertEquals(4, p6.payloadLength)
    }

    @Test fun sniAcrossSegments() {
        val ch = clientHello("graph.facebook.com")
        val s = HostSniffer()
        assertEquals(HostSniffer.Result.NeedMore, s.feed(ch, 0, 20))
        val r = s.feed(ch, 20, ch.size - 20)
        assertEquals(HostSniffer.Result.Found("graph.facebook.com", "sni"), r)
        val http = "GET / HTTP/1.1\r\nHost: Example.org:8080\r\n\r\n".toByteArray()
        assertEquals(HostSniffer.Result.Found("example.org", "http"), HostSniffer().feed(http, 0, http.size))
    }

    @Test fun dnsAnswers() {
        // risposta: graph.facebook.com CNAME star.c10r.facebook.com, A 157.240.1.1 (con compressione)
        val q = byteArrayOf(5) + "graph".toByteArray() + byteArrayOf(8) + "facebook".toByteArray() + byteArrayOf(3) + "com".toByteArray() + byteArrayOf(0)
        val pkt = ByteArrayOutputStream().apply {
            write(byteArrayOf(0x12, 0x34, 0x81.toByte(), 0x80.toByte(), 0, 1, 0, 2, 0, 0, 0, 0))
            write(q); write(byteArrayOf(0, 1, 0, 1))
            write(byteArrayOf(0xc0.toByte(), 12, 0, 5, 0, 1, 0, 0, 0, 60, 0, 7))
            write(byteArrayOf(4) + "star".toByteArray() + byteArrayOf(0xc0.toByte(), 18))
            write(byteArrayOf(0xc0.toByte(), 12, 0, 1, 0, 1, 0, 0, 0, 60, 0, 4, 157.toByte(), 240.toByte(), 1, 1))
        }.toByteArray()
        assertEquals("graph.facebook.com", Dns.queryName(pkt, 0, pkt.size))
        assertEquals(listOf("157.240.1.1" to "graph.facebook.com"), Dns.answers(pkt, 0, pkt.size))
    }

    @Test fun tcpEchoWithSniAndCleanClose() {
        val server = ServerSocket(0, 5, InetAddress.getByName("127.0.0.1"))
        Thread {
            server.accept().use { s ->
                val buf = ByteArray(4096)
                while (true) { val n = s.getInputStream().read(buf); if (n < 0) break; s.getOutputStream().write(buf, 0, n) }
            }
        }.start()
        val h = Harness()
        val port = server.localPort
        tcp(h, 40000, port, TcpFlags.SYN, 1000, 0)
        val synAck = h.recv()
        assertTrue(synAck.has(TcpFlags.SYN) && synAck.has(TcpFlags.ACK))
        assertEquals(1001, synAck.ack)
        var mySeq = 1001
        val srvSeq = synAck.seq + 1
        tcp(h, 40000, port, TcpFlags.ACK, mySeq, srvSeq)

        val hello = clientHello("example.com")
        tcp(h, 40000, port, TcpFlags.ACK or TcpFlags.PSH, mySeq, srvSeq, hello)
        mySeq += hello.size
        // Riceviamo: ACK dei nostri dati + i dati in eco (ordine non garantito)
        val echoed = ByteArrayOutputStream()
        var theirSeq = srvSeq
        while (echoed.size() < hello.size) {
            val p = h.recv()
            if (p.payloadLength > 0) {
                assertEquals(theirSeq, p.seq)
                echoed.write(p.raw, p.payloadOffset, p.payloadLength); theirSeq += p.payloadLength
                tcp(h, 40000, port, TcpFlags.ACK, mySeq, theirSeq)
            }
        }
        assertArrayEquals(hello, echoed.toByteArray())
        assertEquals("example.com", h.flows[0].host)
        assertEquals("sni", h.flows[0].hostSource)

        // Chiusura: FIN dall'app -> il server chiude -> FIN dal Forwarder
        tcp(h, 40000, port, TcpFlags.FIN or TcpFlags.ACK, mySeq, theirSeq)
        mySeq += 1
        var gotFin = false
        val deadline = System.currentTimeMillis() + 5000
        while (!gotFin && System.currentTimeMillis() < deadline) {
            val p = h.recv()
            if (p.has(TcpFlags.FIN)) { gotFin = true; theirSeq = p.seq + 1 }
        }
        assertTrue(gotFin)
        tcp(h, 40000, port, TcpFlags.ACK, mySeq, theirSeq)
        Thread.sleep(300)
        assertEquals(1, h.closed.size)
        assertEquals(hello.size.toLong(), h.closed[0].bytesOut)
        assertEquals(hello.size.toLong(), h.closed[0].bytesIn)
        h.stop(); server.close()
    }

    @Test fun tcpBulkDownloadRespectsWindowAndOrder() {
        val payload = Random(42).nextBytes(600_000)
        val server = ServerSocket(0, 5, InetAddress.getByName("127.0.0.1"))
        Thread { server.accept().use { it.getOutputStream().write(payload) } }.start()
        val h = Harness()
        val port = server.localPort
        tcp(h, 40001, port, TcpFlags.SYN, 5, 0)
        val synAck = h.recv()
        var theirSeq = synAck.seq + 1
        val win = 16384           // finestra piccola: il Forwarder deve rispettarla
        tcp(h, 40001, port, TcpFlags.ACK, 6, theirSeq, win = win)
        val got = ByteArrayOutputStream()
        var fin = false
        val deadline = System.currentTimeMillis() + 20000
        while (!fin && System.currentTimeMillis() < deadline) {
            val p = h.recv()
            if (p.payloadLength > 0) {
                if (p.seq == theirSeq) { got.write(p.raw, p.payloadOffset, p.payloadLength); theirSeq += p.payloadLength }
                assertTrue("finestra superata", p.payloadLength <= 1460)
            }
            if (p.has(TcpFlags.FIN) && p.seq == theirSeq) { fin = true; theirSeq += 1 }
            tcp(h, 40001, port, TcpFlags.ACK, 6, theirSeq, win = win)
        }
        assertTrue("FIN non ricevuto", fin)
        assertArrayEquals(payload, got.toByteArray())
        h.stop(); server.close()
    }

    @Test fun udpDnsRedirectAndCache() {
        // "DNS" locale che risponde con un A record fisso; la query va al DNS virtuale 10.215.173.2
        val dnsSrv = DatagramSocket(0, InetAddress.getByName("127.0.0.1"))
        Thread {
            val b = ByteArray(512); val pk = DatagramPacket(b, b.size); dnsSrv.receive(pk)
            val q = b.copyOf(pk.length)
            q[2] = 0x81.toByte(); q[3] = 0x80.toByte(); q[7] = 1
            val resp = q + byteArrayOf(0xc0.toByte(), 12, 0, 1, 0, 1, 0, 0, 0, 30, 0, 4, 1, 2, 3, 4)
            dnsSrv.send(DatagramPacket(resp, resp.size, pk.socketAddress))
        }.start()
        val h = Harness()
        val query = byteArrayOf(0, 7, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 7) + "example".toByteArray() + byteArrayOf(3) + "com".toByteArray() + byteArrayOf(0, 0, 1, 0, 1)
        // destinazione virtuale, ma porta reale del server di test (il redirect cambia solo l'indirizzo)
        h.fwd.submit(PacketBuilder.udp(client, byteArrayOf(10, 215.toByte(), 173.toByte(), 2), 33333, dnsSrv.localPort, query, 0, query.size))
        val r = h.recv()
        assertEquals(17, r.protocol)
        assertArrayEquals(byteArrayOf(10, 215.toByte(), 173.toByte(), 2), r.src)   // risponde "dal" DNS virtuale
        assertEquals(33333, r.dstPort)
        assertNotNull(h.flows.firstOrNull())
        Thread.sleep(100)
        assertEquals(listOf("1.2.3.4" to "example.com"), h.dns.toList())
        h.stop(); dnsSrv.close()
    }
}
