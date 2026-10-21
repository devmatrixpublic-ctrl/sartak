package com.satark.detector

import kotlin.test.Test
import kotlin.test.assertEquals

/** Pins the "missing_signal_defaults" documented in contracts/schema.json to the code. */
class MissingSignalDefaultsTest {
    private val model = ModelConfig.loadBundled()
    private fun f(trace: PaymentTrace, name: String) = trace.features[model.features.indexOf(name)]

    private fun lastPayment(events: List<Event>): PaymentTrace {
        val det = Detector(model, "36-59", Baseline.fixed(200.0, 80.0))
        val traces = ArrayList<PaymentTrace>().also { l -> det.traceSink = { l.add(it) } }
        events.forEach { det.onEvent(it) }
        return traces.last()
    }

    private val pay = Event(10_000_000, EventType.PAYMENT_ATTEMPT, payeeId = "p9", payeeIsNew = true, amountInr = 90_000.0, paymentType = PaymentType.P2P)

    @Test
    fun callerKnownNullGivesNoUnknownContactEvidence() {
        val t = lastPayment(listOf(
            Event(1_000_000, EventType.CALL_START, callerKnown = null),
            Event(2_000_000, EventType.APP_INSTALL, appPackage = "com.anydesk.anydeskandroid", installSource = InstallSource.SIDELOAD),
            Event(3_000_000, EventType.NEW_PAYEE, payeeId = "p9"),
            pay,
        ))
        for (n in listOf("unk_contact_recent", "unk_call_active", "unk_video_active", "mins_since_unk_log", "install_play_during_unk",
            "install_sideload_during_unk", "payee_added_after_unk", "ocss_ordered", "unk_x_newpayee")) assertEquals(0.0, f(t, n), n)
        assertEquals(1.0, f(t, "watchlist_app")) // the watch-list needs no call state
        assertEquals(1.0, f(t, "new_payee"))
    }

    @Test
    fun nullFieldsFallBackToDocumentedDefaults() {
        val t = lastPayment(listOf(pay.copy(payeeId = null, payeeIsNew = null, amountInr = Double.NaN, paymentType = null)))
        assertEquals(0.0, f(t, "new_payee")); assertEquals(0.0, f(t, "repeat_to_payee")); assertEquals(0.0, f(t, "is_p2p"))
        assertEquals(0.0, f(t, "newpayee_x_amt"), 0.0) // 0 x negative ratio is -0.0, same as the reference
        assertEquals(kotlin.math.ln(1.0 / 201.0).coerceIn(-5.0, 8.0), f(t, "log_amt_ratio"), 1e-12) // amount treated as 0.0
    }

    @Test
    fun installSourceNullNeverTriggersSideloadRule() {
        val det = Detector(model, "18-35", Baseline.fixed(200.0, 80.0))
        det.onEvent(Event(1_000, EventType.CALL_START, callerKnown = false))
        val d = det.onEvent(Event(2_000, EventType.APP_INSTALL, appPackage = "x.y", installSource = null))
        assertEquals(Level.NONE, d.level)
    }
}
