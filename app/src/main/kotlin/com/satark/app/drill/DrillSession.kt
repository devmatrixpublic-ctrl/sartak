package com.satark.app.drill

enum class DrillStage {
    /** The caller is speaking. */
    Caller,
    /** The rehearsal is paused and waiting for the person to choose. */
    Decide,
    /** The choice is made; the caller's reply and the explanation are shown. */
    Lesson,
    /** The end: the summary. */
    Debrief,
}

/** Everything the screen needs for one moment of the rehearsal. Immutable: the session hands out a new one after each move. */
data class DrillState(
    val script: DrillScript,
    val stage: DrillStage,
    val index: Int,
    /** The beat on screen (the last one, at the end). */
    val step: DrillStep,
    /** The choices in the order shown this time. */
    val choices: List<DrillChoice>,
    /** What was chosen at this beat, once it has been. */
    val picked: DrillChoice?,
    val answers: List<DrillAnswer>,
) {
    val total: Int get() = script.steps.size
    /** 1-based, for “Step 2 of 5”. */
    val number: Int get() = index + 1
    /** How much pressure has been put on the person so far, 0 to 1: it climbs with each beat, as it does in a real call. */
    val pressure: Float get() = (index + if (stage == DrillStage.Caller) 0.5f else 1f).coerceAtMost(total.toFloat()) / total
    val result: DrillResult? get() = if (stage == DrillStage.Debrief) DrillResult(script, answers) else null
}

/** The outcome of a finished rehearsal. */
data class DrillResult(val script: DrillScript, val answers: List<DrillAnswer>) {
    val total: Int get() = answers.size
    val spotted: Int get() = answers.count { it.safe }
    val missed: List<DrillAnswer> get() = answers.filter { !it.safe }

    /** A plain verdict, never a pass or a fail: the point is to learn the moves, not to score. */
    val verdict: String get() = when {
        total == 0 -> ""
        spotted == total -> "You held firm every time."
        spotted * 2 >= total -> "You caught most of them. Look at the ones you missed."
        else -> "These moves are built to work on anyone. Now you know them. Try it again."
    }
}

/**
 * The rehearsal as a small state machine: Caller, then Decide, then Lesson, for each beat, then Debrief. Moves made out of order are ignored
 * and return the unchanged state, so a double tap on a button cannot skip a lesson or record two answers.
 *
 * The choices are shuffled for each beat so the right one is not always in the same place. [order] is how; tests pass a fixed order.
 */
class DrillSession(val script: DrillScript, private val order: (List<DrillChoice>) -> List<DrillChoice> = { it.shuffled() }) {
    init { require(script.steps.isNotEmpty()) { "a rehearsal needs at least one beat" } }

    private var stage = DrillStage.Caller
    private var index = 0
    private var shown: List<DrillChoice> = order(script.steps.first().choices)
    private var picked: DrillChoice? = null
    private val answers = ArrayList<DrillAnswer>()

    /** Set once the finished rehearsal has been saved to the history, so turning the phone on the summary does not save it twice. */
    var recorded = false

    val state: DrillState get() = DrillState(script, stage, index, script.steps[index], shown, picked, answers.toList())

    /** The caller has finished speaking: pause and ask. */
    fun callerDone(): DrillState {
        if (stage == DrillStage.Caller) stage = DrillStage.Decide
        return state
    }

    /** The person chose. A choice that is not on screen is ignored. */
    fun choose(choiceId: String): DrillState {
        if (stage != DrillStage.Decide) return state
        val c = shown.firstOrNull { it.id == choiceId } ?: return state
        picked = c
        answers += DrillAnswer(script.steps[index].tactic, c.safe)
        stage = DrillStage.Lesson
        return state
    }

    /** On from the explanation: the next beat, or the summary after the last one. */
    fun next(): DrillState {
        if (stage != DrillStage.Lesson) return state
        picked = null
        if (index == script.steps.lastIndex) stage = DrillStage.Debrief
        else { index++; shown = order(script.steps[index].choices); stage = DrillStage.Caller }
        return state
    }
}
