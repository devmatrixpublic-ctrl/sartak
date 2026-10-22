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
