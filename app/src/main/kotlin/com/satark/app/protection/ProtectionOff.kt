package com.satark.app.protection

/**
 * Turning Satark's protection off is not instant. After the owner check the person asks; protection stays ON for [WAIT_MS] and the
 * trusted contact is told at once, so a scammer who talks someone into switching it off has to keep them on the phone for half an
 * hour while the family is already calling. Cancelling is always immediate. When the wait ends, protection goes off and the contact
 * is told again.
 *
 * A coached person can still wait it out: the point is time and a witness, not a wall. The wait is measured on two clocks, so moving
 * the phone's date forward does not skip it: it ends only when the wall clock has reached the due time AND the phone's uptime clock
 * has run for the whole wait (or the phone restarted since, which resets the uptime clock; then the wall clock decides).
 */
class ProtectionOff(
    private val store: Store,
    private val wallNow: () -> Long,
    private val uptimeNow: () -> Long,
    /** Tell the trusted contact (a no-op when none is linked). Queued by the caller if the phone is offline. */
    private val tell: suspend (type: String) -> Unit,
    private val turnOff: () -> Unit,
    /** Ask for [completeIfDue] to be called after this many milliseconds (WorkManager in the app). */
    private val schedule: (delayMs: Long) -> Unit = {},
    /** How long the wait lasts: [WAIT_MS], or shorter in a labelled demo build. */
    private val waitMs: Long = WAIT_MS,
) {
    interface Store {
        /** Wall-clock time the wait ends; 0 = nothing pending. */
        var dueAtMs: Long
        /** Uptime clock when the wait began. */
        var startedUptimeMs: Long
    }

    val pending: Boolean get() = store.dueAtMs > 0

    /** Milliseconds left, or null when nothing is pending. */
    fun remainingMs(): Long? {
        if (!pending) return null
        val byWall = store.dueAtMs - wallNow()
        val sinceStart = uptimeNow() - store.startedUptimeMs
        val byUptime = if (sinceStart < 0) byWall else waitMs - sinceStart // negative = the phone restarted: trust the wall clock
        return maxOf(byWall, byUptime, 0L)
    }

    /** Begin the wait and tell the contact now. False when one is already running. */
    suspend fun request(): Boolean {
        if (pending) return false
        store.dueAtMs = wallNow() + waitMs
        store.startedUptimeMs = uptimeNow()
        schedule(waitMs)
        tell(TYPE_REQUESTED)
        return true
    }

    /** The person changed their mind. No owner check: keeping protection on is always allowed. */
    fun cancel() {
        store.dueAtMs = 0
        store.startedUptimeMs = 0
    }

    /** Turn protection off and tell the contact if the wait is over. True when it did. */
    suspend fun completeIfDue(): Boolean {
        val left = remainingMs() ?: return false
        if (left > 0) {
            schedule(left) // woke early (clock changed, or the work ran too soon): wait for the rest
            return false
        }
        cancel()
        turnOff()
        tell(TYPE_OFF)
        return true
    }

    companion object {
        const val WAIT_MS = 30 * 60_000L

        /** Alert types the server sends to the trusted contact (contracts/api.yaml). */
        const val TYPE_REQUESTED = "protection_off_requested"
        const val TYPE_OFF = "protection_off"
        const val TYPE_REMOVAL_GUARD_OFF = "removal_guard_off"
    }
}
