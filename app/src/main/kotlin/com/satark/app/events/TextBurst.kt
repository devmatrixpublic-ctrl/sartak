package com.satark.app.events

/**
 * Scammers often message first, and keep messaging, to build pressure before they call or ask for a payment. This counts texts
 * from numbers that are not in the contacts and says so when [threshold] of them arrive within [windowMs]. Only the arrival
 * times are kept (nothing about who sent them or what they said), so a restart of the app does not lose the count.
 *
 * It is an app-level warning, like the nudge: the detector's own decision is untouched. After it fires the count starts again,
 * so a long run of texts warns once per [threshold], not once per text.
 */
class TextBurst(
    private val store: Store,
    private val threshold: Int = THRESHOLD,
    private val windowMs: Long = WINDOW_MS,
) {
    interface Store {
        var times: List<Long>
    }

    /** Count one more stranger text at [nowMs]. True when this one completes a burst. */
    @Synchronized
    fun record(nowMs: Long): Boolean {
        val recent = (store.times + nowMs).filter { it in (nowMs - windowMs)..nowMs }
        return if (recent.size >= threshold) {
            store.times = emptyList()
            true
        } else {
            store.times = recent
            false
        }
    }

    companion object {
        const val THRESHOLD = 3
        const val WINDOW_MS = 10 * 60_000L
    }
}
