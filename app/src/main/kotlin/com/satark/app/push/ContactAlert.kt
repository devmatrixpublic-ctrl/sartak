package com.satark.app.push

/**
 * An alert pushed to a trusted contact (POST /alert on the protected person's phone -> server -> FCM -> here).
 *
 * The text is written for the contact. The reason sentences in strings.xml address the protected person ("You are
 * paying..."), so they are not repeated here; the contact's job is to call and check. That also keeps the details of
 * someone else's payment off the contact's lock screen.
 */
data class ContactAlert(val type: String, val paymentId: String? = null, val ownerName: String? = null) {
    val isLongSession get() = type == LONG_SESSION
    val isLinkRequest get() = type == LINK_REQUEST
    /** Someone switched Satark off, or made it removable: the contact is asked to call, not to decide a payment. */
    val isProtectionChange get() = type in PROTECTION_TYPES

    /** "Priya" when the person signed in with a name, else the wording for "someone you protect". */
    private val who get() = ownerName ?: "Someone you protect"
    private val theirPhone get() = ownerName?.let { "$it's phone" } ?: "their phone"

    fun title(): String =
        if (isLinkRequest) "${ownerName ?: "Someone"} asked you to be their trusted contact"
        else if (type == PROTECTION_OFF_REQUESTED) "${if (ownerName != null) ownerName else "Someone you protect"} asked to turn Satark off"
        else if (type == PROTECTION_OFF) "Satark was turned off on $theirPhone"
        else if (type == REMOVAL_GUARD_OFF) "Satark can now be removed from $theirPhone"
        else if (isLongSession) (if (ownerName != null) "$ownerName is on a long video call with an unknown person" else "Long video call with an unknown person")
        else "$who may be being scammed"

    /** Alerts that carry a held payment ask the contact to decide, not just to call. */
    val canDecide get() = paymentId != null && !isLongSession && !isLinkRequest

    fun text(): String =
        if (isLinkRequest) "Open Satark to accept or decline. Only accept if you know them."
        else if (isProtectionChange) "A scammer may be telling them to do this. Call them now, on a number you know, and check they are safe."
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
        const val PROTECTION_OFF_REQUESTED = "protection_off_requested"
        const val PROTECTION_OFF = "protection_off"
        const val REMOVAL_GUARD_OFF = "removal_guard_off"
        val PROTECTION_TYPES = setOf(PROTECTION_OFF_REQUESTED, PROTECTION_OFF, REMOVAL_GUARD_OFF)

        /** From the FCM data payload (`type`: alarm | long_session | link_request | a protection type); anything else is treated as an alarm. */
        fun from(data: Map<String, String>): ContactAlert =
            ContactAlert(
                data["type"]?.takeIf { it == ALARM || it == LONG_SESSION || it == LINK_REQUEST || it in PROTECTION_TYPES } ?: ALARM,
                data["payment_id"]?.takeIf { it.length in 1..36 },
                data["owner_name"]?.filter { it.isLetterOrDigit() || it == ' ' || it in ".'-" }?.trim()?.take(60)?.takeIf { it.isNotEmpty() },
            )
    }
}
