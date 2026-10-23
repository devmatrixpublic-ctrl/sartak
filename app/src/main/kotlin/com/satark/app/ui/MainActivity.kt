package com.satark.app.ui

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.lifecycleScope
import com.razorpay.Checkout
import com.razorpay.PaymentResultListener
import com.satark.app.BuildConfig
import com.satark.app.SatarkApp
import com.satark.app.payments.PayOutcome
import com.satark.app.payments.UpiIntentLauncher
import com.satark.app.payments.UpiRequest
import com.satark.app.payments.UpiResultParser
import com.satark.app.signals.SignalService
import com.satark.app.ui.alerts.AlertHost
import com.satark.app.ui.alerts.ContactDecisionScreen
import com.satark.app.ui.onboarding.ConsentScreen
import com.satark.app.ui.onboarding.OnboardingFlow
import com.satark.app.ui.pay.PayHome
import com.satark.app.ui.theme.SatarkTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.math.BigDecimal

/** What is in flight between "ALLOW" and the final payment state. */
class PendingPay(val paymentId: String, val request: UpiRequest, val amountInr: BigDecimal)

class MainActivity : ComponentActivity(), PaymentResultListener {
    private val graph get() = (application as SatarkApp).graph
    private var pending: PendingPay? = null
    private var status by mutableStateOf<String?>(null)
    /** The "Protection and trusted contact" screen (also opened by the "pairing code changed" notification). */
    private var showProtection by mutableStateOf(false)
    private var consentAsked by mutableStateOf(false)
    private var decidePaymentId by mutableStateOf<String?>(null) // trusted contact opened a held-payment alert

    private val upiLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        val p = pending ?: return@registerForActivityResult
        val response = r.data?.getStringExtra("response") ?: r.data?.getStringExtra("Status")?.let { "Status=$it" }
        lifecycleScope.launch(Dispatchers.IO) {
            val res = graph.payments.reportUpiResult(p.paymentId, response, p.request, p.amountInr)
            status = when (res?.status) {
                "success" -> "The UPI app reported success (not verified by Satark)."
                "failure" -> "The UPI app reported a failure."
                else -> "No result came back from the UPI app. Check your bank app for the real status."
            }
            pending = null
        }
    }

    override fun attachBaseContext(newBase: android.content.Context) = super.attachBaseContext(Language.wrap(newBase))

    override fun onStart() {
        super.onStart()
        graph.hub.screenRecording.register(getSystemService(android.view.WindowManager::class.java), mainExecutor)
    }

    override fun onStop() {
        graph.hub.screenRecording.unregister(getSystemService(android.view.WindowManager::class.java))
        super.onStop()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge() // Android 15 draws behind the system bars anyway; Root() keeps content clear of them
        super.onCreate(savedInstanceState)
        lifecycleScope.launch(Dispatchers.IO) { runCatching { graph.session.ensureRegistered() } }
        if (graph.store.onboarded && graph.store.consent) SignalService.start(this)
        consentAsked = graph.store.consentAsked
        handleOpen(intent)
        setContent { SatarkTheme { Root() } }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleOpen(intent)
    }

    private fun handleOpen(i: Intent?) {
        i?.getStringExtra(EXTRA_DECIDE_PAYMENT)?.takeIf { it.length in 1..36 }?.let { decidePaymentId = it }
        if (i?.getStringExtra(EXTRA_OPEN) == OPEN_PROTECTION) showProtection = true
    }

    @Composable
    private fun Root() {
        var onboarded by remember { mutableStateOf(graph.store.onboarded) }
        val alert by graph.alerts.current.collectAsState()
        Box(Modifier.fillMaxSize()) {
            Box(Modifier.fillMaxSize().safeDrawingPadding()) { Screens(onboarded) { onboarded = true } }
            AlertHost(alert, graph.alerts, graph.store.dialContactUri) // full-screen warnings pad themselves, so their colour fills the whole screen
        }
    }

    @Composable
    private fun Screens(onboarded: Boolean, onOnboarded: () -> Unit) {
        Box(Modifier.fillMaxSize()) {
            val deciding = decidePaymentId
            if (deciding != null) {
                BackHandler { decidePaymentId = null }
                ContactDecisionScreen(graph.payments, deciding) { decidePaymentId = null }
            } else if (!consentAsked) {
                ConsentScreen { agreed -> graph.store.consent = agreed; consentAsked = true }
            } else if (!onboarded) {
                OnboardingFlow(graph) { graph.store.onboarded = true; onOnboarded(); if (graph.store.consent) SignalService.start(this@MainActivity) }
            } else if (showProtection) {
                BackHandler { showProtection = false }
                OnboardingFlow(graph, settings = true, onDeleted = { showProtection = false; recreate() }) { showProtection = false }
            } else {
                PayHome(graph, status, ::onOutcome, onOpenProtection = { showProtection = true }, onNewPayment = { status = null })
            }
        }
    }

    /** Called by the pay screen with the repository's decision. Held never reaches here. */
    private fun onOutcome(o: PayOutcome, req: UpiRequest, amount: BigDecimal) {
        when (o) {
            is PayOutcome.HandOff -> {
                if (!UpiIntentLauncher.hasUpiApp(packageManager, o.upiUri)) { status = "No UPI app is installed on this phone."; return }
                pending = PendingPay(o.paymentId, req, amount)
                upiLauncher.launch(UpiIntentLauncher.intent(o.upiUri))
            }
            is PayOutcome.Checkout -> {
                pending = PendingPay(o.paymentId, req, amount)
                runCatching {
                    Checkout().apply { setKeyID(BuildConfig.RAZORPAY_KEY_ID) }.open(this, JSONObject().apply {
                        put("name", "Satark"); put("order_id", o.orderId); put("currency", "INR")
                        put("amount", o.amountInr.movePointRight(2).toBigInteger().toString())
                    })
                }.onFailure { status = "Could not open checkout."; pending = null }
            }
            else -> Unit
        }
    }

    // Razorpay callbacks: the SDK result is only a hint; the verified state is the webhook, read from the server.
    override fun onPaymentSuccess(razorpayPaymentId: String?) = settleCheckout(sdkFailed = false)
    override fun onPaymentError(code: Int, message: String?) = settleCheckout(sdkFailed = true)

    private fun settleCheckout(sdkFailed: Boolean) {
        val p = pending ?: return
        status = "Confirming with Satark…"
        lifecycleScope.launch(Dispatchers.IO) {
            // SDK error (cancelled, declined, bad key): check briefly in case a payment did land, then say so plainly.
            val timeout = if (sdkFailed) 6_000L else 60_000L
            status = when (graph.payments.pollCheckout(p.paymentId, p.request, p.amountInr, timeout)) {
                "paid" -> "Payment confirmed (test mode)."
                "failed" -> "Payment failed. No money was taken."
                else -> if (sdkFailed) "Checkout did not complete. No payment was made."
                        else "Still waiting for confirmation. Check again in a moment."
            }
            pending = null
        }
    }

    companion object {
        const val EXTRA_OPEN = "com.satark.app.OPEN"
        const val OPEN_PROTECTION = "protection"
        const val EXTRA_DECIDE_PAYMENT = "com.satark.app.DECIDE_PAYMENT"
    }
}
