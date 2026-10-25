package com.satark.app

import com.satark.app.security.DeviceCheck
import com.satark.app.security.DeviceCheckStore
import com.satark.app.security.DevicePolicy
import com.satark.app.security.DeviceReport
import com.satark.app.security.DeviceRules
import com.satark.app.security.Finding
import com.satark.app.security.FindingKind
import com.satark.app.security.InstalledApp
import com.satark.app.security.PhoneScanner
import com.satark.app.security.Severity
import com.satark.app.ui.alerts.DeviceCheckNotifier
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

private const val SELF = "com.satark.app"
private const val PLAY = "com.android.vending"

private fun app(pkg: String, installer: String? = PLAY, system: Boolean = false, label: String = pkg) = InstalledApp(pkg, label, installer, system)

class DeviceRulesTest {
    private fun reportFor(vararg apps: InstalledApp, root: Boolean = false) = DeviceRules.evaluate(apps.toList(), SELF, root)

    @Test fun aPhoneWithOnlyStoreAppsIsClean() {
        val r = reportFor(app("com.example.notes"), app("com.example.game", "com.vivo.appstore"), app("com.example.shop", "com.heytap.market"))
        assertEquals(Severity.NONE, r.severity)
        assertTrue(r.findings.isEmpty())
    }

    @Test fun everyTrustedStoreIsAccepted() {
        for (store in DeviceRules.TRUSTED_STORES) assertEquals(Severity.NONE, reportFor(app("com.example.a", store)).severity, store)
    }

    @Test fun anAppInstalledFromAFileOrAdbIsSideloadedAndOnlyMedium() {
        for (installer in listOf(null, "com.google.android.packageinstaller", "com.android.packageinstaller", "com.android.shell", "com.example.browser")) {
            val r = reportFor(app("com.example.cracked", installer, label = "Cracked App"))
            assertEquals(Severity.MEDIUM, r.severity, "installer=$installer")
            assertEquals(FindingKind.SIDELOADED, r.findings.single().kind)
        }
    }

    @Test fun systemAppsAreNeverReportedForHowTheyWereInstalled() {
        assertEquals(Severity.NONE, reportFor(app("com.vendor.preinstalled", null, system = true)).severity)
    }

    @Test fun satarkItselfIsLeftOut() {
        assertEquals(Severity.NONE, reportFor(app(SELF, null)).severity, "a developer installs Satark from a file")
    }

    @Test fun remoteAccessAppsAreHighEvenWhenTheyCameFromPlay() {
        val r = reportFor(app("com.anydesk.anydeskandroid", PLAY, label = "AnyDesk"))
        assertEquals(Severity.HIGH, r.severity)
        assertEquals(FindingKind.REMOTE_ACCESS, r.findings.single().kind)
        assertTrue(r.findings.single().removable)
    }

    @Test fun everyListedRemoteAccessPackageIsHigh() {
        for (p in DeviceRules.REMOTE_ACCESS) assertEquals(FindingKind.REMOTE_ACCESS, reportFor(app(p)).findings.single().kind, p)
    }

    @Test fun theDetectorsRemoteAccessWatchListIsCoveredToo() {
        // contracts/watchlist.json (frozen with the detector) must never be a weaker list than this one.
        for (p in listOf("com.anydesk.anydeskandroid", "com.teamviewer.quicksupport.market", "com.google.chromeremotedesktop"))
            assertTrue(p in DeviceRules.REMOTE_ACCESS, p)
    }

    @Test fun rootAndHookToolsAreHigh() {
        assertEquals(FindingKind.ROOT_OR_HOOK_TOOL, reportFor(app("com.topjohnwu.magisk", null)).findings.single().kind)
        assertEquals(FindingKind.ROOT_OR_HOOK_TOOL, reportFor(app("org.lsposed.manager")).findings.single().kind)
    }

    @Test fun aSuBinaryIsReportedAsRootAccessAndCannotBeUninstalled() {
        val f = reportFor(root = true).findings.single()
        assertEquals(Severity.HIGH, reportFor(root = true).severity)
        assertEquals(FindingKind.ROOT_OR_HOOK_TOOL, f.kind)
        assertFalse(f.removable)
    }

    @Test fun moddedMessagingClonesAreHigh() {
        for (p in DeviceRules.MODDED_APPS) assertEquals(FindingKind.MODDED_APP, reportFor(app(p)).findings.single().kind, p)
    }

    @Test fun aWellKnownPaymentAppFromOutsideAStoreIsHigh() {
        assertEquals(Severity.NONE, reportFor(app("com.phonepe.app", PLAY)).severity)
        assertEquals(Severity.NONE, reportFor(app("com.phonepe.app", "com.vivo.appstore")).severity)
        val r = reportFor(app("com.phonepe.app", null, label = "PhonePe"))
        assertEquals(Severity.HIGH, r.severity)
        assertEquals(FindingKind.PAYMENT_APP_FROM_UNOFFICIAL_SOURCE, r.findings.single().kind)
    }

    @Test fun anAppGetsOnlyItsStrongestFinding() {
        val r = reportFor(app("com.anydesk.anydeskandroid", null))
        assertEquals(1, r.findings.size)
        assertEquals(FindingKind.REMOTE_ACCESS, r.findings.single().kind)
    }

    @Test fun theWorstFindingsComeFirst() {
        val r = reportFor(app("com.example.zebra", null, label = "Zebra"), app("com.anydesk.anydeskandroid", PLAY, label = "AnyDesk"), app("com.example.apple", null, label = "Apple"))
        assertEquals(listOf("AnyDesk", "Apple", "Zebra"), r.findings.map { it.label })
    }

    @Test fun oneSideloadedAppAmongManyStoreAppsIsStillTheOnlyFinding() {
        val apps = (1..80).map { app("com.example.app$it") } + app("com.example.mod", null, label = "Mod")
        assertEquals(listOf("Mod"), DeviceRules.evaluate(apps, SELF).findings.map { it.label })
    }

    @Test fun theFingerprintIsStableInAnyOrderAndChangesWithTheSet() {
        val a = Finding("com.a.one", "One", FindingKind.SIDELOADED)
        val b = Finding("com.b.two", "Two", FindingKind.SIDELOADED)
        assertEquals(DeviceReport(listOf(a, b)).fingerprint, DeviceReport(listOf(b, a)).fingerprint)
        assertNotEquals(DeviceReport(listOf(a, b)).fingerprint, DeviceReport(listOf(a)).fingerprint)
        assertNotEquals(DeviceReport(listOf(a)).fingerprint, DeviceReport(listOf(Finding("com.a.one", "One", FindingKind.REMOTE_ACCESS))).fingerprint)
        assertFalse(DeviceReport(listOf(a)).fingerprint.contains("One"), "no app names in what is stored")
    }

    @Test fun everyFindingHasAPlainSentence() {
        for (k in FindingKind.values()) assertTrue(Finding("com.x.y", "X", k).sentence.isNotBlank())
    }
}

class DevicePolicyTest {
    private class Mem : DeviceCheckStore {
        override var ackFingerprint: String? = null
        override var ackAtMs = 0L
        override var notifiedFingerprint: String? = null
        override var notifiedAtMs = 0L
    }

    private val medium = DeviceReport(listOf(Finding("com.example.mod", "Mod", FindingKind.SIDELOADED)))
    private val other = DeviceReport(listOf(Finding("com.example.other", "Other", FindingKind.SIDELOADED)))
    private val high = DeviceReport(listOf(Finding("com.anydesk.anydeskandroid", "AnyDesk", FindingKind.REMOTE_ACCESS)))
    private val day = DevicePolicy.NOTIFY_MS
    private val week = DevicePolicy.ACK_MS

    @Test fun aCleanPhoneIsNeverAskedAboutOrNotified() {
        val p = DevicePolicy(Mem())
        assertFalse(p.shouldAsk(DeviceReport(emptyList()), 0))
        assertFalse(p.shouldNotify(DeviceReport(emptyList()), 0))
    }

    @Test fun aSeriousFindingAsksBeforeEveryPaymentEvenAfterContinuing() {
        val p = DevicePolicy(Mem())
        repeat(3) { assertTrue(p.shouldAsk(high, it * 1000L)); p.acknowledge(high, it * 1000L) }
    }

    @Test fun theWeakestFindingAsksOnceThenStaysQuietForAWeek() {
        val p = DevicePolicy(Mem())
        assertTrue(p.shouldAsk(medium, 0))
        p.acknowledge(medium, 0)
        assertFalse(p.shouldAsk(medium, week - 1))
        assertTrue(p.shouldAsk(medium, week), "asks again after a week")
    }

    @Test fun aDifferentSetOfAppsAsksAgainAtOnce() {
        val p = DevicePolicy(Mem())
        p.acknowledge(medium, 0)
        assertTrue(p.shouldAsk(other, 1000))
    }

    @Test fun aNotificationIsSentOncePerDayForTheSameSet() {
        val p = DevicePolicy(Mem())
        assertTrue(p.shouldNotify(medium, 0))
        p.markNotified(medium, 0)
        assertFalse(p.shouldNotify(medium, day - 1))
        assertTrue(p.shouldNotify(medium, day))
        assertTrue(p.shouldNotify(other, 1000), "a different set notifies at once")
    }

    @Test fun aClockThatMovesBackDoesNotSilenceItForever() {
        val p = DevicePolicy(Mem())
        p.markNotified(medium, 10 * day)
        assertTrue(p.shouldNotify(medium, 0), "a time before the last notification is not 'recent'")
    }
}

class DeviceCheckGlueTest {
    private class FakeScanner(var apps: List<InstalledApp>, var root: Boolean = false, var boom: Boolean = false) : PhoneScanner {
        override fun installedApps(): List<InstalledApp> { if (boom) error("package manager unavailable"); return apps }
        override fun rootBinaryFound() = root
    }

    private class Mem : DeviceCheckStore {
        override var ackFingerprint: String? = null
        override var ackAtMs = 0L
        override var notifiedFingerprint: String? = null
        override var notifiedAtMs = 0L
    }

    private var clock = 1_000_000L
    private val sent = mutableListOf<DeviceReport>()
    private var shadow = false

    private fun check(scanner: PhoneScanner) = DeviceCheck(scanner, DevicePolicy(Mem()), SELF, { sent += it }, { shadow }, { clock })

    @Test fun payingWithSomethingWrongOnThePhoneNotifiesOnceAndAsks() {
        val c = check(FakeScanner(listOf(app("com.anydesk.anydeskandroid", label = "AnyDesk"))))
        val r = c.checkAndNotify()
        assertEquals(Severity.HIGH, r.severity)
        assertEquals(1, sent.size)
        assertTrue(c.shouldAsk(r))
        c.checkAndNotify()
        assertEquals(1, sent.size, "the same set is not notified again within a day")
    }

    @Test fun aCleanPhoneSendsNothingAndAsksNothing() {
        val c = check(FakeScanner(listOf(app("com.example.notes"))))
        val r = c.checkAndNotify()
        assertEquals(Severity.NONE, r.severity)
        assertTrue(sent.isEmpty())
        assertFalse(c.shouldAsk(r))
    }

    @Test fun continuingPastAWeakFindingSilencesTheDialogButNotTheCard() {
        val c = check(FakeScanner(listOf(app("com.example.mod", null))))
        val r = c.checkAndNotify()
        assertTrue(c.shouldAsk(r))
        c.acknowledge(r)
        assertFalse(c.shouldAsk(c.scan()))
        assertEquals(Severity.MEDIUM, c.scan().severity, "the card on the Pay screen still shows it")
    }

    @Test fun shadowModeShowsNothing() {
        shadow = true
        val c = check(FakeScanner(listOf(app("com.anydesk.anydeskandroid"))))
        val r = c.checkAndNotify()
        assertTrue(sent.isEmpty())
        assertFalse(c.shouldAsk(r))
        assertFalse(c.visible)
    }

    @Test fun aScannerThatFailsIsQuietNotAWarning() {
        val c = check(FakeScanner(emptyList(), boom = true))
        assertEquals(Severity.NONE, c.checkAndNotify().severity)
        assertTrue(sent.isEmpty())
    }

    @Test fun aNotifierThatFailsDoesNotStopThePayment() {
        val c = DeviceCheck(FakeScanner(listOf(app("com.anydesk.anydeskandroid"))), DevicePolicy(Mem()), SELF, { error("no notification permission") }, { false }, { clock })
        assertEquals(Severity.HIGH, c.checkAndNotify().severity)
    }
}

class DeviceCheckNotifierTextTest {
    @Test fun aSeriousFindingNamesTheWorstAppAndHowManyMore() {
        val r = DeviceRules.evaluate(listOf(app("com.anydesk.anydeskandroid", label = "AnyDesk"), app("com.example.a", null, label = "A"), app("com.example.b", null, label = "B")), SELF)
        assertEquals("AnyDesk can let someone see or control your phone and 2 more. Open Satark to review before you pay.", DeviceCheckNotifier.text(r))
    }

    @Test fun aWeakFindingCountsTheApps() {
        assertEquals("1 app was installed from outside an official store. Open Satark to review.",
            DeviceCheckNotifier.text(DeviceRules.evaluate(listOf(app("com.example.a", null)), SELF)))
        assertEquals("3 apps were installed from outside an official store. Open Satark to review.",
            DeviceCheckNotifier.text(DeviceRules.evaluate(listOf(app("com.example.a", null), app("com.example.b", null), app("com.example.c", null)), SELF)))
    }

    @Test fun theNotificationNeverContainsAnAmountOrAPayee() {
        val r = DeviceRules.evaluate(listOf(app("com.example.a", null, label = "A")), SELF)
        assertFalse(DeviceCheckNotifier.text(r).contains("₹"))
    }
}
