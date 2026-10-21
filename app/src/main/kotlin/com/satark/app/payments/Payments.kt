package com.satark.app.payments

import android.content.Intent
import android.net.Uri
import com.satark.app.events.EventDispatcher
import com.satark.app.events.KnownPayee
import com.satark.app.events.SatarkDao
import com.satark.app.net.DecisionDto
import com.satark.app.net.PaymentResultRequest
import com.satark.app.net.RiskCheckRequest
import com.satark.app.net.SatarkApi
import com.satark.app.signals.RawSignal
import com.satark.detector.Decision
import kotlinx.coroutines.delay
import java.io.IOException
import java.math.BigDecimal

/** What the UI must do next. Nothing here ever moves money by itself. */
sealed interface PayOutcome {
    /** Server said HOLD (or the detector alarmed and the server was unreachable): no intent, no checkout. */
    data class Held(val paymentId: String?, val reasons: List<String>) : PayOutcome
    data class HandOff(val paymentId: String, val upiUri: String) : PayOutcome
    data class Checkout(val paymentId: String, val orderId: String, val amountInr: BigDecimal) : PayOutcome
    data class Failed(val message: String) : PayOutcome
}

object UpiIntentLauncher {
    /** Chooser over every installed UPI app; null-safe when there is none (caller shows "no UPI app"). */
    fun intent(upiUri: String): Intent =
        Intent.createChooser(Intent(Intent.ACTION_VIEW, Uri.parse(upiUri)), "Pay with")

    fun hasUpiApp(pm: android.content.pm.PackageManager, upiUri: String) =
        pm.queryIntentActivities(Intent(Intent.ACTION_VIEW, Uri.parse(upiUri)), 0).isNotEmpty()
}

class PaymentRepository(
    private val api: () -> SatarkApi,
    private val dao: SatarkDao,
    private val dispatcher: EventDispatcher,
    private val hasher: PayeeHasher,
    private val now: () -> Long = System::currentTimeMillis,
) {
    /**
     * Pay via Satark. Events reach the detector BEFORE any money moves; then /risk-check; HOLD stops everything.
     * If the server cannot be reached nothing is launched, and an alarmed payment is reported as held.
     */
    suspend fun start(req: UpiRequest, amountInr: BigDecimal, source: String, method: String): PayOutcome {
        val hash = hasher.hash(req.payeeVpa)
        val isNew = dao.payeeCount(hash) == 0
        val t = now()
        val signals = buildList {
            if (isNew) add(RawSignal.PayeeAdded(t, hash))
            add(RawSignal.PaymentAttempt(t, hash, amountInr.toDouble(), req.isP2P, isNew, source))
        }
        val decision: Decision = dispatcher.submitAndDecide(signals, source)
        val dto = DecisionDto(decision.level.name, decision.score, decision.reasons.take(3))
        val check = try {
            api().riskCheck(RiskCheckRequest(dto, method, amountInr.toDouble(), hash, req.isP2P))
        } catch (e: IOException) {
            return if (decision.level.name != "NONE") PayOutcome.Held(null, decision.reasons)
            else PayOutcome.Failed("Can't reach Satark. Check your connection; no payment was made.")
        } catch (e: retrofit2.HttpException) {
            return PayOutcome.Failed("Satark could not check this payment (${e.code()}). No payment was made.")
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            // Bad response body, TLS/pinning failure, etc.: same safety rule as offline, never a crash.
            return if (decision.level.name != "NONE") PayOutcome.Held(null, decision.reasons)
            else PayOutcome.Failed("Satark could not check this payment. No payment was made.")
        }
        if (check.decision == "HOLD") return PayOutcome.Held(check.paymentId, decision.reasons)
        return when (method) {
            "checkout" -> check.orderId?.let { PayOutcome.Checkout(check.paymentId, it, amountInr) }
                ?: PayOutcome.Failed("Checkout order missing; no payment was made.")
            else -> PayOutcome.HandOff(check.paymentId, UpiUriParser.build(req, amountInr))
        }
    }

    /** Hand-off result: app-reported, never verified. A payment the server holds rejects this call (4xx), which is fine. */
    suspend fun reportUpiResult(paymentId: String, response: String?, req: UpiRequest, amountInr: BigDecimal): UpiResultParser.Result? {
        val r = UpiResultParser.parse(response) ?: return null
        runCatching { api().paymentResult(paymentId, PaymentResultRequest(r.status, r.txnRef)) }
        if (r.status == "success") markCompleted(req.payeeVpa, amountInr.toDouble())
        return r
    }

    /** Checkout: the final state comes from the Razorpay webhook, so poll the server. */
    suspend fun pollCheckout(paymentId: String, req: UpiRequest, amountInr: BigDecimal, timeoutMs: Long = 60_000): String {
        val end = now() + timeoutMs
        while (now() < end) {
            val p = runCatching { api().payment(paymentId) }.getOrNull()
            when (p?.state) {
                "paid" -> { markCompleted(req.payeeVpa, amountInr.toDouble()); return "paid" }
                "failed" -> return "failed"
            }
            delay(2000)
        }
        return "pending"
    }

    private suspend fun markCompleted(vpa: String, amountInr: Double) {
        dao.addPayee(KnownPayee(hasher.hash(vpa)))
        dispatcher.onPaymentCompleted(amountInr)
    }
}
