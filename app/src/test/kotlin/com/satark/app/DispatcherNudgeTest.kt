package com.satark.app

import com.satark.app.events.AlertStat
import com.satark.app.events.CompletedPayment
import com.satark.app.events.DecisionRow
import com.satark.app.events.EventDispatcher
import com.satark.app.events.EventRow
import com.satark.app.events.KnownPayee
import com.satark.app.events.QueuedCall
import com.satark.app.events.SatarkDao
import com.satark.app.signals.RawSignal
import com.satark.detector.Level
import com.satark.detector.ModelConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** The real dispatcher with an in-memory store: what a payment started during an unknown call earns, end to end. */
class DispatcherNudgeTest {
    private class FakeDao : SatarkDao {
        override suspend fun insertEvent(e: EventRow) = 1L
        override suspend fun markDispatched(id: Long) {}
        override suspend fun pruneEvents(before: Long) {}
        override suspend fun pruneDecisions(before: Long) {}
        override suspend fun eventsSince(since: Long): List<EventRow> = emptyList()
        override suspend fun insertDecision(d: DecisionRow) {}
        override suspend fun recentDecisions(n: Int): List<DecisionRow> = emptyList()
        override suspend fun eventCount() = 0
        override suspend fun addPayee(p: KnownPayee) {}
        override suspend fun payeeCount(hash: String) = 0
        override suspend fun addCompleted(p: CompletedPayment) {}
        override suspend fun lastAmounts(n: Int): List<Double> = emptyList()
        override suspend fun alertStat(key: String): AlertStat? = null
        override suspend fun putAlertStat(s: AlertStat) {}
        override suspend fun heldCount() = 0
        override suspend fun alertsShown() = 0
        override suspend fun alertsMerged() = 0
        override suspend fun enqueue(q: QueuedCall) {}
        override suspend fun queued(): List<QueuedCall> = emptyList()
        override suspend fun dequeue(id: Long) {}
        override suspend fun bump(id: Long) {}
    }

    private fun payment(t: Long, payee: String, amount: Double) =
        listOf(RawSignal.PayeeAdded(t, payee), RawSignal.PaymentAttempt(t, payee, amount, true, true, "manual"))

    private fun withDispatcher(block: suspend (EventDispatcher) -> Unit) = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            val d = EventDispatcher(FakeDao(), ModelConfig.loadBundled(), null, scope)
            d.start()
            delay(400) // the session is restored (nothing to restore) and the dispatcher is ready
            block(d)
        } finally { scope.cancel() }
    }

    @Test fun aPaymentWithNoCallIsQuiet() = withDispatcher { d ->
        val r = d.submitAndDecideFull(payment(System.currentTimeMillis(), "p1", 5_000.0), "manual")
        assertEquals(Level.NONE, r.decision.level)
        assertNull(r.nudge)
    }

    @Test fun duringAnUnknownCallAnAboveUsualPaymentToANewPayeeEarnsANudgeNotAStop() = withDispatcher { d ->
        d.submit(RawSignal.CallStarted(System.currentTimeMillis() - 4_000, callerKnown = false))
        delay(2_600) // the call event is released to the detector
        val r = d.submitAndDecideFull(payment(System.currentTimeMillis(), "p2", 5_000.0), "manual")
        assertEquals(Level.NONE, r.decision.level, "allowed, not held")
        val nudge = assertNotNull(r.nudge, "the person is asked to take a moment before it goes on")
        assertEquals(listOf("F_UNK_CALL_ACTIVE", "F_NEW_PAYEE", "F_LOG_AMT_RATIO"), nudge.reasons)
    }

    @Test fun aLargePaymentDuringTheCallIsStoppedAndGetsNoNudge() = withDispatcher { d ->
        d.submit(RawSignal.CallStarted(System.currentTimeMillis() - 4_000, callerKnown = false))
        delay(2_600)
        val r = d.submitAndDecideFull(payment(System.currentTimeMillis(), "p3", 30_000.0), "manual")
        assertTrue(r.decision.level == Level.HARD, "stopped")
        assertNull(r.nudge)
    }

    @Test fun aSmallPaymentDuringTheCallNeedsNoNudge() = withDispatcher { d ->
        d.submit(RawSignal.CallStarted(System.currentTimeMillis() - 4_000, callerKnown = false))
        delay(2_600)
        val r = d.submitAndDecideFull(payment(System.currentTimeMillis(), "p4", 200.0), "manual")
        assertEquals(Level.NONE, r.decision.level)
        assertNull(r.nudge, "under twice the usual amount")
    }
}
