package com.satark.app.drill

import kotlinx.serialization.Serializable

/**
 * Scam Inoculation Mode: a short, optional rehearsal of a scam call, played inside the app. Nothing here touches the detector, a real call,
 * a real payment or the network, and it never asks for a real OTP, PIN or card number (the "pressure" is a button, not a text box).
 */

/** The pressure moves a scam caller uses. Each has one rule the person can carry into a real call. */
enum class Tactic(val label: String, val rule: String) {
    AUTHORITY("Fear of a fake authority", "Real police, courts and customs do not phone to say you are in trouble. Hang up and look up the office yourself."),
    URGENCY("A countdown", "A real problem is still there after you hang up and check. A scammer needs you to decide before you can think."),
    SECRECY("“Tell no one”", "Anyone who says not to tell your family or your bank is the danger. Tell someone you trust straight away."),
    STAY_ON_VIDEO("Kept on the line", "You can end any call. Nobody can arrest, watch or “hold” you through a screen."),
    SHARE_OTP("Asking for a code", "Never read out an OTP, PIN or CVV. No real caller needs it."),
    SHARE_CARD("Asking for card details", "Your bank already has your card number. It never asks you to read it, or the digits on the back, over the phone."),
    INSTALL_APP("Installing an app", "Never install an app because someone on a call or a message told you to, least of all a screen-sharing app."),
    OPEN_LINK("A link to tap", "Do not tap links from strangers. Type the website yourself or open the company's own app."),
    ENTER_PIN("Your PIN “to receive” money", "You never enter a UPI PIN to receive money. A PIN is only for paying."),
    PAY_NOW("Pay now to fix it", "No real agency asks you to move money to prove your innocence or to a “safe account”. Do not pay a stranger."),
}

/**
 * One thing the person can do at a decision point. [safe] marks the one that protects them. [reaction] is what the caller says next, so the
 * rehearsal feels like a conversation and the push-back a real scammer gives is part of the lesson.
 */
data class DrillChoice(val id: String, val text: String, val safe: Boolean, val reaction: String)

/**
 * One beat of the call: the caller says [caller], the rehearsal pauses and asks [ask], and after the choice explains [why]
 * under [headline]. [satarkNote] says what Satark itself does about this move, when it does something.
 */
data class DrillStep(
    val tactic: Tactic,
    val caller: String,
    val ask: String,
    val choices: List<DrillChoice>,
    val why: String,
    val headline: String = "A real caller would never need this.",
    val satarkNote: String? = null,
)

data class DrillScript(
    val id: String,
    val title: String,
    val blurb: String,
    val callerName: String,
    val callerRole: String,
    val steps: List<DrillStep>,
) {
    /** The number shown on the practice call screen. Never a real number. */
    val callerNumber: String get() = "Unknown number"

    /** How long the caller is on the line, in seconds: what he says and how he replies. The call clock stops while the rehearsal is paused to explain. */
    val callSeconds: Int get() = steps.sumOf { s -> ((words(s.caller) + s.choices.map { words(it.reaction) }.average()) / SPEECH_WORDS_PER_SEC).toInt() }

    /** About how long the whole rehearsal takes: the call, a moment to choose at each beat, and reading each explanation. */
    val estimatedSeconds: Int get() = callSeconds + steps.sumOf { s -> ((words(s.headline) + words(s.why)) / READING_WORDS_PER_SEC).toInt() + DECIDE_SECONDS }

    /** [estimatedSeconds] in words, to the nearest half minute. */
    val lengthLabel: String get() {
        val halves = Math.round(estimatedSeconds / 30.0).toInt()
        return when {
            halves <= 2 -> "about a minute"
            halves % 2 == 1 -> "about ${halves / 2}½ minutes"
            else -> "about ${halves / 2} minutes"
        }
    }

    private fun words(t: String) = t.trim().split(Regex("\\s+")).count { it.isNotEmpty() }

    companion object {
        const val SPEECH_WORDS_PER_SEC = 2.5
        const val READING_WORDS_PER_SEC = 4.0
        const val DECIDE_SECONDS = 4
    }
}

/** What the person chose at one beat. */
data class DrillAnswer(val tactic: Tactic, val safe: Boolean)

/** A finished rehearsal, kept on this phone only so the home screen can say when the person last practised. */
@Serializable
data class DrillRecord(val scriptId: String, val atMs: Long, val spotted: Int, val total: Int)
