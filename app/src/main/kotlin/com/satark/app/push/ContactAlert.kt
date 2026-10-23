package com.satark.app.push

/**
 * An alert pushed to a trusted contact (POST /alert on the protected person's phone -> server -> FCM -> here).
 *
 * The text is written for the contact. The reason sentences in strings.xml address the protected person ("You are
 * paying..."), so they are not repeated here; the contact's job is to call and check. That also keeps the details of
 * someone else's payment off the contact's lock screen.
 */
data class ContactAlert(val type: String, val paymentId: String? = null) {
    val isLongSession get() = type == LONG_SESSION
    val isLinkRequest get() = type == LINK_REQUEST

    fun title(): String =
        if (isLinkRequest) "Someone asked you to be their trusted contact"
        else if (isLongSession) "Long video call with an unknown person" else "Someone you protect may be being scammed"

    /** Alerts that carry a held payment ask the contact to decide, not just to call. */
    val canDecide get() = paymentId != null && !isLongSession && !isLinkRequest

    fun text(): String =
        if (isLinkRequest) "Open Satark to accept or decline. Only accept if you know them."
        else if (canDecide) "They are trying to send money and Satark put it on hold. Call them first, then approve or block it here."
        else textBase()

    private fun textBase(): String =
        if (isLongSession) "The person you protect has been on a video call with someone they do not know for a long time. " +
            "Call them now and check they are safe."
        else "Satark on their phone saw signs of a scam. Call them now and check they are safe before they send any money."

    companion object {
        const val ALARM = "alarm"
        const val LONG_SESSION = "long_session"
        const val LINK_REQUEST = "link_request"

        /** From the FCM data payload (`type`: alarm | long_session); anything else is treated as an alarm. */
        fun from(data: Map<String, String>): ContactAlert =
            ContactAlert(
                data["type"]?.takeIf { it == ALARM || it == LONG_SESSION || it == LINK_REQUEST } ?: ALARM,
                data["payment_id"]?.takeIf { it.length in 1..36 },
            )
    }
}
