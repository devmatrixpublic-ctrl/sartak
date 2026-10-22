package com.satark.detector

import kotlin.math.ceil

/** Per-cohort split-conformal alarm threshold. `age_band` selects the threshold only; it is never a feature. */
object ConformalThreshold {
    /** Threshold for a cohort, falling back to the pooled threshold when the band is unknown or missing. */
    fun forCohort(model: ModelConfig, ageBand: String?): Double =
        model.cohortThresholds[ageBand]?.threshold ?: model.pooledThreshold

    /**
     * Split-conformal quantile, a port of satark_detector.conformal_threshold: the k-th smallest calibration score with
     * k = ceil((n + 1)(1 - alpha)), same double arithmetic as the reference so exported thresholds are reproducible.
     * Empty input gives +infinity (never alarms). The guarantee is only non-trivial when k <= n.
     */
    fun quantile(scores: DoubleArray, alpha: Double): Double {
        if (scores.isEmpty()) return Double.POSITIVE_INFINITY
        val s = scores.sortedArray()
        val k = ceil((s.size + 1) * (1 - alpha)).toInt()
        return s[minOf(k, s.size) - 1]
    }
}
