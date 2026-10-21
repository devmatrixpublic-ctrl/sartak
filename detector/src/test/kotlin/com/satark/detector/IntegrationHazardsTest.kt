package com.satark.detector

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Hazards found when reviewing how the app (M1) drives the detector over a long-lived process. */
class IntegrationHazardsTest {
    private val model = ModelConfig.loadBundled()
    private fun detector(band: String = "36-59") = Detector(model, band, Baseline.fixed(500.0, 200.0))
    private val hours = 3_600_000L

    /** onTick is called every 30 s by the app; a long session must raise ONE alarm, not one per tick (alarm/push spam). */
    @Test
    fun longSessionAlarmIsRaisedOncePerVideoSession() {
        val d = detector()
        d.onEvent(Event(0, EventType.VIDEO_SESSION_START, callerKnown = false, appPackage = "com.whatsapp"))
        assertEquals(Level.NONE, d.onTick(2 * hours - 1).level)
        val first = d.onTick(2 * hours + 30_000)
        assertEquals(Level.HARD, first.level)
        assertEquals(2 * hours, first.alarmTMs)
        repeat(5) { i -> assertEquals(Level.NONE, d.onTick(2 * hours + 60_000 + i * 30_000L).level, "tick $i repeated the alarm") }
        // a NEW unknown video session may alarm again
        d.onEvent(Event(5 * hours, EventType.VIDEO_SESSION_END, appPackage = "com.whatsapp"))
        d.onEvent(Event(6 * hours, EventType.VIDEO_SESSION_START, callerKnown = false, appPackage = "com.whatsapp"))
        assertEquals(Level.HARD, d.onTick(8 * hours + 1).level)
    }

    /** A user who taps "pay" again within the dedup window must get the same hold, never a NONE that the server would ALLOW. */
    @Test
    fun retryOfAHeldPaymentWithinTheDedupWindowIsStillHeld() {
        val d = detector()
        d.onEvent(Event(0, EventType.CALL_START, callerKnown = false))
        d.onEvent(Event(100_000, EventType.NEW_PAYEE, payeeId = "acct1"))
        val pay = Event(200_000, EventType.PAYMENT_ATTEMPT, payeeId = "acct1", payeeIsNew = true, amountInr = 160_000.0, paymentType = PaymentType.P2P)
        val first = d.onEvent(pay)
        assertEquals(Level.HARD, first.level)
        val retry = d.onEvent(pay.copy(tMs = 201_500)) // 1.5 s later, identical
        assertEquals(Level.HARD, retry.level, "retry inside the dedup window was waved through")
        assertEquals(first.reasons, retry.reasons)
        // a retry that is NOT a duplicate (other amount) is evaluated on its own merits
        assertTrue(d.onEvent(pay.copy(tMs = 202_000, amountInr = 150_000.0)).level == Level.HARD)
    }

    @Test
    fun duplicateNonPaymentEventsStillDoNothing() {
        val d = detector()
        val e = Event(0, EventType.CALL_START, callerKnown = false)
        assertEquals(Level.NONE, d.onEvent(e).level)
        assertEquals(Level.NONE, d.onEvent(e.copy(tMs = 1000)).level)
    }
}
