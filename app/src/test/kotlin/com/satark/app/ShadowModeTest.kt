package com.satark.app

import com.satark.detector.Level
import com.satark.detector.showsScreen
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ShadowModeTest {
    @Test fun logAndNoneNeverShowAScreen() {
        assertFalse(Level.NONE.showsScreen)
        assertFalse(Level.LOG.showsScreen)
    }

    @Test fun everyOtherLevelStillInterrupts() =
        listOf(Level.NUDGE, Level.HARD, Level.TRUSTED_CONTACT).forEach { assertTrue(it.showsScreen, it.name) }

    @Test fun logSitsBetweenNoneAndNudgeAndNamesAreStable() =
        assertEquals(listOf("NONE", "LOG", "NUDGE", "HARD", "TRUSTED_CONTACT"), Level.values().map { it.name })
}
