package com.satark.app.events

/**
 * What the app does with the age a person may type in. It is optional, stays on this phone, and is used for two things only:
 * which cohort threshold the detector uses (the model's own age bands, as calibrated), and the amount at which
 * [HighValueNewPayee] holds a payment to a new payee. Under [YOUNG_BELOW] that amount is lower (assumed to be a student whose
 * usual payments are small), so a smaller sum to a new payee after an unknown call is already worth a pause.
 */
object AgeProfile {
    const val YOUNG_BELOW = 22
    const val MIN_AGE = 10
    const val MAX_AGE = 110

    /** The detector's cohort ("18-35", "36-59", "60+"). Null (the pooled threshold) when no age is given or the person is under 18. */
    fun bandOf(ageYears: Int?): String? = when {
        ageYears == null || ageYears < 18 -> null
        ageYears <= 35 -> "18-35"
        ageYears <= 59 -> "36-59"
        else -> "60+"
    }

    fun isYoung(ageYears: Int?): Boolean = ageYears != null && ageYears < YOUNG_BELOW

    /** The new-payee hold amount for this age: Rs 10,000 under [YOUNG_BELOW], otherwise Rs 25,000 (also when no age is given). */
    fun highValueThreshold(ageYears: Int?): Double =
        if (isYoung(ageYears)) HighValueNewPayee.YOUNG_THRESHOLD_INR else HighValueNewPayee.THRESHOLD_INR

    /** A typed age, or null when it is empty or not a believable number of years. */
    fun parse(text: String): Int? = text.trim().toIntOrNull()?.takeIf { it in MIN_AGE..MAX_AGE }
}
