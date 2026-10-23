package com.satark.app.ui.alerts

import android.content.Context
import com.satark.app.events.EventDispatcher
import com.satark.app.net.AlertRequest
import com.satark.app.net.OfflineQueue
import com.satark.app.net.SignatureRequest
import com.satark.app.security.TokenStore
import com.satark.detector.Decision
import com.satark.detector.Mechanism
import com.satark.detector.ModelConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** What the UI shows. Chosen from Decision.level / mechanism; the detector itself only emits NONE or HARD. */
sealed interface AlertUi {
    data class Nudge(val reasons: List<String>) : AlertUi
    data class Hard(val reasons: List<String>) : AlertUi
    data class LongSession(val reasons: List<String>) : AlertUi
    /** Shown after a Hard pause once the trusted contact has been told. */
    data class TrustedContact(val reasons: List<String>) : AlertUi
}

class AlertController(
    private val dispatcher: EventDispatcher,
    private val queue: OfflineQueue,
    private val store: TokenStore,
    private val model: ModelConfig,
    private val scope: CoroutineScope,
    private val pause: PaymentPause,
    private val onContinueAnyway: () -> Unit = {},
    /** Shadow mode (TokenStore.shadowMode): score and log only, show nothing. Read on every alarm, so it can change live. */
    private val shadow: () -> Boolean = { false },
    private val log: (String) -> Unit = { android.util.Log.i("SatarkShadow", it) },
    /** Repeat alerts within 60 minutes are merged. Null = no merging (tests). */
    private val merger: AlertMerger? = null,
    private val now: () -> Long = System::currentTimeMillis,
    /** Called once for each alert that is actually shown (not for merged repeats): the notification. */
    private val onShown: (Decision) -> Unit = {},
) {
    private val _current = MutableStateFlow<AlertUi?>(null)
    val current: StateFlow<AlertUi?> = _current.asStateFlow()

    fun start() {
        scope.launch {
            dispatcher.alarms.collect { a ->
                val d = a.decision
                if (!shadow() && merger != null && !merger.admit(AlertMerger.keyOf(d.mechanism, d.reasons), now())) return@collect
                if (shadow()) { log("level=${d.level} score=${"%.3f".format(d.score)} mechanism=${d.mechanism} reasons=${d.reasons.joinToString(",")}"); return@collect }
                _current.value = when (d.mechanism) {
                    Mechanism.LONG_SESSION -> AlertUi.LongSession(d.reasons)
                    else -> AlertUi.Hard(d.reasons).also { pause.start() }
                }
                onShown(d)
                notifyServer(d, a.trace?.features)
            }
        }
        scope.launch { dispatcher.nudges.collect { if (!shadow()) _current.value = it.let { n -> AlertUi.Nudge(n.reasons) } } }
    }

    /** Alarm -> POST /alert (trusted-contact push) and an anonymised /signature, both queued if offline. */
    private suspend fun notifyServer(d: Decision, features: DoubleArray?) {
        val id = store.deviceId ?: return
        val type = if (d.mechanism == Mechanism.LONG_SESSION) "long_session" else "alarm"
        queue.alert(AlertRequest(id, type, d.reasons))
        // Only the detector's 16 feature values leave the phone; no numbers, names or raw amounts.
        val f = features?.let { v -> model.features.zip(v.toList()).toMap() } ?: emptyMap()
        // Rule alarms carry no features; the server rejects an empty map with 400, so skip it.
        if (f.isNotEmpty()) queue.signature(SignatureRequest(d.mechanism ?: "payment_score", f))
    }

    /** A payment is held: tell the trusted contact which one, so they can approve or block it (queued if offline). */
    suspend fun requestApproval(paymentId: String, reasons: List<String>) {
        val id = store.deviceId ?: return
        queue.alert(AlertRequest(id, "alarm", reasons.take(3), paymentId))
    }

    fun escalateToTrustedContact() {
        (_current.value as? AlertUi.Hard)?.let { _current.value = AlertUi.TrustedContact(it.reasons) }
    }

    /** "Hold payment 30 minutes": payments in Satark wait the longer pause, then the screen closes. */
    fun holdThirtyMinutes() { pause.start(Friction.HOLD_MS); _current.value = null }

    /** "Continue anyway": the person overrides the hold. The pay screen releases it through the server; the screen closes. */
    fun continueAnyway() { onContinueAnyway(); _current.value = null }

    fun dismiss() { _current.value = null }
}

/**
 * Reason code -> sentence. M4 generates `reason_<code lowercase>` strings into values/strings.xml and
 * `ops/strings/validate_strings.py` fails the build when a code has none. The raw-code fallback below is only a safety
 * net for a code added after the strings were generated; it is no longer a temporary stub.
 */
object ReasonText {
    fun of(ctx: Context, code: String): String {
        val id = ctx.resources.getIdentifier("reason_" + code.lowercase(), "string", ctx.packageName)
        return if (id != 0) ctx.getString(id) else code
    }
}
