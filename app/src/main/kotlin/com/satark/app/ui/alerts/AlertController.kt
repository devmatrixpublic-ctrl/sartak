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
    /** Several texts from numbers not in the contacts in a short time. A warning only; nothing is held. */
    data object TextBurst : AlertUi
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
    /** A UPI app came to the front soon after an alarm: warn again, over that app. */
    private val onPaymentAppOpened: (List<String>) -> Unit = {},
    /** The warning for a burst of stranger texts, when Satark is not on screen: the notification. */
    private val onTextBurst: () -> Unit = {},
) {
    private val reminder = OpenReminder(now)

    private val _current = MutableStateFlow<AlertUi?>(null)
    val current: StateFlow<AlertUi?> = _current.asStateFlow()

    fun start() {
        scope.launch {
            dispatcher.alarms.collect { a ->
                val d = a.decision
                val first = shadow() || merger == null || merger.admit(AlertMerger.keyOf(d.mechanism, d.reasons), now())
                // A repeat of a background alert stays folded. A payment the person has just tried to make is always explained on the
                // Stop screen: they are acting right now and must be told why it did not go through.
                if (!first && !a.fromPayment) return@collect
                if (shadow()) { log("level=${d.level} score=${"%.3f".format(d.score)} mechanism=${d.mechanism} reasons=${d.reasons.joinToString(",")}"); return@collect }
                _current.value = when (d.mechanism) {
                    Mechanism.LONG_SESSION -> AlertUi.LongSession(d.reasons)
                    else -> AlertUi.Hard(d.reasons)
                }
                // The notification, the reminder over the UPI app and the push to the trusted contact go out once per incident.
                if (first) {
                    reminder.alarmed(d.reasons)
                    onShown(d)
                    notifyServer(d, a.trace?.features)
                }
            }
        }
        scope.launch { dispatcher.nudges.collect { if (!shadow()) _current.value = it.let { n -> AlertUi.Nudge(n.reasons) } } }
    }

    /** A burst of texts from strangers. Never replaces a Stop screen that is already showing. */
    fun strangerTextBurst() {
        if (shadow()) { log("stranger text burst"); return }
        if (_current.value == null) _current.value = AlertUi.TextBurst
        onTextBurst()
    }

    /** A UPI app opened. Within 30 minutes of an alarm, remind the person (at most once every 2 minutes). */
    fun paymentAppOpened() {
        if (shadow()) return
        reminder.due()?.let(onPaymentAppOpened)
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

    companion object {
        /** UPI apps people use for payments. The debug build also counts the test stand-in. */
        val UPI_APPS = setOf(
            "com.google.android.apps.nbu.paisa.user", "com.phonepe.app", "net.one97.paytm",
            "in.amazon.mShop.android.shopping", "in.org.npci.upiapp", "com.dreamplug.androidapp",
        )
    }
}

/** After an alarm, the first UPI app to open within 30 minutes earns one reminder. One per incident, so it never nags. */
class OpenReminder(private val now: () -> Long) {
    private var alarmMs = 0L
    private var reasons: List<String> = emptyList()
    private var reminded = false

    fun alarmed(r: List<String>) { alarmMs = now(); reasons = r; reminded = false }

    /** The reasons to warn with, or null when no reminder is due. */
    fun due(): List<String>? {
        if (alarmMs == 0L || reminded || now() - alarmMs > WINDOW_MS) return null
        reminded = true
        return reasons
    }

    companion object { const val WINDOW_MS = 30 * 60_000L }
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
