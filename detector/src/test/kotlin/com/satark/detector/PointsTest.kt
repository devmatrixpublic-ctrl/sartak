package com.satark.detector

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.double
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PointsTest {
    private val cases = Json.parseToJsonElement(
        PointsTest::class.java.classLoader.getResourceAsStream("golden/points_cases.json")!!.bufferedReader().readText(),
    ).jsonObject

    @Test fun pointsAndBandsMatchTheSharedCasesUsedByThePythonMirror() {
        for (c in cases.getValue("points").jsonArray) assertEquals(c.jsonArray[1].jsonPrimitive.int, PointsScale.points(c.jsonArray[0].jsonPrimitive.double), c.toString())
        for (c in cases.getValue("bands").jsonArray) assertEquals(c.jsonArray[1].jsonPrimitive.content, PointsScale.band(c.jsonArray[0].jsonPrimitive.int), c.toString())
    }

    @Test fun everyPaymentAlarmCarriesOnePointValuePerReasonAndABandThatMatchesItsTotal() {
        val model = ModelConfig.loadBundled()
        val sessions = loadSessions("golden/golden_events.csv"); val users = loadUsers("golden/golden_users.csv")
        var alarms = 0
        for ((_, ue) in sessions) {
            val (uid, events) = ue
            for (d in runSession(model, users[uid], events).decisions.filter { it.mechanism == Mechanism.PAYMENT_SCORE }) {
                alarms++
                assertEquals(d.reasons.size, d.points.size)
                assertEquals(d.points.sum(), d.totalPoints)
                assertEquals(PointsScale.band(d.totalPoints!!), d.band)
                assertTrue(d.points.all { it >= 1 })
            }
        }
        assertTrue(alarms > 0)
    }

    @Test fun ruleAlarmsAndNonAlarmsCarryNoPoints() {
        val model = ModelConfig.loadBundled()
        val sessions = loadSessions("golden/golden_events.csv"); val users = loadUsers("golden/golden_users.csv")
        for ((_, ue) in sessions) {
            val (uid, events) = ue
            for (d in runSession(model, users[uid], events).decisions.filter { it.mechanism != Mechanism.PAYMENT_SCORE }) {
                assertTrue(d.points.isEmpty()); assertNull(d.totalPoints); assertNull(d.band)
            }
        }
    }
}
