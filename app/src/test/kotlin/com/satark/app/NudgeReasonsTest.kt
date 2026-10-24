package com.satark.app

import com.satark.app.events.NudgePolicy
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class NudgeReasonsTest {
    @Test fun whileTheCallIsOpenTheNudgeSaysSo() {
        assertEquals(listOf("F_UNK_CALL_ACTIVE", "F_NEW_PAYEE", "F_LOG_AMT_RATIO"), NudgePolicy.reasons(callActive = true))
    }

    @Test fun afterTheCallEndedTheNudgeDoesNotClaimItIsStillOpen() {
        val r = NudgePolicy.reasons(callActive = false)
        assertFalse("F_UNK_CALL_ACTIVE" in r)
        assertTrue("F_UNK_CONTACT_RECENT" in r && "F_NEW_PAYEE" in r)
        assertEquals(3, r.size, "the screen shows at most three reasons")
    }

    @Test fun aNudgeStillNeedsAnUnknownContactANewPayeeAndAnAmountWellAboveTheUsual() {
        assertTrue(NudgePolicy.shouldNudge(true, true, 5_000.0, 161.57))
        assertFalse(NudgePolicy.shouldNudge(false, true, 5_000.0, 161.57), "no unknown contact")
        assertFalse(NudgePolicy.shouldNudge(true, false, 5_000.0, 161.57), "a known payee")
        assertFalse(NudgePolicy.shouldNudge(true, true, 300.0, 161.57), "under twice the usual")
    }
}
