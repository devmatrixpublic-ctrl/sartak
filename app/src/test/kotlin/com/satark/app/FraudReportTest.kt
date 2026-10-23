package com.satark.app

import com.satark.app.ui.alerts.FraudReport
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class FraudReportTest {
    private val codes = listOf("F_UNK_CALL_ACTIVE", "F_NEW_PAYEE", "RULE_SIDELOAD_DURING_CALL")
    private val text = FraudReport.summary(1_700_000_000_000L, codes, listOf("You are on a call with someone not in your contacts."), 12_345.67)

    @Test fun summaryHasNoPhoneNumberVpaOrExactAmount() {
        assertFalse(Regex("\\d{6,}").containsMatchIn(text.replace(Regex("\\d{1,2} \\w{3} \\d{4}, \\d{2}:\\d{2}"), "")), "no long digit run (phone numbers)")
        assertFalse(Regex("[A-Za-z0-9._-]+@[A-Za-z0-9]+").containsMatchIn(text), "no UPI ID / email shape")
        assertFalse(text.contains("12345") || text.contains("12,345"), "no exact amount")
        assertFalse(Regex("(https?://|www\\.)", RegexOption.IGNORE_CASE).containsMatchIn(text), "no link")
    }

    @Test fun summaryNeverClaimsToHaveFiledAComplaint() {
        assertTrue(text.contains(FraudReport.LABEL))
        assertTrue(text.contains("has not filed a complaint"))
    }

    @Test fun summaryStatesBandSignalsAndCodes() {
        assertTrue(text.contains("Rs 10,000 to 50,000"))
        assertTrue(text.contains("call from someone not in contacts") && text.contains("payment to a new payee"))
        assertTrue(text.contains("F_NEW_PAYEE"))
    }

    @Test fun bandEdges() {
        assertEquals("under Rs 500", FraudReport.amountBand(499.99))
        assertEquals("Rs 500 to 2,000", FraudReport.amountBand(500.0))
        assertEquals("over Rs 2,00,000", FraudReport.amountBand(5e6))
        assertEquals("not applicable", FraudReport.amountBand(null))
    }

    @Test fun everyReasonCodeMapsToASignalType() {
        val all = org.json.JSONObject(java.io.File("../contracts/reason_codes.json").readText()).getJSONArray("codes")
        val missing = (0 until all.length()).map { all.getJSONObject(it).getString("code") }.filter { FraudReport.signalTypes(listOf(it)).isEmpty() }
        assertTrue(missing.isEmpty(), "codes without a signal type: $missing")
    }

    @Test fun helplineIs1930() = assertEquals("1930", FraudReport.HELPLINE)
}
