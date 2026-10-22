package com.satark.detector

import kotlin.math.abs

/**
 * The user's own payment-amount baseline: median and MAD (raw, unscaled) of the last `windowN` completed payments,
 * blended with a fixed population prior while history is thin: weight of own history = n / (n + blendK).
 *
 * The reference detector takes a fixed per-user median/MAD as an input (SatarkSim `hist_median_inr`, `hist_mad_inr`);
 * [fixed] reproduces that exactly. The rolling window and the blend are design choices of the on-device port, not
 * fitted or measured by the reference, and must be validated before being quoted as results.
 *
 * Call [observe] only for payments that actually completed; never for a payment attempt that was held, so an
 * attacker-driven payment cannot move what counts as "normal" for this user.
 */
class Baseline private constructor(
    private val priorMedian: Double,
    private val priorMad: Double,
    private val windowN: Int,
    private val blendK: Int,
    private val frozen: Boolean,
) {
    private val window = ArrayDeque<Double>()

    val observations: Int get() = if (frozen) Int.MAX_VALUE else window.size

    fun observe(amountInr: Double) {
        if (frozen || !amountInr.isFinite() || amountInr < 0) return
        window.addLast(amountInr)
        while (window.size > windowN) window.removeFirst()
    }

    val median: Double get() = blend(ownMedian(), priorMedian)

    val mad: Double get() = blend(ownMad(), priorMad)

    private fun blend(own: Double, prior: Double): Double {
        if (frozen) return prior
        val n = window.size
        if (n == 0) return prior
        val w = n.toDouble() / (n + blendK)
        return w * own + (1.0 - w) * prior
    }

    private fun ownMedian(): Double = medianOf(window.toDoubleArray())

    private fun ownMad(): Double {
        val m = ownMedian()
        return medianOf(DoubleArray(window.size) { abs(window.elementAt(it) - m) })
    }

    companion object {
        /** Cold-start baseline: population prior from model.json. */
        fun coldStart(model: ModelConfig) = with(model.baseline) { Baseline(priorMedianInr, priorMadInr, windowN, blendK, false) }

        /** Fixed history statistics supplied from outside (reference behaviour; used by the test vectors). */
        fun fixed(medianInr: Double, madInr: Double) = Baseline(medianInr, madInr, 0, 0, true)

        internal fun medianOf(x: DoubleArray): Double {
            if (x.isEmpty()) return 0.0
            val s = x.sortedArray()
            val n = s.size
            return if (n % 2 == 1) s[n / 2] else (s[n / 2 - 1] + s[n / 2]) / 2.0
        }
    }
}
