package com.satark.detector

/** Event vocabulary of contracts/schema.json (same names as the SatarkSim event table). */
enum class EventType { CALL_START, CALL_END, VIDEO_SESSION_START, VIDEO_SESSION_END, APP_INSTALL, APP_FOREGROUND, NEW_PAYEE, PAYMENT_ATTEMPT }

enum class InstallSource { PLAY_STORE, SIDELOAD }

enum class PaymentType { P2P, P2M }

/**
 * One device event. Every optional field is null when its signal is unavailable or not applicable;
 * the detector's defaults for null are documented in contracts/schema.json ("missing_signal_defaults").
 *
 * @property tMs  device clock, epoch milliseconds. Only differences are used, never the wall clock.
 * @property callerKnown  false = number not in contacts (unknown contact); null = not reported.
 * @property payeeId  hashed VPA, never a raw VPA.
 * @property amountInr  rupees; non-finite or negative values are treated as missing (0.0).
 */
data class Event(
    val tMs: Long,
    val type: EventType,
    val callerKnown: Boolean? = null,
    val appPackage: String? = null,
    val installSource: InstallSource? = null,
    val payeeId: String? = null,
    val payeeIsNew: Boolean? = null,
    val amountInr: Double? = null,
    val paymentType: PaymentType? = null,
)
