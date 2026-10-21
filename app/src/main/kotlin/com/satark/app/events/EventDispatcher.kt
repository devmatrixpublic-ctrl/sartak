package com.satark.app.events

import com.satark.app.signals.RawSignal
import com.satark.detector.Baseline
import com.satark.detector.Decision
import com.satark.detector.Detector
import com.satark.detector.Event
import com.satark.detector.EventType
import com.satark.detector.Level
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
data class Alarm(val decision: Decision, val trace: PaymentTrace?, val unknownCallActive: Boolean)

/** A payment attempt to a new payee during an unknown call that did not reach an alarm: shown as a nudge. */
data class Nudge(val reasons: List<String>)

/**
 * signal -> EventMapper -> Deduplicator -> store -> EventSequencer -> Detector.onEvent() -> store Decision.
 * The detector is single-threaded; every call into it goes through [lock].
 */
class EventDispatcher(
    private val dao: SatarkDao,
    private val model: ModelConfig,
    private val ageBand: String?,
    private val scope: CoroutineScope,
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val lock = Mutex()
    private val dedup = Deduplicator((model.constants.dedupeWindowS * 1000).toLong())
    private val sequencer = EventSequencer()
    private val baseline = Baseline.coldStart(model)
    private var lastTrace: PaymentTrace? = null
    private val detector = Detector.create(ageBand, baseline, model).also { it.traceSink = { t -> lastTrace = t } }

    private var unknownCallActive = false
    private var callOpen = false
    private var videoOpenSince: Long? = null
    private val startedAt = now()
    private var restoredUpTo: Long? = null // time of the last event replayed after a restart
    private val videoOrigin = VideoOrigin()
    private var lastEventT = 0L
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
            while (true) {
                delay(TICK_MS)
                pump(flushAll = false)
            }
        }
    }

    fun submit(s: RawSignal, source: String? = null) {
        scope.launch {
            val e = EventMapper.map(s)
            lock.withLock {
                if (dedup.isDuplicate(e)) return@withLock
                dao.insertEvent(EventRow(tMs = e.tMs, json = JSONObject(EventMapper.toSchemaMap(e, source)).toString()))
                sequencer.add(e)
            }
            pump(flushAll = false)
            // The sequencer holds new events briefly for reordering; release this one as soon as the hold ends,
            // not at the next 30 s tick (an alarm must show while the scam call is still going).
            delay(RELEASE_AFTER_MS)
            pump(flushAll = false)
        }
    }

    /** Submit already-mapped events and return the worst Decision they produced (used right before a risk check). */
    suspend fun submitAndDecide(signals: List<RawSignal>, source: String): Decision {
        lock.withLock {
            for (s in signals) {
                val e = EventMapper.map(s)
                if (dedup.isDuplicate(e)) continue
                dao.insertEvent(EventRow(tMs = e.tMs, json = JSONObject(EventMapper.toSchemaMap(e, source)).toString()))
                sequencer.add(e)
            }
        }
        return pump(flushAll = true)
    }

    private suspend fun pump(flushAll: Boolean): Decision = lock.withLock {
        if (!ready) return@withLock Decision.none()
        val batch = if (flushAll) sequencer.flush() else sequencer.drain(now())
        var worst = Decision.none()
        for (e in batch) {
            val d = feed(e) ?: continue
            if (d.level != Level.NONE || e.type == EventType.PAYMENT_ATTEMPT) {
                dao.insertDecision(DecisionRow(tMs = e.tMs, level = d.level.name, score = d.score, reasons = d.reasons.joinToString(","), mechanism = d.mechanism))
            }
            if (d.level != Level.NONE) {
                _alarms.tryEmit(Alarm(d, lastTrace, unknownCallActive))
                if (worst.level == Level.NONE) worst = d
            } else if (e.type == EventType.PAYMENT_ATTEMPT && unknownCallActive && e.payeeIsNew == true) {
                _nudges.tryEmit(Nudge(emptyList()))
                worst = d
            } else if (e.type == EventType.PAYMENT_ATTEMPT && worst.level == Level.NONE) worst = d
        }
        if (flushAll) detector.onTick(maxOf(lastEventT, now()))
            .takeIf { it.level != Level.NONE && worst.level == Level.NONE }?.let {
                _alarms.tryEmit(Alarm(it, null, unknownCallActive)); worst = it
            }
        else detector.onTick(now()).takeIf { it.level != Level.NONE }?.let { _alarms.tryEmit(Alarm(it, null, unknownCallActive)) }
        worst
    }

    /** One event into the detector, with the app's session policy. Null when the event is ignored. Call under [lock]. */
    private fun feed(raw: Event): Decision? {
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
        // A new unknown-contact episode after a long gap is a new session (session policy lives here, not in the detector).
        if (lastEventT != 0L && e.tMs - lastEventT > (model.constants.contactWindowS * 1000).toLong() && !unknownCallActive) detector.reset()
        lastEventT = ev.tMs
        trackCall(ev)
        lastTrace = null
        return detector.onEvent(ev)
    }

    /**
     * The detector's session lives in memory. If Android kills the app mid-scam, rebuild it from the stored events of the
     * last few hours so the unknown call, the sideload, etc. still count. Alarms were already shown before: no re-emit.
     */
    private suspend fun restoreSession() {
        val since = now() - RESTORE_WINDOW_MS
        runCatching {
            // Only what happened before this process started; newer rows are already queued in the sequencer.
            for (row in dao.eventsSince(since)) if (row.tMs < startedAt) EventMapper.fromSchemaJson(row.json)?.let { feed(it); restoredUpTo = it.tMs }
        }.onFailure { android.util.Log.w("Satark.dispatch", "session restore failed", it) }
    }

    private fun trackCall(e: Event) {
        when (e.type) {
            EventType.CALL_START -> { unknownCallActive = e.callerKnown == false; callOpen = true }
            EventType.CALL_END -> { unknownCallActive = false; callOpen = false }
            EventType.VIDEO_SESSION_START -> videoOpenSince = e.tMs
            EventType.VIDEO_SESSION_END -> videoOpenSince = null
            else -> Unit
        }
    }

    /** Call only when a payment actually completed (never for held attempts). */
    suspend fun onPaymentCompleted(amountInr: Double) = lock.withLock {
        baseline.observe(amountInr)
        dao.addCompleted(CompletedPayment(amountInr = amountInr))
    }

    companion object {
        const val TICK_MS = 30_000L
        const val RELEASE_AFTER_MS = 1_700L // EventSequencer hold (1.5 s) + margin
        const val RESTORE_WINDOW_MS = 3 * 3600_000L // > long-session rule (2 h) and the contact window
    }
}
