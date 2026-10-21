package com.satark.app.events

import com.satark.detector.Event
import com.satark.detector.EventType

/**
 * Android cannot tell who is on the other end of a WhatsApp/Meet video session, so the usage source sends
 * VIDEO_SESSION_START with caller_known = null, which the detector reads as "not unknown". The digital-arrest
 * playbook moves an unknown caller onto video, so: a video session that starts during an unknown call, or within
 * [linkWindowMs] after one ended, is treated as unknown (detector/INTEGRATION_NOTES.md #6). Known or unknown values
 * that a source did supply are never changed.
 */
class VideoOrigin(private val linkWindowMs: Long = DEFAULT_LINK_WINDOW_MS) {
    private var unknownCallActive = false
    private var lastUnknownCallEnd: Long? = null

    fun classify(e: Event): Event {
        when (e.type) {
            EventType.CALL_START -> if (e.callerKnown != null) unknownCallActive = e.callerKnown == false
            EventType.CALL_END -> { if (unknownCallActive) lastUnknownCallEnd = e.tMs; unknownCallActive = false }
            EventType.VIDEO_SESSION_START -> if (e.callerKnown == null) {
                val recent = lastUnknownCallEnd?.let { e.tMs - it in 0..linkWindowMs } == true
                if (unknownCallActive || recent) return e.copy(callerKnown = false)
            }
            else -> Unit
        }
        return e
    }

    companion object { const val DEFAULT_LINK_WINDOW_MS = 15 * 60_000L }
}
