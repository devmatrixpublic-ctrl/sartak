package com.satark.app.push

/**
 * The code a trusted contact's Satark shows and the protected person pastes: "<device id>:<push token>".
 * The device id is the contact's Satark device id (a UUID from the server); the token is their Firebase push token,
 * which can itself contain ':'. POST /trusted-contact sends both (trusted_device_id <= 36 chars, fcm_token <= 4096).
 */
object PairingCode {
    data class Parsed(val deviceId: String, val pushToken: String)

    // FCM tokens are "<instance id>:<base64url>" (one ':'; very old ones have no prefix). Matching that shape, and
    // refusing a token that runs on into more token characters, stops pasted text glued to the code from being
    // swallowed into the token (which the server would accept and every alert would then silently fail).
    private val CODE = Regex(
        "([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})" +
            ":((?:[A-Za-z0-9_-]{1,64}:)?[A-Za-z0-9_-]{20,4000})(?![A-Za-z0-9_-])",
    )

    fun format(deviceId: String, pushToken: String) = "$deviceId:$pushToken"

    /**
     * Finds the code inside pasted text: messaging apps add words around it or wrap it over lines, so whitespace is
     * ignored and the first "<uuid>:<token>" wins. Null when there is no code.
     */
    fun parse(text: String): Parsed? {
        val m = CODE.find(text.filterNot(Char::isWhitespace)) ?: return null
        return Parsed(m.groupValues[1], m.groupValues[2])
    }
}
