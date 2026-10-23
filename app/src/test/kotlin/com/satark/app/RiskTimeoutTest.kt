package com.satark.app

import com.satark.app.payments.RiskTimeout
import com.satark.app.payments.RiskTimeout.Fallback
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class RiskTimeoutTest {
    @Test fun budgetIs300Ms() = assertEquals(300L, RiskTimeout.MS)

    @Test fun aCheckoutGetsTimeToCreateTheOrderAtRazorpay() {
        assertEquals(RiskTimeout.MS, RiskTimeout.budgetMs("upi_intent"))
        assertTrue(RiskTimeout.budgetMs("checkout") >= 5_000)
        assertTrue(RiskTimeout.SIGN_IN_MS > RiskTimeout.MS)
    }

    @Test fun anAlarmIsHeldWhateverTheMethod() {
        assertEquals(Fallback.HOLD, RiskTimeout.fallback(alarmed = true, method = "upi_intent"))
        assertEquals(Fallback.HOLD, RiskTimeout.fallback(alarmed = true, method = "checkout"))
    }

    @Test fun aCleanUpiPaymentGoesAheadLocally() = assertEquals(Fallback.ALLOW_LOCAL, RiskTimeout.fallback(false, "upi_intent"))

    @Test fun aCleanCheckoutCannotContinueWithoutTheServersOrder() = assertEquals(Fallback.FAIL, RiskTimeout.fallback(false, "checkout"))

    @Test fun neverAutoConfirmsAnAlarm() {
        for (method in listOf("upi_intent", "checkout")) assertFalse(RiskTimeout.fallback(true, method) in listOf(Fallback.ALLOW_LOCAL))
    }

    @Test fun localIdsAreRecognisedSoNothingIsReportedForThem() {
        assertTrue(RiskTimeout.isLocal(RiskTimeout.LOCAL_PREFIX + "abc"))
        assertFalse(RiskTimeout.isLocal("6abf5a43-0cc2-4520-a433-3156d87d55ac"))
    }
}
