package com.satark.app

import com.satark.app.events.NudgePolicy
import com.satark.app.events.SessionPolicy
import com.satark.app.events.SplitGuard
import com.satark.detector.Baseline
import com.satark.detector.Decision
import com.satark.detector.Detector
import com.satark.detector.Event
import com.satark.detector.Level
import com.satark.detector.EventType
import com.satark.detector.ModelConfig
import com.satark.detector.PaymentType
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Named scam workflows run through the app's own path (session policy, detector, split guard, nudge rule), so a judge can be
 * told exactly what each one does. The events are the ones the phone's signals produce.
 */
class ScenarioTest {
    private val model = ModelConfig.loadBundled()
    private val min = 60_000L
    private val usual = 500.0

    private class Outcome(val alarm: Boolean, val nudge: Boolean)

    private fun run(events: List<Event>): Outcome {
        val baseline = Baseline.fixed(usual, 200.0)
        val detector = Detector.create("36-55", baseline, model)
        val guard = SplitGuard(model, "36-55", baseline)
        val policy = SessionPolicy()
        var alarm = false
        var nudge = false
        for (raw in events) {
            val step = policy.prepare(raw) ?: continue
            if (step.resetFirst) { detector.reset(); guard.reset() }
            val d: Decision = detector.onEvent(step.event)
            val g: Decision = guard.onEvent(step.event)
            if (d.level == Level.HARD || g.level == Level.HARD) alarm = true
            else if (raw.type == EventType.PAYMENT_ATTEMPT && NudgePolicy.shouldNudge(policy.unknownCallActive, raw.payeeIsNew, raw.amountInr, usual)) nudge = true
        }
        return Outcome(alarm, nudge)
    }

    private fun pay(t: Long, payee: String, amount: Double, new: Boolean) =
        Event(t, EventType.PAYMENT_ATTEMPT, payeeId = payee, payeeIsNew = new, amountInr = amount, paymentType = PaymentType.P2P)

    /** An unknown caller in a cloned voice of a relative claims an emergency and asks for money to a number the person never paid. */
    @Test fun clonedVoiceFamilyEmergencyIsNotLeftUnwarned() {
        val o = run(listOf(
            Event(0, EventType.CALL_START, callerKnown = false),
            Event(4 * min, EventType.NEW_PAYEE, payeeId = "P"),
            pay(6 * min, "P", 40_000.0, true),
        ))
        assertTrue(o.alarm || o.nudge, "an unknown call, then a new payee, then a very large amount must warn")
    }

    /** The same fraud cut into three pieces to stay under any one-payment check. */
    @Test fun splittingThePaymentDoesNotHideIt() {
        val whole = run(listOf(
            Event(0, EventType.CALL_START, callerKnown = false),
            Event(2 * min, EventType.NEW_PAYEE, payeeId = "P"),
            pay(4 * min, "P", 30_000.0, true),
        ))
        val split = run(listOf(
            Event(0, EventType.CALL_START, callerKnown = false),
            Event(2 * min, EventType.NEW_PAYEE, payeeId = "P"),
            pay(4 * min, "P", 10_000.0, true),
            pay(7 * min, "P", 10_000.0, false),
            pay(10 * min, "P", 10_000.0, false),
        ))
        assertTrue(!whole.alarm || split.alarm, "if the whole payment alarms, the split one must too")
    }

    @Test fun anOrdinaryCallAndAFamiliarPayeeStaysQuiet() {
        val o = run(listOf(
            Event(0, EventType.CALL_START, callerKnown = false),
            pay(5 * min, "K", 450.0, false),
        ))
        assertTrue(!o.alarm && !o.nudge)
    }
}
