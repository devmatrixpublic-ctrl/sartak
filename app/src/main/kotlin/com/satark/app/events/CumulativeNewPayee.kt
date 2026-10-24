package com.satark.app.events

import com.satark.detector.Event
import com.satark.detector.EventType

/**
 * Closes the "split the payment" gap. A scammer can ask for three small transfers to the same new payee instead of one large
 * one; the detector scores each payment on its own, so each looks ordinary (the AI-variants test held 0 of 90 such sessions,
 * ops/eval/reports/ai_variants.md).
 *
 * Within an hour of the first payment to a payee who was new, later payments to that payee are shown to the detector as one
 * payment to a new payee for the running total. The detector's model and thresholds are unchanged; only what it is shown is.
 * A retry of the same payment (same amount, within two minutes) is not counted twice.
 */
class CumulativeNewPayee(private val windowMs: Long = WINDOW_MS, private val retryMs: Long = RETRY_MS) {
    private class Tally(val firstMs: Long, var total: Double, var lastAmount: Double, var lastMs: Long)

    private val byPayee = HashMap<String, Tally>()

    fun reset() = byPayee.clear()

    fun apply(e: Event): Event {
        if (e.type != EventType.PAYMENT_ATTEMPT) return e
        val payee = e.payeeId ?: return e
        val amount = e.amountInr?.takeIf { it.isFinite() && it >= 0 } ?: return e
        val tally = byPayee[payee]
        if (tally == null || e.tMs - tally.firstMs > windowMs) {
            // First payment to this payee in the window. Only a new payee starts a running total.
            if (e.payeeIsNew == true) byPayee[payee] = Tally(e.tMs, amount, amount, e.tMs) else byPayee.remove(payee)
            return e
        }
        val retry = amount == tally.lastAmount && e.tMs - tally.lastMs <= retryMs
        if (!retry) tally.total += amount
        tally.lastAmount = amount
        tally.lastMs = e.tMs
        return e.copy(amountInr = tally.total, payeeIsNew = true)
    }

    companion object {
        const val WINDOW_MS = 60 * 60_000L
        const val RETRY_MS = 120_000L
    }
}
