package com.satark.detector

import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class RobustnessTest {
    private val model = ModelConfig.loadBundled()
    private val sessions = loadSessions("golden/golden_events.csv")
    private val users = loadUsers("golden/golden_users.csv")

    @Test
    fun sameInputGivesSameOutput() {
        for ((_, ue) in sessions) {
            val (uid, events) = ue
            val a = runSession(model, users.getValue(uid), events)
            val b = runSession(model, users.getValue(uid), events)
            assertEquals(a.decisions, b.decisions)
            assertEquals(a.traces.map { it.score }, b.traces.map { it.score })
        }
    }

    /** 1,000 random or partial event streams, including nulls, non-finite amounts and unordered times: no exceptions. */
    @Test
    fun fuzz1000RandomStreamsNeverThrow() {
        val rnd = Random(20261021)
        val pkgs = listOf(null, "com.anydesk.anydeskandroid", "com.whatsapp", "apk.unknown.1", "")
        repeat(1000) {
            val det = Detector(model, listOf("18-35", "36-59", "60+", null, "weird").random(rnd), if (rnd.nextBoolean()) Baseline.coldStart(model) else Baseline.fixed(rnd.nextDouble(0.0, 5000.0), rnd.nextDouble(0.0, 5000.0)))
            repeat(rnd.nextInt(0, 40)) {
                val e = Event(
                    tMs = rnd.nextLong(-1_000_000, 100_000_000),
                    type = EventType.values().random(rnd),
                    callerKnown = listOf(null, true, false).random(rnd),
                    appPackage = pkgs.random(rnd),
                    installSource = listOf(null, InstallSource.PLAY_STORE, InstallSource.SIDELOAD).random(rnd),
                    payeeId = listOf(null, "p1", "p2").random(rnd),
                    payeeIsNew = listOf(null, true, false).random(rnd),
                    amountInr = listOf(null, 0.0, -5.0, 1e12, Double.NaN, Double.POSITIVE_INFINITY, rnd.nextDouble(0.0, 1e6)).random(rnd),
                    paymentType = listOf(null, PaymentType.P2P, PaymentType.P2M).random(rnd),
                )
                val d = det.onEvent(e)
                assertTrue(d.reasons.size <= 3)
                assertTrue(d.level == Level.NONE || d.reasons.isNotEmpty(), "HARD decision without a reason")
                assertTrue(!d.score.isNaN(), "NaN score")
            }
            det.onTick(rnd.nextLong(0, 200_000_000))
            det.finish()
            det.reset()
        }
    }

    /** Plan 2.6: call-state / usage signals UNAVAILABLE (events absent or fields null) still give valid decisions. */
    @Test
    fun missingSignalsStillProduceValidDecisions() {
        val vectors = loadSessions("vectors/detector_test_vectors_events.csv")
        val vusers = loadUsers("vectors/detector_test_vectors_users.csv")
        for ((_, ue) in vectors) {
            val (uid, events) = ue
            val noCall = events.filter { it.type !in setOf(EventType.CALL_START, EventType.CALL_END, EventType.VIDEO_SESSION_START, EventType.VIDEO_SESSION_END) }
            val nullFields = events.map { it.copy(callerKnown = null, installSource = null, appPackage = null) }
            for (variant in listOf(noCall, nullFields)) {
                val r = runSession(model, vusers.getValue(uid), variant)
                assertTrue(r.decisions.all { it.score.isFinite() })
                assertTrue(r.level == Level.NONE || r.level == Level.HARD)
            }
        }
    }

    @Test
    fun bundledModelHasThe16FeaturesInPlanOrder() {
        assertEquals(
            listOf(
                "unk_contact_recent", "unk_call_active", "unk_video_active", "mins_since_unk_log",
                "install_play_during_unk", "install_sideload_during_unk", "watchlist_app",
                "new_payee", "payee_added_after_unk", "log_amt_ratio", "robust_z_pos", "repeat_to_payee", "is_p2p",
                "ocss_ordered", "newpayee_x_amt", "unk_x_newpayee",
            ),
            model.features,
        )
    }
}
