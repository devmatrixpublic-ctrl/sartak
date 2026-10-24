package com.satark.app

import com.satark.app.events.Deduplicator
import com.satark.app.events.EventMapper
import com.satark.app.events.SessionPolicy
import com.satark.app.events.SplitGuard
import com.satark.app.vectors.Vectors
import com.satark.detector.Baseline
import com.satark.detector.Level
import com.satark.detector.ModelConfig
import org.json.JSONObject
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * The split-payment guard runs beside the main detector and may only add alarms. This runs M2's 36 vectors through both and
 * pins down exactly what it changes, so a later edit cannot quietly alter a frozen decision or add a false alarm.
 */
class SplitGuardVectorsTest {
    private val dir = File("../data/satarksim")
    private val data = Vectors.parse(
        File(dir, "detector_test_vectors_events.csv").readText(),
        File(dir, "detector_test_vectors_users.csv").readText(),
        File(dir, "detector_test_vectors_expected.csv").readText(),
    )
    private val model = ModelConfig.loadBundled()

    /** First alarm time (ms) from the guard's own detector, fed exactly as the app feeds its main one. */
    private fun guardAlarmMs(sessionId: String): Long? {
        val s = data.sessions.getValue(sessionId)
        val user = data.users[s.userId]
        val guard = SplitGuard(model, user?.ageBand, if (user != null) Baseline.fixed(user.median, user.mad) else Baseline.coldStart(model))
        val dedup = Deduplicator((model.constants.dedupeWindowS * 1000).toLong())
        val policy = SessionPolicy()
        var first: Long? = null
        for (raw in s.events) {
            val stored = EventMapper.fromSchemaJson(JSONObject(EventMapper.toSchemaMap(raw)).toString()) ?: error("event did not survive storage")
            if (dedup.isDuplicate(stored)) continue
            val step = policy.prepare(stored) ?: continue
            if (step.resetFirst) guard.reset()
            val d = guard.onEvent(step.event)
            if (d.level == Level.HARD) first = minOf(first ?: Long.MAX_VALUE, d.alarmTMs!!)
        }
        return first
    }

    private fun mainAlarmMs(sessionId: String): Long? {
        val s = data.sessions.getValue(sessionId)
        return Vectors.run(model, data.users[s.userId], s.events, Vectors.Path.APP_PIPELINE).alarmTMs
    }

    @Test fun theGuardNeverAlarmsLaterThanM2sExpectedTimeAndAddsNoFalseAlarm() {
        for (x in data.expected) {
            val main = mainAlarmMs(x.sessionId)
            val combined = listOfNotNull(main, guardAlarmMs(x.sessionId)).minOrNull()
            if (!x.alarm) assertEquals(null, combined, "${x.sessionId}: M2 expects no alarm, so the guard must not add one")
            else {
                assertNotNull(combined, x.sessionId)
                assertTrue(combined <= main!!, "${x.sessionId}: the guard must not make an alarm later")
            }
        }
    }

    @Test fun theOnlyVectorTheGuardChangesIsTheSplitFamilyEmergencyAndItAlarmsEarlier() {
        val changed = data.expected.filter { x ->
            val main = mainAlarmMs(x.sessionId)
            val combined = listOfNotNull(main, guardAlarmMs(x.sessionId)).minOrNull()
            combined != main
        }.map { it.sessionId }
        assertEquals(listOf("S050138"), changed, "any other change needs M2's sign-off, because it alters a frozen decision")
        assertTrue(guardAlarmMs("S050138")!! < mainAlarmMs("S050138")!!)
    }
}
