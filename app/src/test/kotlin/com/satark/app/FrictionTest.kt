package com.satark.app

import com.satark.app.ui.alerts.Friction
import com.satark.app.ui.alerts.PaymentPause
import org.json.JSONObject
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** The app-side friction ladder (ui/alerts/Friction.kt): playbook, purpose question, payment pause. */
class FrictionTest {
    private fun contractCodes(): List<String> {
        val f = listOf(File("../contracts/reason_codes.json"), File("contracts/reason_codes.json")).first { it.exists() }
        val arr = JSONObject(f.readText()).getJSONArray("codes")
        return (0 until arr.length()).map { arr.getJSONObject(it).getString("code") }
    }

    @Test fun everyReasonCodeAndNoneGetsAPlaybook() {
        for (c in contractCodes() + listOf("SOMETHING_NEW")) {
            val p = Friction.playbook(listOf(c))
            assertTrue(p.title.isNotBlank() && p.text.isNotBlank(), c)
        }
        assertTrue(Friction.playbook(emptyList()).text.isNotBlank())
    }

    @Test fun mostSpecificScamWins() {
        assertTrue(Friction.playbook(listOf("F_NEW_PAYEE", "F_UNK_VIDEO_ACTIVE")).title.contains("Digital arrest"))
        assertTrue(Friction.playbook(listOf("RULE_LONG_SESSION")).title.contains("Digital arrest"))
        assertTrue(Friction.playbook(listOf("F_UNK_CALL_ACTIVE", "F_WATCHLIST_APP")).title.contains("screen"))
        assertTrue(Friction.playbook(listOf("RULE_SIDELOAD_DURING_CALL")).title.contains("link or file"))
        assertTrue(Friction.playbook(listOf("f_unk_call_active")).title.contains("don't know"))
        assertTrue(Friction.playbook(listOf("F_NEW_PAYEE", "F_LOG_AMT_RATIO")).title.contains("someone new"))
    }

    @Test fun everyPurposeHasAReply() {
        assertEquals(6, Friction.Purpose.entries.size)
        Friction.Purpose.entries.forEach { assertTrue(it.label.isNotBlank() && it.reply.isNotBlank(), it.name) }
    }

    @Test fun phraseIgnoresCaseAndPunctuationButNotWords() {
        assertTrue(Friction.phraseMatches(Friction.PHRASE))
        assertTrue(Friction.phraseMatches("  no one is telling me to make this payment. "))
        assertTrue(Friction.phraseMatches("No one, is telling me to make this payment!"))
        assertFalse(Friction.phraseMatches("Someone is telling me to make this payment"))
        assertFalse(Friction.phraseMatches("No one is telling me"))
        assertFalse(Friction.phraseMatches(""))
    }

    @Test fun clockShowsMinutesAndSeconds() {
        assertEquals("15:00", Friction.clock(Friction.PAUSE_MS))
        assertEquals("0:01", Friction.clock(1))
        assertEquals("0:00", Friction.clock(0))
        assertEquals(0, Friction.remainingMs(1_000, 5_000))
        assertEquals(Friction.HOLD_MS, Friction.remainingMs(10 * Friction.PAUSE_MS, 0))
    }

    private class MemStore : PaymentPause.Store {
        override var untilMs = 0L
        override var phraseOwed = false
    }

    @Test fun pauseWaitsThenAsksForThePhraseOnce() {
        var now = 1_000_000L
        val store = MemStore()
        val p = PaymentPause(store) { now }
        assertEquals(PaymentPause.State.Clear, p.state.value)

        p.start()
        assertEquals(PaymentPause.State.Waiting(now + Friction.PAUSE_MS), p.state.value)
        assertFalse(p.confirm(Friction.PHRASE), "the phrase cannot cut the wait short")

        now += Friction.PAUSE_MS
        p.refresh()
        assertEquals(PaymentPause.State.PhraseOwed, p.state.value)
        assertFalse(p.confirm("yes"))
        assertEquals(PaymentPause.State.PhraseOwed, p.state.value)
        assertTrue(p.confirm(Friction.PHRASE))
        assertEquals(PaymentPause.State.Clear, p.state.value)

        // Survives a restart: a new instance reads the same store.
        p.start()
        assertEquals(PaymentPause.State.Waiting(now + Friction.PAUSE_MS), PaymentPause(store) { now }.state.value)
    }

    @Test fun clockMovedBackCannotStretchThePause() {
        var now = 10 * Friction.PAUSE_MS
        val store = MemStore()
        val p = PaymentPause(store) { now }
        p.start()
        now = 0 // clock set back by hours
        p.refresh()
        assertEquals(PaymentPause.State.Waiting(Friction.HOLD_MS), p.state.value)
    }

    @Test fun holdThirtyMinutesLastsThirty() {
        val now = 1_000L
        val p = PaymentPause(MemStore()) { now }
        p.start(Friction.HOLD_MS)
        assertEquals(PaymentPause.State.Waiting(now + Friction.HOLD_MS), p.state.value)
    }

    @Test fun debugClearEndsEverything() {
        val store = MemStore()
        val p = PaymentPause(store) { 5L }
        p.start()
        p.clearForTesting()
        assertEquals(PaymentPause.State.Clear, p.state.value)
        assertFalse(store.phraseOwed)
    }
}
