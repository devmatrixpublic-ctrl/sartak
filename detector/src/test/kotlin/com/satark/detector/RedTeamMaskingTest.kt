package com.satark.detector

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Red team: what if an attacker (or a phone maker) hides a signal? Replays the golden sessions with one signal source
 * removed and compares recall on scam sessions and false alarms on legitimate ones. Prints a table; the unmasked row
 * must equal the frozen reference decisions, and no mask may crash the detector.
 */
class RedTeamMaskingTest {
    private val model = ModelConfig.loadBundled()
    private val sessions = loadSessions("golden/golden_events.csv")
    private val users = loadUsers("golden/golden_users.csv")
    private val labels = Csv.read("golden/golden_sessions.csv").associate { it.getValue("session_id") to it }

    private val masks: Map<String, (Event) -> Boolean> = linkedMapOf(
        "none (baseline)" to { _ -> true },
        "no call state" to { e -> e.type != EventType.CALL_START && e.type != EventType.CALL_END },
        "no video state" to { e -> e.type != EventType.VIDEO_SESSION_START && e.type != EventType.VIDEO_SESSION_END },
        "no install events" to { e -> e.type != EventType.APP_INSTALL },
        "no app foreground" to { e -> e.type != EventType.APP_FOREGROUND },
        "no call, video or installs" to { e -> e.type in setOf(EventType.NEW_PAYEE, EventType.PAYMENT_ATTEMPT, EventType.APP_FOREGROUND) },
    )

    private class Row(val name: String, val recall: Double, val falseAlarm: Double, val scams: Int, val legit: Int)

    private fun run(keep: (Event) -> Boolean): Row {
        var scamHit = 0; var scams = 0; var legitHit = 0; var legit = 0
        for ((sid, ue) in sessions) {
            val (uid, events) = ue
            val res = runSession(model, users[uid], events.filter(keep))
            when (labels.getValue(sid).getValue("label")) {
                "scam" -> { scams++; if (res.alarm) scamHit++ }
                else -> { legit++; if (res.alarm) legitHit++ }
            }
        }
        return Row("", scamHit.toDouble() / scams, legitHit.toDouble() / legit, scams, legit)
    }

    @Test
    fun maskingASignalNeverCrashesAndTheBaselineMatchesTheReference() {
        val rows = masks.map { (name, keep) -> name to run(keep) }
        println("| mask | scam recall | false alarms on legit |\n|---|---|---|")
        rows.forEach { (n, r) -> println("| $n | %.1f%% (of ${r.scams}) | %.2f%% (of ${r.legit}) |".format(r.recall * 100, r.falseAlarm * 100)) }
        val base = rows.first().second
        val refScamHits = labels.values.count { it.getValue("label") == "scam" && it.getValue("alarm") == "True" }
        val refLegitHits = labels.values.count { it.getValue("label") != "scam" && it.getValue("alarm") == "True" }
        assertEquals(refScamHits.toDouble() / base.scams, base.recall, 1e-12)
        assertEquals(refLegitHits.toDouble() / base.legit, base.falseAlarm, 1e-12)
        assertTrue(rows.all { it.second.recall in 0.0..1.0 })
    }
}
