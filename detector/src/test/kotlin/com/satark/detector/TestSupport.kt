package com.satark.detector

import kotlin.math.abs

/** Minimal CSV reader for the SatarkSim files (no quoted fields). Rows are maps keyed by header name. */
object Csv {
    fun read(resource: String): List<Map<String, String>> {
        val stream = Csv::class.java.classLoader.getResourceAsStream(resource) ?: error("missing test resource $resource")
        val lines = stream.bufferedReader().use { it.readLines() }.filter { it.isNotBlank() }
        val header = lines.first().split(",")
        return lines.drop(1).mapIndexed { i, l ->
            val f = l.split(",", limit = Int.MAX_VALUE)
            check(f.size == header.size) { "$resource line ${i + 2}: ${f.size} fields, expected ${header.size}" }
            header.zip(f).toMap()
        }
    }
}

fun String.bool(): Boolean? = when (this) { "True" -> true; "False" -> false; else -> null }

fun toEvent(r: Map<String, String>): Event = Event(
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

class UserInfo(val ageBand: String, val median: Double, val mad: Double)

fun loadUsers(resource: String): Map<String, UserInfo> =
    Csv.read(resource).associate { it.getValue("user_id") to UserInfo(it.getValue("age_band"), it.getValue("hist_median_inr").toDouble(), it.getValue("hist_mad_inr").toDouble()) }

/** session_id -> (user_id, events in stable timestamp order), as the app feeds them. */
fun loadSessions(resource: String): Map<String, Pair<String, List<Event>>> {
    val rows = Csv.read(resource)
    val byS = LinkedHashMap<String, MutableList<Map<String, String>>>()
    for (r in rows) byS.getOrPut(r.getValue("session_id")) { ArrayList() }.add(r)
    return byS.mapValues { (_, rs) -> rs.first().getValue("user_id") to rs.map(::toEvent).sortedBy { it.tMs } }
}

class SessionResult(
    val alarm: Boolean,
    val mechanism: String,
    val alarmTMs: Long?,
    val firstPayTMs: Long?,
    val interdicted: Boolean,
    val level: Level,
    val reasons: List<String>,
    val traces: List<PaymentTrace>,
    val decisions: List<Decision>,
)

/** Runs one session exactly like the evaluation: events in order, then finish(). Session-level fields mirror satark_detector.decide. */
fun runSession(model: ModelConfig, user: UserInfo?, events: List<Event>): SessionResult {
    val det = Detector(model, user?.ageBand, if (user != null) Baseline.fixed(user.median, user.mad) else Baseline.coldStart(model))
    val traces = ArrayList<PaymentTrace>()
    det.traceSink = { traces.add(it) }
    val decisions = events.map { det.onEvent(it) } + det.finish()
    val hard = decisions.filter { it.level == Level.HARD }
    val rule = hard.filter { it.mechanism != Mechanism.PAYMENT_SCORE }
    val pay = hard.filter { it.mechanism == Mechanism.PAYMENT_SCORE }
    val ruleT = rule.minOfOrNull { it.alarmTMs!! }
    val payT = pay.minOfOrNull { it.alarmTMs!! }
    val alarmT = listOfNotNull(ruleT, payT).minOrNull()
    val mech = when {
        alarmT == null -> "none"
        ruleT != null && ruleT <= (payT ?: Long.MAX_VALUE) -> rule.sortedBy { it.alarmTMs!! }.first().mechanism!!
        else -> Mechanism.PAYMENT_SCORE
    }
    val firstPay = traces.minOfOrNull { it.tMs }
    val first = hard.minByOrNull { it.alarmTMs!! }
    return SessionResult(
        alarm = alarmT != null, mechanism = mech, alarmTMs = alarmT, firstPayTMs = firstPay,
        interdicted = alarmT != null && (firstPay == null || alarmT <= firstPay),
        level = if (alarmT != null) Level.HARD else Level.NONE, reasons = first?.reasons ?: emptyList(),
        traces = traces, decisions = decisions,
    )
}

fun close(a: Double, b: Double, tol: Double = 1e-9) = abs(a - b) <= tol
