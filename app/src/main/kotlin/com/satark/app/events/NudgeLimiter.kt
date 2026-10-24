package com.satark.app.events

/**
 * A ceiling on the amber nudge: at most [max] in any rolling [windowMs], so a genuine user cannot be nudged more often than
 * the alert budget (1 a month, ops/eval/reports/alert_budget.md) however busy they are. It never touches alarms or holds,
 * which come from the detector and are not rate-limited.
 *
 * The times are kept through [store] so a restart of the app (now common, see RestartReceiver) does not reset the count.
 */
class NudgeLimiter(
    private val store: Store,
    private val now: () -> Long = System::currentTimeMillis,
    private val max: Int = MAX_PER_WINDOW,
    private val windowMs: Long = WINDOW_MS,
) {
    interface Store {
        var times: List<Long>
    }

    /** True and counted if a nudge may be shown now; false if the budget for the window is already used. */
    @Synchronized
    fun tryAcquire(): Boolean {
        val t = now()
        val recent = store.times.filter { it in (t - windowMs)..t }
        if (recent.size >= max) {
            store.times = recent
            return false
        }
        store.times = recent + t
        return true
    }

    /** Nudges shown in the current window, for the history screen. */
    fun shownInWindow(): Int { val t = now(); return store.times.count { it in (t - windowMs)..t } }

    companion object {
        const val MAX_PER_WINDOW = 1
        const val WINDOW_MS = 30L * 24 * 3600_000
    }
}
