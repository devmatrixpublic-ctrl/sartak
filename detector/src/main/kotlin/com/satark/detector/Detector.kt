package com.satark.detector

/** What the detector computed at one payment attempt (for logging, tests and the explanation screen). */
class PaymentTrace(val tMs: Long, val features: DoubleArray, val score: Double, val threshold: Double)

/**
 * The on-device detector for ONE session. Deterministic: no wall-clock reads, no randomness; the result depends only on
 * the model, the age band (threshold selection only), the baseline and the events fed in timestamp order.
 *
 *  - [onEvent]: feed every event in timestamp order.
 *  - [onTick]: call periodically (and once at session end with the last event time) so a long unknown-origin video
 *    session can raise its alarm without waiting for another event.
 *  - Baseline is updated by the caller with [Baseline.observe] on payments that completed, never on attempts.
 *
 * Session boundaries (when to call [reset]) are an app policy; the reference detector evaluates self-contained sessions.
 */
class Detector(
    private val model: ModelConfig,
    private val ageBand: String?,
    private val baseline: Baseline,
    var traceSink: ((PaymentTrace) -> Unit)? = null,
) {
    private val state = SessionState()
    private val scorer = Scorer(model)
    private val extractor = FeatureExtractor(model)
    private val rules = Rules(model)
    private val explainer = Explainer(model, scorer)
    private val threshold = ConformalThreshold.forCohort(model, ageBand)
    private val dedupeMs = (model.constants.dedupeWindowS * 1000).toLong()

    private var lastEventT: Long? = null
    private var lastResult: Decision = Decision.none()

    fun reset() {
        state.reset()
        lastEventT = null
        lastResult = Decision.none()
    }

    fun onEvent(e: Event): Decision {
        // A duplicate is dropped from the evidence, but a repeated PAYMENT_ATTEMPT (user taps pay again) must get the same
        // decision as the original, never NONE: otherwise a held payment can be released by retrying within the window.
        if (state.isDuplicate(e, dedupeMs)) return if (e.type == EventType.PAYMENT_ATTEMPT) lastResult else Decision.none()
        val t = e.tMs
        lastEventT = maxOf(lastEventT ?: t, t)
        var payment: Decision? = null
        var ruleAlarm: Decision? = null
        when (e.type) {
            EventType.CALL_START -> {
                state.callActive = true
                if (e.callerKnown == false && state.unkT == null) state.unkT = t
            }
            EventType.CALL_END -> state.callActive = false
            EventType.VIDEO_SESSION_START -> {
                state.videoActive = true
                if (e.callerKnown == false) {
                    state.videoUnkT = t
                    if (state.unkT == null) state.unkT = t
                }
            }
            EventType.VIDEO_SESSION_END -> {
                ruleAlarm = longSession(t)
                state.videoActive = false
            }
            EventType.APP_INSTALL -> {
                state.installs.add(SessionState.Install(t, e.installSource, e.appPackage))
                if (e.appPackage != null && e.appPackage in model.watchlistSet) state.watchlistSeen = true
                if (rules.sideloadDuringCall(state, e)) ruleAlarm = ruleDecision(Mechanism.SIDELOAD_DURING_CALL, t)
            }
            EventType.APP_FOREGROUND -> if (e.appPackage != null && e.appPackage in model.watchlistSet) state.watchlistSeen = true
            EventType.NEW_PAYEE -> e.payeeId?.let { state.payeeAddedT[it] = t }
            EventType.PAYMENT_ATTEMPT -> {
                ruleAlarm = longSession(t)
                val x = extractor.extract(state, e, baseline.median, baseline.mad)
                val score = scorer.score(x)
                traceSink?.invoke(PaymentTrace(t, x, score, threshold))
                e.payeeId?.let { state.paidTo[it] = (state.paidTo[it] ?: 0) + 1 }
                payment = if (score >= threshold) {
                    val (pts, total, band) = explainer.pointsForPayment(x)
                    Decision(Level.HARD, score, explainer.reasonsForPayment(x), Mechanism.PAYMENT_SCORE, t, pts, total, band)
                } else Decision.none(score)
            }
        }
        // Same precedence as the reference: a rule alarm wins when its alarm time is <= the payment alarm time.
        val result = when {
            ruleAlarm != null && (payment == null || payment.level != Level.HARD || ruleAlarm.alarmTMs!! <= t) -> ruleAlarm
            payment != null -> payment
            else -> Decision.none()
        }
        lastResult = result
        return result
    }

    /** Call once when a session ends: checks a video session still running at the last event (same as the reference). */
    fun finish(): Decision = lastEventT?.let { onTick(it) } ?: Decision.none()

    /** Raises the long-session alarm (once per video session) when an unknown-origin video session has reached LONG_SESSION_H at [nowMs]. */
    fun onTick(nowMs: Long): Decision = longSession(nowMs) ?: Decision.none()

    /** Raised once per unknown video session, so a periodic [onTick] does not repeat the alarm (and the trusted-contact push). */
    private fun longSession(nowMs: Long): Decision? {
        val at = rules.longSessionAlarmT(state, nowMs) ?: return null
        if (state.longSessionRaisedFor == state.videoUnkT) return null
        state.longSessionRaisedFor = state.videoUnkT
        return ruleDecision(Mechanism.LONG_SESSION, at)
    }

    private fun ruleDecision(mechanism: String, alarmT: Long) =
        Decision(Level.HARD, threshold, explainer.reasonForRule(mechanism), mechanism, alarmT)

    companion object {
        fun create(ageBand: String?, baseline: Baseline, model: ModelConfig = ModelConfig.loadBundled()) =
            Detector(model, ageBand, baseline)
    }
}
