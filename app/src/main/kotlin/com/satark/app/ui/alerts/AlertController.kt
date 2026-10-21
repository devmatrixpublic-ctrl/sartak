package com.satark.app.ui.alerts

import android.content.Context
import com.satark.app.SatarkStub
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
) {
    private val _current = MutableStateFlow<AlertUi?>(null)
    val current: StateFlow<AlertUi?> = _current.asStateFlow()

    fun start() {
        scope.launch {
            dispatcher.alarms.collect { a ->
                val d = a.decision
                _current.value = when (d.mechanism) {
                    Mechanism.LONG_SESSION -> AlertUi.LongSession(d.reasons)
                    else -> AlertUi.Hard(d.reasons)
                }
                notifyServer(d, a.trace?.features)
            }
        }
        scope.launch { dispatcher.nudges.collect { _current.value = it.let { n -> AlertUi.Nudge(n.reasons) } } }
    }

    /** Alarm -> POST /alert (trusted-contact push) and an anonymised /signature, both queued if offline. */
    private suspend fun notifyServer(d: Decision, features: DoubleArray?) {
        val id = store.deviceId ?: return
        val type = if (d.mechanism == Mechanism.LONG_SESSION) "long_session" else "alarm"
        queue.alert(AlertRequest(id, type, d.reasons))
        // Only the detector's 16 feature values leave the phone; no numbers, names or raw amounts.
        val f = features?.let { v -> model.features.zip(v.toList()).toMap() } ?: emptyMap()
        queue.signature(SignatureRequest(d.mechanism ?: "payment_score", f))
    }

    fun escalateToTrustedContact() {
        (_current.value as? AlertUi.Hard)?.let { _current.value = AlertUi.TrustedContact(it.reasons) }
    }

    fun dismiss() { _current.value = null }
}

/**
 * Reason code -> sentence. M4 generates `reason_<code lowercase>` strings into values/strings.xml; until they exist
 * the raw code is shown.
 */
object ReasonText {
    @SatarkStub("raw reason codes on screen until M4's validated strings.xml is merged")
    fun of(ctx: Context, code: String): String {
        val id = ctx.resources.getIdentifier("reason_" + code.lowercase(), "string", ctx.packageName)
        return if (id != 0) ctx.getString(id) else code
    }
}
