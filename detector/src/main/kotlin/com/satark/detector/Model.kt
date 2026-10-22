package com.satark.detector

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class Scaler(val mean: List<Double>, val scale: List<Double>)

@Serializable
data class Logistic(val coef: List<Double>, val intercept: Double)

@Serializable
data class CohortThreshold(val threshold: Double, @SerialName("n_cal") val nCal: Int, val k: Int, val method: String)

@Serializable
data class Constants(
    @SerialName("LONG_SESSION_H") val longSessionH: Double,
    @SerialName("CONTACT_WINDOW_S") val contactWindowS: Double,
    @SerialName("OCSS_WINDOW_S") val ocssWindowS: Double,
    @SerialName("DEDUPE_WINDOW_S") val dedupeWindowS: Double,
    @SerialName("AMOUNT_RATIO_CLIP") val amountRatioClip: List<Double>,
    @SerialName("ROBUST_Z_MAD_SCALE") val robustZMadScale: Double,
    @SerialName("ROBUST_Z_MAD_FLOOR") val robustZMadFloor: Double,
    @SerialName("ROBUST_Z_CAP") val robustZCap: Double,
    @SerialName("REPEAT_CAP") val repeatCap: Int,
)

@Serializable
data class BaselineConfig(
    @SerialName("window_n") val windowN: Int,
    @SerialName("blend_k") val blendK: Int,
    @SerialName("prior_median_inr") val priorMedianInr: Double,
    @SerialName("prior_mad_inr") val priorMadInr: Double,
)

/** Mirror of detector/src/main/resources/model.json, written by detector/tools/export_model.py. */
@Serializable
data class ModelConfig(
    @SerialName("model_version") val modelVersion: String,
    val alpha: Double,
    val features: List<String>,
    val scaler: Scaler,
    val logistic: Logistic,
    @SerialName("cohort_thresholds") val cohortThresholds: Map<String, CohortThreshold>,
    @SerialName("pooled_threshold") val pooledThreshold: Double,
    val constants: Constants,
    val watchlist: List<String>,
    val baseline: BaselineConfig,
) {
    val watchlistSet: Set<String> by lazy { watchlist.toSet() }

    init {
        require(features.size == scaler.mean.size && features.size == scaler.scale.size && features.size == logistic.coef.size) {
            "model.json: feature / scaler / coefficient sizes disagree"
        }
        require(scaler.scale.all { it != 0.0 }) { "model.json: zero scaler scale" }
        require(constants.amountRatioClip.size == 2) { "model.json: AMOUNT_RATIO_CLIP must have 2 entries" }
    }

    companion object {
        private val json = Json { ignoreUnknownKeys = true }

        fun parse(text: String): ModelConfig = json.decodeFromString(serializer(), text)

        /** Loads the model bundled in the library (src/main/resources/model.json). */
        fun loadBundled(): ModelConfig {
            val stream = ModelConfig::class.java.classLoader.getResourceAsStream("model.json")
                ?: error("model.json not found on the classpath")
            return parse(stream.bufferedReader().use { it.readText() })
        }
    }
}
