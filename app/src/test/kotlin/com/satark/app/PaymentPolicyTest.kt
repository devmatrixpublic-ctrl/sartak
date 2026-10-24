package com.satark.app

import com.satark.app.events.CumulativeNewPayee
import com.satark.app.events.NudgePolicy
import com.satark.app.events.SessionPolicy
import com.satark.detector.Event
import com.satark.detector.EventType
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PaymentPolicyTest {
    private fun pay(t: Long, payee: String, amount: Double, new: Boolean) =
        Event(t, EventType.PAYMENT_ATTEMPT, payeeId = payee, payeeIsNew = new, amountInr = amount)

    private val min = 60_000L

    // --- nudge rule

    @Test fun nudgeNeedsUnknownCallNewPayeeAndAnAmountWellAboveUsual() {
        assertTrue(NudgePolicy.shouldNudge(true, true, 400.0, 161.0))
        assertTrue(NudgePolicy.shouldNudge(true, true, 322.0, 161.0), "exactly twice is enough")
        assertFalse(NudgePolicy.shouldNudge(true, true, 200.0, 161.0), "an ordinary amount no longer nudges")
        assertFalse(NudgePolicy.shouldNudge(false, true, 5000.0, 161.0), "no unknown call")
        assertFalse(NudgePolicy.shouldNudge(true, false, 5000.0, 161.0), "a payee already known")
        assertFalse(NudgePolicy.shouldNudge(true, null, 5000.0, 161.0))
    }

    @Test fun nudgeNeverTriggersOnBadNumbers() {
        assertFalse(NudgePolicy.shouldNudge(true, true, null, 161.0))
        assertFalse(NudgePolicy.shouldNudge(true, true, Double.NaN, 161.0))
        assertFalse(NudgePolicy.shouldNudge(true, true, 500.0, Double.NaN))
        assertFalse(NudgePolicy.shouldNudge(true, true, 500.0, -1.0))
    }

    // --- split-payment guard (mirrors ops/eval/split_guard.py; the same cases are in test_split_guard.py)

    @Test fun threeSmallPaymentsToANewPayeeAreShownAsOneRunningTotal() {
        val g = CumulativeNewPayee()
        assertEquals(1000.0, g.apply(pay(0, "P", 1000.0, true)).amountInr)
        val second = g.apply(pay(3 * min, "P", 1000.0, false))
        assertEquals(2000.0, second.amountInr); assertEquals(true, second.payeeIsNew)
        assertEquals(3500.0, g.apply(pay(6 * min, "P", 1500.0, false)).amountInr)
    }

    @Test fun aRetryOfTheSamePaymentIsNotCountedTwice() {
        val g = CumulativeNewPayee()
        g.apply(pay(0, "P", 1000.0, true))
        assertEquals(2000.0, g.apply(pay(3 * min, "P", 1000.0, false)).amountInr)
        assertEquals(2000.0, g.apply(pay(3 * min + 20_000, "P", 1000.0, false)).amountInr, "a tap on Pay again within two minutes")
    }

    @Test fun anOldOrKnownPayeeIsNeverAccumulated() {
        val g = CumulativeNewPayee()
        val known = g.apply(pay(0, "K", 500.0, false))
        assertEquals(500.0, known.amountInr); assertEquals(false, known.payeeIsNew)
        assertEquals(500.0, g.apply(pay(2 * min, "K", 500.0, false)).amountInr, "a payee who was never new")
        g.apply(pay(0, "P", 1000.0, true))
        val late = g.apply(pay(61 * min, "P", 1000.0, false))
        assertEquals(1000.0, late.amountInr, "past the hour it is an ordinary payment again")
        assertEquals(false, late.payeeIsNew)
    }

    @Test fun differentPayeesAreKeptApart() {
        val g = CumulativeNewPayee()
        g.apply(pay(0, "A", 1000.0, true))
        assertEquals(700.0, g.apply(pay(min, "B", 700.0, true)).amountInr)
        assertEquals(2000.0, g.apply(pay(3 * min, "A", 1000.0, false)).amountInr)
        assertEquals(1400.0, g.apply(pay(4 * min, "B", 700.0, false)).amountInr)
    }

    @Test fun otherEventsAndMissingFieldsPassThroughUntouched() {
        val g = CumulativeNewPayee()
        val install = Event(5, EventType.APP_INSTALL, appPackage = "x")
        assertEquals(install, g.apply(install))
        val noAmount = Event(0, EventType.PAYMENT_ATTEMPT, payeeId = "P", payeeIsNew = true)
        assertEquals(noAmount, g.apply(noAmount))
        val noPayee = Event(0, EventType.PAYMENT_ATTEMPT, payeeIsNew = true, amountInr = 10.0)
        assertEquals(noPayee, g.apply(noPayee))
        assertNull(g.apply(noPayee).payeeId)
    }

    @Test fun resetForgetsEverything() {
        val g = CumulativeNewPayee()
        g.apply(pay(0, "P", 1000.0, true))
        g.reset()
        assertEquals(1000.0, g.apply(pay(min, "P", 1000.0, false)).amountInr)
    }

    @Test fun theSessionPolicyLeavesPaymentsAloneSoM2sVectorsStayExact() {
        val p = SessionPolicy()
        p.prepare(Event(0, EventType.CALL_START, callerKnown = false))
        p.prepare(pay(10 * min, "P", 1000.0, true))
        val second = p.prepare(pay(13 * min, "P", 1000.0, false))!!.event
        assertEquals(1000.0, second.amountInr)
        assertEquals(false, second.payeeIsNew)
    }
}
