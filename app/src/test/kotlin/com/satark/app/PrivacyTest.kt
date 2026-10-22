package com.satark.app

import com.satark.app.events.EventMapper
import com.satark.app.net.NetJson
import com.satark.app.net.DecisionDto
import com.satark.app.net.RiskCheckRequest
import com.satark.app.payments.PayeeHasher
import com.satark.app.signals.RawSignal
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * Privacy data-flow guards (app/privacy_check.md): no phone number or call content can enter the pipeline, and a VPA
 * only ever leaves the payment screen as a salted hash.
 */
class PrivacyTest {
    /** Every field any signal source can emit. Adding a field (e.g. a number) must be a deliberate, reviewed change. */
    private val allowedSignalFields = setOf(
        "tMs", "callerKnown", "appPackage", "source", "payeeHash", "amountInr", "isP2P", "payeeIsNew",
    )

    @Test fun signalsCannotCarryANumberOrCallContent() {
        val kinds = RawSignal::class.java.declaredClasses.filter { RawSignal::class.java.isAssignableFrom(it) }
        assertTrue(kinds.size >= 8, "found ${kinds.map { it.simpleName }}")
        for (k in kinds) {
            val fields = k.declaredFields.filterNot { java.lang.reflect.Modifier.isStatic(it.modifiers) }.map { it.name }.toSet()
            val extra = fields - allowedSignalFields
            assertTrue(extra.isEmpty(), "${k.simpleName} has unreviewed fields $extra")
        }
    }

    private val vpa = "Privacy.Canary@okhdfc"

    @Test fun payeeHashIsSaltedAndNeverTheVpa() {
        val a = PayeeHasher(ByteArray(32) { 1 }).hash(vpa)
        val b = PayeeHasher(ByteArray(32) { 2 }).hash(vpa)
        assertTrue(Regex("^[0-9a-f]{64}$").matches(a))
        assertFalse(a.contains("canary", ignoreCase = true))
        assertNotEquals(a, b, "different installs must give different hashes (no cross-device linking)")
        assertEquals(a, PayeeHasher(ByteArray(32) { 1 }).hash(" privacy.canary@OKHDFC "), "same payee, same install")
    }

    @Test fun storedEventsAndRiskCheckNeverContainTheVpa() {
        val h = PayeeHasher(ByteArray(32) { 7 }).hash(vpa)
        val signals = listOf(
            RawSignal.CallStarted(1, false),
            RawSignal.PayeeAdded(2, h),
            RawSignal.PaymentAttempt(3, h, 499.0, true, true, "qr"),
        )
        for (s in signals) {
            val stored = JSONObject(EventMapper.toSchemaMap(EventMapper.map(s), "qr")).toString()
            assertFalse(stored.contains("canary", ignoreCase = true) || stored.contains("@"), stored)
        }
        val body = NetJson.encodeToString(RiskCheckRequest.serializer(),
            RiskCheckRequest(DecisionDto("NONE", 0.0, emptyList()), "upi_intent", 499.0, h, true))
        assertFalse(body.contains("canary", ignoreCase = true) || body.contains("@"), body)
    }
}
