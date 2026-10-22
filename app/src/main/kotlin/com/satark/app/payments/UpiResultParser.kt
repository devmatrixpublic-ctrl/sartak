package com.satark.app.payments

/** Parses the string a UPI app returns, e.g. `txnId=X&responseCode=00&Status=SUCCESS&txnRef=Y` (contracts/upi.md). */
object UpiResultParser {
    data class Result(val status: String, val txnRef: String?)

    /** Returns null when the app returned nothing usable (SUBMITTED, unknown or empty): the server then times out to no_result. */
    fun parse(response: String?): Result? {
        if (response.isNullOrBlank()) return null
        val kv = response.split('&').mapNotNull { p ->
            val i = p.indexOf('=')
            if (i <= 0) null else p.substring(0, i).lowercase() to p.substring(i + 1)
        }.toMap()
        val status = when (kv["status"]?.uppercase()) {
            "SUCCESS" -> "success"
            "FAILURE", "FAILED" -> "failure"
            else -> return null
        }
        return Result(status, (kv["txnref"] ?: kv["txnid"])?.takeIf { it.isNotBlank() })
    }
}
