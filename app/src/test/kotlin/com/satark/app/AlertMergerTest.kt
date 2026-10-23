package com.satark.app

import com.satark.app.events.AlertStat
import com.satark.app.ui.alerts.AlertMerger
import com.satark.app.ui.alerts.ReadAloud
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AlertMergerTest {
    private val min = 60_000L
    private class Fake : AlertMerger.Store {
        val rows = mutableMapOf<String, AlertStat>()
        override suspend fun get(key: String) = rows[key]
        override suspend fun put(stat: AlertStat) { rows[stat.alertKey] = stat }
    }

    private fun merger(f: Fake) = AlertMerger(f)

    @Test fun firstAlertIsShownAndCounted() = runBlocking {
        val f = Fake()
        assertTrue(merger(f).admit("k", 1000))
        assertEquals(AlertStat("k", 1, 0, 1000), f.rows["k"])
    }

    @Test fun repeatWithinAnHourIsMergedAndCounted() = runBlocking {
        val f = Fake(); val m = merger(f)
        m.admit("k", 0)
        assertFalse(m.admit("k", 30 * min))
        assertFalse(m.admit("k", 59 * min))
        assertEquals(AlertStat("k", 1, 2, 0), f.rows["k"])
    }

    @Test fun afterAnHourTheAlertIsShownAgain() = runBlocking {
        val f = Fake(); val m = merger(f)
        m.admit("k", 0); m.admit("k", 10 * min)
        assertTrue(m.admit("k", 60 * min))
        assertEquals(AlertStat("k", 2, 1, 60 * min), f.rows["k"])
    }

    @Test fun differentKindsAreIndependent() = runBlocking {
        val m = merger(Fake())
        assertTrue(m.admit("a", 0)); assertTrue(m.admit("b", 1))
    }

    @Test fun aClockMovedBackNeverHidesAnAlert() = runBlocking {
        val m = merger(Fake())
        m.admit("k", 10 * 60 * min)
        assertTrue(m.admit("k", 0))
    }

    @Test fun keyIgnoresReasonOrder() =
        assertEquals(AlertMerger.keyOf("payment_score", listOf("B", "A")), AlertMerger.keyOf("payment_score", listOf("A", "B")))

    @Test fun readAloudJoinsTitleBodyAndReasonsWithPauses() =
        assertEquals("Stop. Hang up. You are paying a new person.", ReadAloud.spokenText("Stop.", "Hang up", listOf("You are paying a new person.")))

    @Test fun readAloudSkipsEmptyParts() = assertEquals("Stop.", ReadAloud.spokenText("Stop", " ", emptyList()))
}
