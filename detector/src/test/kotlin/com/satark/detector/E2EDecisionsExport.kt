package com.satark.detector

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * Runs the REAL detector (bundled model.json) over named scenarios and writes build/e2e/decisions.json. The cross-module
 * test `ops/e2e/run_e2e.py` feeds these decisions to the REAL server, so nothing between detector and server is mocked.
 * The expected level of each scenario is stated here as ground truth and asserted, so this test fails if the detector drifts.
 */
class E2EDecisionsExport {
    private val model = ModelConfig.loadBundled()
    private val h = 3_600_000L
    private val anydesk = "com.anydesk.anydeskandroid"

    private class Out(val name: String, val kind: String, val expected: Level, val decision: Decision, val amount: Double?,
                      val payee: String?, val isP2p: Boolean?, val features: DoubleArray?)

    private fun run(name: String, band: String, median: Double, mad: Double, expected: Level, events: List<Event>, tickAt: Long? = null): Out {
        val d = Detector(model, band, Baseline.fixed(median, mad))
        var trace: PaymentTrace? = null
        d.traceSink = { trace = it }
        val decisions = events.map { d.onEvent(it) }.toMutableList()
        if (tickAt != null) decisions += d.onTick(tickAt)
        val hard = decisions.filter { it.level == Level.HARD }.minByOrNull { it.alarmTMs ?: Long.MAX_VALUE }
        val last = events.lastOrNull { it.type == EventType.PAYMENT_ATTEMPT }
        val chosen = hard ?: decisions.lastOrNull { it.mechanism == null && it.score != 0.0 } ?: decisions.last()
        return Out(name, if (last == null) "rule" else "payment", expected, chosen, last?.amountInr, last?.payeeId,
            last?.paymentType?.let { it == PaymentType.P2P }, trace?.features)
    }

    @Test
    fun exportDecisions() {
        val outs = ArrayList<Out>()
        outs += run("scam_remote_access", "60+", 800.0, 400.0, Level.HARD, listOf(
            Event(0, EventType.CALL_START, callerKnown = false),
            Event(600_000, EventType.APP_INSTALL, appPackage = anydesk, installSource = InstallSource.PLAY_STORE),
            Event(1_200_000, EventType.NEW_PAYEE, payeeId = "acct-1"),
            Event(1_500_000, EventType.PAYMENT_ATTEMPT, payeeId = "acct-1", payeeIsNew = true, amountInr = 160_000.0, paymentType = PaymentType.P2P)))
        outs += run("scam_sideload_then_payment", "36-59", 500.0, 200.0, Level.HARD, listOf(
            Event(0, EventType.CALL_START, callerKnown = false),
            Event(300_000, EventType.APP_INSTALL, appPackage = "apk.unknown.1", installSource = InstallSource.SIDELOAD),
            Event(900_000, EventType.NEW_PAYEE, payeeId = "acct-2"),
            Event(1_000_000, EventType.PAYMENT_ATTEMPT, payeeId = "acct-2", payeeIsNew = true, amountInr = 25_000.0, paymentType = PaymentType.P2P)))
        outs += run("scam_sideload_rule_only", "36-59", 500.0, 200.0, Level.HARD, listOf(
            Event(0, EventType.CALL_START, callerKnown = false),
            Event(300_000, EventType.APP_INSTALL, appPackage = "apk.unknown.1", installSource = InstallSource.SIDELOAD)))
        outs += run("scam_long_video_rule_only", "60+", 800.0, 400.0, Level.HARD, listOf(
            Event(0, EventType.VIDEO_SESSION_START, callerKnown = false, appPackage = "com.whatsapp")), tickAt = 2 * h + 1_000)
        outs += run("clean_known_contact", "36-59", 500.0, 200.0, Level.NONE, listOf(
            Event(0, EventType.CALL_START, callerKnown = true),
            Event(300_000, EventType.PAYMENT_ATTEMPT, payeeId = "landlord", payeeIsNew = false, amountInr = 600.0, paymentType = PaymentType.P2P)))
        outs += run("clean_plain_merchant", "18-35", 300.0, 150.0, Level.NONE, listOf(
            Event(0, EventType.PAYMENT_ATTEMPT, payeeId = "shop-1", payeeIsNew = false, amountInr = 50.0, paymentType = PaymentType.P2M)))

        // two real SatarkSim vectors through the same path: S050031 (remote-access scam) and S000006 (plain payment)
        val sessions = loadSessions("vectors/detector_test_vectors_events.csv")
        val users = loadUsers("vectors/detector_test_vectors_users.csv")
        for ((sid, expected) in listOf("S050031" to Level.HARD, "S000006" to Level.NONE)) {
            val (uid, events) = sessions.getValue(sid)
            val u = users.getValue(uid)
            outs += run("vector_$sid", u.ageBand, u.median, u.mad, expected, events)
        }

        val json = buildJsonObject {
            put("model_version", model.modelVersion)
            put("scenarios", buildJsonArray {
                for (o in outs) {
                    assertEquals(o.expected, o.decision.level, "${o.name}: detector decision drifted")
                    add(buildJsonObject {
                        put("name", o.name); put("kind", o.kind); put("expected_level", o.expected.name)
                        put("decision", buildJsonObject {
                            put("level", o.decision.level.name); put("score", o.decision.score)
                            put("reasons", buildJsonArray { o.decision.reasons.forEach { add(JsonPrimitive(it)) } })
                            put("mechanism", o.decision.mechanism?.let { JsonPrimitive(it) } ?: JsonNull)
                        })
                        put("amount", o.amount?.let { JsonPrimitive(it) } ?: JsonNull)
                        put("payee", o.payee?.let { JsonPrimitive(it) } ?: JsonNull)
                        put("is_p2p", o.isP2p?.let { JsonPrimitive(it) } ?: JsonNull)
                        val f: JsonElement = o.features?.let { v -> buildJsonObject { model.features.forEachIndexed { i, n -> put(n, v[i]) } } } ?: JsonNull
                        put("features", f)
                    })
                }
            })
        }
        val out = File("build/e2e/decisions.json")
        out.parentFile.mkdirs()
        out.writeText(Json { prettyPrint = true }.encodeToString(JsonElement.serializer(), json))
        println("wrote ${outs.size} scenarios to ${out.absolutePath}")
    }
}
