package com.satark.app

import com.satark.app.events.AgeProfile
import com.satark.app.events.HighValueNewPayee
import com.satark.detector.Event
import com.satark.detector.EventType
import com.satark.detector.Level
import com.satark.detector.PaymentType
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class AgeProfileTest {
    private fun pay(amount: Double) =
        Event(0, EventType.PAYMENT_ATTEMPT, payeeId = "P", payeeIsNew = true, amountInr = amount, paymentType = PaymentType.P2P)

    private fun holds(ageYears: Int?, amount: Double) =
        HighValueNewPayee(AgeProfile.highValueThreshold(ageYears)).onEvent(pay(amount), true, true).level == Level.HARD

    @Test fun under22IsHeldFromTenThousandEveryoneElseFromTwentyFiveThousand() {
        assertEquals(10_000.0, AgeProfile.highValueThreshold(21))
        assertEquals(10_000.0, AgeProfile.highValueThreshold(17))
        assertEquals(25_000.0, AgeProfile.highValueThreshold(22), "22 is the first age that is not young")
        assertEquals(25_000.0, AgeProfile.highValueThreshold(45))
        assertEquals(25_000.0, AgeProfile.highValueThreshold(70))
        assertEquals(25_000.0, AgeProfile.highValueThreshold(null), "no age given")
    }

    @Test fun theRuleUsesTheAgeSpecificAmount() {
        assertTrue(holds(21, 10_000.0))
        assertFalse(holds(21, 9_999.0))
        assertFalse(holds(22, 10_000.0), "a 22-year-old needs Rs 25,000")
        assertTrue(holds(22, 25_000.0))
        assertFalse(holds(null, 10_000.0))
    }

    @Test fun ageMapsToTheModelsOwnBands() {
        assertNull(AgeProfile.bandOf(null))
        assertNull(AgeProfile.bandOf(16), "the model has no band under 18, so the pooled threshold applies")
        assertEquals("18-35", AgeProfile.bandOf(18))
        assertEquals("18-35", AgeProfile.bandOf(35))
        assertEquals("36-59", AgeProfile.bandOf(36))
        assertEquals("36-59", AgeProfile.bandOf(59))
        assertEquals("60+", AgeProfile.bandOf(60))
        assertEquals("60+", AgeProfile.bandOf(95))
    }

    @Test fun onlyBelievableAgesAreAccepted() {
        assertEquals(21, AgeProfile.parse(" 21 "))
        assertEquals(10, AgeProfile.parse("10"))
        assertNull(AgeProfile.parse("9"))
        assertNull(AgeProfile.parse("111"))
        assertNull(AgeProfile.parse(""))
        assertNull(AgeProfile.parse("twenty"))
    }
}
