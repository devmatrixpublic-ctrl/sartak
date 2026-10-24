package com.satark.app.events

import com.satark.detector.Decision
import com.satark.detector.Event
import com.satark.detector.EventType
import com.satark.detector.Level

/**
 * A plain rule beside the detector, for the payments that matter most: a person who has been in touch with someone they do not
 * know (a call or video that is open, or that ended within [RECENT_MS]) and now pays a payee who is new, for [THRESHOLD_INR] or
 * more, counting what has already gone to that payee within the hour (split payments, see [CumulativeNewPayee]).
 *
 * It closes two gaps the condition matrix showed: a payment made soon AFTER the unknown call ended was never held, and the
 * older age band needed a much larger amount than the others before anything was held. The threshold is [THRESHOLD_INR] for
 * everyone, and [YOUNG_THRESHOLD_INR] for a person who says they are under [AgeProfile.YOUNG_BELOW] (see [AgeProfile]).
 * It only ever adds a hold, never lowers the detector's decision, and the person can still choose "Continue anyway", so a
 * genuine payment is delayed, not lost. Measured on the simulator (ops/eval/reports/high_value_rule.md): it holds 20 more of
 * 578 scams and 8 more of 9,887 genuine sessions (false alarms 0.071% to 0.152%, over the deck's 0.100% target) at the single
 * Rs 25,000 threshold; the lower amount for the young is measured separately in the same report.
 */
class HighValueNewPayee(private val thresholdInr: Double = THRESHOLD_INR) {
    private val tally = CumulativeNewPayee()

    fun reset() = tally.reset()

    /** Every event, in order. A HARD decision when this payment must be held, otherwise none. */
    fun onEvent(raw: Event, unknownCallActive: Boolean, unknownContactRecent: Boolean): Decision {
        val e = tally.apply(raw)
        if (e.type != EventType.PAYMENT_ATTEMPT || !unknownContactRecent || e.payeeIsNew != true) return Decision.none()
        val total = e.amountInr ?: return Decision.none()
        if (!total.isFinite() || total < thresholdInr) return Decision.none()
        val why = if (unknownCallActive) "F_UNK_CALL_ACTIVE" else "F_UNK_CONTACT_RECENT"
        return Decision(Level.HARD, 0.0, listOf("F_UNK_X_NEWPAYEE", "F_NEWPAYEE_X_AMT", why), MECHANISM, e.tMs)
    }

    companion object {
        const val THRESHOLD_INR = 25_000.0
        const val YOUNG_THRESHOLD_INR = 10_000.0
        const val RECENT_MS = 30 * 60_000L
        const val MECHANISM = "high_value_new_payee"
    }
}
