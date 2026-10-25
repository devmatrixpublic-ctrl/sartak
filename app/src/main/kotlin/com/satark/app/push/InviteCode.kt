package com.satark.app.push

/**
 * The short invite code a would-be trusted contact reads out to the person they will protect: eight characters shown as XXXX-XXXX.
 * It uses no 0, O, 1, I or L, so it survives being read over a phone call. The server is what checks it; this only tidies what was typed.
 */
object InviteCode {
    const val ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    const val LENGTH = 8

    /** "k7m4 q2xh", "K7M4-Q2XH" and "k7m4q2xh" all give "K7M4-Q2XH"; anything that cannot be a code gives null. */
    fun normalize(input: String): String? {
        val s = input.uppercase().filter { it.isLetterOrDigit() }
        if (s.length != LENGTH || s.any { it !in ALPHABET }) return null
        return s.substring(0, 4) + "-" + s.substring(4)
    }
}
