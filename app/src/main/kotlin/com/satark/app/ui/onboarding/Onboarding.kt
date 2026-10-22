package com.satark.app.ui.onboarding

import android.Manifest
import android.content.ClipData
import android.content.ClipDescription
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.PersistableBundle
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.satark.app.AppGraph
import com.satark.app.net.TrustedContactRequest
import com.satark.app.push.PairingCode
import com.satark.app.push.Push
import com.satark.app.signals.SignalStatus
import com.satark.app.signals.SourceName
import com.satark.app.signals.SourceState
import kotlinx.coroutines.CancellationException
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

/** First run, and later the "Protection and trusted contact" screen ([settings] = true) reached from the pay screen. */
@Composable
fun OnboardingFlow(graph: AppGraph, settings: Boolean = false, onDone: () -> Unit) {
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
        Text(if (settings) "Protection and trusted contact" else "Set up Satark", style = MaterialTheme.typography.headlineSmall)
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

        Button(onClick = onDone, modifier = Modifier.fillMaxWidth()) {
            Text(when {
                settings -> "Back to Pay via Satark"
                status.allAvailable -> "Start protection"
                else -> "Continue with limited protection"
            })
        }
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
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Trusted contact", style = MaterialTheme.typography.titleMedium)
            Text("A person who gets an alert on their phone if Satark thinks you may be being scammed. They need Satark too.")
            LinkTrustedContact(graph)
            HorizontalDivider(Modifier.padding(vertical = 4.dp))
            MyPairingCode(graph)
        }
    }
}

/** The protected person pastes the contact's code: POST /trusted-contact {trusted_device_id, fcm_token}. */
@Composable
private fun LinkTrustedContact(graph: AppGraph) {
    var code by rememberSaveable { mutableStateOf("") }
    var msg by rememberSaveable { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    Text("Get alerts sent to someone you trust", style = MaterialTheme.typography.titleSmall)
    Text("Ask them to open Satark, tap “Show my pairing code” and send you the code. Paste it here.")
    OutlinedTextField(code, { code = it; msg = null }, label = { Text("Their pairing code") }, modifier = Modifier.fillMaxWidth(), maxLines = 3)
    OutlinedButton(enabled = !busy, onClick = {
        val p = PairingCode.parse(code)
        when {
            p == null -> msg = "That code does not look right. Copy the whole code from their Satark."
            p.deviceId == graph.store.deviceId -> msg = "That is your own code. Paste the code from the other person's phone."
            else -> {
                busy = true
                scope.launch {
                    msg = withContext(Dispatchers.IO) { linkContact(graph, p) }
                    busy = false
                }
            }
        }
    }) { Text(if (busy) "Linking…" else "Link") }
    msg?.let { Text(it) }
}

private suspend fun linkContact(graph: AppGraph, p: PairingCode.Parsed): String = try {
    graph.session.ensureRegistered()
    if (graph.api.trustedContact(TrustedContactRequest(p.deviceId, p.pushToken)).linked)
        "Linked. They will get an alert if Satark thinks you are being scammed."
    else "Could not link. Try again."
} catch (e: CancellationException) {
    throw e
} catch (e: retrofit2.HttpException) {
    when (e.code()) {
        404 -> "Their Satark is not registered yet. Ask them to open Satark once with internet on, then try again."
        422 -> "That code does not look right. Copy the whole code from their Satark."
        else -> "Could not link (error ${e.code()}). Try again later."
    }
} catch (e: Exception) {
    "Could not reach Satark. Check your internet connection and try again."
}

private sealed interface CodeUi {
    data object Hidden : CodeUi
    data object Loading : CodeUi
    data class Ready(val code: String) : CodeUi
    data class Failed(val message: String) : CodeUi
}

/** The contact's side: registers for push only now, then shows "<device id>:<push token>" to copy or share. */
@Composable
private fun MyPairingCode(graph: AppGraph) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var ui by remember { mutableStateOf<CodeUi>(CodeUi.Hidden) }
    var notifTick by remember { mutableIntStateOf(0) }
    val askNotifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { notifTick++ }
    fun load() {
        ui = CodeUi.Loading
        scope.launch { ui = withContext(Dispatchers.IO) { loadPairingCode(ctx, graph) } }
    }
    Text("Be someone's trusted contact", style = MaterialTheme.typography.titleSmall)
    Text("Show your pairing code and send it to the person you protect. This phone is registered for alerts only when you tap the button.")
    when (val s = ui) {
        CodeUi.Hidden -> OutlinedButton(onClick = { load() }) { Text("Show my pairing code") }
        CodeUi.Loading -> Text("Getting your code…")
        is CodeUi.Failed -> {
            Text(s.message)
            OutlinedButton(onClick = { load() }) { Text("Try again") }
        }
        is CodeUi.Ready -> {
            SelectionContainer { Text(s.code, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { copyPairingCode(ctx, s.code) }) { Text("Copy") }
                OutlinedButton(onClick = { sharePairingCode(ctx, s.code) }) { Text("Share") }
            }
            val canNotify = remember(notifTick) {
                Build.VERSION.SDK_INT < 33 ||
                    ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
            }
            if (!canNotify) {
                Text("Turn on notifications so the alert can reach you.")
                OutlinedButton(onClick = { askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS) }) { Text("Allow notifications") }
            }
        }
    }
}

private suspend fun loadPairingCode(ctx: Context, graph: AppGraph): CodeUi {
    if (!Push.isConfigured(ctx)) {
        return CodeUi.Failed("Alerts to a trusted contact are not set up in this build of Satark (Firebase is not configured).")
    }
    runCatching { graph.session.ensureRegistered() }
    val id = graph.store.deviceId
        ?: return CodeUi.Failed("Satark could not register this phone yet. Check your internet connection and try again.")
    val token = Push.token(ctx)
        ?: return CodeUi.Failed("Could not set up alerts on this phone. Check your internet connection and that Google Play services is up to date, then try again.")
    graph.store.sharedPushTokenHash = Push.hash(token)
    return CodeUi.Ready(PairingCode.format(id, token))
}

private fun copyPairingCode(ctx: Context, code: String) {
    val clip = ClipData.newPlainText("Satark pairing code", code)
    if (Build.VERSION.SDK_INT >= 33) clip.description.extras = PersistableBundle().apply { putBoolean(ClipDescription.EXTRA_IS_SENSITIVE, true) }
    runCatching { ctx.getSystemService(ClipboardManager::class.java).setPrimaryClip(clip) }
}

private fun sharePairingCode(ctx: Context, code: String) {
    val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, code)
    runCatching { ctx.startActivity(Intent.createChooser(send, "Send my Satark pairing code")) }
}
