package com.satark.app.account

/** What the sign-in screens accept and show for a phone number. India only for now (+91). */
object PhoneNumber {
    const val COUNTRY = "+91"
    const val CODE_LENGTH = 6
    const val NAME_MAX = 60

    /**
     * Digits only. A leading country code (91) or trunk zero that the person typed or pasted is dropped. Null unless what is left is a
     * 10-digit Indian mobile number, which starts with 6, 7, 8 or 9.
     */
    fun normalize(input: String): String? {
        var d = input.filter(Char::isDigit)
        if (d.length == 12 && d.startsWith("91")) d = d.drop(2)
        if (d.length == 11 && d.startsWith("0")) d = d.drop(1)
        return d.takeIf { it.length == 10 && it[0] in '6'..'9' }
    }

    fun e164(national: String) = COUNTRY + national

    /** "+91 •••••• 3210": enough to recognise it, not enough to read it out. */
    fun masked(e164: String): String {
        val national = e164.removePrefix(COUNTRY)
        return if (national.length < 4) COUNTRY else "$COUNTRY ${"•".repeat(national.length - 4)} ${national.takeLast(4)}"
    }

    fun isCode(input: String) = input.length == CODE_LENGTH && input.all(Char::isDigit)

    /** A name as typed: trimmed, inner whitespace folded, at most [NAME_MAX] characters; null when empty. */
    fun cleanName(input: String): String? =
        input.trim().replace(Regex("\\s+"), " ").take(NAME_MAX).trim().ifEmpty { null }
}
