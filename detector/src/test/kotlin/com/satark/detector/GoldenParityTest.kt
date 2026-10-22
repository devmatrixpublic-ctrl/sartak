package com.satark.detector

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Kotlin port vs the Python reference on hundreds of simulated sessions: features and scores to 1e-9, decisions exactly. */
class GoldenParityTest {
    private val model = ModelConfig.loadBundled()
    private val sessions = loadSessions("golden/golden_events.csv")
    private val users = loadUsers("golden/golden_users.csv")
    private val expected = Csv.read("golden/golden_sessions.csv").associateBy { it.getValue("session_id") }
    private val payments = Csv.read("golden/golden_payments.csv").groupBy { it.getValue("session_id") }

    @Test
    fun sessionDecisionsMatchReference() {
        assertTrue(sessions.size > 700, "golden set unexpectedly small: ${sessions.size}")
        val bad = ArrayList<String>()
        for ((sid, ue) in sessions) {
            val (uid, events) = ue
            val r = runSession(model, users.getValue(uid), events)
            val x = expected.getValue(sid)
            val wantAlarm = x.getValue("alarm") == "True"
            val wantT = x.getValue("alarm_t").ifEmpty { null }?.toDouble()?.let { (it * 1000).toLong() }
            if (r.alarm != wantAlarm || r.mechanism != x.getValue("mechanism") || r.alarmTMs != wantT ||
                r.interdicted != (x.getValue("interdicted") == "True")
            ) bad += "$sid alarm=${r.alarm}/$wantAlarm mech=${r.mechanism}/${x.getValue("mechanism")} t=${r.alarmTMs}/$wantT"
        }
        assertTrue(bad.isEmpty(), "${bad.size}/${sessions.size} sessions differ:\n" + bad.take(20).joinToString("\n"))
    }

    @Test
    fun paymentFeaturesAndScoresMatchTo1e9() {
        var n = 0
        var worst = 0.0
        val bad = ArrayList<String>()
        for ((sid, ue) in sessions) {
            val (uid, events) = ue
            val r = runSession(model, users.getValue(uid), events)
            val want = payments[sid].orEmpty()
            if (r.traces.size != want.size) { bad += "$sid: ${r.traces.size} payments vs ${want.size}"; continue }
            for ((i, w) in want.withIndex()) {
                val t = r.traces[i]
                if (t.tMs != w.getValue("t").toDouble().toLong() * 1000) bad += "$sid[$i]: time ${t.tMs} vs ${w.getValue("t")}"
                for ((j, f) in model.features.withIndex()) {
                    val d = kotlin.math.abs(t.features[j] - w.getValue(f).toDouble())
                    worst = maxOf(worst, d)
                    if (d > 1e-9) bad += "$sid[$i].$f: ${t.features[j]} vs ${w.getValue(f)}"
                }
                val ds = kotlin.math.abs(t.score - w.getValue("score").toDouble())
                worst = maxOf(worst, ds)
                if (ds > 1e-9) bad += "$sid[$i].score: ${t.score} vs ${w.getValue("score")}"
                n++
            }
        }
        println("parity: $n payments compared, worst abs difference = $worst")
        assertTrue(bad.isEmpty(), "mismatches (${bad.size}):\n" + bad.take(20).joinToString("\n"))
        assertTrue(n > 500, "too few payments compared: $n")
        assertEquals(0, bad.size)
    }
}
