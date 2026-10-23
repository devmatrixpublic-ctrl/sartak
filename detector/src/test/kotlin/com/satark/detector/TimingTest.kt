package com.satark.detector

import kotlin.test.Test
import kotlin.test.assertTrue

/** The decision for one event must come back within 100 ms (it runs before a payment is released). */
class TimingTest {
    private val model = ModelConfig.loadBundled()
    private val sessions = loadSessions("golden/golden_events.csv")
    private val users = loadUsers("golden/golden_users.csv")

    private fun replayAll(record: MutableList<Long>?) {
        for ((_, ue) in sessions) {
            val (uid, events) = ue
            val u = users[uid]
            val det = Detector(model, u?.ageBand, if (u != null) Baseline.fixed(u.median, u.mad) else Baseline.coldStart(model))
            for (e in events) {
                val t0 = System.nanoTime()
                det.onEvent(e)
                record?.add(System.nanoTime() - t0)
            }
            val t0 = System.nanoTime(); det.finish(); record?.add(System.nanoTime() - t0)
        }
    }

    @Test
    fun everyEventIsDecidedWithin100Ms() {
        repeat(3) { replayAll(null) } // warm up the JIT: the app calls this repeatedly, not once cold
        val times = ArrayList<Long>()
        replayAll(times)
        assertTrue(times.size > 100, "enough events to mean something: ${times.size}")
        val maxMs = times.max() / 1e6
        val p99Ms = times.sorted()[(times.size * 0.99).toInt().coerceAtMost(times.size - 1)] / 1e6
        println("detector timing: ${times.size} events, p99 = %.3f ms, max = %.3f ms".format(p99Ms, maxMs))
        assertTrue(maxMs <= 100.0, "slowest event took $maxMs ms")
    }
}
