package com.droidsnex.agent.net

import java.net.InetAddress

/**
 * Parsing e costruzione di pacchetti IP grezzi (quelli che leggiamo/scriviamo
 * sull'interfaccia TUN della VPN).
 *
 * Il TUN ci consegna pacchetti IP "nudi" (nessun header Ethernet): il primo
 * nibble del primo byte è la versione IP (4 o 6).
 *
 * Supportiamo IPv4 e IPv6 (senza extension header), con TCP e UDP.
 * Tutto il resto (ICMP, frammenti, ecc.) viene scartato dal chiamante.
 */
object Proto {
    const val TCP = 6
    const val UDP = 17
}

object TcpFlags {
    const val FIN = 0x01
    const val SYN = 0x02
    const val RST = 0x04
    const val PSH = 0x08
    const val ACK = 0x10
}

class ParsedPacket(
    val raw: ByteArray,
    val length: Int,
    val ipVersion: Int,
    val src: ByteArray,          // 4 o 16 byte
    val dst: ByteArray,
    val protocol: Int,
    val l4Offset: Int,
    val srcPort: Int,
    val dstPort: Int,
    val payloadOffset: Int,
    val payloadLength: Int,
    // Campi solo TCP (0 per UDP)
    val seq: Int = 0,
    val ack: Int = 0,
    val flags: Int = 0,
    val window: Int = 0,
    val mss: Int = 0,             // opzione MSS del SYN, 0 se assente
) {
    fun has(flag: Int) = (flags and flag) != 0
    fun srcAddr(): InetAddress = InetAddress.getByAddress(src)
    fun dstAddr(): InetAddress = InetAddress.getByAddress(dst)
}

object PacketParser {

    /** Ritorna null per pacchetti non gestiti o malformati. */
    fun parse(buf: ByteArray, len: Int): ParsedPacket? {
        if (len < 20) return null
        val version = (buf[0].toInt() ushr 4) and 0x0f
        val src: ByteArray
        val dst: ByteArray
        val proto: Int
        val l4: Int
        val ipEnd: Int
        when (version) {
            4 -> {
                val ihl = (buf[0].toInt() and 0x0f) * 4
                val total = u16(buf, 2)
                if (ihl < 20 || total > len || total < ihl) return null
                // Frammenti: offset != 0 o flag MF -> non gestiti (rarissimi in uscita)
                val fragField = u16(buf, 6)
                if ((fragField and 0x1fff) != 0 || (fragField and 0x2000) != 0) return null
                proto = buf[9].toInt() and 0xff
                src = buf.copyOfRange(12, 16)
                dst = buf.copyOfRange(16, 20)
                l4 = ihl
                ipEnd = total
            }
            6 -> {
                if (len < 40) return null
                val payloadLen = u16(buf, 4)
                proto = buf[6].toInt() and 0xff   // next header (niente extension header)
                src = buf.copyOfRange(8, 24)
                dst = buf.copyOfRange(24, 40)
                l4 = 40
                ipEnd = minOf(len, 40 + payloadLen)
            }
            else -> return null
        }

        return when (proto) {
            Proto.TCP -> {
                if (ipEnd - l4 < 20) return null
                val dataOff = ((buf[l4 + 12].toInt() ushr 4) and 0x0f) * 4
                if (dataOff < 20 || l4 + dataOff > ipEnd) return null
                val flags = buf[l4 + 13].toInt() and 0x3f
                var mss = 0
                if ((flags and TcpFlags.SYN) != 0) mss = parseMss(buf, l4 + 20, l4 + dataOff)
                ParsedPacket(
                    buf, len, version, src, dst, proto, l4,
                    srcPort = u16(buf, l4), dstPort = u16(buf, l4 + 2),
                    payloadOffset = l4 + dataOff, payloadLength = ipEnd - l4 - dataOff,
                    seq = s32(buf, l4 + 4), ack = s32(buf, l4 + 8),
                    flags = flags, window = u16(buf, l4 + 14), mss = mss,
                )
            }
            Proto.UDP -> {
                if (ipEnd - l4 < 8) return null
                val udpLen = u16(buf, l4 + 4)
                val end = if (udpLen >= 8) minOf(ipEnd, l4 + udpLen) else ipEnd
                ParsedPacket(
                    buf, len, version, src, dst, proto, l4,
                    srcPort = u16(buf, l4), dstPort = u16(buf, l4 + 2),
                    payloadOffset = l4 + 8, payloadLength = end - l4 - 8,
                )
            }
            else -> null
        }
    }

    private fun parseMss(b: ByteArray, start: Int, end: Int): Int {
        var i = start
        while (i < end) {
            val kind = b[i].toInt() and 0xff
            if (kind == 0) break
            if (kind == 1) { i++; continue }
            if (i + 1 >= end) break
            val l = b[i + 1].toInt() and 0xff
            if (l < 2) break
            if (kind == 2 && l == 4 && i + 3 < end) return u16(b, i + 2)
            i += l
        }
        return 0
    }

    fun u16(b: ByteArray, o: Int) = ((b[o].toInt() and 0xff) shl 8) or (b[o + 1].toInt() and 0xff)
    fun s32(b: ByteArray, o: Int) =
        ((b[o].toInt() and 0xff) shl 24) or ((b[o + 1].toInt() and 0xff) shl 16) or
            ((b[o + 2].toInt() and 0xff) shl 8) or (b[o + 3].toInt() and 0xff)
}

/**
 * Costruisce i pacchetti di risposta che scriviamo nel TUN: per l'app sul
 * telefono devono sembrare arrivati dal server remoto, quindi src/dst sono
 * invertiti rispetto al pacchetto originale e i checksum devono essere giusti
 * (il kernel scarta silenziosamente pacchetti con checksum errato).
 */
object PacketBuilder {
    private var ipId = 0

    fun tcp(
        src: ByteArray, dst: ByteArray, srcPort: Int, dstPort: Int,
        seq: Int, ack: Int, flags: Int, window: Int,
        payload: ByteArray? = null, payloadOff: Int = 0, payloadLen: Int = 0,
        mss: Int = 0,
    ): ByteArray {
        val optLen = if (mss > 0) 4 else 0
        val tcpLen = 20 + optLen + payloadLen
        val pkt = ipHeader(src, dst, Proto.TCP, tcpLen)
        val o = pkt.size - tcpLen
        put16(pkt, o, srcPort)
        put16(pkt, o + 2, dstPort)
        put32(pkt, o + 4, seq)
        put32(pkt, o + 8, ack)
        pkt[o + 12] = (((20 + optLen) / 4) shl 4).toByte()
        pkt[o + 13] = flags.toByte()
        put16(pkt, o + 14, window)
        // checksum (o+16) e urgent pointer (o+18) restano a zero per ora
        if (mss > 0) {
            pkt[o + 20] = 2; pkt[o + 21] = 4; put16(pkt, o + 22, mss)
        }
        if (payloadLen > 0) System.arraycopy(payload!!, payloadOff, pkt, o + 20 + optLen, payloadLen)
        put16(pkt, o + 16, l4Checksum(pkt, src, dst, Proto.TCP, o, tcpLen))
        return pkt
    }

    fun udp(
        src: ByteArray, dst: ByteArray, srcPort: Int, dstPort: Int,
        payload: ByteArray, payloadOff: Int, payloadLen: Int,
    ): ByteArray {
        val udpLen = 8 + payloadLen
        val pkt = ipHeader(src, dst, Proto.UDP, udpLen)
        val o = pkt.size - udpLen
        put16(pkt, o, srcPort)
        put16(pkt, o + 2, dstPort)
        put16(pkt, o + 4, udpLen)
        System.arraycopy(payload, payloadOff, pkt, o + 8, payloadLen)
        var c = l4Checksum(pkt, src, dst, Proto.UDP, o, udpLen)
        if (c == 0) c = 0xffff // in UDP 0 significa "nessun checksum"
        put16(pkt, o + 6, c)
        return pkt
    }

    /** Alloca il pacchetto intero e scrive l'header IP (v4 o v6 in base alla lunghezza dell'indirizzo). */
    private fun ipHeader(src: ByteArray, dst: ByteArray, proto: Int, l4Len: Int): ByteArray {
        if (src.size == 4) {
            val total = 20 + l4Len
            val p = ByteArray(total)
            p[0] = 0x45
            put16(p, 2, total)
            ipId = (ipId + 1) and 0xffff
            put16(p, 4, ipId)
            put16(p, 6, 0x4000) // Don't Fragment
            p[8] = 64           // TTL
            p[9] = proto.toByte()
            System.arraycopy(src, 0, p, 12, 4)
            System.arraycopy(dst, 0, p, 16, 4)
            put16(p, 10, checksum(p, 0, 20, 0))
            return p
        } else {
            val p = ByteArray(40 + l4Len)
            p[0] = 0x60
            put16(p, 4, l4Len)
            p[6] = proto.toByte()
            p[7] = 64           // hop limit
            System.arraycopy(src, 0, p, 8, 16)
            System.arraycopy(dst, 0, p, 24, 16)
            return p
        }
    }

    /** Checksum TCP/UDP: include lo "pseudo-header" IP (indirizzi, protocollo, lunghezza). */
    private fun l4Checksum(p: ByteArray, src: ByteArray, dst: ByteArray, proto: Int, off: Int, len: Int): Int {
        var sum = 0L
        sum = sumWords(src, 0, src.size, sum)
        sum = sumWords(dst, 0, dst.size, sum)
        sum += proto.toLong()
        sum += len.toLong()   // per IPv6 la lunghezza è a 32 bit, ma < 65536 quindi equivalente
        return checksum(p, off, len, sum)
    }

    private fun sumWords(b: ByteArray, off: Int, len: Int, initial: Long): Long {
        var sum = initial
        var i = off
        val end = off + len
        while (i + 1 < end) {
            sum += (((b[i].toInt() and 0xff) shl 8) or (b[i + 1].toInt() and 0xff)).toLong()
            i += 2
        }
        if (i < end) sum += ((b[i].toInt() and 0xff) shl 8).toLong()
        return sum
    }

    /** Somma in complemento a uno a 16 bit (RFC 1071). */
    private fun checksum(b: ByteArray, off: Int, len: Int, initial: Long): Int {
        var sum = sumWords(b, off, len, initial)
        while (sum ushr 16 != 0L) sum = (sum and 0xffff) + (sum ushr 16)
        return sum.inv().toInt() and 0xffff
    }

    private fun put16(b: ByteArray, o: Int, v: Int) {
        b[o] = (v ushr 8).toByte(); b[o + 1] = v.toByte()
    }

    private fun put32(b: ByteArray, o: Int, v: Int) {
        b[o] = (v ushr 24).toByte(); b[o + 1] = (v ushr 16).toByte()
        b[o + 2] = (v ushr 8).toByte(); b[o + 3] = v.toByte()
    }
}
