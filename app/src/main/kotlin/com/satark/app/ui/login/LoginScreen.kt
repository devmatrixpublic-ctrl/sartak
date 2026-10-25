package com.satark.app.ui.login

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.satark.app.AppGraph
import com.satark.app.account.AccountRepository
import com.satark.app.account.DevPhoneAuth
import com.satark.app.account.PhoneNumber
import com.satark.app.account.SendResult
import com.satark.app.account.VerifyResult
import com.satark.app.ui.theme.Card
import com.satark.app.ui.theme.SatarkHeader
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private enum class Step { PHONE, CODE, PROFILE }

private const val RESEND_SECONDS = 30

/**
 * First-run sign-in: phone number, the 6-digit code, then (for a new account) a name. Nothing here is required to use Satark: "Continue
 * without an account" is always offered, with what it costs. The phone number is never kept by the server, only a keyed hash.
 */
@Composable
fun LoginFlow(graph: AppGraph, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val auth = graph.phoneAuth
    var step by rememberSaveable { mutableStateOf(Step.PHONE) }
    var digits by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    var name by rememberSaveable { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var cooldown by remember { mutableIntStateOf(0) }
    val national = PhoneNumber.normalize(digits)

    LaunchedEffect(cooldown) { if (cooldown > 0) { delay(1_000); cooldown-- } }

    suspend fun finishWith(idToken: String) {
        val phone = PhoneNumber.e164(national ?: return)
        when (val r = graph.accounts.signIn(idToken, phone)) {
            is AccountRepository.SignIn.Failed -> { error = r.message; step = Step.PHONE }
            // A brand-new account (or one with no name yet) is asked for a name; signing in to an existing one is done.
            is AccountRepository.SignIn.Ok -> if (r.created || r.name == null) { step = Step.PROFILE; name = r.name.orEmpty() } else onDone()
        }
    }

    fun send() {
        val activity = ctx.findActivity() ?: run { error = "Could not start sign-in here."; return }
        val n = national ?: return
        busy = true; error = null
        scope.launch {
            try {
                when (val r = auth.sendCode(activity, PhoneNumber.e164(n))) {
                    SendResult.Sent -> { step = Step.CODE; code = ""; cooldown = RESEND_SECONDS }
                    is SendResult.AutoVerified -> finishWith(r.idToken)
                    is SendResult.Failed -> error = r.message
                }
            } finally { busy = false }
        }
    }

    Column(
        Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        when (step) {
            Step.PHONE -> {
                SatarkHeader("Sign in to Satark", "Your number lets your family find you as a trusted contact, and keeps your settings if you change phones.")
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("Your mobile number", style = MaterialTheme.typography.titleMedium)
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text(PhoneNumber.COUNTRY, style = MaterialTheme.typography.titleMedium)
                            OutlinedTextField(
                                digits, { v -> digits = v.filter { it.isDigit() || it == ' ' }.take(15); error = null },
                                label = { Text("10-digit number") }, singleLine = true, modifier = Modifier.weight(1f),
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                            )
                        }
                        Button(onClick = { send() }, enabled = national != null && !busy, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                            Text(if (busy) "Sending…" else "Send code", style = MaterialTheme.typography.titleSmall)
                        }
                        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                        if (auth.isTestMode) Text("Test build: the code is ${DevPhoneAuth.TEST_CODE}.", style = MaterialTheme.typography.labelLarge,
                            color = MaterialTheme.colorScheme.error)
                    }
                }
                Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("What Satark does with your number", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onPrimaryContainer)
                        Text("Satark sends one sign-in code to this number by SMS. That is the only code it ever sends. It never asks for your UPI PIN, " +
                            "a bank OTP or your card details. Our server keeps only a scrambled version of the number that it cannot turn back into the number.",
                            color = MaterialTheme.colorScheme.onPrimaryContainer)
                    }
                }
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("Prefer not to sign in?", style = MaterialTheme.typography.titleSmall)
                        Text("Satark still protects you. Without an account your trusted contact will not see your name, and your settings do not move to a new phone.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                        OutlinedButton(onClick = { graph.accounts.skip(); onDone() }) { Text("Continue without an account") }
                    }
                }
            }

            Step.CODE -> {
                SatarkHeader("Enter the code", "We sent a 6-digit code by SMS to ${PhoneNumber.masked(PhoneNumber.e164(national ?: "")) }.")
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedTextField(
                            code, { v -> code = v.filter(Char::isDigit).take(PhoneNumber.CODE_LENGTH); error = null },
                            label = { Text("6-digit code") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                        )
                        Button(
                            onClick = {
                                busy = true; error = null
                                scope.launch {
                                    try {
                                        when (val r = auth.verify(code)) {
                                            is VerifyResult.Ok -> finishWith(r.idToken)
                                            is VerifyResult.Failed -> error = r.message
                                        }
                                    } finally { busy = false }
                                }
                            },
                            enabled = PhoneNumber.isCode(code) && !busy, modifier = Modifier.fillMaxWidth().height(52.dp),
                        ) { Text(if (busy) "Checking…" else "Verify", style = MaterialTheme.typography.titleSmall) }
                        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                        if (auth.isTestMode) Text("Test build: the code is ${DevPhoneAuth.TEST_CODE}.", style = MaterialTheme.typography.labelLarge,
                            color = MaterialTheme.colorScheme.error)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            TextButton(onClick = { send() }, enabled = cooldown == 0 && !busy) {
                                Text(if (cooldown > 0) "Send again in ${cooldown}s" else "Send the code again")
                            }
                            TextButton(onClick = { step = Step.PHONE; error = null }) { Text("Change number") }
                        }
                    }
                }
            }

            Step.PROFILE -> {
                SatarkHeader("What should we call you?", "If Satark thinks you may be in danger, your trusted contact sees this name. They never see your number, amounts or payees.")
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedTextField(
                            name, { name = it.take(PhoneNumber.NAME_MAX) }, label = { Text("Your name (optional)") }, singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        Button(
                            onClick = {
                                busy = true; error = null
                                scope.launch {
                                    try {
                                        if (graph.accounts.setName(name)) onDone() else error = "Could not save the name. Check your connection, or continue without it."
                                    } finally { busy = false }
                                }
                            },
                            enabled = !busy, modifier = Modifier.fillMaxWidth().height(52.dp),
                        ) { Text(if (busy) "Saving…" else "Continue", style = MaterialTheme.typography.titleSmall) }
                        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                        TextButton(onClick = onDone) { Text("Skip, I'll add it later") }
                    }
                }
                Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("One thing to know about Satark", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onPrimaryContainer)
                        Text("Satark checks that it is really you before it lets you turn protection off, change your trusted contact or age, delete your data, " +
                            "or continue past a Stop warning. It uses your fingerprint (or your phone's PIN if there is no fingerprint). That way a scammer " +
                            "who is controlling your screen cannot switch Satark off. You set this up on the next screen.",
                            color = MaterialTheme.colorScheme.onPrimaryContainer)
                    }
                }
            }
        }
    }
}

private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}
