package com.satark.app.events

import com.satark.app.signals.RawSignal
import com.satark.detector.Baseline
import com.satark.detector.Decision
import com.satark.detector.Detector
import com.satark.detector.Event
import com.satark.detector.EventType
import com.satark.detector.Level
import com.satark.detector.showsScreen
import com.satark.detector.ModelConfig
import com.satark.detector.PaymentTrace
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject

/** An alarm the UI must show, with the features behind it (for the anonymised /signature). */
data class Alarm(val decision: Decision, val trace: PaymentTrace?, val unknownCallActive: Boolean, val fromPayment: Boolean = false)

/** A payment attempt to a new payee during an unknown call that did not reach an alarm: shown as a nudge. */
data class Nudge(val reasons: List<String>)

/** What the checks said about one payment: the decision, and a nudge when it is allowed but worth a pause. */
data class Decided(val decision: Decision, val nudge: Nudge?)

/**
 * signal -> EventMapper -> Deduplicator -> store -> EventSequencer -> Detector.onEvent() -> store Decision.
 * The detector is single-threaded; every call into it goes through [lock].
 */
class EventDispatcher(
    private val dao: SatarkDao,
    private val model: ModelConfig,
    ageYears: Int?,
    private val scope: CoroutineScope,
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val lock = Mutex()
    private val dedup = Deduplicator((model.constants.dedupeWindowS * 1000).toLong())
    private val sequencer = EventSequencer()
    private val baseline = Baseline.coldStart(model)
    private var lastTrace: PaymentTrace? = null
    private var detector = newDetector(ageYears)
    private var splitGuard = SplitGuard(model, AgeProfile.bandOf(ageYears), baseline)
    private var highValue = HighValueNewPayee(AgeProfile.highValueThreshold(ageYears))

    private fun newDetector(ageYears: Int?) =
        Detector.create(AgeProfile.bandOf(ageYears), baseline, model).also { it.traceSink = { t -> lastTrace = t } }

    /**
     * The person typed (or cleared) their age: use the matching cohort threshold and new-payee hold amount from now on. The three
     * checks start a fresh session, as they do after a long quiet gap, so an age changed in the middle of a call is not remembered.
     */
    suspend fun setAge(ageYears: Int?) = lock.withLock {
        detector = newDetector(ageYears)
        splitGuard = SplitGuard(model, AgeProfile.bandOf(ageYears), baseline)
        highValue = HighValueNewPayee(AgeProfile.highValueThreshold(ageYears))
    }

    private val policy = SessionPolicy()
    private val unknownCallActive get() = policy.unknownCallActive
    private val startedAt = now()
    private var ready = false

    private val _alarms = MutableSharedFlow<Alarm>(extraBufferCapacity = 16)
    val alarms: SharedFlow<Alarm> = _alarms.asSharedFlow()
    private val _nudges = MutableSharedFlow<Nudge>(extraBufferCapacity = 8)
    val nudges: SharedFlow<Nudge> = _nudges.asSharedFlow()

    /** Rebuild the baseline from completed payments and start the periodic tick (long-session rule). */
    fun start() {
        scope.launch {
            lock.withLock {
                dao.lastAmounts(model.baseline.windowN).asReversed().forEach(baseline::observe)
                restoreSession()
                ready = true
            }
            prune()
            var ticks = 0
            while (true) {
                delay(TICK_MS)
                pump(flushAll = false)
                if (++ticks % PRUNE_EVERY_TICKS == 0) prune()
            }
        }
    }

    fun submit(s: RawSignal, source: String? = null) {
        scope.launch {
            val events = EventMapper.mapAll(s)
            lock.withLock {
                if (s is RawSignal.UnknownMessage && policy.callIsOpen) return@withLock // a call is already in progress: leave it alone
                for (e in events) {
                    if (dedup.isDuplicate(e)) continue
                    dao.insertEvent(EventRow(tMs = e.tMs, json = JSONObject(EventMapper.toSchemaMap(e, source)).toString()))
                    sequencer.add(e)
                }
            }
            pump(flushAll = false)
            // The sequencer holds new events briefly for reordering; release this one as soon as the hold ends,
            // not at the next 30 s tick (an alarm must show while the scam call is still going).
            delay(RELEASE_AFTER_MS)
            pump(flushAll = false)
        }
    }

    /** Submit already-mapped events and return the worst Decision they produced (used right before a risk check). */
    suspend fun submitAndDecide(signals: List<RawSignal>, source: String): Decision = submitAndDecideFull(signals, source).decision

    /** Like [submitAndDecide], plus the nudge to show before the payment goes on (returned, not broadcast, so the person sees it first). */
    suspend fun submitAndDecideFull(signals: List<RawSignal>, source: String): Decided {
        lock.withLock {
            for (e in signals.flatMap(EventMapper::mapAll)) {
                if (dedup.isDuplicate(e)) continue
                dao.insertEvent(EventRow(tMs = e.tMs, json = JSONObject(EventMapper.toSchemaMap(e, source)).toString()))
                sequencer.add(e)
            }
        }
        return pumpFull(flushAll = true)
    }

    private suspend fun pump(flushAll: Boolean): Decision = pumpFull(flushAll).decision

    private suspend fun pumpFull(flushAll: Boolean): Decided = lock.withLock {
        if (!ready) return@withLock Decided(Decision.none(), null)
        var nudged: Nudge? = null
        val batch = if (flushAll) sequencer.flush() else sequencer.drain(now())
        var worst = Decision.none()
        for (e in batch) {
            val d = feed(e) ?: continue
            if (d.level != Level.NONE || e.type == EventType.PAYMENT_ATTEMPT) {
                dao.insertDecision(DecisionRow(tMs = e.tMs, level = d.level.name, score = d.score, reasons = d.reasons.joinToString(","), mechanism = d.mechanism))
            }
            if (d.level.showsScreen) {
                _alarms.tryEmit(Alarm(d, lastTrace, unknownCallActive, fromPayment = e.type == EventType.PAYMENT_ATTEMPT))
                if (worst.level == Level.NONE) worst = d
            } else if (e.type == EventType.PAYMENT_ATTEMPT && NudgePolicy.shouldNudge(policy.unknownContactRecent(e.tMs), e.payeeIsNew, e.amountInr, baseline.median)) {
                // A payment started in Satark waits for the person (returned to the caller); anything else is shown as a banner.
                val n = Nudge(NudgePolicy.reasons(policy.unknownCallActive))
                if (flushAll) nudged = n else _nudges.tryEmit(n)
                worst = d
            } else if (e.type == EventType.PAYMENT_ATTEMPT && worst.level == Level.NONE) worst = d
        }
        if (flushAll) detector.onTick(maxOf(policy.lastEventTMs, now()))
            .takeIf { it.level.showsScreen && worst.level == Level.NONE }?.let {
                _alarms.tryEmit(Alarm(it, null, unknownCallActive)); worst = it
            }
        else detector.onTick(now()).takeIf { it.level.showsScreen }?.let { _alarms.tryEmit(Alarm(it, null, unknownCallActive)) }
        Decided(worst, nudged)
    }

    /** One event into the detector, with the app's session policy. Null when the event is ignored. Call under [lock]. */
    private fun feed(raw: Event): Decision? {
        val step = policy.prepare(raw) ?: return null
        if (step.resetFirst) { detector.reset(); splitGuard.reset(); highValue.reset() }
        lastTrace = null
        val main = detector.onEvent(step.event)
        // A second look for payments split into pieces. It only ever adds an alarm; the main decision is never lowered.
        val extra = splitGuard.onEvent(step.event)
        if (!main.level.showsScreen && extra.level.showsScreen) { lastTrace = splitGuard.lastTrace; return extra }
        // A third look for the payments that matter most: new payee, a large amount, and an unknown call that is open or just ended.
        val big = highValue.onEvent(step.event, policy.unknownCallActive, policy.unknownContactRecent(step.event.tMs))
        if (!main.level.showsScreen && big.level.showsScreen) { lastTrace = null; return big }
        return main
    }

    /**
     * The detector's session lives in memory. If Android kills the app mid-scam, rebuild it from the stored events of the
     * last few hours so the unknown call, the sideload, etc. still count. Alarms were already shown before: no re-emit.
     */
    private suspend fun restoreSession() {
        val since = now() - RESTORE_WINDOW_MS
        runCatching {
            // Only what happened before this process started; newer rows are already queued in the sequencer.
            for (row in dao.eventsSince(since)) if (row.tMs < startedAt) EventMapper.fromSchemaJson(row.json)?.let { feed(it); policy.restoredUpTo = it.tMs }
        }.onFailure { android.util.Log.w("Satark.dispatch", "session restore failed", it) }
    }

    /**
     * Privacy: event_queue holds which apps were opened and when. Keep it only as long as session restore needs it
     * (plus margin), never as a usage history. Decisions (levels and reason codes only) are kept a little longer.
     */
    private suspend fun prune() = runCatching {
        dao.pruneEvents(now() - EVENT_RETENTION_MS)
        dao.pruneDecisions(now() - DECISION_RETENTION_MS)
    }.onFailure { android.util.Log.w("Satark.dispatch", "prune failed", it) }

    /** Call only when a payment actually completed (never for held attempts). */
    suspend fun onPaymentCompleted(amountInr: Double) = lock.withLock {
        baseline.observe(amountInr)
        dao.addCompleted(CompletedPayment(amountInr = amountInr))
    }

    companion object {
        const val TICK_MS = 30_000L
        const val RELEASE_AFTER_MS = 1_700L // EventSequencer hold (1.5 s) + margin
        const val RESTORE_WINDOW_MS = 3 * 3600_000L // > long-session rule (2 h) and the contact window
        const val EVENT_RETENTION_MS = 24 * 3600_000L // must stay >= RESTORE_WINDOW_MS
        const val DECISION_RETENTION_MS = 30L * 24 * 3600_000L
        const val PRUNE_EVERY_TICKS = 120 // ~1 h
    }
}
