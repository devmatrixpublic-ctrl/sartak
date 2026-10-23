package com.satark.detector

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class ReasonCode(val code: String, val kind: String, val source: String, val meaning: String)

@Serializable
data class ReasonCodeFile(val version: Int, val codes: List<ReasonCode>, val max_reasons: Int = 3)

/**
 * Turns an alarm into 1-3 stable reason codes (contracts/reason_codes.json).
 * Payment alarms: the top per-feature contributions (weight x standardised value; ties break by feature order), restricted
 * to features that are actually PRESENT (value > 0) and whose weight points toward scam (> 0). Without that restriction a
 * zero-valued feature with a negative weight (a statistical artefact of correlated features, e.g. unk_contact_recent)
 * scores as positive "evidence" and the screen would state something that did not happen.
 * Rule alarms carry their own rule code only.
 */
/**
 * Display-only "points": each reason's contribution (weight x scaled value, in logit units) is quantised to whole points,
 * and the total is named with a band. Nothing here feeds back into the score, the threshold or the level; the numbers
 * only help a person see roughly how much each reason weighed. They are NOT calibrated probabilities. Mirror:
 * detector/tools/points.py, with the shared cases in detector/src/test/resources/golden/points_cases.json.
 */
object PointsScale {
    /** One point is this many logit units. */
    const val LOGIT_PER_POINT = 0.5

    /** At least 1 point for any positive contribution that is listed; otherwise the nearest whole number. */
    fun points(contribution: Double): Int = maxOf(1, Math.floor(contribution / LOGIT_PER_POINT + 0.5).toInt())

    fun band(total: Int): String = when {
        total <= 3 -> "LOG"
        total <= 5 -> "NUDGE"
        total <= 8 -> "PAUSE"
        else -> "ESCALATE"
    }
}

class Explainer(private val model: ModelConfig, private val scorer: Scorer, file: ReasonCodeFile = loadBundled()) {
    private val maxReasons = file.max_reasons
    private val featureCode: Map<String, String> = file.codes.filter { it.kind == "feature" }.associate { it.source to it.code }
    private val ruleCode: Map<String, String> = file.codes.filter { it.kind == "rule" }.associate { it.source to it.code }

    init {
        val missing = model.features.filter { it !in featureCode }
        require(missing.isEmpty()) { "reason_codes.json has no code for features: $missing" }
    }

    private fun topFeatures(x: DoubleArray, contrib: DoubleArray): List<Int> = model.features.indices
        .filter { contrib[it] > 0.0 && x[it] > 0.0 && model.logistic.coef[it] > 0.0 }
        .sortedByDescending { contrib[it] } // stable sort: equal contributions keep feature order
        .take(maxReasons)

    fun reasonsForPayment(x: DoubleArray): List<String> =
        topFeatures(x, scorer.contributions(x)).map { featureCode.getValue(model.features[it]) }

    /** Points for the same reasons, in the same order (display only). */
    fun pointsForPayment(x: DoubleArray): Triple<List<Int>, Int, String> {
        val contrib = scorer.contributions(x)
        val pts = topFeatures(x, contrib).map { PointsScale.points(contrib[it]) }
        val total = pts.sum()
        return Triple(pts, total, PointsScale.band(total))
    }

    fun reasonForRule(mechanism: String): List<String> = listOf(ruleCode.getValue(mechanism))

    val allCodes: Set<String> get() = (featureCode.values + ruleCode.values).toSet()

    companion object {
        fun loadBundled(): ReasonCodeFile {
            val stream = Explainer::class.java.classLoader.getResourceAsStream("reason_codes.json")
                ?: error("reason_codes.json not found on the classpath")
            return Json { ignoreUnknownKeys = true }.decodeFromString(ReasonCodeFile.serializer(), stream.bufferedReader().use { it.readText() })
        }
    }
}
