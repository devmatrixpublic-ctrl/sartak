package com.satark.detector

/** Same levels as contracts/api.yaml `Decision.level`. The detector emits NONE or HARD; NUDGE and TRUSTED_CONTACT are
 *  escalation levels owned by the app / server and are never produced here. LOG is silent: recorded, no screen, no
 *  pause, no push (the app uses it for shadow mode); the detector does not produce it either. */
enum class Level { NONE, LOG, NUDGE, HARD, TRUSTED_CONTACT }

/** True for the levels that interrupt the person (everything except NONE and the silent LOG). */
val Level.showsScreen: Boolean get() = this != Level.NONE && this != Level.LOG

object Mechanism {
    const val PAYMENT_SCORE = "payment_score"
    const val SIDELOAD_DURING_CALL = "sideload_during_call"
    const val LONG_SESSION = "long_session"
}

/**
 * Result of one event. `level`, `score`, `reasons` are the contracts/api.yaml `Decision`.
 * `score` is the logistic logit and only meaningful for PAYMENT_ATTEMPT (rule alarms report the cohort threshold,
 * i.e. the alarm boundary; events that are not payments report 0.0).
 * `mechanism` and `alarmTMs` are extra, for logging and evaluation: `alarmTMs` is the moment the alarm condition was
 * first true (a long-session alarm is back-dated to start + LONG_SESSION_H, even if detected at a later event).
 */
data class Decision(
    val level: Level,
    val score: Double,
    val reasons: List<String>,
    val mechanism: String? = null,
    val alarmTMs: Long? = null,
    /** DISPLAY ONLY (see PointsScale). Never read by the detector: level and score do not depend on these. Payment alarms only. */
    val points: List<Int> = emptyList(),
    val totalPoints: Int? = null,
    val band: String? = null,
) {
    companion object {
        fun none(score: Double = 0.0) = Decision(Level.NONE, score, emptyList())
    }
}
