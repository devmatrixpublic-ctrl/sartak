package com.satark.app.ui.alerts

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp

/** Picks the screen from the AlertUi. Nudge is a dismissible banner; the rest take over the screen. */
@Composable
fun AlertHost(alert: AlertUi?, controller: AlertController, dialContactUri: String? = null) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    when (alert) {
        null -> Unit
        is AlertUi.Nudge -> NudgeBanner(alert, controller::dismiss)
        is AlertUi.Hard -> HardIntervention(
            alert,
            onCallContact = {
                runCatching { ctx.startActivity(ContactDialer.intent(ctx, dialContactUri)) } // no dialler: still tell the contact
                controller.escalateToTrustedContact()
            },
            onHold30 = controller::holdThirtyMinutes, onContinue = controller::continueAnyway,
        )
        is AlertUi.LongSession -> LongSessionAlert(alert, controller::dismiss)
        is AlertUi.TrustedContact -> TrustedContactAlert(alert, controller::dismiss)
    }
}

/** 1-3 reasons, each a sentence from strings.xml. */
@Composable
fun Reasons(codes: List<String>, color: Color = MaterialTheme.colorScheme.onSurface) {
    val ctx = LocalContext.current
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        codes.take(3).forEach { Text("•  " + ReasonText.of(ctx, it), style = MaterialTheme.typography.bodyLarge, color = color) }
    }
}

/** Rung 1: the scam this looks like, in plain words. */
@Composable
fun PlaybookCard(codes: List<String>) {
    val p = Friction.playbook(codes)
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest)) {
        Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Icon(Icons.Filled.Info, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(p.title, style = MaterialTheme.typography.titleMedium)
                Text(p.text, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

/** Rung 2: what the money is for. The answer stays on this screen; it never releases the payment. */
@Composable
private fun PurposeQuestion() {
    var picked by rememberSaveable { mutableStateOf<Friction.Purpose?>(null) }
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("What is this payment for?", style = MaterialTheme.typography.titleMedium)
            val p = picked
            if (p == null) {
                Text("Choose what you were told. Your answer stays on this phone.", style = MaterialTheme.typography.bodyMedium)
                Friction.Purpose.entries.forEach { option ->
                    OutlinedButton(onClick = { picked = option }, modifier = Modifier.fillMaxWidth()) {
                        Text(option.label, modifier = Modifier.fillMaxWidth())
                    }
                }
            } else {
                Text(p.label, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(p.reply, style = MaterialTheme.typography.bodyLarge)
                TextButton(onClick = { picked = null }) { Text("Choose a different answer") }
            }
        }
    }
}

@Composable
private fun FullScreen(container: Color, content: @Composable () -> Unit) {
    Surface(Modifier.fillMaxSize(), color = container) {
        Column(
            Modifier.safeDrawingPadding().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) { content() }
    }
}

@Composable
private fun AlertTitle(text: String, color: Color) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Icon(Icons.Filled.Warning, contentDescription = null, tint = color, modifier = Modifier.size(36.dp))
        Text(text, style = MaterialTheme.typography.headlineMedium, color = color)
    }
}

@Composable
fun NudgeBanner(a: AlertUi.Nudge, onDismiss: () -> Unit) {
    Card(
        Modifier.safeDrawingPadding().fillMaxWidth().padding(12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer),
        elevation = CardDefaults.cardElevation(defaultElevation = 6.dp),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(Icons.Filled.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.onTertiaryContainer)
                Text("Take a moment", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onTertiaryContainer)
            }
            Text("You are paying someone new while on a call with a number you don't know. Is anyone asking you to do this?",
                color = MaterialTheme.colorScheme.onTertiaryContainer)
            Reasons(a.reasons, MaterialTheme.colorScheme.onTertiaryContainer)
            OutlinedButton(onClick = onDismiss) { Text("I'm sure") }
        }
    }
}

/** Forced pause. The held payment cannot be continued from here: the only ways out are cancel or tell someone. */
@Composable
fun HardIntervention(a: AlertUi.Hard, onCallContact: () -> Unit, onHold30: () -> Unit, onContinue: () -> Unit) {
    val on = MaterialTheme.colorScheme.onErrorContainer
    FullScreen(MaterialTheme.colorScheme.errorContainer) {
        AlertTitle("Stop. This looks like a scam.", on)
        Text("Hang up. A real bank or police officer will never ask you to move money or install an app.",
            style = MaterialTheme.typography.titleMedium, color = on)
        Text("Why Satark stopped this", style = MaterialTheme.typography.labelLarge, color = on)
        Reasons(a.reasons, on)
        ReportFraudButton(a.reasons, color = on)
        ReadAloudButton("Stop. This looks like a scam.", "Hang up. A real bank or police officer will never ask you to move money or install an app.", a.reasons, on)
        PlaybookCard(a.reasons)
        PurposeQuestion()
        Text("Payments in Satark are paused for ${Friction.PAUSE_MS / 60_000} minutes so you can talk to someone you trust.",
            style = MaterialTheme.typography.bodyMedium, color = on)
        Button(
            onClick = onCallContact, modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error, contentColor = MaterialTheme.colorScheme.onError),
        ) { Text("Call trusted contact") }
        OutlinedButton(onClick = onHold30, modifier = Modifier.fillMaxWidth()) { Text("Hold payment 30 minutes", color = on) }
        TextButton(onClick = onContinue, modifier = Modifier.fillMaxWidth()) { Text("Continue anyway", color = on) }
    }
}

@Composable
fun TrustedContactAlert(a: AlertUi.TrustedContact, onDone: () -> Unit) {
    FullScreen(MaterialTheme.colorScheme.background) {
        AlertTitle("Your trusted contact has been told", MaterialTheme.colorScheme.primary)
        Text("They will see that Satark was worried. Call them now on a number you know, and do not continue the other call.",
            style = MaterialTheme.typography.titleMedium)
        Reasons(a.reasons)
        ReportFraudButton(a.reasons)
        ReadAloudButton("Your trusted contact has been told", "Call them now on a number you know, and do not continue the other call.", a.reasons)
        PlaybookCard(a.reasons)
        Button(onClick = onDone, modifier = Modifier.fillMaxWidth()) { Text("OK") }
    }
}

@Composable
fun LongSessionAlert(a: AlertUi.LongSession, onDone: () -> Unit) {
    val on = MaterialTheme.colorScheme.onTertiaryContainer
    FullScreen(MaterialTheme.colorScheme.tertiaryContainer) {
        AlertTitle("This video call has been going on for hours", on)
        Text("Scammers keep people on a video call for a long time so they can't think or ask anyone. Take a break and talk to someone you trust.",
            style = MaterialTheme.typography.titleMedium, color = on)
        Reasons(a.reasons, on)
        ReadAloudButton("This video call has been going on for hours", "Take a break and talk to someone you trust.", a.reasons, on)
        PlaybookCard(a.reasons)
        Button(onClick = onDone, modifier = Modifier.fillMaxWidth()) { Text("OK") }
    }
}
