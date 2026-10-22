package com.satark.app.events

import com.satark.detector.Event
import com.satark.detector.EventType
import kotlin.math.abs

/**
 * Same rule as schema.json x-rules.deduplication: an event is a duplicate when its key equals the key of the PREVIOUS
 * raw event (even if that one was itself dropped) and |dt| <= window. Must not be stricter than the detector's own rule.
 *
 * PAYMENT_ATTEMPT is never dropped here: a retried payment must reach the detector, which repeats the original
 * decision. Dropping it would send level NONE to /risk-check and get an ALLOW (detector/INTEGRATION_NOTES.md #3).
 */
class Deduplicator(private val windowMs: Long = 3000) {
    private data class Key(val type: Any, val pkg: String?, val payee: String?, val amount: Double?)

    private var prevKey: Key? = null
    private var prevT = 0L

    fun isDuplicate(e: Event): Boolean {
        val k = Key(e.type, e.appPackage, e.payeeId, e.amountInr)
        val dup = e.type != EventType.PAYMENT_ATTEMPT && prevKey == k && abs(e.tMs - prevT) <= windowMs
        prevKey = k
        prevT = e.tMs
        return dup
    }

    fun reset() { prevKey = null }
}
