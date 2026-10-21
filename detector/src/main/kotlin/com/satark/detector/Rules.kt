package com.satark.detector

/** The two timing-independent rule alarms (master doc 4.1 and 4.6). */
class Rules(private val model: ModelConfig) {
    private val contactMs = (model.constants.contactWindowS * 1000).toLong()
    val longSessionMs: Long = (model.constants.longSessionH * 3600 * 1000).toLong()

    /** Unknown call in progress (first unknown contact within the contact window) + app SIDELOADED. */
    fun sideloadDuringCall(s: SessionState, install: Event): Boolean {
        val unk = s.unkT ?: return false
        return install.installSource == InstallSource.SIDELOAD && install.tMs - unk <= contactMs
    }

    /** Alarm time of a long unknown-origin video session, or null when it has not reached LONG_SESSION_H at [nowMs]. */
    fun longSessionAlarmT(s: SessionState, nowMs: Long): Long? {
        val start = s.videoUnkT ?: return null
        return if (s.videoActive && nowMs - start >= longSessionMs) start + longSessionMs else null
    }
}
