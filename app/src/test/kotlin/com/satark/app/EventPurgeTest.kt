package com.satark.app

import com.satark.app.events.EventPurgeWorker
import kotlin.test.Test
import kotlin.test.assertEquals

class EventPurgeTest {
    private val day = 24 * 3600_000L

    @Test fun cutoffIsExactlySevenDaysBack() = assertEquals(100 * day - 7 * day, EventPurgeWorker.cutoff(100 * day))

    @Test fun purgeIsLooserThanTheDispatcherButStillShort() {
        // The dispatcher keeps 24 h for session restore; the worker is only a backstop and must never be tighter.
        assert(EventPurgeWorker.RETENTION_MS >= com.satark.app.events.EventDispatcher.EVENT_RETENTION_MS)
        assert(EventPurgeWorker.RETENTION_MS <= 7 * day)
    }
}
