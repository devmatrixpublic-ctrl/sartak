package com.satark.app.payments

import java.math.BigDecimal
import java.net.URLDecoder
import java.net.URLEncoder

/** A parsed `upi://pay` request. [amountInr] is null when `am` is absent (the user must type it). */
data class UpiRequest(
    val payeeVpa: String,
    val payeeName: String?,
    val amountInr: BigDecimal?,
    val note: String?,
    val merchantCode: String?,
) {
    val isP2P: Boolean get() = merchantCode.isNullOrBlank()
}

sealed interface UpiParseResult {
    data class Ok(val request: UpiRequest) : UpiParseResult
    data class Rejected(val reason: String) : UpiParseResult
}

/** Rules are in contracts/upi.md. Pure Kotlin so it is unit-testable on the JVM. */
object UpiUriParser {
    private val vpa = Regex("^[A-Za-z0-9._-]{2,256}@[A-Za-z][A-Za-z0-9.-]{1,63}$")
    private val amount = Regex("^\\d{1,9}(\\.\\d{1,2})?$")

    fun parse(raw: String): UpiParseResult {
        val s = raw.trim()
        val schemeEnd = s.indexOf("://")
        if (schemeEnd < 0 || !s.substring(0, schemeEnd).equals("upi", ignoreCase = true)) return reject("not a upi:// URI")
        val rest = s.substring(schemeEnd + 3)
        val q = rest.indexOf('?')
        val host = if (q < 0) rest else rest.substring(0, q)
        if (!host.trimEnd('/').equals("pay", ignoreCase = true)) return reject("not a upi://pay URI")
        if (q < 0) return reject("no parameters")

        val params = HashMap<String, String>()
        for (pair in rest.substring(q + 1).substringBefore('#').split('&')) {
            if (pair.isEmpty()) continue
            val eq = pair.indexOf('=')
            val key = (if (eq < 0) pair else pair.substring(0, eq)).lowercase()
            val value = if (eq < 0) "" else decode(pair.substring(eq + 1)) ?: return reject("bad encoding in $key")
            params.putIfAbsent(key, value)
        }

        val pa = params["pa"]?.trim().orEmpty()
        if (!vpa.matches(pa)) return reject("missing or invalid payee VPA")
        val cu = params["cu"]
        if (!cu.isNullOrBlank() && !cu.equals("INR", ignoreCase = true)) return reject("unsupported currency")

        val am = params["am"]?.trim()?.takeIf { it.isNotEmpty() }
        val amountInr = if (am == null) null else {
            if (!amount.matches(am)) return reject("invalid amount")
            val v = BigDecimal(am)
            if (v.signum() <= 0) return reject("amount must be positive")
            v
        }
        return UpiParseResult.Ok(
            UpiRequest(
                payeeVpa = pa,
                payeeName = params["pn"]?.takeIf { it.isNotBlank() },
                amountInr = amountInr,
                note = params["tn"]?.takeIf { it.isNotBlank() },
                merchantCode = params["mc"]?.trim()?.takeIf { it.isNotEmpty() },
            )
        )
    }

    /** Builds the intent URI for the hand-off, with the same payee/amount the risk check saw. */
    fun build(r: UpiRequest, amountInr: BigDecimal): String = buildString {
        append("upi://pay?pa=").append(enc(r.payeeVpa))
        r.payeeName?.let { append("&pn=").append(enc(it)) }
        append("&am=").append(amountInr.setScale(2).toPlainString())
        append("&cu=INR")
        r.note?.let { append("&tn=").append(enc(it)) }
        r.merchantCode?.let { append("&mc=").append(enc(it)) }
    }

    private fun reject(why: String) = UpiParseResult.Rejected(why)

    private fun decode(v: String): String? =
        try { URLDecoder.decode(v, "UTF-8") } catch (e: IllegalArgumentException) { null }

    private fun enc(v: String): String = URLEncoder.encode(v, "UTF-8").replace("+", "%20")
}
