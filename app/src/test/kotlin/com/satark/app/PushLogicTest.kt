package com.satark.app

import com.satark.app.push.ContactAlert
import com.satark.app.push.PairingCode
import com.satark.app.push.Push
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Trusted-contact push: the pairing code a person pastes, and what the contact's phone shows. */
class PushLogicTest {
    private val id = "6abf5a43-0cc2-4520-a433-3156d87d55ac"
    // Real FCM tokens look like this: an instance id, ':', then a long base64url string.
    private val token = "cH4xZ9pQS0e2nL1fYbVq3k:APA91bF7xQ_kd-21aZp9Lm0NqR3sT4uV5wX6yZ7aB8cD9eF0gH1iJ2kL3mN4oP5qR6s"

    @Test fun roundTrip() = assertEquals(PairingCode.Parsed(id, token), PairingCode.parse(PairingCode.format(id, token)))

    @Test fun codeIsFoundInsideAMessageAndAcrossWrappedLines() {
        val pasted = "Here is my Satark pairing code:\n${id}:${token.substring(0, 30)}\n${token.substring(30)}\nthanks"
        val p = PairingCode.parse(pasted)
        assertEquals(id, p?.deviceId)
        assertTrue(p!!.pushToken.startsWith(token), "token keeps its ':' and is rejoined across the line break")
    }

    @Test fun badCodesAreRejected() {
        assertNull(PairingCode.parse(""))
        assertNull(PairingCode.parse("hello"))
        assertNull(PairingCode.parse("not-a-uuid:$token"))
        assertNull(PairingCode.parse("$id:"))
        assertNull(PairingCode.parse("$id:short"), "a token under 20 characters is not a push token")
    }

    @Test fun codesFitTheServerLimits() {
        val p = PairingCode.parse(PairingCode.format(id, token))!!
        assertTrue(p.deviceId.length <= 36)      // TrustedContactIn.trusted_device_id max_length=36
        assertTrue(p.pushToken.length <= 4096)   // TrustedContactIn.fcm_token max_length=4096
        assertNull(PairingCode.parse("$id:" + "a".repeat(5000)), "an over-long token is refused, not cut")
    }

    @Test fun textGluedToTheCodeIsNotSwallowedIntoTheToken() {
        // A code pasted twice, or with more text stuck to it, must still give exactly the real token.
        assertEquals(token, PairingCode.parse("$id:$token:$id:$token")?.pushToken)
        assertEquals(token, PairingCode.parse("$id:$token.Thanks!")?.pushToken)
        assertEquals("APA91bOldStyleTokenWithoutInstancePrefix_0123", PairingCode.parse("$id:APA91bOldStyleTokenWithoutInstancePrefix_0123")?.pushToken)
        assertEquals(PairingCode.Parsed(id, token), PairingCode.parse("Here it is $id:$token"), "words right before the code")
        assertEquals(id, PairingCode.parse("code$id:$token")?.deviceId, "hex letters before the code do not shift the id")
    }

    @Test fun alertTypeComesFromTheServerData() {
        assertTrue(ContactAlert.from(mapOf("type" to "long_session", "owner_device_id" to id)).isLongSession)
        assertFalse(ContactAlert.from(mapOf("type" to "alarm")).isLongSession)
        assertEquals(ContactAlert.ALARM, ContactAlert.from(emptyMap()).type, "missing type: still an alarm")
        assertEquals(ContactAlert.ALARM, ContactAlert.from(mapOf("type" to "<script>")).type)
    }

    @Test fun contactTextIsForTheContactAndHasNoPaymentDetails() {
        for (a in listOf(ContactAlert(ContactAlert.ALARM), ContactAlert(ContactAlert.LONG_SESSION))) {
            assertTrue(a.text().contains("Call them"), a.text())
            assertFalse(Regex("\\bYou(r|'re)?\\b").containsMatchIn(a.title() + " " + a.text().substringBefore("Call")), "speaks to the contact, not the victim")
            assertFalse(a.text().contains("₹") || a.text().contains("F_") || a.text().contains("RULE_"))
        }
    }

    @Test fun tokenHashIsOneWay() {
        val h = Push.hash(token)
        assertEquals(64, h.length)
        assertFalse(h.contains(token.take(10)))
        assertNotEquals(h, Push.hash(token + "x"))
    }
}

/** Held-payment approval: what the trusted contact's phone does with a payment id, and how the owner reads the server state. */
class HeldPaymentDecisionTest {
    private val uuid = "6abf5a43-0cc2-4520-a433-3156d87d55ac"

    private fun payment(method: String, state: String, order: String? = null) =
        com.satark.app.net.PaymentResponse(uuid, method, state, "500_2k", "h", razorpayOrderId = order)

    @Test fun linkRequestPushIsNotAnAlarmAndHasNoDecideButtons() {
        val a = ContactAlert.from(mapOf("type" to "link_request", "owner_device_id" to uuid, "payment_id" to uuid))
        assertTrue(a.isLinkRequest)
        assertFalse(a.canDecide)
        assertFalse(a.text().contains("http", ignoreCase = true))
        assertFalse(Regex("\\b(PIN|OTP)\\b", RegexOption.IGNORE_CASE).containsMatchIn(a.title() + a.text()))
    }

    @Test fun pushWithAPaymentIdAsksTheContactToDecide() {
        val a = ContactAlert.from(mapOf("type" to "alarm", "payment_id" to uuid))
        assertTrue(a.canDecide)
        assertEquals(uuid, a.paymentId)
    }

    @Test fun pushWithoutAPaymentIdOrWithABadOneStaysAPlainWarning() {
        assertFalse(ContactAlert.from(mapOf("type" to "alarm")).canDecide)
        assertFalse(ContactAlert.from(mapOf("type" to "alarm", "payment_id" to "")).canDecide)
        assertFalse(ContactAlert.from(mapOf("type" to "alarm", "payment_id" to "x".repeat(37))).canDecide)
        assertFalse(ContactAlert.from(mapOf("type" to "long_session", "payment_id" to uuid)).canDecide)
    }

    @Test fun contactNotificationNeverShowsAmountOrPayee() {
        val text = ContactAlert.from(mapOf("type" to "alarm", "payment_id" to uuid)).text()
        assertFalse(text.contains("₹")); assertFalse(text.contains("@"))
    }

    @Test fun ownerWaitsWhileHeld() =
        assertEquals(com.satark.app.payments.HoldResolution.Waiting, com.satark.app.payments.HoldResolution.of(payment("upi_intent", "held")))

    @Test fun blockedIsFinal() =
        assertEquals(com.satark.app.payments.HoldResolution.Blocked, com.satark.app.payments.HoldResolution.of(payment("checkout", "blocked")))

    @Test fun approvedUpiStartsTheHandOff() =
        assertEquals(com.satark.app.payments.HoldResolution.ApprovedUpi, com.satark.app.payments.HoldResolution.of(payment("upi_intent", "handed_off")))

    @Test fun approvedCheckoutNeedsItsOrder() {
        assertEquals(
            com.satark.app.payments.HoldResolution.ApprovedCheckout("order_1"),
            com.satark.app.payments.HoldResolution.of(payment("checkout", "approved", "order_1")),
        )
        // Approved by the contact but no order yet: the owner's app must fetch it.
        assertEquals(com.satark.app.payments.HoldResolution.ApprovedCheckout(null), com.satark.app.payments.HoldResolution.of(payment("checkout", "approved")))
    }

    @Test fun anythingElseDoesNothingAutomatic() {
        listOf("paid", "failed", "allowed", "created").forEach {
            assertEquals(com.satark.app.payments.HoldResolution.Unknown, com.satark.app.payments.HoldResolution.of(payment("checkout", it)), it)
        }
    }
}
