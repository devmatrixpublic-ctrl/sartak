package com.satark.app

import com.satark.app.events.TextBurst
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class TextBurstTest {
    private class Mem(override var times: List<Long> = emptyList()) : TextBurst.Store
    private val min = 60_000L

    @Test fun thirdStrangerTextInTenMinutesWarns() {
        val b = TextBurst(Mem())
        assertFalse(b.record(0))
        assertFalse(b.record(2 * min))
        assertTrue(b.record(5 * min))
    }

    @Test fun slowTextsNeverWarn() {
        val b = TextBurst(Mem())
        assertFalse(b.record(0)); assertFalse(b.record(11 * min)); assertFalse(b.record(22 * min)); assertFalse(b.record(33 * min))
    }

    @Test fun afterAWarningTheCountStartsAgain() {
        val b = TextBurst(Mem())
        b.record(0); b.record(min)
        assertTrue(b.record(2 * min))
        assertFalse(b.record(3 * min), "the next text starts a new count")
        assertFalse(b.record(4 * min))
        assertTrue(b.record(5 * min))
    }

    @Test fun theCountSurvivesARestart() {
        val store = Mem()
        TextBurst(store).record(0); TextBurst(store).record(min)
        assertTrue(TextBurst(store).record(2 * min), "a new object on the same store still remembers")
    }
}
