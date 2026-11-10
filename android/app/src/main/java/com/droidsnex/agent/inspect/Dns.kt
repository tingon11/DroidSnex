package com.droidsnex.agent.inspect

import java.net.InetAddress

/**
 * Parser DNS minimale (RFC 1035), solo lettura.
 *
 * Usi:
 *  - dalla query in uscita ricaviamo il nome cercato (host della "connessione" UDP/53);
 *  - dalle risposte ricaviamo le coppie IP -> nome, così quando poco dopo l'app
 *    apre una connessione TCP verso quell'IP sappiamo a quale dominio corrisponde.
 */
object Dns {

    /** Una risposta DNS letta per intero (per il tab DNS del PC). */
    class Response(val qname: String, val qtype: Int, val rcode: Int,
                   val answers: List<String>, val cnames: List<String>, val ttl: Int)

    fun typeName(t: Int): String = when (t) {
        1 -> "A"; 28 -> "AAAA"; 5 -> "CNAME"; 15 -> "MX"; 16 -> "TXT"; 33 -> "SRV"; 65 -> "HTTPS"; 64 -> "SVCB"
        12 -> "PTR"; 2 -> "NS"; 6 -> "SOA"; 255 -> "ANY"; else -> "T$t"
    }

    /** Risposta completa: nome e tipo della domanda, rcode, IP (A/AAAA), CNAME. Null se non è una risposta. */
    fun response(b: ByteArray, off: Int, len: Int): Response? {
        try {
            if (len < 12) return null
            val flags = PacketU.u16(b, off + 2)
            if ((flags and 0x8000) == 0) return null
            val rcode = flags and 0x000f
            val qd = PacketU.u16(b, off + 4)
            val an = PacketU.u16(b, off + 6)
            var p = off + 12
            var qname = ""
            var qtype = 0
            repeat(qd) {
                val (name, next) = readName(b, off, len, p) ?: return null
                if (qname.isEmpty()) { qname = name; qtype = PacketU.u16(b, next) }
                p = next + 4
            }
            val ips = ArrayList<String>()
            val cn = ArrayList<String>()
            var ttl = -1
            repeat(an) {
                val (_, next) = readName(b, off, len, p) ?: return Response(qname, qtype, rcode, ips, cn, ttl)
                p = next
                if (p + 10 > off + len) return Response(qname, qtype, rcode, ips, cn, ttl)
                val type = PacketU.u16(b, p)
                val rttl = (PacketU.u16(b, p + 4) shl 16) or PacketU.u16(b, p + 6)
                val rdlen = PacketU.u16(b, p + 8)
                p += 10
                if (p + rdlen > off + len) return Response(qname, qtype, rcode, ips, cn, ttl)
                when {
                    (type == 1 && rdlen == 4) || (type == 28 && rdlen == 16) -> {
                        InetAddress.getByAddress(b.copyOfRange(p, p + rdlen)).hostAddress?.let { ips.add(it) }
                        if (ttl < 0 || rttl < ttl) ttl = rttl
                    }
                    type == 5 -> readName(b, off, len, p)?.let { cn.add(it.first) }
                }
                p += rdlen
            }
            return Response(qname, qtype, rcode, ips, cn, ttl)
        } catch (e: Exception) {
            return null
        }
    }

    /** Nome della prima domanda, o null. */
    fun queryName(b: ByteArray, off: Int, len: Int): String? = try {
        if (len < 12 || PacketU.u16(b, off + 4) < 1) null
        else readName(b, off, len, off + 12)?.first
    } catch (e: Exception) {
        null
    }

    /**
     * Ritorna le risposte A/AAAA come coppie (ip testuale, nome della domanda).
     * Usiamo il nome della *domanda* (es. "graph.facebook.com") e non quello
     * finale della catena CNAME ("star.c10r.facebook.com"), che è più leggibile.
     */
    fun answers(b: ByteArray, off: Int, len: Int): List<Pair<String, String>> {
        val out = ArrayList<Pair<String, String>>()
        try {
            if (len < 12) return out
            val flags = PacketU.u16(b, off + 2)
            if ((flags and 0x8000) == 0) return out          // non è una risposta
            val qd = PacketU.u16(b, off + 4)
            val an = PacketU.u16(b, off + 6)
            var p = off + 12
            var qname: String? = null
            repeat(qd) {
                val (name, next) = readName(b, off, len, p) ?: return out
                if (qname == null) qname = name
                p = next + 4                                   // qtype + qclass
            }
            repeat(an) {
                val (rname, next) = readName(b, off, len, p) ?: return out
                p = next
                if (p + 10 > off + len) return out
                val type = PacketU.u16(b, p)
                val rdlen = PacketU.u16(b, p + 8)
                p += 10
                if (p + rdlen > off + len) return out
                if ((type == 1 && rdlen == 4) || (type == 28 && rdlen == 16)) {
                    val ip = InetAddress.getByAddress(b.copyOfRange(p, p + rdlen)).hostAddress
                    if (ip != null) out.add(ip to (qname ?: rname))
                }
                p += rdlen
            }
        } catch (e: Exception) {
            // pacchetto malformato: teniamo quello che abbiamo
        }
        return out
    }

    /** Legge un nome DNS con supporto ai puntatori di compressione. Ritorna (nome, offset dopo il nome). */
    private fun readName(b: ByteArray, base: Int, len: Int, start: Int): Pair<String, Int>? {
        val sb = StringBuilder()
        var p = start
        var end = -1
        var jumps = 0
        val limit = base + len
        while (true) {
            if (p >= limit) return null
            val l = b[p].toInt() and 0xff
            when {
                l == 0 -> { if (end < 0) end = p + 1; break }
                (l and 0xc0) == 0xc0 -> {
                    if (p + 1 >= limit || ++jumps > 20) return null
                    if (end < 0) end = p + 2
                    p = base + (((l and 0x3f) shl 8) or (b[p + 1].toInt() and 0xff))
                }
                else -> {
                    if (p + 1 + l > limit) return null
                    if (sb.isNotEmpty()) sb.append('.')
                    for (i in 0 until l) sb.append((b[p + 1 + i].toInt() and 0xff).toChar())
                    p += 1 + l
                }
            }
        }
        return sb.toString().lowercase() to end
    }
}

internal object PacketU {
    fun u16(b: ByteArray, o: Int) = ((b[o].toInt() and 0xff) shl 8) or (b[o + 1].toInt() and 0xff)
    fun u24(b: ByteArray, o: Int) = ((b[o].toInt() and 0xff) shl 16) or u16(b, o + 1)
}
