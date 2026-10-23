package com.satark.app.signals

import com.satark.detector.InstallSource

/** What the signal sources emit. Only EventMapper consumes these. */
sealed interface RawSignal {
    val tMs: Long

    data class CallStarted(override val tMs: Long, val callerKnown: Boolean?) : RawSignal
    data class CallEnded(override val tMs: Long) : RawSignal
    data class VideoStarted(override val tMs: Long, val appPackage: String?, val callerKnown: Boolean?) : RawSignal
    data class VideoEnded(override val tMs: Long, val appPackage: String?) : RawSignal
    data class AppInstalled(override val tMs: Long, val appPackage: String, val source: InstallSource?) : RawSignal
    data class AppForeground(override val tMs: Long, val appPackage: String) : RawSignal
    data class PayeeAdded(override val tMs: Long, val payeeHash: String) : RawSignal
    data class PaymentAttempt(
        override val tMs: Long,
        val payeeHash: String,
        val amountInr: Double,
        val isP2P: Boolean,
        val payeeIsNew: Boolean,
        val source: String, // "qr" | "manual"
    ) : RawSignal
}

enum class SourceName { CALL, USAGE, INSTALL, WATCHLIST }

/** Per-source availability, shown in settings and used for banners. A missing source never crashes anything. */
enum class SourceState { AVAILABLE, DENIED, UNSUPPORTED }

data class SignalStatus(
    val states: Map<SourceName, SourceState>,
    /** Informational only (Android 15+, this app's own window); not part of [allAvailable] and never a detector input. */
    val screenRecording: SourceState = SourceState.UNSUPPORTED,
) {
    fun of(s: SourceName) = states[s] ?: SourceState.UNSUPPORTED
    val allAvailable get() = SourceName.entries.all { of(it) == SourceState.AVAILABLE }
}
