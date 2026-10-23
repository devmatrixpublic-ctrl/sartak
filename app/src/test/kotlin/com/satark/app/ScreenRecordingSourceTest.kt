package com.satark.app

import com.satark.app.signals.ScreenRecordingSource
import com.satark.app.signals.SignalStatus
import com.satark.app.signals.SourceName
import com.satark.app.signals.SourceState
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ScreenRecordingSourceTest {
    private val direct = java.util.concurrent.Executor { it.run() }

    @Test fun olderPhonesReportUnavailableWithoutCrashing() {
        for (sdk in listOf(21, 28, 33, 34)) {
            val s = ScreenRecordingSource(sdk)
            assertEquals(SourceState.UNSUPPORTED, s.state(), "sdk $sdk")
            s.register(null, direct)       // no WindowManager and an old SDK: nothing happens
            s.unregister(null)
            assertNull(s.lastVisible)
        }
    }

    @Test fun android15AndUpIsAvailable() {
        assertEquals(SourceState.AVAILABLE, ScreenRecordingSource(35).state())
        assertEquals(SourceState.AVAILABLE, ScreenRecordingSource(36).state())
        ScreenRecordingSource(35).register(null, direct) // still safe with no window to listen on
    }

    @Test fun itNeverChangesWhetherProtectionIsFullyAvailable() {
        val all = SourceName.entries.associateWith { SourceState.AVAILABLE }
        assertTrue(SignalStatus(all).allAvailable)
        assertTrue(SignalStatus(all, SourceState.UNSUPPORTED).allAvailable, "an old phone must not look like missing protection")
    }
}
