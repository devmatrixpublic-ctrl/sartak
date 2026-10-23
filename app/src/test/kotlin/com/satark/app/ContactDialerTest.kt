package com.satark.app

import com.satark.app.ui.alerts.ContactDialer
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class ContactDialerTest {
    @Test fun formatsANumberForTheDialler() {
        assertEquals("tel:+919876543210", ContactDialer.telUri("+91 98765-43210"))
        assertEquals("tel:9876543210", ContactDialer.telUri("(98765) 43210"))
    }

    @Test fun noUsableNumberMeansAnEmptyDialler() {
        assertNull(ContactDialer.telUri(null))
        assertNull(ContactDialer.telUri(""))
        assertNull(ContactDialer.telUri("ab"))
        assertNull(ContactDialer.telUri("12"))
    }

    @Test fun aPlusInTheMiddleIsDroppedSoNothingOddReachesTheDialler() =
        assertEquals("tel:12345", ContactDialer.telUri("123+45"))
}
