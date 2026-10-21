package com.satark.app

import com.satark.app.events.Deduplicator
import com.satark.app.events.EventMapper
import com.satark.app.events.EventSequencer
import com.satark.app.payments.PayeeHasher
import com.satark.app.payments.UpiParseResult
import com.satark.app.payments.UpiUriParser
import com.satark.app.signals.RawSignal
import com.satark.detector.Event
import com.satark.detector.EventType
import com.satark.detector.InstallSource
import com.satark.detector.ModelConfig
import java.io.File
import java.math.BigDecimal
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class UpiUriParserTest {
    private fun ok(uri: String) = (UpiUriParser.parse(uri) as UpiParseResult.Ok).request
    private fun rejected(uri: String) = assertTrue(UpiUriParser.parse(uri) is UpiParseResult.Rejected, uri)

    @Test fun validP2P() {
        val r = ok("upi://pay?pa=ramesh@okbank&pn=Ramesh&am=150.50&cu=INR&tn=lunch")
        assertEquals("ramesh@okbank", r.payeeVpa)
        assertEquals(BigDecimal("150.50"), r.amountInr)
        assertTrue(r.isP2P)
    }

    @Test fun merchantCodeMeansP2M() = assertFalse(ok("upi://pay?pa=shop@upi&am=10&mc=5411").isP2P)

    @Test fun missingAmountIsNull() = assertNull(ok("upi://pay?pa=a.b@upi").amountInr)

    @Test fun urlEncodedFields() {
        val r = ok("upi://pay?pa=a%2Eb@upi&pn=Ram%20Kumar&tn=a%26b")
        assertEquals("a.b@upi", r.payeeVpa)
        assertEquals("Ram Kumar", r.payeeName)
        assertEquals("a&b", r.note)
    }

    @Test fun uppercaseParamNamesAndScheme() = assertEquals("xy@upi", ok("UPI://PAY?PA=xy@upi&AM=1").payeeVpa)

    @Test fun malformedAndNonUpiRejected() {
        rejected("https://example.com/pay?pa=a@b")
        rejected("upi://mandate?pa=a@upi")
        rejected("upi://pay")
        rejected("upi://pay?am=10")
        rejected("upi://pay?pa=notavpa&am=10")
        rejected("upi://pay?pa=a@upi&am=abc")
        rejected("upi://pay?pa=a@upi&am=-5")
        rejected("upi://pay?pa=a@upi&am=0")
        rejected("upi://pay?pa=a@upi&am=1.234")
        rejected("upi://pay?pa=a@upi&cu=USD")
        rejected("upi://pay?pa=a@upi&tn=%ZZ")
        rejected("")
    }

    @Test fun buildKeepsPayeeAndAmount() {
        val r = ok("upi://pay?pa=ab@upi&pn=Ram%20K&mc=1234")
        val again = ok(UpiUriParser.build(r, BigDecimal("1")))
        assertEquals(r.payeeVpa, again.payeeVpa)
        assertEquals(BigDecimal("1.00"), again.amountInr)
        assertEquals("1234", again.merchantCode)
    }
}

class EventPipelineTest {
    private val hasher = PayeeHasher(ByteArray(32) { 7 })

    @Test fun hashIsHex64AndCaseInsensitive() {
        val h = hasher.hash("Ram@UPI")
        assertTrue(Regex("^[0-9a-f]{64}$").matches(h))
        assertEquals(h, hasher.hash("  ram@upi "))
    }

    @Test fun everyMappedEventSatisfiesSchemaRules() {
        val h = hasher.hash("a@upi")
        val signals = listOf(
            RawSignal.CallStarted(1, false), RawSignal.CallEnded(2), RawSignal.VideoStarted(3, "com.x", null),
            RawSignal.VideoEnded(4, "com.x"), RawSignal.AppInstalled(5, "com.anydesk.anydeskandroid", InstallSource.SIDELOAD),
            RawSignal.AppForeground(6, "com.x"), RawSignal.PayeeAdded(7, h),
            RawSignal.PaymentAttempt(8, h, 100.0, true, true, "qr"),
        )
        for (s in signals) {
            val m = EventMapper.toSchemaMap(EventMapper.map(s))
            assertTrue(m["event_type"] != null && m["t_ms"] is Long)
            when (m["event_type"]) {
                "PAYMENT_ATTEMPT" -> assertTrue(listOf("payee_id", "amount_inr", "payment_type").all { m[it] != null })
                "NEW_PAYEE" -> assertTrue(m["payee_id"] != null)
                "APP_INSTALL", "APP_FOREGROUND" -> assertTrue(m["app_package"] != null)
            }
            (m["payee_id"] as String?)?.let { assertTrue(Regex("^[0-9a-f]{16,128}$").matches(it)) }
            assertTrue(m.keys.all { it in allowedKeys }, "unexpected key in $m")
        }
    }

    private val allowedKeys = setOf(
        "event_type", "t_ms", "caller_known", "app_package", "install_source",
        "payee_id", "payee_is_new", "amount_inr", "payment_type", "source",
    )

    @Test fun sameEventTwiceDeliveredOnce() {
        val d = Deduplicator()
        val e = Event(1000, EventType.APP_INSTALL, appPackage = "com.x")
        assertFalse(d.isDuplicate(e))
        assertTrue(d.isDuplicate(e.copy(tMs = 2500)))
        assertFalse(d.isDuplicate(e.copy(tMs = 9000)))
    }

    @Test fun dedupeComparesWithPreviousRawEventEvenIfDropped() {
        val d = Deduplicator()
        val e = Event(0, EventType.APP_FOREGROUND, appPackage = "p")
        assertFalse(d.isDuplicate(e))
        assertTrue(d.isDuplicate(e.copy(tMs = 2000)))
        assertTrue(d.isDuplicate(e.copy(tMs = 4000))) // 2000 apart from the previous raw event, which was itself dropped
    }

    @Test fun retriedPaymentIsNeverDroppedByAppDedup() {
        val d = Deduplicator()
        val p = Event(0, EventType.PAYMENT_ATTEMPT, payeeId = "h", amountInr = 500.0)
        assertFalse(d.isDuplicate(p))
        assertFalse(d.isDuplicate(p.copy(tMs = 1000))) // detector must see it to repeat the original decision
    }

    @Test fun storedEventsReadBackIdentically() {
        val events = listOf(
            Event(1, EventType.CALL_START, callerKnown = false),
            Event(2, EventType.APP_INSTALL, appPackage = "com.x", installSource = com.satark.detector.InstallSource.SIDELOAD),
            Event(3, EventType.PAYMENT_ATTEMPT, payeeId = "h", payeeIsNew = true, amountInr = 25000.0, paymentType = com.satark.detector.PaymentType.P2P),
            Event(4, EventType.CALL_START),
        )
        for (e in events) {
            val json = org.json.JSONObject(EventMapper.toSchemaMap(e, "qr")).toString()
            assertEquals(e, EventMapper.fromSchemaJson(json))
        }
        assertNull(EventMapper.fromSchemaJson("not json"))
    }

    @Test fun videoAfterUnknownCallIsUnknown() {
        val v = com.satark.app.events.VideoOrigin(linkWindowMs = 600_000)
        val video = { t: Long -> Event(t, EventType.VIDEO_SESSION_START, appPackage = "com.whatsapp") }
        assertEquals(null, v.classify(video(0)).callerKnown) // no call yet: unchanged
        v.classify(Event(10, EventType.CALL_START, callerKnown = false))
        assertEquals(false, v.classify(video(20)).callerKnown) // during the unknown call
        v.classify(Event(30, EventType.CALL_END))
        assertEquals(false, v.classify(video(30 + 599_000)).callerKnown) // inside the window
        assertEquals(null, v.classify(video(30 + 601_000)).callerKnown) // too late
        v.classify(Event(700_000, EventType.CALL_START, callerKnown = true))
        assertEquals(null, v.classify(video(700_010)).callerKnown) // known caller: unchanged
        assertEquals(true, v.classify(video(700_020).copy(callerKnown = true)).callerKnown) // supplied value kept
    }

    @Test fun longVideoCallStaysOneSession() {
        val out = mutableListOf<com.satark.app.signals.RawSignal>()
        val v = com.satark.app.signals.VideoSessionTracker(setOf("com.whatsapp"), graceMs = 30_000) { out += it }
        v.resumed("com.whatsapp", 0)
        for (t in 3_000L..3 * 3600_000L step 3_000L) v.poll(t) // 3 h in the call, no new events
        assertEquals(1, out.size) // started, never ended
        v.resumed("com.bank", 3 * 3600_000L + 1_000)
        v.poll(3 * 3600_000L + 20_000); assertEquals(1, out.size) // short switch away: still the same session
        v.resumed("com.whatsapp", 3 * 3600_000L + 25_000)
        v.paused("com.whatsapp", 3 * 3600_000L + 40_000)
        v.poll(3 * 3600_000L + 80_000)
        assertEquals(2, out.size)
        assertTrue(out.last() is com.satark.app.signals.RawSignal.VideoEnded)
        assertEquals(3 * 3600_000L + 40_000, out.last().tMs)
    }

    @Test fun outOfOrderEventsReleasedInTimestampOrder() {
        val s = EventSequencer()
        s.add(Event(300, EventType.CALL_END))
        s.add(Event(100, EventType.CALL_START, callerKnown = false))
        s.add(Event(200, EventType.APP_FOREGROUND, appPackage = "p"))
        assertEquals(listOf(100L, 200L, 300L), s.flush().map { it.tMs })
        s.add(Event(50, EventType.CALL_END)) // late: clamped, never goes backwards
        assertEquals(listOf(300L), s.flush().map { it.tMs })
    }

    @Test fun drainHoldsRecentEvents() {
        val s = EventSequencer(holdMs = 1000)
        s.add(Event(5000, EventType.CALL_END))
        assertTrue(s.drain(5500).isEmpty())
        assertEquals(1, s.drain(6000).size)
    }
}

class WatchlistConsistencyTest {
    @Test fun appWatchlistMatchesDetectorModel() {
        val json = File("../contracts/watchlist.json").readText()
        val app = Regex("\"(com\\.[a-z0-9._]+)\"").findAll(json).map { it.groupValues[1] }.toSet()
        assertEquals(ModelConfig.loadBundled().watchlistSet, app)
    }
}

class UpiResultParserTest {
    @Test fun successWithRef() {
        val r = com.satark.app.payments.UpiResultParser.parse("txnId=T1&responseCode=00&Status=SUCCESS&txnRef=R9")!!
        assertEquals("success", r.status); assertEquals("R9", r.txnRef)
    }
    @Test fun failureFallsBackToTxnId() {
        val r = com.satark.app.payments.UpiResultParser.parse("Status=FAILURE&txnId=T2")!!
        assertEquals("failure", r.status); assertEquals("T2", r.txnRef)
    }
    @Test fun submittedUnknownOrEmptyPostsNothing() {
        for (s in listOf("Status=SUBMITTED", "Status=PENDING", "garbage", "", null)) assertNull(com.satark.app.payments.UpiResultParser.parse(s), s)
    }
}

class ContractTest {
    private val yaml = File("../contracts/api.yaml").readText()

    @Test fun everyPathTheClientCallsIsInApiYaml() {
        for (p in listOf("/auth/challenge", "/auth/device", "/auth/refresh", "/trusted-contact", "/risk-check",
            "/payments/{id}:", "/payments/{id}/result", "/alert", "/signature")) assertTrue(yaml.contains(p), p)
    }

    @Test fun requestFieldNamesMatchApiYaml() {
        val ours = File("src/main/kotlin/com/satark/app/net/Api.kt").readText()
        for (f in listOf("trusted_device_id", "fcm_token", "payee_hash", "is_p2p", "razorpay_order_id", "reported_txn_ref",
            "txn_ref", "device_id", "pattern_id", "attestation_chain", "public_key", "refresh_token", "order_id", "payment_id")) {
            assertTrue(yaml.contains(f), "api.yaml lacks $f")
            assertTrue(ours.contains("\"$f\""), "Api.kt lacks $f")
        }
    }

    @Test fun manifestQueriesMatchWatchlist() {
        val manifest = File("src/main/AndroidManifest.xml").readText()
        val q = Regex("<package android:name=\"([^\"]+)\"").findAll(manifest).map { it.groupValues[1] }.toSet()
        assertEquals(ModelConfig.loadBundled().watchlistSet, q)
    }
}
