package com.satark.app

import com.satark.app.guard.DownloadGuard
import com.satark.app.guard.DownloadGuardNotifier
import com.satark.app.guard.GuardEvent
import com.satark.app.guard.GuardRecord
import com.satark.app.guard.GuardStore
import java.io.File
import java.nio.file.Files
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class DownloadGuardTest {
    private class Mem : GuardStore {
        override var records: List<GuardRecord> = emptyList()
        override var allowed: Set<String> = emptySet()
    }

    private val root: File = Files.createTempDirectory("satark-guard").toFile()
    private val downloads = File(root, "Download").apply { mkdirs() }
    private val whatsapp = File(root, "WhatsApp Documents").apply { mkdirs() }
    private val quarantine = File(root, "quarantine")
    private val store = Mem()
    private val events = mutableListOf<GuardEvent>()
    private var on = true
    private var clock = 1_000_000L

    private val guard = DownloadGuard({ listOf(downloads, whatsapp) }, quarantine, store, { on }, { events += it }, { clock })

    @AfterTest fun cleanUp() { root.deleteRecursively() }

    private fun put(dir: File, name: String, text: String = "x") = File(dir, name).apply { writeText(text) }

    @Test fun aScamNamedApkIsMovedOutOfReachAndWarnedAbout() {
        val f = put(downloads, "RTO Challan.apk", "payload")
        guard.handle(downloads, f.name)
        assertFalse(f.exists(), "it can no longer be opened or installed from Downloads")
        val e = events.single() as GuardEvent.Quarantined
        assertEquals("RTO Challan.apk", e.record.name)
        assertEquals("traffic fine (RTO challan)", e.record.category)
        assertTrue(e.record.held)
        assertEquals("payload", File(File(quarantine, e.record.id), "RTO Challan.apk").readText(), "kept intact, not deleted")
        assertEquals(1, guard.records.size)
    }

    @Test fun aDocumentWithAScamLikeNameIsWarnedAboutButLeftWhereItIs() {
        val f = put(downloads, "Electricity Bill.pdf")
        guard.handle(downloads, f.name)
        assertTrue(f.exists(), "a genuine bill must not disappear")
        val e = events.single() as GuardEvent.Warned
        assertFalse(e.record.held)
    }

    @Test fun anOrdinaryFileIsLeftAloneWithNoWarning() {
        for (n in listOf("holiday photo.jpg", "notes.apk", "invoice_2024.pdf")) { val f = put(downloads, n); guard.handle(downloads, n); assertTrue(f.exists(), n) }
        assertTrue(events.isEmpty())
        assertTrue(guard.records.isEmpty())
    }

    @Test fun aDownloadInProgressIsDeletedSoItCannotFinish() {
        val f = put(downloads, ".pending-1699999999-SBI KYC Update.apk")
        guard.handle(downloads, f.name)
        assertFalse(f.exists())
        assertTrue(events.single() is GuardEvent.Stopped)
        val g = put(downloads, "ICICI KYC.apk.crdownload")
        guard.handle(downloads, g.name)
        assertFalse(g.exists())
        assertEquals(2, events.size)
    }

    @Test fun oneDownloadThatMakesSeveralEventsIsHandledOnce() {
        val f = put(downloads, "SBI KYC Update.apk")
        guard.handle(downloads, f.name)
        put(downloads, "SBI KYC Update.apk") // the browser writes it again under the same name
        guard.handle(downloads, "SBI KYC Update.apk")
        assertEquals(1, events.size)
    }

    @Test fun theSameNameMuchLaterIsHandledAgain() {
        guard.handle(downloads, put(downloads, "SBI KYC Update.apk").name)
        clock += DownloadGuard.DEDUPE_MS + 1
        guard.handle(downloads, put(downloads, "SBI KYC Update.apk").name)
        assertEquals(2, events.size)
    }

    @Test fun nothingHappensWhileTheGuardIsOff() {
        on = false
        val f = put(downloads, "RTO Challan.apk")
        guard.handle(downloads, f.name)
        guard.sweep()
        assertTrue(f.exists())
        assertTrue(events.isEmpty())
    }

    @Test fun aSweepFindsFilesThatArrivedWhileNotWatching() {
        put(downloads, "Aadhaar Update.apk"); put(whatsapp, "PM Kisan Yojana.apk"); put(downloads, "family photo.jpg")
        guard.sweep()
        assertEquals(2, events.size)
        assertEquals(2, guard.records.count { it.held })
        assertTrue(File(downloads, "family photo.jpg").exists())
    }

    @Test fun aFolderNamedLikeAScamIsNotTouched() {
        File(downloads, "RTO Challan.apk").mkdirs()
        guard.handle(downloads, "RTO Challan.apk")
        assertTrue(events.isEmpty())
        assertTrue(File(downloads, "RTO Challan.apk").isDirectory)
    }

    @Test fun aHeldFileCanBeRestoredAndIsThenLeftAlone() {
        val f = put(downloads, "Instant Loan.apk", "data")
        guard.handle(downloads, f.name)
        val id = guard.records.single().id
        assertTrue(guard.restore(id))
        assertEquals("data", File(downloads, "Instant Loan.apk").readText())
        assertTrue(guard.records.isEmpty())
        clock += DownloadGuard.DEDUPE_MS + 1
        guard.sweep()
        assertEquals(1, events.size, "a restored file is not quarantined a second time")
        assertTrue(File(downloads, "Instant Loan.apk").exists())
    }

    @Test fun restoringNeverOverwritesAFileOfTheSameName() {
        guard.handle(downloads, put(downloads, "Instant Loan.apk", "first").name)
        put(downloads, "Instant Loan.apk", "second")
        val id = guard.records.single().id
        assertTrue(guard.restore(id))
        assertEquals("second", File(downloads, "Instant Loan.apk").readText())
        assertEquals("first", File(downloads, "Instant Loan (1).apk").readText())
    }

    @Test fun aHeldFileCanBeDeletedForGood() {
        guard.handle(downloads, put(downloads, "Lucky Draw.apk").name)
        val id = guard.records.single().id
        assertTrue(guard.delete(id))
        assertFalse(File(quarantine, id).exists())
        assertTrue(guard.records.isEmpty())
    }

    @Test fun restoringSomethingThatIsNotHeldDoesNothing() {
        guard.handle(downloads, put(downloads, "Electricity Bill.pdf").name)
        assertFalse(guard.restore(guard.records.single().id), "a warning has no held copy")
        assertFalse(guard.restore("no-such-id"))
    }

    @Test fun theRecordListIsCapped() {
        repeat(DownloadGuard.MAX_RECORDS + 10) { i -> clock += DownloadGuard.DEDUPE_MS + 1; guard.handle(downloads, put(downloads, "Lucky Draw $i.apk").name) }
        assertEquals(DownloadGuard.MAX_RECORDS, guard.records.size)
    }

    @Test fun theWarningsAreWrittenForThePersonWhoDownloadedTheFile() {
        guard.handle(downloads, put(downloads, "RTO Challan.apk").name)
        guard.handle(downloads, put(downloads, "Electricity Bill.pdf").name)
        guard.handle(downloads, put(downloads, ".pending-1-ICICI KYC.apk").name)
        for (e in events) {
            val (title, text) = DownloadGuardNotifier.words(e)
            assertTrue(title.startsWith("Scam warning"), title)
            assertTrue(e.record.name in text, text)
            assertFalse(text.contains("₹"), "a file warning carries no payment detail")
        }
        assertTrue(DownloadGuardNotifier.words(events[0]).second.contains("Do not install it"))
        assertTrue(DownloadGuardNotifier.words(events[1]).second.contains("unless you were expecting it"))
    }

    @Test fun aNotifierThatFailsDoesNotLoseTheRecord() {
        val g = DownloadGuard({ listOf(downloads) }, quarantine, store, { true }, { error("no notification permission") }, { clock })
        g.handle(downloads, put(downloads, "RTO Challan.apk").name)
        assertEquals(1, g.records.size)
        assertFalse(File(downloads, "RTO Challan.apk").exists())
    }
}
