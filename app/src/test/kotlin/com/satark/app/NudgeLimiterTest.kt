package com.satark.app

import com.satark.app.events.NudgeLimiter
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class NudgeLimiterTest {
    private val day = 24 * 3600_000L
    private class Mem(override var times: List<Long> = emptyList()) : NudgeLimiter.Store

    @Test fun oneNudgeAMonthThenQuietUntilTheWindowPasses() {
        var t = 1_000_000L
        val l = NudgeLimiter(Mem(), { t })
        assertTrue(l.tryAcquire())
        t += 10 * day
        assertFalse(l.tryAcquire(), "second nudge inside 30 days is held back")
        t += 21 * day
        assertTrue(l.tryAcquire(), "after 30 days the budget is back")
    }

    @Test fun theCountSurvivesARestart() {
        val store = Mem()
        var t = 5_000_000L
        assertTrue(NudgeLimiter(store, { t }).tryAcquire())
        t += day
        assertFalse(NudgeLimiter(store, { t }).tryAcquire(), "a new limiter on the same store still remembers")
    }

    @Test fun aHigherLimitIsHonoured() {
        var t = 1L
        val l = NudgeLimiter(Mem(), { t }, max = 2)
        assertTrue(l.tryAcquire()); assertTrue(l.tryAcquire()); assertFalse(l.tryAcquire())
        assertEquals(2, Mem(listOf(1L, 2L)).times.size)
    }
}
