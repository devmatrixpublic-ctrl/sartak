package com.satark.app.vectors

import com.satark.app.events.Deduplicator
import com.satark.app.events.EventMapper
import com.satark.app.events.SessionPolicy
import com.satark.detector.Baseline
import com.satark.detector.Decision
import com.satark.detector.Detector
import com.satark.detector.Event
import com.satark.detector.EventType
import com.satark.detector.InstallSource
import com.satark.detector.Level
import com.satark.detector.Mechanism
import com.satark.detector.ModelConfig
import com.satark.detector.PaymentTrace
import com.satark.detector.PaymentType
import org.json.JSONObject

/**
 * M2's 36 test vectors (data/satarksim/detector_test_vectors_*.csv), shared by the on-device test (androidTest) and
 * the JVM test. Session scoring mirrors detector/src/test/.../TestSupport.kt runSession (M2's reference harness).
 */
object Vectors {
    class Expected(val sessionId: String, val alarm: Boolean, val mechanism: String, val level: String,
                   val interdicted: Boolean, val alarmTSec: Double?)
    class User(val ageBand: String, val median: Double, val mad: Double)
    class Session(val userId: String, val events: List<Event>)
    class Data(val sessions: Map<String, Session>, val users: Map<String, User>, val expected: List<Expected>)

    /** How events reach the detector. */
    enum class Path {
        /** Straight into the detector, like M2's JVM test. */
        DETECTOR,
        /** The app's way: stored as schema JSON and read back, app dedup, SessionPolicy, then the detector. */
        APP_PIPELINE,
    }

    class Result(val alarm: Boolean, val mechanism: String, val level: Level, val interdicted: Boolean, val alarmTMs: Long?)

    fun parse(eventsCsv: String, usersCsv: String, expectedCsv: String): Data {
        val users = csv(usersCsv).associate {
            it.getValue("user_id") to User(it.getValue("age_band"), it.getValue("hist_median_inr").toDouble(), it.getValue("hist_mad_inr").toDouble())
        }
        val bySession = LinkedHashMap<String, MutableList<Map<String, String>>>()
        for (r in csv(eventsCsv)) bySession.getOrPut(r.getValue("session_id")) { ArrayList() }.add(r)
        val sessions = bySession.mapValues { (_, rs) -> Session(rs.first().getValue("user_id"), rs.map(::toEvent).sortedBy { it.tMs }) }
        val expected = csv(expectedCsv).map {
            Expected(it.getValue("session_id"), it.getValue("alarm") == "True", it.getValue("mechanism"), it.getValue("level"),
                it.getValue("interdicted") == "True", it.getValue("alarm_t").ifEmpty { null }?.toDouble())
        }
        return Data(sessions, users, expected)
    }

    /** Runs all vectors; returns one line per mismatch (empty = all match). */
    fun check(data: Data, model: ModelConfig, path: Path): List<String> = data.expected.mapNotNull { x ->
        val s = data.sessions.getValue(x.sessionId)
        val r = run(model, data.users[s.userId], s.events, path)
        val p = ArrayList<String>()
        if (r.alarm != x.alarm) p += "alarm ${r.alarm} != ${x.alarm}"
        if (r.mechanism != x.mechanism) p += "mechanism ${r.mechanism} != ${x.mechanism}"
        if (r.level.name != x.level) p += "level ${r.level} != ${x.level}"
        if (r.interdicted != x.interdicted) p += "interdicted ${r.interdicted} != ${x.interdicted}"
        val wantT = x.alarmTSec?.let { it.toLong() * 1000 }
        if (r.alarmTMs != wantT) p += "alarm_t ${r.alarmTMs} != $wantT"
        if (p.isEmpty()) null else "${x.sessionId}: ${p.joinToString("; ")}"
    }

    fun run(model: ModelConfig, user: User?, events: List<Event>, path: Path): Result {
        val det = Detector(model, user?.ageBand, if (user != null) Baseline.fixed(user.median, user.mad) else Baseline.coldStart(model))
        val traces = ArrayList<PaymentTrace>()
        det.traceSink = { traces.add(it) }
        val decisions = ArrayList<Decision>()
        when (path) {
            Path.DETECTOR -> events.forEach { decisions += det.onEvent(it) }
            Path.APP_PIPELINE -> {
                val dedup = Deduplicator((model.constants.dedupeWindowS * 1000).toLong())
                val policy = SessionPolicy() // the app's real settings
                for (raw in events) {
                    // Exactly what EventDispatcher does: store as schema JSON (and read back on restore), dedup, policy.
                    val stored = EventMapper.fromSchemaJson(JSONObject(EventMapper.toSchemaMap(raw)).toString())
                        ?: error("event did not survive storage: $raw")
                    if (dedup.isDuplicate(stored)) continue
                    val step = policy.prepare(stored) ?: continue
                    if (step.resetFirst) det.reset()
                    decisions += det.onEvent(step.event)
                }
            }
        }
        decisions += det.finish()
        val hard = decisions.filter { it.level == Level.HARD }
        val rule = hard.filter { it.mechanism != Mechanism.PAYMENT_SCORE }
        val pay = hard.filter { it.mechanism == Mechanism.PAYMENT_SCORE }
        val ruleT = rule.minOfOrNull { it.alarmTMs!! }
        val payT = pay.minOfOrNull { it.alarmTMs!! }
        val alarmT = listOfNotNull(ruleT, payT).minOrNull()
        val mech = when {
            alarmT == null -> "none"
            ruleT != null && ruleT <= (payT ?: Long.MAX_VALUE) -> rule.minByOrNull { it.alarmTMs!! }!!.mechanism!!
            else -> Mechanism.PAYMENT_SCORE
        }
        val firstPay = traces.minOfOrNull { it.tMs }
        return Result(alarmT != null, mech, if (alarmT != null) Level.HARD else Level.NONE,
            alarmT != null && (firstPay == null || alarmT <= firstPay), alarmT)
    }

    private fun csv(text: String): List<Map<String, String>> {
        val lines = text.lines().filter { it.isNotBlank() }
        val header = lines.first().trim().split(",")
        return lines.drop(1).map { l -> header.zip(l.trim().split(",", limit = Int.MAX_VALUE)).toMap() }
    }

    private fun String.bool(): Boolean? = when (this) { "True" -> true; "False" -> false; else -> null }

    private fun toEvent(r: Map<String, String>) = Event(
        tMs = r.getValue("t_sec").toDouble().toLong() * 1000L,
        type = EventType.valueOf(r.getValue("event_type")),
        callerKnown = r.getValue("caller_known").bool(),
        appPackage = r.getValue("app_package").ifEmpty { null },
        installSource = when (r.getValue("install_source")) { "play_store" -> InstallSource.PLAY_STORE; "sideload" -> InstallSource.SIDELOAD; else -> null },
        payeeId = r.getValue("payee_id").ifEmpty { null },
        payeeIsNew = r.getValue("payee_is_new").bool(),
        amountInr = r.getValue("amount_inr").ifEmpty { null }?.toDouble(),
        paymentType = when (r.getValue("payment_type")) { "P2P" -> PaymentType.P2P; "P2M" -> PaymentType.P2M; else -> null },
    )
}
