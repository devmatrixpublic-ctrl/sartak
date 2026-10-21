package com.satark.detector

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ReferenceVectorsTest {
    private val model = ModelConfig.loadBundled()

    /** Plan 2.3: the 36 test vectors match the reference exactly (decision + level + mechanism + timing). */
    @Test
    fun all36VectorsMatchExactly() {
        val sessions = loadSessions("vectors/detector_test_vectors_events.csv")
        val users = loadUsers("vectors/detector_test_vectors_users.csv")
        val expected = Csv.read("vectors/detector_test_vectors_expected.csv")
        assertEquals(36, expected.size)
        var matched = 0
        val failures = ArrayList<String>()
        for (x in expected) {
            val sid = x.getValue("session_id")
            val (uid, events) = sessions.getValue(sid)
            val r = runSession(model, users.getValue(uid), events)
            val alarmWant = x.getValue("alarm") == "True"
            val problems = ArrayList<String>()
            if (r.alarm != alarmWant) problems += "alarm ${r.alarm} != $alarmWant"
            if (r.mechanism != x.getValue("mechanism")) problems += "mechanism ${r.mechanism} != ${x.getValue("mechanism")}"
            if (r.level.name != x.getValue("level")) problems += "level ${r.level} != ${x.getValue("level")}"
            if (r.interdicted != (x.getValue("interdicted") == "True")) problems += "interdicted ${r.interdicted}"
            x.getValue("alarm_t").ifEmpty { null }?.let { if (r.alarmTMs != it.toDouble().toLong() * 1000) problems += "alarm_t ${r.alarmTMs} != $it" }
            if (x.getValue("alarm_t").isEmpty() && r.alarmTMs != null) problems += "unexpected alarm_t ${r.alarmTMs}"
            if (problems.isEmpty()) matched++ else failures += "$sid: ${problems.joinToString("; ")}"
        }
        assertTrue(failures.isEmpty(), "matched $matched/36. Failures:\n" + failures.joinToString("\n"))
        assertEquals(36, matched)
    }
}
