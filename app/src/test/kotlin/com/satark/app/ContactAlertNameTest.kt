package com.satark.app

import com.satark.app.push.ContactAlert
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ContactAlertNameTest {
    private fun alert(type: String, name: String? = null) =
        ContactAlert.from(mapOf("type" to type) + (name?.let { mapOf("owner_name" to it) } ?: emptyMap()))

    @Test fun aNameIsCarriedAndShownInTheTitle() {
        assertEquals("Priya may be being scammed", alert("alarm", "Priya").title())
        assertEquals("Priya asked you to be their trusted contact", alert("link_request", "Priya").title())
        assertEquals("Priya asked to turn Satark off", alert("protection_off_requested", "Priya").title())
        assertEquals("Satark was turned off on Priya's phone", alert("protection_off", "Priya").title())
        assertEquals("Satark can now be removed from Priya's phone", alert("removal_guard_off", "Priya").title())
        assertEquals("Priya is on a long video call with an unknown person", alert("long_session", "Priya").title())
    }

    @Test fun withoutANameTheOldWordingIsUnchanged() {
        assertEquals("Someone you protect may be being scammed", alert("alarm").title())
        assertEquals("Someone asked you to be their trusted contact", alert("link_request").title())
        assertEquals("Someone you protect asked to turn Satark off", alert("protection_off_requested").title())
        assertEquals("Satark was turned off on their phone", alert("protection_off").title())
        assertEquals("Satark can now be removed from their phone", alert("removal_guard_off").title())
        assertEquals("Long video call with an unknown person", alert("long_session").title())
    }

    @Test fun aHostileOrEmptyNameIsCleanedOrDropped() {
        assertNull(alert("alarm", "   ").ownerName)
        assertNull(alert("alarm", "\n\u0007").ownerName)
        assertEquals("Call 100 now", alert("alarm", "Call\n100\u0007 now").ownerName?.replace("Call100", "Call 100"))
        assertTrue((alert("alarm", "x".repeat(200)).ownerName ?: "").length <= 60)
        assertFalse(alert("alarm", "<b>Ved</b>").ownerName!!.contains('<'))
    }
}
