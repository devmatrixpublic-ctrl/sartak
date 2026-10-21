package com.satark.app.ui.alerts

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp

/** Picks the screen from the AlertUi. Nudge is a dismissible banner; the rest take over the screen. */
@Composable
fun AlertHost(alert: AlertUi?, controller: AlertController) {
    when (alert) {
        null -> Unit
        is AlertUi.Nudge -> NudgeBanner(alert, controller::dismiss)
        is AlertUi.Hard -> HardIntervention(alert, controller::escalateToTrustedContact, controller::dismiss)
        is AlertUi.LongSession -> LongSessionAlert(alert, controller::dismiss)
        is AlertUi.TrustedContact -> TrustedContactAlert(alert, controller::dismiss)
    }
}

@Composable
private fun Reasons(codes: List<String>) {
    val ctx = LocalContext.current
    // 1-3 reasons; each is text from strings.xml (raw code until M4's strings land).
    codes.take(3).forEach { Text("• " + ReasonText.of(ctx, it), style = MaterialTheme.typography.bodyLarge) }
}

@Composable
fun NudgeBanner(a: AlertUi.Nudge, onDismiss: () -> Unit) {
    Card(
        Modifier.fillMaxWidth().padding(12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Take a moment", style = MaterialTheme.typography.titleMedium)
            Text("You are paying someone new while on a call with a number you don't know. Is anyone asking you to do this?")
            Reasons(a.reasons)
            OutlinedButton(onClick = onDismiss) { Text("I'm sure") }
        }
    }
}

/** Forced pause. The held payment cannot be continued from here: the only ways out are cancel or tell someone. */
@Composable
fun HardIntervention(a: AlertUi.Hard, onTellContact: () -> Unit, onCancel: () -> Unit) {
    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.errorContainer) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Stop. This looks like a scam.", style = MaterialTheme.typography.headlineMedium)
            Text("Hang up. A real bank or police officer will never ask you to move money or install an app.")
            Reasons(a.reasons)
            Button(onClick = onTellContact, modifier = Modifier.fillMaxWidth()) { Text("Tell my trusted contact") }
            OutlinedButton(onClick = onCancel, modifier = Modifier.fillMaxWidth()) { Text("Cancel this payment") }
        }
    }
}

@Composable
fun TrustedContactAlert(a: AlertUi.TrustedContact, onDone: () -> Unit) {
    Surface(Modifier.fillMaxSize()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Your trusted contact has been told", style = MaterialTheme.typography.headlineSmall)
            Text("They will see that Satark was worried. Call them now on a number you know, and do not continue the other call.")
            Reasons(a.reasons)
            Button(onClick = onDone, modifier = Modifier.fillMaxWidth()) { Text("OK") }
        }
    }
}

@Composable
fun LongSessionAlert(a: AlertUi.LongSession, onDone: () -> Unit) {
    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.tertiaryContainer) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("This video call has been going on for hours", style = MaterialTheme.typography.headlineSmall)
            Text("Scammers keep people on a video call for a long time so they can't think or ask anyone. Take a break and talk to someone you trust.")
            Reasons(a.reasons)
            Button(onClick = onDone, modifier = Modifier.fillMaxWidth()) { Text("OK") }
        }
    }
}
