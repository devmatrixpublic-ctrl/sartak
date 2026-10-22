package com.satark.detector

/** Standard scaler + logistic regression, evaluated as a logit (the decision is taken on the logit, not the probability). */
class Scorer(private val model: ModelConfig) {
    private val mean = model.scaler.mean.toDoubleArray()
    private val scale = model.scaler.scale.toDoubleArray()
    private val coef = model.logistic.coef.toDoubleArray()
    private val intercept = model.logistic.intercept

    /** Sequential sum in feature order, exactly as export_model.rescore_from_json, so results match to ~1e-15. */
    fun score(x: DoubleArray): Double {
        require(x.size == coef.size) { "expected ${coef.size} features, got ${x.size}" }
        var s = 0.0
        for (j in coef.indices) s += ((x[j] - mean[j]) / scale[j]) * coef[j]
        return s + intercept
    }

    /** Per-feature contribution to the logit: weight x standardised value. */
    fun contributions(x: DoubleArray): DoubleArray = DoubleArray(coef.size) { j -> ((x[j] - mean[j]) / scale[j]) * coef[j] }
}
