package com.satark.app.events

import com.satark.app.signals.RawSignal
import com.satark.detector.Event
import com.satark.detector.EventType
import com.satark.detector.PaymentType

/** Raw signal -> detector [Event] (contracts/schema.json). Payee ids are always hashes. */
object EventMapper {
    fun map(s: RawSignal): Event = when (s) {
        is RawSignal.CallStarted -> Event(s.tMs, EventType.CALL_START, callerKnown = s.callerKnown)
        is RawSignal.CallEnded -> Event(s.tMs, EventType.CALL_END)
        is RawSignal.VideoStarted -> Event(s.tMs, EventType.VIDEO_SESSION_START, callerKnown = s.callerKnown, appPackage = s.appPackage)
        is RawSignal.VideoEnded -> Event(s.tMs, EventType.VIDEO_SESSION_END, appPackage = s.appPackage)
        is RawSignal.AppInstalled -> Event(s.tMs, EventType.APP_INSTALL, appPackage = s.appPackage, installSource = s.source)
        is RawSignal.AppForeground -> Event(s.tMs, EventType.APP_FOREGROUND, appPackage = s.appPackage)
        is RawSignal.PayeeAdded -> Event(s.tMs, EventType.NEW_PAYEE, payeeId = s.payeeHash)
        is RawSignal.PaymentAttempt -> Event(
            s.tMs, EventType.PAYMENT_ATTEMPT,
            payeeId = s.payeeHash, payeeIsNew = s.payeeIsNew, amountInr = s.amountInr,
            paymentType = if (s.isP2P) PaymentType.P2P else PaymentType.P2M,
        )
    }

    /** Map in the exact shape of contracts/schema.json (used for the queue, logs and the schema test). */
    /** Inverse of [toSchemaMap] for rows read back from event_queue; null if the row is unreadable. */
    fun fromSchemaJson(json: String): Event? = runCatching {
        val o = org.json.JSONObject(json)
        fun str(k: String) = if (o.has(k) && !o.isNull(k)) o.getString(k) else null
        fun bool(k: String) = if (o.has(k) && !o.isNull(k)) o.getBoolean(k) else null
        Event(
            tMs = o.getLong("t_ms"),
            type = EventType.valueOf(o.getString("event_type")),
            callerKnown = bool("caller_known"),
            appPackage = str("app_package"),
            installSource = str("install_source")?.let { com.satark.detector.InstallSource.valueOf(it.uppercase()) },
            payeeId = str("payee_id"),
            payeeIsNew = bool("payee_is_new"),
            amountInr = if (o.has("amount_inr") && !o.isNull("amount_inr")) o.getDouble("amount_inr") else null,
            paymentType = str("payment_type")?.let { PaymentType.valueOf(it) },
        )
    }.getOrNull()

    fun toSchemaMap(e: Event, source: String? = null): Map<String, Any?> = buildMap {
        put("event_type", e.type.name)
        put("t_ms", e.tMs)
        e.callerKnown?.let { put("caller_known", it) }
        e.appPackage?.let { put("app_package", it) }
        e.installSource?.let { put("install_source", it.name.lowercase()) }
        e.payeeId?.let { put("payee_id", it) }
        e.payeeIsNew?.let { put("payee_is_new", it) }
        e.amountInr?.let { put("amount_inr", it) }
        e.paymentType?.let { put("payment_type", it.name) }
        source?.let { put("source", it) }
    }
}
