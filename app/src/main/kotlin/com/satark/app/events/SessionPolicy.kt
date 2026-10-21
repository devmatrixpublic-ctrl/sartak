package com.satark.app.events

import com.satark.detector.Event
import com.satark.detector.EventType

/**
 * The app's session rules, applied to every event before it reaches the detector (pure, no Android; unit-tested and
 * run over the 36 test vectors). Session policy lives in the app, not the detector.
 */
class SessionPolicy(
    private val idleResetMs: Long = IDLE_RESET_MS,
    private val videoOrigin: VideoOrigin = VideoOrigin(),
) {
    /** The event to give the detector, and whether to reset the detector's session first. */
    class Step(val event: Event, val resetFirst: Boolean)

    var unknownCallActive = false
        private set
    var lastEventTMs = 0L
        private set
    /** Time of the last event replayed after a restart (see EventDispatcher.restoreSession). */
    var restoredUpTo: Long? = null

    private var callOpen = false
    private var videoOpenSince: Long? = null

    /** Null when the event must be ignored. */
    fun prepare(raw: Event): Step? {
        val e = videoOrigin.classify(raw)
        // A CALL_START with no caller info while a call is already open (e.g. the app restarted mid-call and only saw
        // the current call state) carries nothing new and must not erase that the open call is from an unknown number.
        if (e.type == EventType.CALL_START && e.callerKnown == null && callOpen) return null
        // Sources report the current state when they start (call idle, no video app in front). Those closing events
        // only matter if a restored session left a call or video open; otherwise they are noise.
        if (e.type == EventType.CALL_END && !callOpen) return null
        if (e.type == EventType.VIDEO_SESSION_START && videoOpenSince != null) return null // keep the original start
        var ev = e
        if (e.type == EventType.VIDEO_SESSION_END) {
            val since = videoOpenSince ?: return null
            // A start-up "no video now" end (no package) is dated at the last thing we actually saw, never "now",
            // so a restart cannot stretch a session into a false long-session alarm.
            if (e.appPackage == null) ev = e.copy(tMs = maxOf(since, minOf(e.tMs, restoredUpTo ?: e.tMs)))
        }
        // A new session only after a long silence, and never while a call or video session is open. The detector's
        // features carry their own time windows; M2's numbers were measured on sessions up to 96 h long with quiet
        // gaps up to 88 h and no reset, so resetting earlier (it used to be after 2 h) changes its decisions: it
        // dropped the long-session alarm of an open unknown video call (test vectors S050008, S050139).
        val reset = lastEventTMs != 0L && e.tMs - lastEventTMs > idleResetMs && !callOpen && videoOpenSince == null
        lastEventTMs = ev.tMs
        track(ev)
        return Step(ev, reset)
    }

    companion object { const val IDLE_RESET_MS = 96 * 3600_000L } // longest SatarkSim session

    private fun track(e: Event) {
        when (e.type) {
            EventType.CALL_START -> { unknownCallActive = e.callerKnown == false; callOpen = true }
            EventType.CALL_END -> { unknownCallActive = false; callOpen = false }
            EventType.VIDEO_SESSION_START -> videoOpenSince = e.tMs
            EventType.VIDEO_SESSION_END -> videoOpenSince = null
            else -> Unit
        }
    }
}
