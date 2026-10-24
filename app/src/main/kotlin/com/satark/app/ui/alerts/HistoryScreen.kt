package com.satark.app.ui.alerts

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.satark.app.AppGraph
import com.satark.app.events.DecisionRow
import com.satark.app.ui.theme.SatarkHeader
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** What Satark has warned about, and what it keeps on this phone. Everything shown here is read from the phone's own storage. */
@Composable
fun HistoryScreen(graph: AppGraph, onBack: () -> Unit) {
    val ctx = LocalContext.current
    var rows by remember { mutableStateOf<List<DecisionRow>?>(null) }
    var counts by remember { mutableStateOf<Pair<Int, Int>?>(null) }
    var kept by remember { mutableStateOf<Int?>(null) }
    var nudges by remember { mutableStateOf<Int?>(null) }
    var held by remember { mutableStateOf<Int?>(null) }
    LaunchedEffect(Unit) {
        rows = runCatching { graph.recentDecisions(30) }.getOrDefault(emptyList())
        counts = runCatching { graph.alertCounts() }.getOrNull()
        kept = runCatching { graph.eventCount() }.getOrNull()
        held = runCatching { graph.heldCount() }.getOrNull()
        nudges = runCatching { graph.dispatcher.nudgesThisMonth() }.getOrNull()
    }

    Column(
        Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        SatarkHeader(
            "Alert history",
            "What Satark warned you about, and what it keeps on this phone.",
            trailing = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") } },
        )
        Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                val on = MaterialTheme.colorScheme.onPrimaryContainer
                Text("Kept on this phone", style = MaterialTheme.typography.titleSmall, color = on)
                counts?.let { (shown, merged) ->
                    Text("• Warnings shown: $shown. Repeats folded into them: $merged.", color = on)
                }
                kept?.let { Text("• Signals held right now: $it (each deleted within 24 hours).", color = on) }
                Text("• This warning list is deleted after 30 days.", color = on)
                Text("• Phone numbers and UPI IDs are never stored in readable form.", color = on)
                Text("• The text of your messages and the audio of your calls are never read.", color = on)
            }
        }
        Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("How often Satark interrupts", style = MaterialTheme.typography.titleSmall)
                held?.let { Text("• Payments Satark held for you in the last 30 days: $it.") }
                nudges?.let { Text("• Gentle nudges in the last 30 days: $it (Satark shows at most 1 a month).") }
                Text("• Goal: at most 1 alarm a quarter and 1 nudge a month for a genuine user.")
                Text("• Simulated users (not real people): about 0.08 alarms a quarter and 0.5 nudges a month.")
                Text("• Busy users can still see slightly more than 1 nudge a month. See ops/eval/reports/alert_budget.md.")
            }
        }
        val list = rows
        when {
            list == null -> Text("Loading...", color = MaterialTheme.colorScheme.onSurfaceVariant)
            list.isEmpty() -> Text("No warnings yet. When Satark warns you, it is listed here.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            else -> list.forEach { r -> HistoryRow(ctx, r) }
        }
    }
}

@Composable
private fun HistoryRow(ctx: android.content.Context, r: DecisionRow) {
    val whenText = remember(r.tMs) { SimpleDateFormat("d MMM, h:mm a", Locale.getDefault()).format(Date(r.tMs)) }
    val codes = r.reasons.split(",").map { it.trim() }.filter { it.isNotEmpty() }
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(whenText, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(
                if (r.level == "HARD") "Warning: this looked like a scam" else "Note",
                style = MaterialTheme.typography.titleSmall,
            )
            codes.take(3).forEach { Text("• ${ReasonText.of(ctx, it)}", style = MaterialTheme.typography.bodyMedium) }
        }
    }
}
