package com.satark.app

import com.satark.app.events.SessionPolicy
import com.satark.app.events.SplitGuard
import com.satark.detector.Baseline
import com.satark.detector.Detector
import com.satark.detector.Event
import com.satark.detector.EventType
import com.satark.detector.Level
import com.satark.detector.ModelConfig
import com.satark.detector.PaymentType
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The numbers behind the on-device demo (docs/DEMO_SPLIT_GUARD.md): an unknown call and a new payee, no remote-access app,
 * a fresh-install baseline (usual payment about Rs 160). Rs 75,000 in one payment is held by the main detector; the same
 * Rs 75,000 sent as three Rs 25,000 pieces is not, and only the split guard holds it.
 */
class SplitGuardDemoTest {
    private val model = ModelConfig.loadBundled()
    private val min = 60_000L

    private fun pay(t: Long, amount: Double, new: Boolean) =
        Event(t, EventType.PAYMENT_ATTEMPT, payeeId = "P", payeeIsNew = new, amountInr = amount, paymentType = PaymentType.P2P)

    private fun held(age: String, events: List<Event>): Pair<Boolean, Boolean> {
        val baseline = Baseline.coldStart(model)
        val main = Detector.create(age, baseline, model)
        val guard = SplitGuard(model, age, baseline)
        val policy = SessionPolicy()
        var m = false
        var g = false
        for (raw in events) {
            val step = policy.prepare(raw) ?: continue
            if (main.onEvent(step.event).level == Level.HARD) m = true
            if (guard.onEvent(step.event).level == Level.HARD) g = true
        }
        return m to g
    }

    private val call = Event(0, EventType.CALL_START, callerKnown = false)
    private val newPayee = Event(2 * min - 1, EventType.NEW_PAYEE, payeeId = "P")

    @Test fun oneLargePaymentIsHeldByTheMainDetector() {
        for (age in listOf("18-35", "36-59")) {
            val (main, _) = held(age, listOf(call, newPayee, pay(2 * min, 75_000.0, true)))
            assertTrue(main, "$age: a single Rs 75,000 payment to a new payee during an unknown call")
        }
    }

    @Test fun theSameTotalInThreePiecesSlipsPastTheMainDetectorButNotTheGuard() {
        for (age in listOf("18-35", "36-59")) {
            val pieces = listOf(newPayee, pay(2 * min, 25_000.0, true), pay(4 * min, 25_000.0, false), pay(6 * min, 25_000.0, false))
            val (main, guard) = held(age, listOf(call) + pieces)
            assertFalse(main, "$age: no single piece looks large enough for the main detector")
            assertTrue(guard, "$age: the running total to the new payee does")
        }
    }

    @Test fun smallPiecesStayQuiet() {
        val (main, guard) = held("36-59", listOf(call, newPayee, pay(2 * min, 3_000.0, true), pay(4 * min, 3_000.0, false), pay(6 * min, 3_000.0, false)))
        assertFalse(main || guard, "Rs 9,000 in total is not held")
    }
}
