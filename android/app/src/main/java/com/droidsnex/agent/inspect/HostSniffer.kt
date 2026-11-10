package com.droidsnex.agent.inspect

/**
 * Estrae il nome host dai primi byte che un'app invia su una connessione TCP,
 * SENZA decifrare nulla:
 *
 *  - TLS: il ClientHello viaggia in chiaro e contiene l'estensione SNI
 *    (server_name) con il dominio richiesto.
 *  - HTTP in chiaro: header "Host:".
 *
 * Il ClientHello moderno (es. con chiavi post-quantum) può superare un segmento
 * TCP, quindi i dati vengono accumulati finché il parsing non è conclusivo.
 *
 * Nota: con Encrypted Client Hello (ECH) lo SNI visibile è quello "esterno"
 * (es. il nome pubblico del CDN), non il dominio reale.
 */
class HostSniffer {
    private val buf = java.io.ByteArrayOutputStream()
    var done = false
        private set

    sealed class Result {
        data class Found(val host: String, val source: String) : Result()
        object NeedMore : Result()
        object NotFound : Result()
    }

    fun feed(data: ByteArray, off: Int, len: Int): Result {
        if (done) return Result.NotFound
        buf.write(data, off, minOf(len, MAX - buf.size()).coerceAtLeast(0))
        val b = buf.toByteArray()
        val r = when {
            b.isEmpty() -> Result.NeedMore
            b[0].toInt() == 0x16 -> parseTls(b)
            looksLikeHttp(b) -> parseHttp(b)
            else -> Result.NotFound
        }
        if (r !is Result.NeedMore || buf.size() >= MAX) {
            done = true
            buf.reset()
        }
        return if (r is Result.NeedMore && done) Result.NotFound else r
    }

    private fun parseTls(b: ByteArray): Result {
        // Il ClientHello può essere spezzato su più record TLS: ricostruiamo il
        // messaggio handshake concatenando i payload dei record di tipo 22.
        val hs = java.io.ByteArrayOutputStream()
        var p = 0
        while (p + 5 <= b.size && b[p].toInt() == 0x16) {
            val rl = PacketU.u16(b, p + 3)
            val avail = minOf(rl, b.size - p - 5)
            hs.write(b, p + 5, avail)
            if (avail < rl) break
            p += 5 + rl
        }
        val h = hs.toByteArray()
        if (h.size < 4) return Result.NeedMore
        if (h[0].toInt() != 0x01) return Result.NotFound           // non è ClientHello
        val hsLen = PacketU.u24(h, 1)
        if (h.size < 4 + hsLen) return Result.NeedMore
        return try {
            var q = 4 + 2 + 32                                      // version + random
            q += 1 + (h[q].toInt() and 0xff)                        // session id
            q += 2 + PacketU.u16(h, q)                              // cipher suites
            q += 1 + (h[q].toInt() and 0xff)                        // compression
            if (q + 2 > 4 + hsLen) return Result.NotFound
            val extEnd = q + 2 + PacketU.u16(h, q)
            q += 2
            while (q + 4 <= extEnd) {
                val type = PacketU.u16(h, q)
                val l = PacketU.u16(h, q + 2)
                q += 4
                if (type == 0 && l >= 5) {                          // server_name
                    val nameType = h[q + 2].toInt()
                    val nameLen = PacketU.u16(h, q + 3)
                    if (nameType == 0 && q + 5 + nameLen <= h.size) {
                        return Result.Found(String(h, q + 5, nameLen, Charsets.US_ASCII).lowercase(), "sni")
                    }
                }
                q += l
            }
            Result.NotFound
        } catch (e: IndexOutOfBoundsException) {
            Result.NotFound
        }
    }

    private fun looksLikeHttp(b: ByteArray): Boolean {
        val s = String(b, 0, minOf(b.size, 8), Charsets.US_ASCII)
        return METHODS.any { s.startsWith(it) || it.startsWith(s) }
    }

    private fun parseHttp(b: ByteArray): Result {
        val s = String(b, Charsets.ISO_8859_1)
        val headersEnd = s.indexOf("\r\n\r\n")
        val head = if (headersEnd >= 0) s.substring(0, headersEnd) else s
        for (line in head.split("\r\n")) {
            if (line.length > 5 && line.regionMatches(0, "host:", 0, 5, ignoreCase = true)) {
                val host = line.substring(5).trim().substringBefore(':').lowercase()
                return if (host.isNotEmpty()) Result.Found(host, "http") else Result.NotFound
            }
        }
        return if (headersEnd >= 0) Result.NotFound else Result.NeedMore
    }

    companion object {
        private const val MAX = 16 * 1024
        private val METHODS = listOf("GET ", "POST ", "HEAD ", "PUT ", "DELETE ", "OPTIONS ", "PATCH ", "CONNECT ")
    }
}
