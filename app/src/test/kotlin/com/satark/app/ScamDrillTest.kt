package com.satark.app

import com.satark.app.drill.DrillChoice
import com.satark.app.drill.DrillHistory
import com.satark.app.drill.DrillRecord
import com.satark.app.drill.DrillScript
import com.satark.app.drill.DrillScripts
import com.satark.app.drill.DrillSession
import com.satark.app.drill.DrillStage
import com.satark.app.drill.DrillStore
import com.satark.app.drill.Tactic
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ScamDrillTest {
    private val inOrder: (List<DrillChoice>) -> List<DrillChoice> = { it }

    // ---- the scripts themselves -------------------------------------------------------------------------------------------------------

    @Test fun everyBeatHasExactlyOneSafeChoiceAndTwoWaysToGoWrong() {
        for (s in DrillScripts.all) for ((i, step) in s.steps.withIndex()) {
            assertEquals(3, step.choices.size, "${s.id} beat ${i + 1}")
            assertEquals(1, step.choices.count { it.safe }, "${s.id} beat ${i + 1} must have exactly one safe choice")
        }
    }

    @Test fun choiceIdsAreUniqueAcrossAllScripts() {
        val ids = DrillScripts.all.flatMap { s -> s.steps.flatMap { st -> st.choices.map { it.id } } }
        assertEquals(ids.size, ids.toSet().size)
        assertTrue(DrillScripts.all.map { it.id }.let { it.size == it.toSet().size })
    }

    @Test fun everyBeatIsFullyWrittenOut() {
        for (s in DrillScripts.all) for (st in s.steps) {
            assertTrue(st.why.isNotBlank() && st.caller.isNotBlank() && st.ask.isNotBlank() && st.headline.isNotBlank())
            assertTrue(st.choices.all { it.text.isNotBlank() && it.reaction.isNotBlank() })
        }
    }

    @Test fun theFourMovesNamedInTheBriefAreAllRehearsed() {
        val tactics = DrillScripts.digitalArrest.steps.map { it.tactic }
        for (t in listOf(Tactic.SHARE_OTP, Tactic.INSTALL_APP, Tactic.STAY_ON_VIDEO, Tactic.PAY_NOW)) assertTrue(t in tactics, "$t")
        assertTrue(DrillScripts.all.flatMap { s -> s.steps.map { it.tactic } }.toSet().size >= 9, "the set of scenarios should cover the common moves")
    }

    @Test fun theCallItselfRunsAboutAMinuteAndAHalfAndTheWholeThingUnderThreeMinutes() {
        // The brief: the caller is on the line for 60 to 90 seconds. The call clock stops while the screen pauses to explain.
        for (s in DrillScripts.all) {
            println("DRILL ${s.id}: call ${s.callSeconds}s, total ${s.estimatedSeconds}s, ${s.lengthLabel}")
            assertTrue(s.callSeconds in 60..90, "${s.id}: call ${s.callSeconds}s")
            assertTrue(s.estimatedSeconds in 60..150, "${s.id}: total ${s.estimatedSeconds}s")
            assertTrue(s.estimatedSeconds > s.callSeconds)
        }
    }

    @Test fun theLengthIsToldInWordsToTheNearestHalfMinute() {
        fun label(total: Int): String {
            // A script whose caller line alone takes `total` seconds (2.5 words a second), with nothing to read.
            val words = List((total * 2.5).toInt()) { "w" }.joinToString(" ")
            val step = DrillScripts.digitalArrest.steps.first().copy(caller = words, headline = "", why = "", choices = listOf(
                DrillChoice("x1", "a", true, ""), DrillChoice("x2", "b", false, ""), DrillChoice("x3", "c", false, "")))
            return DrillScript("t", "t", "b", "n", "r", listOf(step)).lengthLabel
        }
        // 4 seconds of choosing is added to every beat.
        assertEquals("about a minute", label(40))   // 44 s
        assertEquals("about 1½ minutes", label(86)) // 90 s
        assertEquals("about 2 minutes", label(116)) // 120 s
        assertEquals("about 2½ minutes", label(146)) // 150 s
    }

    @Test fun lineLengthsStayShortSoTheCallerFeelsLikeACaller() {
        for (s in DrillScripts.all) for (st in s.steps) {
            assertTrue(st.caller.split(" ").size <= 26, "${s.id}: '${st.caller}'")
            assertTrue(st.why.split(" ").size <= 45, "${s.id}: '${st.why}'")
        }
    }

    @Test fun nothingInARehearsalLooksLikeARealNumberAccountOrPerson() {
        val digits = Regex("\\d{6,}")
        for (s in DrillScripts.all) {
            val text = buildString {
                append(s.title).append(s.blurb).append(s.callerName).append(s.callerRole).append(s.callerNumber)
                for (st in s.steps) { append(st.caller).append(st.ask).append(st.why).append(st.satarkNote.orEmpty()); st.choices.forEach { append(it.text).append(it.reaction) } }
            }
            assertNull(digits.find(text.replace(",", "")), "${s.id} must not contain a long digit string (a number or account)")
            assertFalse(text.contains("@"), "no UPI ids or e-mail addresses")
            assertFalse(Regex("https?://|www\\.", RegexOption.IGNORE_CASE).containsMatchIn(text), "no real links")
        }
        // The only helpline named is the national one, and the only site is the national reporting portal.
        assertTrue(DrillScripts.realCallRules.any { it.contains("1930") && it.contains("cybercrime.gov.in") })
    }

    @Test fun aRehearsalNeverAsksForTheRealThing() {
        // The screen offers buttons for every choice and has no text box. These words must stay in the explanation, never in an instruction to type.
        for (s in DrillScripts.all) for (st in s.steps) assertFalse(st.ask.contains("type", ignoreCase = true) || st.ask.contains("enter your", ignoreCase = true), st.ask)
    }

    @Test fun theReactionToTheSafeChoiceIsAPushBackNotAnApproval() {
        // A real scammer escalates when refused; none of the safe-choice replies may read as the caller being satisfied.
        val pleased = Regex("\\b(good|thank you|perfect|wise|received|done)\\b", RegexOption.IGNORE_CASE)
        for (s in DrillScripts.all) for (st in s.steps) {
            val safe = st.choices.single { it.safe }
            assertFalse(pleased.containsMatchIn(safe.reaction), "${s.id}: '${safe.reaction}'")
        }
    }

    @Test fun everyScriptIsFoundById() {
        for (s in DrillScripts.all) assertEquals(s, DrillScripts.byId(s.id))
        assertNull(DrillScripts.byId("nope"))
    }

    @Test fun everyTacticHasALabelAndARule() {
        for (t in Tactic.entries) assertTrue(t.label.isNotBlank() && t.rule.isNotBlank())
    }

    // ---- the session --------------------------------------------------------------------------------------------------------------------

    private fun safeId(s: DrillSession) = s.state.choices.single { it.safe }.id
    private fun wrongId(s: DrillSession) = s.state.choices.first { !it.safe }.id

    @Test fun aSafeRunSpotsEverything() {
        val s = DrillSession(DrillScripts.digitalArrest, inOrder)
        repeat(s.script.steps.size) {
            assertEquals(DrillStage.Caller, s.state.stage)
            s.callerDone(); assertEquals(DrillStage.Decide, s.state.stage)
            s.choose(safeId(s)); assertEquals(DrillStage.Lesson, s.state.stage); assertTrue(s.state.picked!!.safe)
            s.next()
        }
        val r = s.state.result!!
        assertEquals(DrillStage.Debrief, s.state.stage)
        assertEquals(5, r.spotted); assertEquals(5, r.total); assertTrue(r.missed.isEmpty())
        assertEquals("You held firm every time.", r.verdict)
    }

    @Test fun aRunThatGivesInEveryTimeSpotsNothingAndSaysWhichMovesWorked() {
        val s = DrillSession(DrillScripts.bankKyc, inOrder)
        repeat(s.script.steps.size) { s.callerDone(); s.choose(wrongId(s)); s.next() }
        val r = s.state.result!!
        assertEquals(0, r.spotted)
        assertEquals(s.script.steps.map { it.tactic }, r.missed.map { it.tactic })
        assertTrue(r.verdict.contains("Try it again"))
    }

    @Test fun aMixedRunIsCountedPerBeat() {
        val s = DrillSession(DrillScripts.customsParcel, inOrder)
        val plan = listOf(true, false, true, true, false)
        plan.forEach { good -> s.callerDone(); s.choose(if (good) safeId(s) else wrongId(s)); s.next() }
        val r = s.state.result!!
        assertEquals(3, r.spotted)
        assertEquals(listOf(Tactic.OPEN_LINK, Tactic.SECRECY), r.missed.map { it.tactic })
        assertEquals("You caught most of them. Look at the ones you missed.", r.verdict)
    }

    @Test fun movesOutOfOrderAreIgnored() {
        val s = DrillSession(DrillScripts.digitalArrest, inOrder)
        assertEquals(DrillStage.Caller, s.choose(safeId(s)).stage, "cannot choose before the caller has finished")
        assertEquals(DrillStage.Caller, s.next().stage, "cannot skip ahead from the caller")
        s.callerDone()
        assertEquals(DrillStage.Decide, s.callerDone().stage)
        assertEquals(DrillStage.Decide, s.next().stage, "cannot skip a decision")
        assertEquals(DrillStage.Decide, s.choose("no-such-choice").stage, "a choice that is not on screen does nothing")
        assertTrue(s.state.answers.isEmpty())
    }

    @Test fun aDoubleTapDoesNotRecordTwoAnswersOrSkipTheLesson() {
        val s = DrillSession(DrillScripts.digitalArrest, inOrder)
        s.callerDone()
        val id = safeId(s)
        s.choose(id); s.choose(wrongId(s)) // the second tap arrives before the screen has changed
        assertEquals(1, s.state.answers.size)
        assertTrue(s.state.answers.single().safe)
        s.next(); s.next()
        assertEquals(DrillStage.Caller, s.state.stage)
        assertEquals(1, s.state.index, "two taps on Continue moved on once")
    }

    @Test fun theLessonStageKeepsTheChoiceUntilContinue() {
        val s = DrillSession(DrillScripts.digitalArrest, inOrder)
        s.callerDone(); s.choose(wrongId(s))
        assertFalse(s.state.picked!!.safe)
        s.next()
        assertNull(s.state.picked)
    }

    @Test fun theChoicesAreShuffledEachBeatAndAllStayOnScreen() {
        val reversed: (List<DrillChoice>) -> List<DrillChoice> = { it.reversed() }
        val s = DrillSession(DrillScripts.digitalArrest, reversed)
        assertEquals(DrillScripts.digitalArrest.steps[0].choices.reversed(), s.state.choices)
        // With the real shuffle, over many runs the safe choice is not stuck in one position.
        val positions = (1..200).map { DrillSession(DrillScripts.bankKyc).state.choices.indexOfFirst { c -> c.safe } }.toSet()
        assertEquals(setOf(0, 1, 2), positions)
    }

    @Test fun pressureClimbsAsTheCallGoesOn() {
        val s = DrillSession(DrillScripts.digitalArrest, inOrder)
        var last = s.state.pressure
        repeat(5) {
            s.callerDone(); assertTrue(s.state.pressure >= last); last = s.state.pressure
            s.choose(safeId(s)); assertTrue(s.state.pressure >= last); last = s.state.pressure
            s.next()
        }
        assertEquals(1f, s.state.pressure)
        assertTrue(s.state.pressure <= 1f)
    }

    @Test fun theNumberOfTheStepIsOneBased() {
        val s = DrillSession(DrillScripts.digitalArrest, inOrder)
        assertEquals(1, s.state.number); assertEquals(5, s.state.total)
    }

    @Test fun aFinishedRehearsalStartsUnrecordedSoTheScreenSavesItOnce() {
        val s = DrillSession(DrillScripts.digitalArrest, inOrder)
        assertFalse(s.recorded)
        s.recorded = true
        assertTrue(s.recorded)
    }

    @Test fun aSessionWithNoBeatsIsRefused() {
        val empty = DrillScript("x", "t", "b", "n", "r", emptyList())
        var failed = false
        try { DrillSession(empty) } catch (_: IllegalArgumentException) { failed = true }
        assertTrue(failed)
    }

    @Test fun theResultIsOnlyAvailableAtTheEnd() {
        val s = DrillSession(DrillScripts.digitalArrest, inOrder)
        assertNull(s.state.result)
        s.callerDone(); s.choose(safeId(s)); s.next()
        assertNull(s.state.result)
    }

    // ---- the history --------------------------------------------------------------------------------------------------------------------

    private class Mem : DrillStore { override var records: List<DrillRecord> = emptyList() }

    private fun finished(script: DrillScript, good: Int): com.satark.app.drill.DrillResult {
        val s = DrillSession(script, inOrder)
        script.steps.forEachIndexed { i, _ -> s.callerDone(); s.choose(if (i < good) safeId(s) else wrongId(s)); s.next() }
        return s.state.result!!
    }

    private val day = 86_400_000L

    @Test fun aFinishedRehearsalIsRememberedNewestFirst() {
        var now = 10 * day
        val h = DrillHistory(Mem(), { now })
        h.add(finished(DrillScripts.digitalArrest, 5))
        now += day
        h.add(finished(DrillScripts.bankKyc, 3))
        assertEquals(listOf("bank-kyc", "digital-arrest"), h.records.map { it.scriptId })
        assertEquals(3, h.last()!!.spotted); assertEquals(5, h.last()!!.total)
        assertEquals(5, h.lastFor("digital-arrest")!!.spotted)
        assertNull(h.lastFor("customs-parcel"))
    }

    @Test fun theRecordListIsCapped() {
        val h = DrillHistory(Mem(), { 1L })
        repeat(DrillHistory.MAX_RECORDS + 7) { h.add(finished(DrillScripts.digitalArrest, 1)) }
        assertEquals(DrillHistory.MAX_RECORDS, h.records.size)
    }

    @Test fun theSuggestionIsAScenarioNotTriedYetThenTheOneLeftLongest() {
        var now = 100 * day
        val h = DrillHistory(Mem(), { now })
        assertEquals(DrillScripts.digitalArrest, h.suggested())
        h.add(finished(DrillScripts.digitalArrest, 5)); now += day
        assertEquals(DrillScripts.bankKyc, h.suggested())
        h.add(finished(DrillScripts.bankKyc, 5)); now += day
        h.add(finished(DrillScripts.customsParcel, 5)); now += day
        assertEquals(DrillScripts.digitalArrest, h.suggested(), "all done: the oldest comes round again")
        h.add(finished(DrillScripts.digitalArrest, 5))
        assertEquals(DrillScripts.bankKyc, h.suggested())
    }

    @Test fun theHomeLineSaysWhenYouLastPractisedAndWhenARefresherIsDue() {
        var now = 200 * day
        val h = DrillHistory(Mem(), { now })
        assertTrue(h.summary().startsWith("Rehearse a scam call"))
        h.add(finished(DrillScripts.digitalArrest, 4))
        assertEquals("Last practised today: 4 of 5 spotted", h.summary())
        now += day; assertEquals("Last practised yesterday: 4 of 5 spotted", h.summary())
        now += 5 * day; assertEquals("Last practised 6 days ago: 4 of 5 spotted", h.summary())
        now += 30 * day; assertEquals("Last practised 36 days ago. Time for a refresher", h.summary())
        now += 40 * day; assertEquals("Last practised 2 months ago. Time for a refresher", h.summary())
    }

    @Test fun aClockThatMovesBackNeverShowsANegativeAge() {
        var now = 500 * day
        val h = DrillHistory(Mem(), { now })
        h.add(finished(DrillScripts.digitalArrest, 5))
        now -= 3 * day
        assertEquals("Last practised today: 5 of 5 spotted", h.summary())
    }

    @Test fun practisingNeverChangesAnythingElse() {
        // The history only holds its own records: there is nothing in it for a payment decision to read.
        val store = Mem()
        DrillHistory(store, { 1L }).add(finished(DrillScripts.digitalArrest, 5))
        assertEquals(1, store.records.size)
        assertNotEquals(0L, store.records.single().atMs)
    }
}
