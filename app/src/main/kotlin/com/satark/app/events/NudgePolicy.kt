package com.satark.app.events

/**
 * When the amber "Take a moment" nudge is shown. The detector's own decision is untouched: this is only the app's choice of
 * when a softer warning is worth a person's attention.
 *
 * The nudge used to fire for any payment to a new payee during an unknown call. In the simulator that was 2.3% of genuine
 * payments, about 0.85 a month for the average user and 1.85 for the busiest (ops/eval/reports/alert_budget.md), too often to
 * stay credible. Requiring the amount to be at least twice the person's usual payment cuts that by about 39%.
 */
object NudgePolicy {
    const val MIN_RATIO = 2.0

    /** The reasons shown under the nudge, in the same reason-code language as an alarm (strings in values/ and values-hi/). */
    val REASONS = listOf("F_UNK_CALL_ACTIVE", "F_NEW_PAYEE", "F_LOG_AMT_RATIO")

    /** The call itself while it is open; afterwards, that someone the person does not know reached them recently. */
    fun reasons(callActive: Boolean): List<String> =
        if (callActive) REASONS else listOf("F_UNK_CONTACT_RECENT", "F_NEW_PAYEE", "F_LOG_AMT_RATIO")

    fun shouldNudge(unknownContactRecent: Boolean, payeeIsNew: Boolean?, amountInr: Double?, usualPaymentInr: Double): Boolean {
        if (!unknownContactRecent || payeeIsNew != true) return false
        val amount = amountInr ?: return false
        if (!amount.isFinite() || !usualPaymentInr.isFinite() || usualPaymentInr < 0) return false
        return amount >= MIN_RATIO * usualPaymentInr
    }
}
