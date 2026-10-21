package com.satark.app.ui.onboarding

import android.Manifest
import android.content.Intent
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.satark.app.AppGraph
import com.satark.app.net.TrustedContactRequest
import com.satark.app.signals.SignalStatus
import com.satark.app.signals.SourceName
import com.satark.app.signals.SourceState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Plain-language reason for each protection, shown next to its permission request. */
private data class Step(val source: SourceName, val title: String, val why: String)

private val steps = listOf(
    Step(SourceName.CALL, "Phone calls", "Satark notices when you are on a call with someone who is not in your contacts. Call audio is never recorded."),
    Step(SourceName.USAGE, "Usage access", "Satark sees which app is open, to notice screen-sharing and video-call apps. Opens Settings; switch Satark on."),
    Step(SourceName.INSTALL, "App installs", "Satark notices when a new app is installed and whether it came from Google Play."),
)

@Composable
fun OnboardingFlow(graph: AppGraph, onDone: () -> Unit) {
    val ctx = LocalContext.current
    var tick by remember { mutableIntStateOf(0) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { tick++ }
    val status = remember(tick) { graph.hub.status() }
    val scope = rememberCoroutineScope()

    val perms = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { tick++ }
    fun askPhone() {
        val list = mutableListOf(Manifest.permission.READ_PHONE_STATE, Manifest.permission.READ_CALL_LOG, Manifest.permission.READ_CONTACTS)
        if (Build.VERSION.SDK_INT >= 33) list += Manifest.permission.POST_NOTIFICATIONS
        perms.launch(list.toTypedArray())
    }

    Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Set up Satark", style = MaterialTheme.typography.headlineSmall)
        Text("Satark looks for the pattern of a coached payment scam. Nothing you say or see leaves your phone.")
        steps.forEach { s ->
            Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(s.title, style = MaterialTheme.typography.titleMedium)
                    Text(s.why)
                    val st = status.of(s.source)
                    Text(stateText(st))
                    if (st == SourceState.DENIED) Button(onClick = {
                        if (s.source == SourceName.USAGE) ctx.startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)) else askPhone()
                    }) { Text("Allow") }
                }
            }
        }
        ProtectionBanners(status)

        TrustedContactSetup(graph)

        Button(onClick = onDone, modifier = Modifier.fillMaxWidth()) { Text(if (status.allAvailable) "Start protection" else "Continue with limited protection") }
    }
}

private fun stateText(s: SourceState) = when (s) {
    SourceState.AVAILABLE -> "On"
    SourceState.DENIED -> "Off: permission needed"
    SourceState.UNSUPPORTED -> "Not available on this phone"
}

/** A banner for every protection that is unavailable or denied (degraded mode). */
@Composable
fun ProtectionBanners(status: SignalStatus) {
    val off = SourceName.entries.filter { status.of(it) != SourceState.AVAILABLE && it != SourceName.WATCHLIST }
    if (off.isEmpty()) return
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
        Column(Modifier.padding(12.dp)) {
            Text("Reduced protection", style = MaterialTheme.typography.titleSmall)
            off.forEach { Text("• ${it.name.lowercase().replaceFirstChar(Char::uppercase)} signal is ${stateText(status.of(it)).lowercase()}") }
            Text("Satark still checks payment amounts and new payees.")
        }
    }
}

@Composable
fun TrustedContactSetup(graph: AppGraph) {
    var code by remember { mutableStateOf("") }
    var msg by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Trusted contact", style = MaterialTheme.typography.titleMedium)
            Text("Someone who gets a message if Satark thinks you may be being scammed. They need Satark installed. Paste the pairing code from their app (device-id:token).")
            OutlinedTextField(code, { code = it }, label = { Text("Pairing code") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedButton(onClick = {
                val (id, token) = code.trim().split(":", limit = 2).let { (it.getOrNull(0) ?: "") to (it.getOrNull(1) ?: "") }
                if (id.isBlank() || token.isBlank()) { msg = "That code does not look right."; return@OutlinedButton }
                scope.launch {
                    msg = withContext(Dispatchers.IO) {
                        runCatching { graph.session.ensureRegistered(); graph.api.trustedContact(TrustedContactRequest(id, token)) }
                            .fold({ if (it.linked) "Linked." else "Could not link." }, { "Could not link: check the code and your connection." })
                    }
                }
            }) { Text("Link") }
            msg?.let { Text(it) }
            Spacer(Modifier.height(2.dp))
            Text("Your own pairing code (to give to someone who protects you or whom you protect): ${graph.store.deviceId ?: "registering…"}:<push token>")
            Text("Push delivery needs a Firebase project (google-services.json); until it is added the token part is not available.", style = MaterialTheme.typography.bodySmall)
        }
    }
}
