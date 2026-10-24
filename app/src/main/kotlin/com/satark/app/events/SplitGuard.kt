package com.satark.app.events

import com.satark.detector.Baseline
import com.satark.detector.Decision
import com.satark.detector.Detector
import com.satark.detector.Event
import com.satark.detector.ModelConfig
import com.satark.detector.PaymentTrace

/**
 * A second look at the same events, for payments split into pieces. It shows the detector the running total paid to a payee
 * who was new within the last hour ([CumulativeNewPayee]), using a second copy of the same model with the same thresholds.
 *
 * It lives beside the main detector, not inside the session policy, on purpose: M2's 36 shared test vectors run through the
 * session policy and must keep matching M2's expected decisions exactly. The app raises an alarm if either check does, so this
 * can only add a warning, never remove one.
 */
class SplitGuard(model: ModelConfig, ageBand: String?, baseline: Baseline) {
    private val tally = CumulativeNewPayee()
    var lastTrace: PaymentTrace? = null
        private set
    private val detector = Detector.create(ageBand, baseline, model).also { it.traceSink = { t -> lastTrace = t } }

    fun reset() { tally.reset(); detector.reset() }

    fun onEvent(e: Event): Decision {
        lastTrace = null
        return detector.onEvent(tally.apply(e))
    }
}
