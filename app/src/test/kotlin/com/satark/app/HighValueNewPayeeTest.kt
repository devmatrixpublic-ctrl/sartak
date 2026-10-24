package com.satark.app

import com.satark.app.events.HighValueNewPayee
import com.satark.app.events.SessionPolicy
import com.satark.detector.Event
import com.satark.detector.EventType
import com.satark.detector.Level
import com.satark.detector.PaymentType
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class HighValueNewPayeeTest {
    private val min = 60_000L
    private fun pay(t: Long, amount: Double, new: Boolean, who: String = "P") =
        Event(t, EventType.PAYMENT_ATTEMPT, payeeId = who, payeeIsNew = new, amountInr = amount, paymentType = PaymentType.P2P)

    @Test fun holdsFromTheThresholdAndOnlyForANewPayeeWithAnUnknownContact() {
        val r = HighValueNewPayee()
        assertEquals(Level.NONE, r.onEvent(pay(0, 24_999.0, true), true, true).level)
        assertEquals(Level.HARD, HighValueNewPayee().onEvent(pay(0, 25_000.0, true), true, true).level)
        assertEquals(Level.NONE, HighValueNewPayee().onEvent(pay(0, 90_000.0, false), true, true).level, "a known payee")
        assertEquals(Level.NONE, HighValueNewPayee().onEvent(pay(0, 90_000.0, true), false, false).level, "no unknown contact")
    }

    @Test fun reasonsNameTheCallWhileItIsOpenAndTheRecentContactAfterIt() {
        val open = HighValueNewPayee().onEvent(pay(0, 30_000.0, true), true, true)
        val over = HighValueNewPayee().onEvent(pay(0, 30_000.0, true), false, true)
        assertTrue("F_UNK_CALL_ACTIVE" in open.reasons && "F_UNK_X_NEWPAYEE" in open.reasons)
        assertTrue("F_UNK_CONTACT_RECENT" in over.reasons && "F_UNK_CALL_ACTIVE" !in over.reasons)
    }

    @Test fun addsUpPaymentsToTheSameNewPayee() {
        val r = HighValueNewPayee()
        assertEquals(Level.NONE, r.onEvent(pay(0, 10_000.0, true), true, true).level)
        assertEquals(Level.NONE, r.onEvent(pay(3 * min, 10_000.0, false), true, true).level)
        assertEquals(Level.HARD, r.onEvent(pay(6 * min, 10_000.0, false), true, true).level, "Rs 30,000 in all")
    }

    @Test fun sessionPolicyKnowsAnUnknownContactJustEnded() {
        val p = SessionPolicy()
        p.prepare(Event(0, EventType.CALL_START, callerKnown = false))
        assertTrue(p.unknownContactRecent(5 * min))
        p.prepare(Event(10 * min, EventType.CALL_END))
        assertTrue(p.unknownContactRecent(20 * min), "10 minutes after it ended")
        assertFalse(p.unknownContactRecent(41 * min), "31 minutes after it ended")
        val known = SessionPolicy()
        known.prepare(Event(0, EventType.CALL_START, callerKnown = true)); known.prepare(Event(min, EventType.CALL_END))
        assertFalse(known.unknownContactRecent(2 * min), "a call from a saved contact never counts")
    }
}
