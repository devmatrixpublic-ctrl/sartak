package com.satark.app.ui.drill

import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.satark.app.AppGraph
import com.satark.app.drill.DrillResult
import com.satark.app.drill.DrillScript
import com.satark.app.drill.DrillScripts
import com.satark.app.drill.DrillSession
import com.satark.app.drill.DrillStage
import com.satark.app.drill.DrillState
import com.satark.app.ui.theme.Card
import com.satark.app.ui.theme.SatarkHeader
import kotlinx.coroutines.delay

/**
 * Scam Inoculation Mode. Satark plays the caller in a short rehearsal; at each point where a real scammer pushes (a code, an app, staying on
 * video, paying) the call pauses, the person chooses, and the screen explains why a real caller would never need it.
 * It is practice only: no call is made or heard by anyone else, nothing is sent, and no real code, PIN or card number is ever asked for.
 */
@Composable
fun DrillScreen(graph: AppGraph, onBack: () -> Unit) {
    // The running rehearsal lives in the graph, so it survives the screen restarting when the phone is turned.
    var session by remember { mutableStateOf(graph.activeDrill) }
    fun set(s: DrillSession?) { graph.activeDrill = s; session = s }
    val s = session
    if (s == null) {
        DrillMenu(graph, onBack) { set(DrillSession(it)) }
    } else {
        BackHandler { set(null) } // leaving mid-call returns to the list; nothing is recorded for an unfinished rehearsal
        DrillPlay(graph, s, onMenu = { set(null) }, onAgain = { set(DrillSession(s.script)) }, onDone = { set(null); onBack() })
    }
}

// ---- the list of rehearsals ------------------------------------------------------------------------------------------------------------

@Composable
private fun DrillMenu(graph: AppGraph, onBack: () -> Unit, onStart: (DrillScript) -> Unit) {
    var voiceOn by remember { mutableStateOf(graph.store.drillVoiceOn) }
    val suggested = remember { graph.drillHistory.suggested() }
    Column(
        Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        SatarkHeader(
            "Practice a scam call",
            "A safe rehearsal, so a real scam call is not the first time you hear it.",
            trailing = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") } },
        )
        Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                val on = MaterialTheme.colorScheme.onPrimaryContainer
                Text("How it works", style = MaterialTheme.typography.titleSmall, color = on)
                Text("• Satark plays the caller. It is not a real call, and nothing is sent anywhere.", color = on)
                Text("• Each time a scammer would push you, the call pauses and you choose what to do.", color = on)
                Text("• Then Satark explains why a real caller would never need it.", color = on)
                Text("• It never asks for a real code, PIN or card number. You only tap.", color = on)
            }
        }
        Card(Modifier.fillMaxWidth()) {
            Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Column(Modifier.weight(1f)) {
                    Text("Hear the caller", style = MaterialTheme.typography.titleSmall)
                    Text("Reads the call aloud in your phone's own voice. Off by default, so it does not speak in public.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Switch(checked = voiceOn, onCheckedChange = { voiceOn = it; graph.store.drillVoiceOn = it })
            }
        }
        DrillScripts.all.forEach { script ->
            ScriptCard(script, graph.drillHistory.lastFor(script.id)?.let { "Last time: ${it.spotted} of ${it.total} spotted" } ?: "Not tried yet",
                suggested = script.id == suggested.id, onStart = { onStart(script) })
        }
        Text("If a call like this is happening right now: hang up, and call 1930, the national cyber crime helpline.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun ScriptCard(script: DrillScript, status: String, suggested: Boolean, onStart: () -> Unit) {
    Card(onClick = onStart, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(script.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                if (suggested) Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = MaterialTheme.shapes.small) {
                    Text("Suggested", Modifier.padding(horizontal = 10.dp, vertical = 4.dp), style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onPrimaryContainer)
                }
            }
            Text(script.blurb, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("${script.steps.size} moments · ${script.lengthLabel} · $status", style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (suggested) Button(onClick = onStart, Modifier.fillMaxWidth()) { Text("Start practice") }
            else OutlinedButton(onClick = onStart, Modifier.fillMaxWidth()) { Text("Start practice") }
        }
    }
}

/** The caller's words appear at about the pace of speech (roughly 2.9 words a second), voice or not, so it feels like a call. A tap shows them all. */
private const val CALLER_MS_PER_CHAR = 60L
private val CALL_BACKGROUND = Color(0xFF1B2538)
private val CALL_TEXT = Color(0xFFF1F4FA)

// ---- the rehearsal ---------------------------------------------------------------------------------------------------------------------

@Composable
private fun DrillPlay(graph: AppGraph, session: DrillSession, onMenu: () -> Unit, onAgain: () -> Unit, onDone: () -> Unit) {
    val ctx = LocalContext.current
    var st by remember(session) { mutableStateOf(session.state) }
    var voiceOn by remember { mutableStateOf(graph.store.drillVoiceOn) }
    val voice = remember { DrillVoice(ctx) }
    DisposableEffect(Unit) { onDispose { voice.shutdown() } }
    val reducedMotion = remember { Settings.Global.getFloat(ctx.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f }
    var callSeconds by remember(session) { mutableIntStateOf(0) }
    val scroll = rememberScrollState()

    // The call clock only runs while the caller is on the line; it stops when the rehearsal pauses to ask or explain.
    LaunchedEffect(st.stage, st.index) {
        while (st.stage == DrillStage.Caller) { delay(1_000); callSeconds++ }
    }
    LaunchedEffect(st.stage, st.index) {
        if (st.stage == DrillStage.Decide) { delay(120); scroll.animateScrollTo(scroll.maxValue) } else scroll.animateScrollTo(0)
    }
    // The finished rehearsal is remembered once, on this phone.
    val result = st.result
    LaunchedEffect(result != null) { if (result != null && !session.recorded) { session.recorded = true; runCatching { graph.drillHistory.add(result) } } }

    Column(
        Modifier.verticalScroll(scroll).padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        PracticeBanner(onExit = { voice.stop(); onMenu() }, showExit = result == null)
        if (result != null) {
            Debrief(result, onAgain = onAgain, onMenu = onMenu, onDone = onDone)
        } else {
            ProgressRow(st)
            // While the reply is explained, the call panel steps aside so the explanation is the first thing on screen.
            if (st.stage != DrillStage.Lesson) CallPanel(st, callSeconds, voice, voiceOn, reducedMotion, onCallerDone = { st = session.callerDone() })
            when (st.stage) {
                DrillStage.Decide -> DecidePanel(st) { id -> voice.stop(); st = session.choose(id) }
                DrillStage.Lesson -> LessonPanel(st, voice, voiceOn) { voice.stop(); st = session.next() }
                else -> Unit
            }
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(if (voiceOn) "Voice on" else "Voice off", style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f))
                Switch(checked = voiceOn, onCheckedChange = { voiceOn = it; graph.store.drillVoiceOn = it; if (!it) voice.stop() })
            }
        }
    }
}

@Composable
private fun PracticeBanner(onExit: () -> Unit, showExit: Boolean) {
    Surface(color = MaterialTheme.colorScheme.tertiaryContainer, shape = MaterialTheme.shapes.small, modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(start = 14.dp, top = 4.dp, bottom = 4.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Icon(Icons.Filled.Info, contentDescription = null, tint = MaterialTheme.colorScheme.onTertiaryContainer)
            Text("PRACTICE · This is not a real call", Modifier.weight(1f), style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onTertiaryContainer)
            if (showExit) IconButton(onClick = onExit) {
                Icon(Icons.Filled.Close, contentDescription = "End practice", tint = MaterialTheme.colorScheme.onTertiaryContainer)
            }
        }
    }
}

@Composable
private fun ProgressRow(st: DrillState) {
    val colour = lerp(MaterialTheme.colorScheme.primary, MaterialTheme.colorScheme.error, st.pressure)
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row {
            Text("Moment ${st.number} of ${st.total}", style = MaterialTheme.typography.labelLarge, modifier = Modifier.weight(1f))
            Text("Pressure from the caller", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        LinearProgressIndicator(
            progress = { st.pressure }, color = colour, trackColor = MaterialTheme.colorScheme.surfaceVariant,
            modifier = Modifier.fillMaxWidth().semantics { contentDescription = "Pressure from the caller: ${(st.pressure * 100).toInt()} percent" },
        )
    }
}

/** The "phone screen": who is calling, the clock, and what they are saying. The words appear as they would be spoken, and a tap shows them all. */
@Composable
private fun CallPanel(
    st: DrillState, seconds: Int, voice: DrillVoice, voiceOn: Boolean, reducedMotion: Boolean, onCallerDone: () -> Unit,
) {
    val line = st.step.caller
    val onCaller = st.stage == DrillStage.Caller
    var shown by remember(st.index, st.stage) { mutableIntStateOf(if (onCaller && !reducedMotion) 0 else line.length) }

    LaunchedEffect(st.index, st.stage) {
        if (!onCaller) return@LaunchedEffect
        if (voiceOn) voice.say(line, asCaller = true)
        while (shown < line.length) { delay(CALLER_MS_PER_CHAR); shown++ }
        delay(450)
        if (voiceOn) voice.finish()
        onCallerDone()
    }

    val pulse = rememberInfiniteTransition(label = "ring")
    val ring by pulse.animateFloat(1f, 1.22f, infiniteRepeatable(tween(850), RepeatMode.Reverse), label = "ring scale")
    // A call screen is dark in both themes.
    val bg = CALL_BACKGROUND
    val fg = CALL_TEXT
    Surface(color = bg, shape = MaterialTheme.shapes.large, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Box(contentAlignment = Alignment.Center, modifier = Modifier.size(60.dp)) {
                    if (onCaller && !reducedMotion) Box(Modifier.size(52.dp).scale(ring).background(MaterialTheme.colorScheme.primary.copy(alpha = 0.28f), CircleShape))
                    Box(Modifier.size(52.dp).background(MaterialTheme.colorScheme.primary, CircleShape), contentAlignment = Alignment.Center) {
                        Text(st.script.callerName.first().toString(), style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onPrimary)
                    }
                }
                Column(Modifier.weight(1f)) {
                    Text(st.script.callerName, style = MaterialTheme.typography.titleMedium, color = fg)
                    Text(st.script.callerRole, style = MaterialTheme.typography.bodySmall, color = fg.copy(alpha = 0.75f))
                    Text(
                        st.script.callerNumber + " · " + if (onCaller) "%02d:%02d".format(seconds / 60, seconds % 60) else "ON HOLD",
                        style = MaterialTheme.typography.bodySmall, color = fg.copy(alpha = 0.75f),
                    )
                }
            }
            Surface(
                color = fg.copy(alpha = 0.12f), shape = MaterialTheme.shapes.medium,
                onClick = { if (onCaller) { shown = line.length; voice.stop() } },
                modifier = Modifier.fillMaxWidth().semantics(mergeDescendants = true) { contentDescription = "The caller says: $line" },
            ) {
                Text("“" + line.take(shown) + if (shown < line.length) "" else "”",
                    Modifier.padding(16.dp).heightIn(min = 72.dp), style = MaterialTheme.typography.bodyLarge, color = fg)
            }
            if (onCaller && shown < line.length) Text("Tap the words to show them all", style = MaterialTheme.typography.labelSmall, color = fg.copy(alpha = 0.7f))
        }
    }
}

@Composable
private fun DecidePanel(st: DrillState, onChoose: (String) -> Unit) {
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("The call is paused", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            Text(st.step.ask, style = MaterialTheme.typography.titleMedium)
            st.choices.forEach { c ->
                Card(
                    onClick = { onChoose(c.id) }, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
                ) {
                    Box(Modifier.padding(horizontal = 16.dp, vertical = 14.dp).heightIn(min = 28.dp), contentAlignment = Alignment.CenterStart) {
                        Text(c.text, style = MaterialTheme.typography.bodyLarge)
                    }
                }
            }
        }
    }
}

@Composable
private fun LessonPanel(st: DrillState, voice: DrillVoice, voiceOn: Boolean, onNext: () -> Unit) {
    val picked = st.picked ?: return
    val step = st.step
    val last = st.index == st.total - 1
    LaunchedEffect(st.index) {
        if (voiceOn) {
            voice.say(picked.reaction, asCaller = true); voice.finish()
            voice.say(step.headline + " Here's why. " + step.why, asCaller = false)
        }
    }
    val good = picked.safe
    Card(
        Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = if (good) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.tertiaryContainer),
    ) {
        val on = if (good) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onTertiaryContainer
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(if (good) Icons.Filled.CheckCircle else Icons.Filled.Warning, contentDescription = null, tint = on)
                Text(if (good) "You held firm" else "This is exactly what the caller wants", style = MaterialTheme.typography.titleMedium, color = on)
            }
            Text("You chose: ${picked.text}", style = MaterialTheme.typography.bodyMedium, color = on)
            Text("${st.script.callerName.substringBefore(' ')} replies: “${picked.reaction}”", style = MaterialTheme.typography.bodyMedium,
                fontStyle = FontStyle.Italic, color = on)
        }
    }
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(step.tactic.label, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            Text(step.headline, style = MaterialTheme.typography.titleMedium)
            Text("Here's why", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(step.why, style = MaterialTheme.typography.bodyLarge)
            step.satarkNote?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            Surface(color = MaterialTheme.colorScheme.surfaceContainer, shape = MaterialTheme.shapes.small) {
                Text("Remember: " + step.tactic.rule, Modifier.padding(12.dp), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
            }
        }
    }
    Button(onClick = onNext, Modifier.fillMaxWidth().heightIn(min = 52.dp)) {
        Text(if (last) "See how you did" else "Continue the call", style = MaterialTheme.typography.titleSmall)
    }
}

// ---- the summary -----------------------------------------------------------------------------------------------------------------------

@Composable
private fun Debrief(r: DrillResult, onAgain: () -> Unit, onMenu: () -> Unit, onDone: () -> Unit) {
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
        val on = MaterialTheme.colorScheme.onPrimaryContainer
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(r.script.title, style = MaterialTheme.typography.labelLarge, color = on)
            Text("${r.spotted} of ${r.total}", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Bold, color = on)
            Text("pressure moves resisted", style = MaterialTheme.typography.bodyMedium, color = on)
            Text(r.verdict, style = MaterialTheme.typography.titleSmall, color = on)
        }
    }
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Moment by moment", style = MaterialTheme.typography.titleSmall)
            r.answers.forEachIndexed { i, a ->
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
                    Icon(if (a.safe) Icons.Filled.CheckCircle else Icons.Filled.Warning, contentDescription = if (a.safe) "Resisted" else "Missed",
                        tint = if (a.safe) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.tertiary)
                    Column {
                        Text("${i + 1}. ${a.tactic.label}", style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold)
                        if (!a.safe) Text(a.tactic.rule, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("On a real call", style = MaterialTheme.typography.titleSmall)
            DrillScripts.realCallRules.forEachIndexed { i, rule -> Text("${i + 1}. $rule", style = MaterialTheme.typography.bodyMedium) }
        }
    }
    Button(onClick = onMenu, Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text("Try another scenario", style = MaterialTheme.typography.titleSmall) }
    OutlinedButton(onClick = onAgain, Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text("Play this one again") }
    TextButton(onClick = onDone, Modifier.fillMaxWidth()) { Text("Done") }
}
