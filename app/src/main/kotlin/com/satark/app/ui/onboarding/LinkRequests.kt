package com.satark.app.ui.onboarding

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.padding
import com.satark.app.AppGraph
import com.satark.app.net.TrustedRespondRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * On the contact's phone: people who asked this phone to be their trusted contact. Nothing reaches this phone for them
 * until the person taps Accept, and Decline ends the request. No names or numbers are shown (none are known).
 */
@Composable
fun LinkRequestsPanel(graph: AppGraph) {
    var requests by remember { mutableStateOf<List<String>>(emptyList()) }
    var note by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    suspend fun load() {
        requests = withContext(Dispatchers.IO) {
            runCatching { graph.api.trustedRequests().requests.map { it.ownerDeviceId } }.getOrDefault(emptyList())
        }
    }
    LaunchedEffect(Unit) { load() }

    if (requests.isEmpty() && note == null) return
    Column(Modifier.padding(vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (requests.isNotEmpty()) Text("Someone asked you to be their trusted contact", style = MaterialTheme.typography.titleSmall)
        requests.forEachIndexed { i, owner ->
            Text("Request ${i + 1}. Only accept if you know the person and they asked you to.", style = MaterialTheme.typography.bodyMedium)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for ((label, decision) in listOf("Accept" to "accept", "Decline" to "decline")) {
                    val primary = decision == "accept"
                    val onClick = {
                        busy = true
                        scope.launch {
                            note = withContext(Dispatchers.IO) {
                                runCatching { graph.api.trustedRespond(TrustedRespondRequest(owner, decision)) }.fold(
                                    { if (primary) "Accepted. You will get an alert if Satark worries about them." else "Declined." },
                                    { "Could not send your answer. Try again." },
                                )
                            }
                            load(); busy = false
                        }
                        Unit
                    }
                    if (primary) Button(enabled = !busy, onClick = onClick) { Text(label) }
                    else OutlinedButton(enabled = !busy, onClick = onClick) { Text(label) }
                }
            }
        }
        note?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
    }
}
