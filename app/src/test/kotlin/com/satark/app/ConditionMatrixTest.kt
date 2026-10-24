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
import kotlin.test.assertEquals

/**
 * Every combination of phone signals a person could meet, run through the app's own decision path (session policy, the
 * detector, the split guard and the nudge rule) exactly as the phone's events would arrive, with the result each one must give
 * (docs/WHEN_SATARK_WARNS.md). A new person is assumed: usual payment about Rs 160. If a change to the detector, the policies
 * or the thresholds alters any warning, one of these fails and the table has to be updated on purpose.
 */
class ConditionMatrixTest {
    private enum class Out { QUIET, NUDGE, HOLD }

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

    private fun run(age: String, events: List<Event>, tickAt: Long?): Out {
        val baseline = Baseline.coldStart(model)
        val main = Detector.create(age, baseline, model)
        val guard = SplitGuard(model, age, baseline)
        val policy = SessionPolicy()
        var hold = false
        var nudge = false
        for (raw in events) {
            val step = policy.prepare(raw) ?: continue
            if (step.resetFirst) { main.reset(); guard.reset() }
            if (main.onEvent(step.event).level == Level.HARD || guard.onEvent(step.event).level == Level.HARD) hold = true
            if (raw.type == EventType.PAYMENT_ATTEMPT && NudgePolicy.shouldNudge(policy.unknownCallActive, raw.payeeIsNew, raw.amountInr, 161.57)) nudge = true
        }
        if (tickAt != null && !hold && main.onTick(tickAt).level == Level.HARD) hold = true
        return if (hold) Out.HOLD else if (nudge) Out.NUDGE else Out.QUIET
    }

    private fun check(name: String, events: List<Event>, adult: Out, older: Out = adult, tickAt: Long? = null) {
        assertEquals(adult, run("36-59", events, tickAt), "$name (36-59)")
        assertEquals(older, run("60+", events, tickAt), "$name (60+)")
    }

    @Test fun noScamSignalsStayQuiet() {
        check("no call, known payee, Rs 300", listOf(pay(0, 300.0, false)), Out.QUIET)
        check("no call, NEW payee, Rs 50,000", listOf(payee(0), pay(1, 50_000.0, true)), Out.QUIET)
        check("unknown call, KNOWN payee, Rs 50,000", listOf(call(0), pay(2 * min, 50_000.0, false)), Out.QUIET)
        check("KNOWN caller + new payee, Rs 50,000", listOf(call(0, known = true), payee(2 * min - 1), pay(2 * min, 50_000.0, true)), Out.QUIET)
    }

    @Test fun unknownCallPlusNewPayeeEscalatesWithTheAmount() {
        fun case(a: Double) = listOf(call(0), payee(2 * min - 1), pay(2 * min, a, true))
        check("Rs 300 is under twice the usual", case(300.0), Out.QUIET)
        check("Rs 5,000", case(5_000.0), Out.NUDGE)
        check("Rs 20,000", case(20_000.0), Out.NUDGE)
        check("Rs 50,000", case(50_000.0), Out.HOLD, Out.NUDGE)
        check("Rs 100,000", case(100_000.0), Out.HOLD)
    }

    @Test fun anUnknownCallThatHasEndedDoesNotTriggerThePaymentChecks() {
        check("call ended 5 min ago, new payee, Rs 50,000",
            listOf(call(0), end(min), payee(6 * min - 1), pay(6 * min, 50_000.0, true)), Out.QUIET)
    }

    @Test fun installsDuringAnUnknownCall() {
        val unknown = listOf(call(0))
        check("sideloaded app, no payment", unknown + install(min, "com.example.supportapp", InstallSource.SIDELOAD), Out.HOLD)
        check("sideloaded app + known payee Rs 300", unknown + install(min, "com.example.supportapp", InstallSource.SIDELOAD) + pay(3 * min, 300.0, false), Out.HOLD)
        check("Play Store app, no payment", unknown + install(min, "com.example.app", InstallSource.PLAY_STORE), Out.QUIET)
        check("remote-access app from Play, no payment", unknown + install(min, remote, InstallSource.PLAY_STORE), Out.QUIET)
        check("remote-access app opened, no payment", unknown + Event(min, EventType.APP_FOREGROUND, appPackage = remote), Out.QUIET)
    }

    @Test fun installsWithoutACallStayQuiet() {
        check("sideloaded app only", listOf(install(0, "com.example.supportapp", InstallSource.SIDELOAD)), Out.QUIET)
        check("remote-access app opened only", listOf(Event(0, EventType.APP_FOREGROUND, appPackage = remote)), Out.QUIET)
        check("sideloaded app + new payee Rs 50,000",
            listOf(install(0, "com.example.supportapp", InstallSource.SIDELOAD), payee(2 * min - 1), pay(2 * min, 50_000.0, true)), Out.QUIET)
    }

    @Test fun videoCalls() {
        check("unknown video 30 min, then new payee Rs 50,000", listOf(video(0, false), payee(30 * min - 1), pay(30 * min, 50_000.0, true)), Out.HOLD)
        check("unknown video call for 2 hours", listOf(video(0, false)), Out.HOLD, tickAt = 2 * hour + min)
        check("known video call for 3 hours", listOf(video(0, true)), Out.QUIET, tickAt = 3 * hour)
    }

    @Test fun paymentsSplitIntoPiecesAreAddedUp() {
        fun split(piece: Double) = listOf(call(0), payee(2 * min - 1), pay(2 * min, piece, true), pay(4 * min, piece, false), pay(6 * min, piece, false))
        check("3 x Rs 3,000", split(3_000.0), Out.NUDGE)
        check("3 x Rs 10,000", split(10_000.0), Out.HOLD, Out.NUDGE)
        check("3 x Rs 25,000", split(25_000.0), Out.HOLD)
    }

    @Test fun aStrangerTextAloneNeverChangesAPaymentDecision() {
        // The phone no longer sends texts to the detector (SmsSource), so a text is simply nothing here; these two are the old
        // behaviour for comparison: a text then a payment is quiet, and only a sideloaded app after it would have held.
        check("stranger text, then new payee Rs 50,000 five minutes later",
            listOf(call(0), end(1), payee(5 * min - 1), pay(5 * min, 50_000.0, true)), Out.QUIET)
        check("payee added right after the unknown call, Rs 5,000",
            listOf(call(0), end(min), payee(2 * min), pay(3 * min, 5_000.0, true)), Out.QUIET)
    }
}
