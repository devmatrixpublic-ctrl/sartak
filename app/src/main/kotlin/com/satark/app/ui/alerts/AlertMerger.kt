package com.satark.app.ui.alerts

import com.satark.app.events.AlertStat

/**
 * Folds repeat alerts into one. An alert of the same kind (same mechanism and reasons) within [windowMs] of the last one
 * that was shown is counted but not shown again: no second screen, notification, pause or push to the trusted contact.
 * The last-shown time is kept in Room, so a restart does not reopen the window. A clock moved backwards never hides an alert.
 */
class AlertMerger(private val store: Store, private val windowMs: Long = WINDOW_MS) {
    interface Store {
        suspend fun get(key: String): AlertStat?
        suspend fun put(stat: AlertStat)
    }

    /** True when the alert should be shown; false when it was merged into one shown within the window. */
    suspend fun admit(key: String, nowMs: Long): Boolean {
        val s = store.get(key)
        val age = if (s == null) null else nowMs - s.lastShownMs
        if (s != null && age != null && age in 0 until windowMs) {
            store.put(s.copy(mergedCount = s.mergedCount + 1))
            return false
        }
        store.put(AlertStat(key, (s?.count ?: 0) + 1, s?.mergedCount ?: 0, nowMs))
        return true
    }

    companion object {
        const val WINDOW_MS = 60 * 60_000L

        /** Same kind of alert = same mechanism and same set of reasons, in any order. */
        fun keyOf(mechanism: String?, reasons: List<String>) = (mechanism ?: "none") + ":" + reasons.sorted().joinToString(",")
    }
}
