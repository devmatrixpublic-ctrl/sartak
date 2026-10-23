package com.satark.app.ui.alerts

/**
 * The app-side rungs of the friction ladder (docs: satark_novel_improvements_roadmap.md, section 3.4). They only ever
 * add caution on top of the detector's decision: nothing here can release a held payment or lower a score, and
 * nothing here leaves the phone.
 *
 * Rung 1: a scam playbook matched to the reasons Satark gave.
 * Rung 2: "What is this payment for?" Each answer explains the matching scam.
 * Rung 3: a 15-minute pause on payments started in Satark, then a phrase typed once before paying again.
 */
object Friction {
    data class Playbook(val title: String, val text: String)

    /** Rung 1. Most specific scam first; every reason code (and none) gets an answer. */
    fun playbook(codes: List<String>): Playbook {
        val c = codes.map { it.uppercase() }.toSet()
        return when {
            "F_UNK_VIDEO_ACTIVE" in c || "RULE_LONG_SESSION" in c -> Playbook(
                "\"Digital arrest\" is not real",
                "Police, CBI, customs and courts never question anyone on a video call and never ask for money to " +
                    "\"clear your name\". End the call.",
            )
            "F_WATCHLIST_APP" in c -> Playbook(
                "No one genuine needs to see your screen",
                "Banks, police and companies never ask you to install a screen-sharing or remote-control app. " +
                    "Close it and uninstall it before you do anything else.",
            )
            "F_INSTALL_SIDELOAD_DURING_UNK" in c || "RULE_SIDELOAD_DURING_CALL" in c -> Playbook(
                "Apps sent as a link or file are a trap",
                "An app from outside Google Play can read your messages and OTPs. Do not open it. Uninstall it, " +
                    "and call your bank on the number on your card.",
            )
            c.any { it in UNKNOWN_CONTACT } -> Playbook(
                "Someone you don't know is guiding this",
                "Hang up. Call the person or company yourself, on a number you already have, before you pay.",
            )
            else -> Playbook(
                "Check before you pay someone new",
                "Confirm who this is on a number you already know. Money sent by UPI is very hard to get back.",
            )
        }
    }

    private val UNKNOWN_CONTACT = setOf(
        "F_UNK_CONTACT_RECENT", "F_UNK_CALL_ACTIVE", "F_MINS_SINCE_UNK_LOG", "F_INSTALL_PLAY_DURING_UNK",
        "F_PAYEE_ADDED_AFTER_UNK", "F_UNK_X_NEWPAYEE", "F_OCSS_ORDERED",
    )

    /** Rung 2. The answers coached victims are told to give, and the scam behind each one. */
    enum class Purpose(val label: String, val reply: String) {
        AUTHORITY(
            "A fine, case or \"verification\" for police, CBI, customs or a court",
            "This is the \"digital arrest\" scam. No officer asks for money on a call, and no one is ever arrested " +
                "over a video call. Hang up now.",
        ),
        KYC(
            "KYC, a refund, a parcel, or to unblock my bank account or SIM",
            "Banks, couriers and TRAI never ask you to pay or install an app to fix KYC, a refund or a parcel. " +
                "Hang up and call the number on your bank card.",
        ),
        FAMILY(
            "A family member or friend in trouble",
            "Scammers pretend to be a relative in an emergency. Call that person on the number you already have " +
                "before you send anything.",
        ),
        OFFER(
            "An investment, a job or a prize",
            "Returns, jobs or prizes that need money first are a common scam. Real ones never ask you to pay to " +
                "receive money.",
        ),
        PURCHASE(
            "Something I bought, or a bill",
            "If someone on the phone is telling you how to pay, stop. Check the bill yourself in the shop's own app " +
                "or website.",
        ),
        TOLD(
            "Someone told me what to choose here",
            "Scammers tell people exactly what to say. Hang up. Anyone genuine will wait while you check.",
        ),
    }

    /** Rung 3. */
    const val PAUSE_MS = 15 * 60_000L
    /** "Hold payment 30 minutes" on the Hard screen; also the longest any pause can be. */
    const val HOLD_MS = 30 * 60_000L
    const val PHRASE = "No one is telling me to make this payment"

    /** Case, punctuation and spacing do not matter; the words do. */
    fun phraseMatches(typed: String): Boolean = normalise(typed) == normalise(PHRASE)

    private fun normalise(s: String) = s.lowercase().replace(Regex("[^a-z ]"), " ").split(' ').filter(String::isNotEmpty)

    /**
     * Time left on a pause that ends at [untilMs]. A clock moved backwards cannot stretch it beyond [HOLD_MS], and a
     * clock moved forwards just ends it (the phrase is still asked for).
     */
    fun remainingMs(untilMs: Long, nowMs: Long): Long = (untilMs - nowMs).coerceIn(0, HOLD_MS)

    /** "14:05" for the countdown. */
    fun clock(ms: Long): String {
        val s = (ms + 999) / 1000
        return String.format(java.util.Locale.ROOT, "%d:%02d", s / 60, s % 60)
    }
}

/**
 * Rung 3 state: after a scam warning, payments started in Satark wait [Friction.PAUSE_MS], then the person types
 * [Friction.PHRASE] once. Kept in the encrypted store, so closing the app or restarting the phone does not skip it.
 * The detector still checks every payment afterwards; this never lets a held payment through.
 */
class PaymentPause(private val store: Store, private val now: () -> Long = System::currentTimeMillis) {
    interface Store {
        var untilMs: Long
        var phraseOwed: Boolean
    }

    sealed interface State {
        data object Clear : State
        data class Waiting(val untilMs: Long) : State
        data object PhraseOwed : State
    }

    private val _state = kotlinx.coroutines.flow.MutableStateFlow(read())
    val state: kotlinx.coroutines.flow.StateFlow<State> = _state

    /** A new warning (re)starts the full pause. */
    fun start(durationMs: Long = Friction.PAUSE_MS) {
        store.untilMs = now() + durationMs.coerceIn(0, Friction.HOLD_MS)
        store.phraseOwed = true
        refresh()
    }

    fun refresh() { _state.value = read() }

    /** Accepted only once the wait is over and the words match. */
    fun confirm(typed: String): Boolean {
        if (read() != State.PhraseOwed || !Friction.phraseMatches(typed)) return false
        store.phraseOwed = false
        refresh()
        return true
    }

    /** Debug builds only (developer section), so testers are not stuck for 15 minutes. */
    fun clearForTesting() {
        store.untilMs = 0
        store.phraseOwed = false
        refresh()
    }

    private fun read(): State {
        val t = now()
        var until = store.untilMs
        if (until - t > Friction.HOLD_MS) { until = t + Friction.HOLD_MS; store.untilMs = until } // clock moved back
        return when {
            until > t -> State.Waiting(until)
            store.phraseOwed -> State.PhraseOwed
            else -> State.Clear
        }
    }
}
