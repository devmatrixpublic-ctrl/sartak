package com.satark.app

import com.satark.app.signals.Evidence
import com.satark.app.signals.RawSignal
import com.satark.detector.InstallSource
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class EvidenceTest {
    private var now = 10_000_000L
    private val e = Evidence({ now }) { if (it == "com.anydesk.anydeskandroid") "AnyDesk" else null }

    @Test fun nothingSeenMeansNoLines() = assertTrue(e.lines().isEmpty())

    @Test fun aStrangersTextAndAnUnsafeAppAreListedWithHowLongAgo() {
        e.record(RawSignal.UnknownMessage(now - 4 * 60_000))
        e.record(RawSignal.AppInstalled(now - 30_000, "com.anydesk.anydeskandroid", InstallSource.SIDELOAD))
        assertEquals(
            listOf("Someone not in your contacts texted you 4 min ago", "\"AnyDesk\" was installed from outside Google Play just now"),
            e.lines(),
        )
    }

    @Test fun anUnknownCallIsListedButAKnownOneIsNot() {
        e.record(RawSignal.CallStarted(now - 5 * 60_000, callerKnown = true))
        assertTrue(e.lines().isEmpty())
        e.record(RawSignal.CallStarted(now - 60_000, callerKnown = false))
        assertEquals(listOf("Someone not in your contacts called you 1 min ago"), e.lines())
    }

    @Test fun theNewestUnsafeAppCanBeOfferedForRemoval() {
        assertEquals(null, e.lastRisky())
        e.record(RawSignal.AppInstalled(now - 60_000, "com.example.unknown", InstallSource.SIDELOAD))
        e.record(RawSignal.AppInstalled(now - 10_000, "com.anydesk.anydeskandroid", InstallSource.SIDELOAD))
        assertEquals("AnyDesk" to "com.anydesk.anydeskandroid", e.lastRisky())
        now += Evidence.WINDOW_MS + 5_000
        assertEquals(null, e.lastRisky())
    }

    @Test fun playStoreInstallsAreNotEvidence() {
        e.record(RawSignal.AppInstalled(now - 1_000, "com.example.game", InstallSource.PLAY_STORE))
        assertTrue(e.lines().isEmpty())
    }

    @Test fun unknownAppFallsBackToItsPackageNameAndOldEvidenceExpires() {
        e.record(RawSignal.AppInstalled(now - 1_000, "com.example.unknown", InstallSource.SIDELOAD))
        assertEquals(listOf("\"com.example.unknown\" was installed from outside Google Play just now"), e.lines())
        now += Evidence.WINDOW_MS + 5_000
        assertTrue(e.lines().isEmpty())
    }
}
