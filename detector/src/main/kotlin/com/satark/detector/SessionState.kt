package com.satark.detector

/**
 * Per-session evidence, advanced one event at a time (port of satark_detector.session_features).
 *
 * "Unknown" means the caller is reported as not in contacts (`callerKnown == false`).
 * Missing-signal defaults (contracts/schema.json): a null `callerKnown` counts as a known contact (no unknown-contact
 * evidence); a null `installSource` is neither Play nor sideload; a null `appPackage` is never on the watch-list;
 * a null `payeeIsNew` is false; a null `payeeId` is neither remembered nor counted as a repeat.
 * Faithful to the reference, `unkT` (first unknown contact) is never cleared within a session; it is also set by an
 * unknown video session.
 */
class SessionState {
    class Install(val tMs: Long, val source: InstallSource?, val pkg: String?)

    var unkT: Long? = null
    var callActive = false
    var videoUnkT: Long? = null
    var videoActive = false
    val installs = ArrayList<Install>()
    var watchlistSeen = false
    val payeeAddedT = HashMap<String, Long>()
    val paidTo = HashMap<String, Int>()

    // consecutive-duplicate filter state (the reference compares each event with the previous RAW event)
    private var lastKey: String? = null
    private var lastT = 0L

    /** True when this event repeats the previous raw event (same type/app/payee/amount) within [windowMs]. */
    fun isDuplicate(e: Event, windowMs: Long): Boolean {
        val key = "${e.type}|${e.appPackage ?: ""}|${e.payeeId ?: ""}|${e.amountInr?.toString() ?: ""}"
        val dup = key == lastKey && kotlin.math.abs(e.tMs - lastT) <= windowMs
        lastKey = key
        lastT = e.tMs
        return dup
    }

    fun reset() {
        unkT = null; callActive = false; videoUnkT = null; videoActive = false
        installs.clear(); watchlistSeen = false; payeeAddedT.clear(); paidTo.clear()
        lastKey = null; lastT = 0L
    }
}
