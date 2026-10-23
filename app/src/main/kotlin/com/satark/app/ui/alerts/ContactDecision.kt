package com.satark.app.ui.alerts

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.satark.app.payments.PaymentRepository
import com.satark.app.ui.theme.SatarkHeader
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Shown on the trusted contact's phone when they tap a held-payment alert. It deliberately shows no payee or amount:
 * the contact cannot read someone else's payment (the server answers only the owner), and the call to the person is
 * what protects them. Approve releases the payment; Block cancels it for good.
 */
@Composable
fun ContactDecisionScreen(payments: PaymentRepository, paymentId: String, onDone: () -> Unit) {
    var busy by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<String?>(null) }
    var failed by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    fun send(approve: Boolean) {
        busy = true; failed = false
        scope.launch {
            val problem = withContext(Dispatchers.IO) { payments.decide(paymentId, approve) }
            busy = false
            if (problem == null) result = if (approve) "You approved the payment. It will go ahead." else "You blocked the payment. Nothing will be paid."
            else { failed = true; result = problem }
        }
    }

    Column(
        Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        SatarkHeader("Payment on hold", "Someone you protect is trying to send money.")
        Text("Call them first. Ask what the payment is for and who asked them to make it.", style = MaterialTheme.typography.bodyLarge)
        Text(
            "Scammers often pose as police, banks or officials and say the payment is urgent or secret. " +
                "If anything feels wrong, block it.",
            style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        val done = result != null && !failed
        result?.let { Text(it, color = if (failed) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.titleSmall) }
        if (done) {
            Button(onClick = onDone, Modifier.fillMaxWidth().height(52.dp)) { Text("Done") }
        } else {
            Button(
                enabled = !busy, onClick = { send(approve = false) }, modifier = Modifier.fillMaxWidth().height(52.dp),
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
            ) { Text(if (busy) "Sending…" else "Block the payment") }
            OutlinedButton(enabled = !busy, onClick = { send(approve = true) }, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                Text("Approve the payment")
            }
            OutlinedButton(onClick = onDone, Modifier.fillMaxWidth()) { Text("Not now") }
        }
    }
}
