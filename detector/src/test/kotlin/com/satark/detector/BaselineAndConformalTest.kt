package com.satark.detector

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class BaselineAndConformalTest {
    private val model = ModelConfig.loadBundled()

    @Test
    fun coldStartUsesThePrior() {
        val b = Baseline.coldStart(model)
        assertEquals(model.baseline.priorMedianInr, b.median)
        assertEquals(model.baseline.priorMadInr, b.mad)
    }

    @Test
    fun baselineConvergesToOwnHistoryAsPaymentsAccumulate() {
        val b = Baseline.coldStart(model)
        val prior = model.baseline.priorMedianInr
        repeat(model.baseline.windowN) { b.observe(5000.0 + (it % 3)) }
        assertTrue(kotlin.math.abs(b.median - 5001.0) < kotlin.math.abs(prior - 5001.0) * 0.5, "median ${b.median} did not move toward own history")
        val few = Baseline.coldStart(model).also { it.observe(5000.0) }
        assertTrue(few.median < b.median, "one payment must move the baseline less than a full window")
    }

    @Test
    fun invalidAmountsAreIgnoredAndFixedBaselineNeverChanges() {
        val b = Baseline.coldStart(model).also { it.observe(Double.NaN); it.observe(-1.0) }
        assertEquals(0, b.observations)
        val f = Baseline.fixed(100.0, 40.0).also { it.observe(99999.0) }
        assertEquals(100.0, f.median); assertEquals(40.0, f.mad)
    }

    @Test
    fun conformalQuantileMatchesTheKRule() {
        assertEquals(Double.POSITIVE_INFINITY, ConformalThreshold.quantile(doubleArrayOf(), 0.001))
        assertEquals(1000.0, ConformalThreshold.quantile(DoubleArray(1000) { (it + 1).toDouble() }, 0.001))
        assertEquals(9.0, ConformalThreshold.quantile(DoubleArray(9) { (it + 1).toDouble() }, 0.1)) // k=9=n
        assertEquals(5.0, ConformalThreshold.quantile(doubleArrayOf(5.0, 1.0, 3.0), 0.0001)) // k > n -> max
    }

    @Test
    fun cohortThresholdAndPooledFallback() {
        for ((band, c) in model.cohortThresholds) assertEquals(c.threshold, ConformalThreshold.forCohort(model, band))
        assertEquals(model.pooledThreshold, ConformalThreshold.forCohort(model, null))
        assertEquals(model.pooledThreshold, ConformalThreshold.forCohort(model, "unknown-band"))
    }
}
