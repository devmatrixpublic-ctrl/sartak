package com.satark.app.ui.guard

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.text.format.DateUtils
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.satark.app.AppGraph
import com.satark.app.guard.hasAllFilesAccess
import com.satark.app.ui.lock.rememberLockGate
import com.satark.app.ui.theme.Card
import kotlinx.coroutines.delay

private const val SHOWN = 8

/**
 * Protection screen: the download guard. It is opt-in, because it needs "All files access". It reads only file names, never what is inside a file.
 * Held files can be restored (behind the fingerprint or PIN, because "put it back" is what a scammer would ask for) or deleted.
 */
@Composable
fun DownloadGuardCard(graph: AppGraph, tick: Int) {
    val ctx = LocalContext.current
    val lock = rememberLockGate()
    var changed by remember { mutableIntStateOf(0) }
    val on = remember(tick, changed) { graph.store.downloadGuardOn }
    val access = remember(tick, changed) { hasAllFilesAccess() }
    // The guard acts while this screen is open (a file arrives, a warning is posted), so the list is read again every couple of seconds.
    var records by remember { mutableStateOf(graph.downloadGuard.records) }
    LaunchedEffect(tick, changed) {
        while (true) { records = graph.downloadGuard.records; delay(2_000) }
    }
    val supported = Build.VERSION.SDK_INT >= 30
    val active = on && access

    fun openAccessSettings() {
        runCatching { ctx.startActivity(Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:" + ctx.packageName))) }
            .onFailure { runCatching { ctx.startActivity(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)) } }
    }

    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Download guard", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                Surface(
                    color = if (active) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant,
                    shape = MaterialTheme.shapes.small,
                ) {
                    Text(
                        when { active -> "On"; on -> "Needs permission"; else -> "Off (optional)" },
                        Modifier.padding(horizontal = 10.dp, vertical = 4.dp), style = MaterialTheme.typography.labelMedium,
                        color = if (active) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Text(
                "Scam apps often arrive as a downloaded file named like “RTO Challan.apk”, “SBI KYC Update.apk” or “Wedding Invitation.apk”. Satark watches your " +
                    "Download folder and the documents you receive on WhatsApp and Telegram. If a file name looks like one of these scams, it moves the app out of reach " +
                    "and warns you. It reads only the file's name, never what is inside it. Documents are warned about, not moved.",
                style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            when {
                !supported -> Text("This needs Android 11 or newer.", style = MaterialTheme.typography.bodyMedium)
                !on -> Button(onClick = { graph.store.downloadGuardOn = true; changed++; openAccessSettings() }) { Text("Turn on") }
                !access -> {
                    Text("Allow “All files access” for Satark so it can see new downloads.", style = MaterialTheme.typography.bodyMedium)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { openAccessSettings() }) { Text("Allow file access") }
                        OutlinedButton(onClick = { graph.store.downloadGuardOn = false; changed++ }) { Text("Turn off") }
                    }
                }
                else -> OutlinedButton(onClick = { graph.store.downloadGuardOn = false; graph.downloadGuard.stop(); changed++ }) { Text("Turn off") }
            }
            if (records.isNotEmpty()) {
                Text("Recent", style = MaterialTheme.typography.titleSmall)
                records.take(SHOWN).forEach { r ->
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(r.name, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold)
                        Text(
                            "${r.category} · " + DateUtils.getRelativeTimeSpanString(r.atMs, System.currentTimeMillis(), DateUtils.MINUTE_IN_MILLIS) + " · " +
                                if (r.held) "moved to quarantine" else "left in place: do not open it unless you expected it",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            if (r.held) {
                                OutlinedButton(onClick = { lock.require("Restore a blocked file") { graph.downloadGuard.restore(r.id); changed++ } }) { Text("Restore") }
                                TextButton(onClick = { graph.downloadGuard.delete(r.id); changed++ }) { Text("Delete") }
                            } else {
                                TextButton(onClick = { graph.downloadGuard.dismiss(r.id); changed++ }) { Text("Dismiss") }
                            }
                        }
                    }
                }
            }
        }
    }
}
