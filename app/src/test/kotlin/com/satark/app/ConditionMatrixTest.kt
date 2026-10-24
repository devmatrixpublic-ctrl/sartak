package com.satark.app

import com.satark.app.events.NudgePolicy
import com.satark.app.events.SessionPolicy
import com.satark.app.events.SplitGuard
import com.satark.detector.Baseline
import com.satark.detector.Detector
import com.satark.detector.Event
import com.satark.detector.EventType
import com.satark.detector.InstallSource
import com.satark.detector.Level
import com.satark.detector.ModelConfig
import com.satark.detector.PaymentType
import kotlin.test.Test

/**
 * Every combination of phone signals a person could meet, run through the app's own decision path (session policy, the
 * detector, the split guard and the nudge rule) exactly as the phone's events would arrive. Prints one line per case so the
 * conditions behind each warning can be read off (docs/WHEN_SATARK_WARNS.md). A new person: usual payment about Rs 160.
 */
class ConditionMatrixTest {
    private val model = ModelConfig.loadBundled()
    private val min = 60_000L
    private val hour = 60 * min
    private val remote = "com.anydesk.anydeskandroid"

    private fun call(t: Long, known: Boolean = false) = Event(t, EventType.CALL_START, callerKnown = known)
    private fun end(t: Long) = Event(t, EventType.CALL_END)
    private fun payee(t: Long) = Event(t, EventType.NEW_PAYEE, payeeId = "P")
    private fun pay(t: Long, amount: Double, new: Boolean, who: String = "P") =
        Event(t, EventType.PAYMENT_ATTEMPT, payeeId = who, payeeIsNew = new, amountInr = amount, paymentType = PaymentType.P2P)
    private fun install(t: Long, pkg: String, src: InstallSource) = Event(t, EventType.APP_INSTALL, appPackage = pkg, installSource = src)
    private fun video(t: Long, known: Boolean) = Event(t, EventType.VIDEO_SESSION_START, callerKnown = known, appPackage = "com.whatsapp")

    private class Result(val hold: String?, val nudge: Boolean)

    private fun run(age: String, events: List<Event>, tickAt: Long? = null): Result {
        val baseline = Baseline.coldStart(model)
        val main = Detector.create(age, baseline, model)
        val guard = SplitGuard(model, age, baseline)
        val policy = SessionPolicy()
        var hold: String? = null
        var nudge = false
        for (raw in events) {
            val step = policy.prepare(raw) ?: continue
            if (step.resetFirst) { main.reset(); guard.reset() }
            val d = main.onEvent(step.event)
            val g = guard.onEvent(step.event)
            if (hold == null && d.level == Level.HARD) hold = "main:${d.mechanism}:${d.reasons.take(3).joinToString("+")}"
            else if (hold == null && g.level == Level.HARD) hold = "split-guard:${g.reasons.take(3).joinToString("+")}"
            if (raw.type == EventType.PAYMENT_ATTEMPT && NudgePolicy.shouldNudge(policy.unknownCallActive, raw.payeeIsNew, raw.amountInr, 161.57)) nudge = true
        }
        if (tickAt != null && hold == null) main.onTick(tickAt).takeIf { it.level == Level.HARD }?.let { hold = "main:${it.mechanism}:${it.reasons.take(3).joinToString("+")}" }
        return Result(hold, nudge)
    }

    private fun show(name: String, events: List<Event>, tickAt: Long? = null) {
        val r = run("36-59", events, tickAt)
        val r60 = run("60+", events, tickAt)
        val out = when {
            r.hold != null -> "HOLD   ${r.hold}"
            r.nudge -> "NUDGE"
            else -> "quiet"
        }
        val out60 = when { r60.hold != null -> "HOLD" ; r60.nudge -> "NUDGE"; else -> "quiet" }
        println("SCEN | $name | $out | 60+: $out60")
    }

    @Test fun printTheConditionMatrix() {
        val amounts = listOf(300.0, 5_000.0, 20_000.0, 50_000.0, 100_000.0)
        // No scam signals at all
        show("no call, known payee, Rs 300", listOf(pay(0, 300.0, false)))
        show("no call, NEW payee, Rs 50,000", listOf(payee(0), pay(1, 50_000.0, true)))
        show("unknown call, KNOWN payee, Rs 50,000", listOf(call(0), pay(2 * min, 50_000.0, false)))
        // Unknown call + new payee at rising amounts
        for (a in amounts) show("unknown call + NEW payee, Rs ${a.toInt()}", listOf(call(0), payee(2 * min - 1), pay(2 * min, a, true)))
        show("KNOWN caller + new payee, Rs 50,000", listOf(call(0, known = true), payee(2 * min - 1), pay(2 * min, 50_000.0, true)))
        show("unknown call ended 5 min ago, new payee, Rs 50,000", listOf(call(0), end(min), payee(6 * min - 1), pay(6 * min, 50_000.0, true)))
        // Installs
        show("unknown call + sideloaded app (no payment)", listOf(call(0), install(min, "com.example.supportapp", InstallSource.SIDELOAD)))
        show("unknown call + sideloaded app + known payee Rs 300", listOf(call(0), install(min, "com.example.supportapp", InstallSource.SIDELOAD), pay(3 * min, 300.0, false)))
        show("unknown call + Play Store app (no payment)", listOf(call(0), install(min, "com.example.app", InstallSource.PLAY_STORE)))
        show("unknown call + remote-access app (Play Store), no payment", listOf(call(0), install(min, remote, InstallSource.PLAY_STORE)))
        show("unknown call + remote-access app opened, no payment", listOf(call(0), Event(min, EventType.APP_FOREGROUND, appPackage = remote)))
        show("no call, sideloaded app only", listOf(install(0, "com.example.supportapp", InstallSource.SIDELOAD)))
        show("no call, remote-access app opened only", listOf(Event(0, EventType.APP_FOREGROUND, appPackage = remote)))
        show("no call, sideloaded app + new payee Rs 50,000", listOf(install(0, "com.example.supportapp", InstallSource.SIDELOAD), payee(2 * min - 1), pay(2 * min, 50_000.0, true)))
        // Video
        show("unknown video call 30 min, then new payee Rs 50,000", listOf(video(0, false), payee(30 * min - 1), pay(30 * min, 50_000.0, true)))
        show("unknown video call for 2 hours (long session rule)", listOf(video(0, false)), tickAt = 2 * hour + min)
        show("known video call for 3 hours", listOf(video(0, true)), tickAt = 3 * hour)
        // Split payments
        for (piece in listOf(3_000.0, 10_000.0, 25_000.0)) {
            show("unknown call + 3 x Rs ${piece.toInt()} to one NEW payee",
                listOf(call(0), payee(2 * min - 1), pay(2 * min, piece, true), pay(4 * min, piece, false), pay(6 * min, piece, false)))
        }
        // Stranger text (the phone reports it as a short unknown contact)
        show("stranger text, then new payee Rs 50,000 five minutes later", listOf(call(0), end(1), payee(5 * min - 1), pay(5 * min, 50_000.0, true)))
        show("stranger text, then sideloaded app", listOf(call(0), end(1), install(2 * min, "com.example.supportapp", InstallSource.SIDELOAD)))
        // Order
        show("payee added right after the unknown call, Rs 5,000", listOf(call(0), end(min), payee(2 * min), pay(3 * min, 5_000.0, true)))
    }
}
