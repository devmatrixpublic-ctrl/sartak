package com.satark.app.payments

import android.content.Intent
import android.net.Uri
import com.satark.app.events.EventDispatcher
import com.satark.app.events.KnownPayee
import com.satark.app.events.SatarkDao
import com.satark.app.net.DecisionDto
import com.satark.app.net.PaymentDecisionRequest
import com.satark.app.net.PaymentResponse
import com.satark.app.net.PaymentResultRequest
import com.satark.app.net.RiskCheckRequest
import com.satark.app.net.SatarkApi
import com.satark.app.signals.RawSignal
import com.satark.detector.Decision
import com.satark.detector.showsScreen
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

/** Where a held payment stands once the owner's trusted contact may have answered (server state, GET /payments/{id}). */
sealed interface HoldResolution {
    data object Waiting : HoldResolution
    data object Blocked : HoldResolution
    /** upi_intent approved: the server has started the hand-off, so the app launches the UPI chooser. */
    data object ApprovedUpi : HoldResolution
    /** checkout approved: the server created the order. */
    /** [orderId] is null when the contact approved but the owner's app still has to fetch the order (needs the amount). */
    data class ApprovedCheckout(val orderId: String?) : HoldResolution
    /** Some other state (already settled, or an approval without an order): do nothing automatic. */
    data object Unknown : HoldResolution

    companion object {
        fun of(p: PaymentResponse): HoldResolution = when {
            p.state == "held" -> Waiting
            p.state == "blocked" -> Blocked
            p.method == "upi_intent" && p.state == "handed_off" -> ApprovedUpi
            p.method == "checkout" && p.state == "approved" -> ApprovedCheckout(p.razorpayOrderId)
            else -> Unknown
        }
    }
}

/**
 * The risk call gets [MS] milliseconds. If the server has not answered by then, the on-device decision stands:
 * an alarm holds the payment (an alarm is never auto-confirmed), a clean payment may go ahead where it can.
 */
object RiskTimeout {
    const val MS = 300L
    /** A checkout waits for the server to create the order at Razorpay (a real round trip, about 0.7 s), so it gets longer. */
    const val CHECKOUT_MS = 10_000L
    /** Signing in (first payment after install, or an expired session) is done before the timed call, not inside it. */
    const val SIGN_IN_MS = 5_000L
    const val LOCAL_PREFIX = "local:"

    fun budgetMs(method: String): Long = if (method == "checkout") CHECKOUT_MS else MS

    enum class Fallback { HOLD, ALLOW_LOCAL, FAIL }

    fun fallback(alarmed: Boolean, method: String): Fallback = when {
        alarmed -> Fallback.HOLD
        method == "checkout" -> Fallback.FAIL // a checkout needs the server's order, so there is nothing to continue with
        else -> Fallback.ALLOW_LOCAL
    }

    fun isLocal(paymentId: String) = paymentId.startsWith(LOCAL_PREFIX)
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
    /** Shadow mode: the decision is reported as LOG (the server allows it) and an alarm does not hold the payment. */
    private val shadow: () -> Boolean = { false },
    /** Called before the timed risk call so a first payment does not spend its budget on registering. Must not throw. */
    private val ready: suspend () -> Unit = {},
) {
    /**
     * Pay via Satark. Events reach the detector BEFORE any money moves; then /risk-check; HOLD stops everything.
     * If the server cannot be reached nothing is launched, and an alarmed payment is reported as held.
     */
    suspend fun start(req: UpiRequest, amountInr: BigDecimal, source: String, method: String): PayOutcome {
        if (amountInr.signum() <= 0 || amountInr > MAX_AMOUNT_INR) return PayOutcome.Failed("Enter an amount between ₹0.01 and ₹1,00,00,000.")
        val hash = hasher.hash(req.payeeVpa)
        val isNew = dao.payeeCount(hash) == 0
        val t = now()
        val signals = buildList {
            if (isNew) add(RawSignal.PayeeAdded(t, hash))
            add(RawSignal.PaymentAttempt(t, hash, amountInr.toDouble(), req.isP2P, isNew, source))
        }
        val decision: Decision = dispatcher.submitAndDecide(signals, source)
        val alarmed = decision.level.showsScreen && !shadow()
        val dto = DecisionDto(if (decision.level.showsScreen && shadow()) "LOG" else decision.level.name, decision.score, decision.reasons.take(3))
        kotlinx.coroutines.withTimeoutOrNull(RiskTimeout.SIGN_IN_MS) { ready() }
        val check = try {
            kotlinx.coroutines.withTimeoutOrNull(RiskTimeout.budgetMs(method)) {
                api().riskCheck(RiskCheckRequest(dto, method, amountInr.toDouble(), hash, req.isP2P))
            }
        } catch (e: IOException) {
            return if (alarmed) PayOutcome.Held(null, decision.reasons)
            else PayOutcome.Failed("Can't reach Satark. Check your connection; no payment was made.")
        } catch (e: retrofit2.HttpException) {
            return PayOutcome.Failed("Satark could not check this payment (${e.code()}). No payment was made.")
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            // Bad response body, TLS/pinning failure, etc.: same safety rule as offline, never a crash.
            return if (alarmed) PayOutcome.Held(null, decision.reasons)
            else PayOutcome.Failed("Satark could not check this payment. No payment was made.")
        }
        if (check == null) return when (RiskTimeout.fallback(alarmed, method)) {
            RiskTimeout.Fallback.HOLD -> PayOutcome.Held(null, decision.reasons)
            RiskTimeout.Fallback.ALLOW_LOCAL ->
                PayOutcome.HandOff(RiskTimeout.LOCAL_PREFIX + java.util.UUID.randomUUID(), UpiUriParser.build(req, amountInr))
            RiskTimeout.Fallback.FAIL -> PayOutcome.Failed("Satark was slow to answer. No payment was made. Try again.")
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
        // api.yaml caps txn_ref at 128 chars; a longer value from a UPI app must not cost us the whole result.
        if (!RiskTimeout.isLocal(paymentId)) runCatching { api().paymentResult(paymentId, PaymentResultRequest(r.status, r.txnRef?.take(128))) }
        if (r.status == "success") markCompleted(req.payeeVpa, amountInr.toDouble())
        return r
    }

    fun hashOf(vpa: String): String = hasher.hash(vpa)

    private val activeHold = java.util.concurrent.atomic.AtomicReference<String?>(null)
    private val overrideRequested = java.util.concurrent.atomic.AtomicBoolean(false)

    /** "Continue anyway" on the Hard screen. Only counts while a payment is being held and waited on. */
    fun requestOverride() { if (activeHold.get() != null) overrideRequested.set(true) }

    /** Release the caller's own held payment (POST /risk-check override). Null when the server refuses or is unreachable. */
    suspend fun overrideHold(paymentId: String, method: String, amountInr: Double, payeeHash: String, isP2p: Boolean): HoldResolution? = try {
        val r = api().riskCheck(RiskCheckRequest(DecisionDto("NONE", 0.0, emptyList()), method, amountInr, payeeHash, isP2p, true, paymentId))
        if (r.decision != "ALLOW") null
        else if (method == "checkout") r.orderId?.let { HoldResolution.ApprovedCheckout(it) } else HoldResolution.ApprovedUpi
    } catch (e: kotlinx.coroutines.CancellationException) {
        throw e
    } catch (e: Exception) {
        null
    }

    /**
     * A held payment waits for the owner's trusted contact. Polls until the contact answers or [timeoutMs] passes; an
     * unanswered hold stays held on the server (it is never released by waiting), so a timeout returns [HoldResolution.Waiting].
     */
    suspend fun waitForDecision(
        paymentId: String, timeoutMs: Long = 10 * 60_000L, pollMs: Long = 3_000L,
        onOverride: (suspend () -> HoldResolution?)? = null,
    ): HoldResolution {
        val end = now() + timeoutMs
        activeHold.set(paymentId); overrideRequested.set(false)
        try {
            while (now() < end) {
                if (overrideRequested.getAndSet(false) && onOverride != null) onOverride()?.let { return it }
                val r = runCatching { api().payment(paymentId) }.getOrNull()?.let { HoldResolution.of(it) }
                if (r is HoldResolution.ApprovedCheckout && r.orderId == null && onOverride != null) {
                    onOverride()?.let { return it } // approved by the contact: ask the server for the order
                } else if (r != null && r != HoldResolution.Waiting) return r
                delay(pollMs)
            }
            return HoldResolution.Waiting
        } finally { activeHold.set(null) }
    }

    /** The trusted contact's answer. Returns null on success, otherwise a sentence for the screen. */
    suspend fun decide(paymentId: String, approve: Boolean): String? = try {
        api().paymentDecision(paymentId, PaymentDecisionRequest(if (approve) "approve" else "block"))
        null
    } catch (e: retrofit2.HttpException) {
        when (e.code()) {
            404 -> "This request is no longer available to you."
            409 -> "This payment has already been decided."
            else -> "Could not send your answer (${e.code()}). Try again."
        }
    } catch (e: kotlinx.coroutines.CancellationException) {
        throw e
    } catch (e: Exception) {
        "Could not reach Satark. Check your connection and try again."
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

    companion object { val MAX_AMOUNT_INR = BigDecimal("10000000") } // api.yaml RiskCheckRequest.amount maximum

    private suspend fun markCompleted(vpa: String, amountInr: Double) {
        dao.addPayee(KnownPayee(hasher.hash(vpa)))
        dispatcher.onPaymentCompleted(amountInr)
    }
}
