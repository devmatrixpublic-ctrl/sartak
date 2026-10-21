package com.satark.app.events

import com.satark.detector.Event
import kotlin.math.abs

/**
 * Same rule as schema.json x-rules.deduplication: an event is a duplicate when its key equals the key of the PREVIOUS
 * raw event (even if that one was itself dropped) and |dt| <= window. Must not be stricter than the detector's own rule.
 */
class Deduplicator(private val windowMs: Long = 3000) {
    private data class Key(val type: Any, val pkg: String?, val payee: String?, val amount: Double?)

    private var prevKey: Key? = null
    private var prevT = 0L

    fun isDuplicate(e: Event): Boolean {
        val k = Key(e.type, e.appPackage, e.payeeId, e.amountInr)
        val dup = prevKey == k && abs(e.tMs - prevT) <= windowMs
        prevKey = k
        prevT = e.tMs
        return dup
    }

    fun reset() { prevKey = null }
}
