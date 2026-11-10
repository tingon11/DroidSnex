package com.droidsnex.agent.net

/**
 * Log che usa android.util.Log sul telefono e stderr altrove (test JVM):
 * così i package net/ e inspect/ non dipendono dal framework Android.
 */
internal object Log {
    fun w(tag: String, msg: String, t: Throwable? = null) {
        try { android.util.Log.w(tag, msg, t) } catch (_: Throwable) { System.err.println("W/$tag: $msg ${t ?: ""}") }
    }
}
