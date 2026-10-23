package com.satark.app.ui.onboarding

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.satark.app.AppGraph
import com.satark.app.signals.SignalService
import com.satark.app.ui.theme.SatarkHeader
import kotlinx.coroutines.launch

/** What the consent screen says it does, and does not do. Kept in one place so the screen and the tests agree. */
object ConsentText {
    val watches = listOf(
        "Whether a call is from someone not in your contacts, and when it starts and ends",
        "When a new app is installed, and whether it came from Google Play",
        "How long video apps are open",
        "The payments you start inside Satark",
    )
    val never = listOf(
        "What anyone says or shows on a call",
        "Your messages, photos or contacts list",
        "Phone numbers or UPI IDs in readable form (they are scrambled on this phone first)",
    )
}

/** First-run consent. Nothing is watched until the person agrees; they can say no and still use the pay screen. */
@Composable
fun ConsentScreen(onChoice: (agreed: Boolean) -> Unit) {
    Column(
        Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        SatarkHeader("Before we start", "Satark needs your OK to watch for signs of a scam on this phone.")
        Text("Satark will look at", style = MaterialTheme.typography.titleSmall)
        ConsentText.watches.forEach { Text("• $it") }
        Text("Satark never reads", style = MaterialTheme.typography.titleSmall)
        ConsentText.never.forEach { Text("• $it") }
        Text(
            "The checks run on your phone. You can turn this off, or delete everything Satark keeps, at any time in Protection settings.",
            style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Button(onClick = { onChoice(true) }, Modifier.fillMaxWidth().height(52.dp)) { Text("I agree") }
        OutlinedButton(onClick = { onChoice(false) }, Modifier.fillMaxWidth().height(52.dp)) { Text("Not now") }
    }
}

/** In Protection settings: the language of the warning reasons. The Hindi is machine-drafted and needs native review. */
@Composable
fun LanguageCard() {
    val ctx = LocalContext.current
    var current by remember { mutableStateOf(com.satark.app.ui.Language.get(ctx)) }
    fun pick(code: String?) {
        com.satark.app.ui.Language.set(ctx, code); current = code
        (ctx as? android.app.Activity)?.recreate()
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Language of warnings", style = MaterialTheme.typography.titleMedium)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for ((label, code) in listOf("English" to com.satark.app.ui.Language.ENGLISH, "हिन्दी" to com.satark.app.ui.Language.HINDI)) {
                    if (current == code) Button(onClick = { pick(code) }) { Text(label) } else OutlinedButton(onClick = { pick(code) }) { Text(label) }
                }
                if (current != null) TextButton(onClick = { pick(null) }) { Text("Phone's language") }
            }
            Text(
                "Only the reasons inside a warning are translated. The Hindi is machine-drafted and still needs review by a native speaker.",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/** In Protection settings: turn watching off or on again, and delete everything Satark keeps on this phone. */
@Composable
fun ConsentCard(graph: AppGraph, onDeleted: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var on by remember { mutableStateOf(graph.store.consent) }
    var confirm by remember { mutableStateOf(false) }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Let Satark watch for scam signals", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                Switch(checked = on, onCheckedChange = { v ->
                    on = v; graph.store.consent = v
                    if (v) SignalService.start(ctx) else SignalService.stop(ctx)
                })
            }
            Text(
                if (on) "On. Satark is watching, on this phone only." else "Off. Satark is not watching calls, installs or video apps. Payments you start in Satark are still checked.",
                style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            var counts by remember { mutableStateOf<Pair<Int, Int>?>(null) }
            androidx.compose.runtime.LaunchedEffect(Unit) { counts = runCatching { graph.alertCounts() }.getOrNull() }
            counts?.let { (shown, merged) ->
                Text("Warnings shown: $shown. Repeats folded together: $merged.", style = MaterialTheme.typography.bodySmall)
            }
            if (com.satark.app.BuildConfig.DEBUG) {
                var shadow by remember { mutableStateOf(graph.store.shadowMode) }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Test build: shadow mode (log only, show nothing)", style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                    Switch(checked = shadow, onCheckedChange = { shadow = it; graph.store.shadowMode = it })
                }
            }
            OutlinedButton(onClick = { confirm = true }, Modifier.fillMaxWidth()) { Text("Delete my data") }
        }
    }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        title = { Text("Delete my data?") },
        text = { Text("This stops Satark, erases what it keeps on this phone (events, decisions, saved contact choice, sign-in) and asks the server to erase its record of this phone. Satark starts fresh next time.") },
        confirmButton = {
            TextButton(onClick = { confirm = false; scope.launch { graph.deleteAllData(); onDeleted() } }) { Text("Delete") }
        },
        dismissButton = { TextButton(onClick = { confirm = false }) { Text("Cancel") } },
    )
}
