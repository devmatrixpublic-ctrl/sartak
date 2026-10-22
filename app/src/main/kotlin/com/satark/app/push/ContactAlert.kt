package com.satark.app.push

/**
 * An alert pushed to a trusted contact (POST /alert on the protected person's phone -> server -> FCM -> here).
 *
 * The text is written for the contact. The reason sentences in strings.xml address the protected person ("You are
 * paying..."), so they are not repeated here; the contact's job is to call and check. That also keeps the details of
 * someone else's payment off the contact's lock screen.
 */
data class ContactAlert(val type: String) {
    val isLongSession get() = type == LONG_SESSION

    fun title(): String =
        if (isLongSession) "Long video call with an unknown person" else "Someone you protect may be being scammed"

    fun text(): String =
        if (isLongSession) "The person you protect has been on a video call with someone they do not know for a long time. " +
            "Call them now and check they are safe."
        else "Satark on their phone saw signs of a scam. Call them now and check they are safe before they send any money."

    companion object {
        const val ALARM = "alarm"
        const val LONG_SESSION = "long_session"

        /** From the FCM data payload (`type`: alarm | long_session); anything else is treated as an alarm. */
        fun from(data: Map<String, String>): ContactAlert =
            ContactAlert(data["type"]?.takeIf { it == ALARM || it == LONG_SESSION } ?: ALARM)
    }
}
