package com.satark.detector

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ExplainerTest {
    private val model = ModelConfig.loadBundled()
    private val explainer = Explainer(model, Scorer(model))
    private val sessions = loadSessions("golden/golden_events.csv")
    private val users = loadUsers("golden/golden_users.csv")

    /** Plan 2.5: every alarm returns 1-3 stable, published codes. */
    @Test
    fun everyAlarmHasOneToThreeKnownStableCodes() {
        var alarms = 0
        for ((_, ue) in sessions) {
            val (uid, events) = ue
            val a = runSession(model, users.getValue(uid), events)
            val b = runSession(model, users.getValue(uid), events)
            for (d in a.decisions.filter { it.level == Level.HARD }) {
                alarms++
                assertTrue(d.reasons.size in 1..3, "reasons=${d.reasons}")
                assertTrue(explainer.allCodes.containsAll(d.reasons), "unknown code in ${d.reasons}")
                assertEquals(d.reasons.toSet().size, d.reasons.size, "duplicate codes")
                if (d.mechanism != Mechanism.PAYMENT_SCORE) assertEquals(1, d.reasons.size)
            }
            assertEquals(a.decisions.map { it.reasons }, b.decisions.map { it.reasons })
        }
        assertTrue(alarms > 100, "too few alarms exercised: $alarms")
    }

    @Test
    fun everyFeatureAndRuleHasACode() {
        assertEquals(model.features.size + 2, explainer.allCodes.size)
        assertEquals(listOf("RULE_SIDELOAD_DURING_CALL"), explainer.reasonForRule(Mechanism.SIDELOAD_DURING_CALL))
        assertEquals(listOf("RULE_LONG_SESSION"), explainer.reasonForRule(Mechanism.LONG_SESSION))
    }

    /** A reason may only be cited when its condition really happened: feature present and weight toward scam. */
    @Test
    fun citedReasonsAreAlwaysTrueStatements() {
        val codeToFeature = Explainer.loadBundled().codes.filter { it.kind == "feature" }.associate { it.code to it.source }
        var checked = 0
        for ((_, ue) in sessions) {
            val (uid, events) = ue
            val r = runSession(model, users.getValue(uid), events)
            val byTime = r.traces.associateBy { it.tMs }
            for (d in r.decisions.filter { it.level == Level.HARD && it.mechanism == Mechanism.PAYMENT_SCORE }) {
                val x = byTime.getValue(d.alarmTMs!!).features
                for (code in d.reasons) {
                    val j = model.features.indexOf(codeToFeature.getValue(code))
                    assertTrue(x[j] > 0.0, "$code cited but feature value is ${x[j]}")
                    assertTrue(model.logistic.coef[j] > 0.0, "$code cited with a non-positive weight")
                    checked++
                }
            }
        }
        assertTrue(checked > 500, "too few reasons checked: $checked")
    }
}
