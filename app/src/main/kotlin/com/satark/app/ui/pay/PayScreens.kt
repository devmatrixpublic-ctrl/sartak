package com.satark.app.ui.pay

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.OptIn
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import android.content.Intent
import android.net.Uri
import com.satark.app.security.DeviceReport
import com.satark.app.security.Severity
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import com.satark.app.ui.theme.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import com.satark.app.AppGraph
import com.satark.app.payments.HoldResolution
import com.satark.app.payments.PayOutcome
import com.satark.app.payments.UpiParseResult
import com.satark.app.payments.UpiRequest
import com.satark.app.payments.UpiUriParser
import com.satark.app.ui.alerts.Friction
import com.satark.app.ui.alerts.PaymentPause
import com.satark.app.ui.alerts.PlaybookCard
import com.satark.app.ui.alerts.ReportFraudButton
import com.satark.app.ui.alerts.Reasons
import com.satark.app.ui.onboarding.ProtectionSummary
import com.satark.app.ui.theme.SatarkHeader
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.math.BigDecimal
import java.util.concurrent.Executors

/** The device check found something and the person is deciding whether to go on to the payment. */
private class PendingDeviceWarning(val report: DeviceReport, val req: UpiRequest, val amt: BigDecimal)

/** A payment that is allowed but earns a nudge, waiting for the person to read it and choose. */
private class PendingNudge(val n: PayOutcome.Nudged, val req: UpiRequest, val amt: BigDecimal)

/**
 * Home: Pay via Satark. Satark can hold only payments started here; payments started directly in GPay or PhonePe can
 * only be warned about, and a UPI hand-off result is reported by the UPI app, not verified.
 */
@Composable
fun PayHome(
    graph: AppGraph,
    status: String?,
    onOutcome: (PayOutcome, UpiRequest, BigDecimal) -> Unit,
    onOpenProtection: () -> Unit = {},
    onNewPayment: () -> Unit = {},
    onOpenHistory: () -> Unit = {},
    onOpenDrill: () -> Unit = {},
) {
    // rememberSaveable: typed values survive the activity being recreated (rotation, call screen, process trim).
    var scanning by rememberSaveable { mutableStateOf(false) }
    var vpa by rememberSaveable { mutableStateOf("") }
    var amount by rememberSaveable { mutableStateOf("") }
    var merchantCode by rememberSaveable { mutableStateOf<String?>(null) }
    var scannedName by rememberSaveable { mutableStateOf<String?>(null) } // pn/tn from the QR, kept for the hand-off
    var scannedNote by rememberSaveable { mutableStateOf<String?>(null) }
    var source by rememberSaveable { mutableStateOf("manual") }
    var method by rememberSaveable { mutableStateOf("upi_intent") }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    var held by rememberSaveable { mutableStateOf<List<String>?>(null) }
    var heldAmountInr by remember { mutableStateOf<Double?>(null) } // only to pick the coarse amount band for the fraud summary
    var holdStatus by remember { mutableStateOf<String?>(null) } // what the trusted contact has done about a hold
    var holdJob by remember { mutableStateOf<kotlinx.coroutines.Job?>(null) } // waiting on the contact; closing the card ends it
    var busy by remember { mutableStateOf(false) }
    var nudge by remember { mutableStateOf<PendingNudge?>(null) }
    var deviceReport by remember { mutableStateOf<DeviceReport?>(null) } // what the last look at this phone's apps found
    var deviceWarning by remember { mutableStateOf<PendingDeviceWarning?>(null) }
    val scope = rememberCoroutineScope()
    val pause by graph.pause.state.collectAsState()
    var resumed by remember { mutableIntStateOf(0) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { graph.pause.refresh(); resumed++ }
    val signals = remember(resumed) { graph.hub.status() } // re-read after Settings or a permission dialog
    // Looked at again on every return to this screen, so removing an app (which leaves Satark) clears the card.
    androidx.compose.runtime.LaunchedEffect(resumed) { deviceReport = withContext(Dispatchers.IO) { graph.deviceCheck.scan() } }

    if (scanning) {
        QrScanScreen(onResult = { text ->
            scanning = false
            when (val r = UpiUriParser.parse(text)) {
                is UpiParseResult.Ok -> {
                    vpa = r.request.payeeVpa; amount = r.request.amountInr?.toPlainString() ?: ""
                    merchantCode = r.request.merchantCode; scannedName = r.request.payeeName; scannedNote = r.request.note; source = "qr"; error = null
                }
                is UpiParseResult.Rejected -> error = "That QR code is not a UPI payment code."
            }
        }, onCancel = { scanning = false })
        return
    }

    // What to do with a payment's outcome. A nudge waits here for the person; everything else goes on as before.
    val handle: suspend (PayOutcome, UpiRequest, BigDecimal) -> Unit = { o, req, amt ->
                        when (o) {
                            is PayOutcome.Held -> {
                                held = ArrayList(o.reasons) // saveable type
                                heldAmountInr = amt.toDouble()
                                holdStatus = null
                                o.paymentId?.let { id ->
                                    // The trusted contact can approve or block this payment; the person can also choose "Continue anyway".
                                    holdStatus = "Asking your trusted contact to approve or block this payment…"
                                    holdJob?.cancel()
                                    holdJob = scope.launch {
                                        withContext(Dispatchers.IO) { runCatching { graph.alerts.requestApproval(id, o.reasons) } }
                                        when (val r = withContext(Dispatchers.IO) {
                                            graph.payments.waitForDecision(id, onOverride = {
                                                graph.payments.overrideHold(id, method, amt.toDouble(), graph.payments.hashOf(req.payeeVpa), req.isP2P)
                                            })
                                        }) {
                                            HoldResolution.Blocked -> holdStatus = "Your trusted contact blocked this payment. Nothing was paid."
                                            HoldResolution.ApprovedUpi -> {
                                                holdStatus = "Payment released."
                                                onOutcome(PayOutcome.HandOff(id, UpiUriParser.build(req, amt)), req, amt)
                                            }
                                            is HoldResolution.ApprovedCheckout -> {
                                                holdStatus = "Your trusted contact approved this payment."
                                                r.orderId?.let { oid -> onOutcome(PayOutcome.Checkout(id, oid, amt), req, amt) }
                                                    ?: run { holdStatus = "Could not start the checkout. Nothing was paid." }
                                            }
                                            HoldResolution.Waiting -> holdStatus = "No answer yet. The payment stays on hold; nothing was paid."
                                            HoldResolution.Unknown -> holdStatus = null
                                        }
                                    }
                                }
                            }
                            is PayOutcome.Nudged -> nudge = PendingNudge(o, req, amt)
                            is PayOutcome.Failed -> error = o.message
                            else -> onOutcome(o, req, amt)
                        }
    }

    val startPayment: (UpiRequest, BigDecimal) -> Unit = { req, amt ->
        busy = true
        scope.launch {
            val o = try {
                withContext(Dispatchers.IO) { graph.payments.start(req, amt, source, method) }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                PayOutcome.Failed("Something went wrong. No payment was made.")
            } finally { busy = false }
            handle(o, req, amt)
        }
    }

    val paused = pause != PaymentPause.State.Clear
    Column(
        Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        SatarkHeader("Pay via Satark", "Satark checks for signs of a scam before your money moves.", onMarkTap = { com.satark.app.ui.DevMode.tap() })
        if (com.satark.app.BuildConfig.DEBUG && com.satark.app.BuildConfig.LONG_SESSION_TEST_MIN > 0) Text(
            "TEST BUILD: long-session alarm after ${com.satark.app.BuildConfig.LONG_SESSION_TEST_MIN} min (real rule: 2 h)",
            color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelLarge,
        )
        ProtectionSummary(signals)
        if (graph.deviceCheck.visible) deviceReport?.let { DeviceCheckCard(it) }
        ProtectionLink(onOpenProtection)
        ToolLink("Alert history", "What Satark saw, and what it keeps", Icons.Filled.Info, onOpenHistory)
        // Re-read on every return to this screen, so finishing a practice call updates the line.
        ToolLink("Practice a scam call", remember(resumed) { graph.drillHistory.summary() }, Icons.Filled.Call, onOpenDrill)
        PauseCard(pause, graph.pause)

        Card(
            Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest),
            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        ) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                FilledTonalButton(onClick = { error = null; scanning = true }, Modifier.fillMaxWidth().height(52.dp)) {
                    Text("Scan UPI QR", style = MaterialTheme.typography.titleSmall)
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HorizontalDivider(Modifier.weight(1f))
                    Text("or enter the details", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    HorizontalDivider(Modifier.weight(1f))
                }
                OutlinedTextField(
                    vpa, { vpa = it; source = "manual"; merchantCode = null; scannedName = null; scannedNote = null },
                    label = { Text("Payee UPI ID") }, placeholder = { Text("name@bank") }, modifier = Modifier.fillMaxWidth(), singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
                )
                OutlinedTextField(
                    amount, { amount = it }, label = { Text("Amount (₹)") }, modifier = Modifier.fillMaxWidth(), singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal, imeAction = ImeAction.Done),
                )
                Text("Pay with", style = MaterialTheme.typography.labelLarge)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(method == "upi_intent", { method = "upi_intent" }, label = { Text("My UPI app") })
                    FilterChip(method == "checkout", { method = "checkout" }, label = { Text("Satark checkout (test)") })
                }
                Button(enabled = !busy && !paused, modifier = Modifier.fillMaxWidth().height(52.dp), onClick = {
                    error = null; held = null
                    onNewPayment() // the last payment's result message must not sit under this one
                    val uri = "upi://pay?pa=${java.net.URLEncoder.encode(vpa.trim(), "UTF-8")}&am=${amount.trim()}" +
                        (merchantCode?.let { "&mc=" + java.net.URLEncoder.encode(it, "UTF-8") } ?: "")
                    val typed = (UpiUriParser.parse(uri) as? UpiParseResult.Ok)?.request
                    val amt = typed?.amountInr
                    val req = typed?.copy(payeeName = scannedName, note = scannedNote)
                    if (req == null || amt == null) { error = "Enter a valid UPI ID and an amount."; return@Button }
                    busy = true
                    scope.launch {
                        // Look at the apps on this phone first. Anything found is a warning; the payment itself is decided as before.
                        val report = withContext(Dispatchers.IO) { graph.deviceCheck.checkAndNotify() }
                        busy = false
                        if (graph.deviceCheck.shouldAsk(report)) deviceWarning = PendingDeviceWarning(report, req, amt)
                        else startPayment(req, amt)
                    }
                }) { Text(if (busy) "Checking…" else "Check and pay", style = MaterialTheme.typography.titleSmall) }
            }
        }

        androidx.compose.runtime.LaunchedEffect(Unit) {
            graph.payments.released.collect { r ->
                held = null; holdStatus = null; error = null
                onOutcome(r.outcome, r.req, r.amountInr)
            }
        }
        nudge?.let { p ->
            AlertDialog(
                onDismissRequest = { nudge = null },
                title = { Text("Take a moment") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("You are about to pay someone new while someone you don't know is in touch. Is anyone asking you to do this?")
                        Reasons(p.n.reasons)
                    }
                },
                confirmButton = {
                    TextButton(onClick = {
                        nudge = null; busy = true
                        scope.launch {
                            val next = try {
                                withContext(Dispatchers.IO) { p.n.proceed() }
                            } catch (e: kotlinx.coroutines.CancellationException) {
                                throw e
                            } catch (e: Exception) {
                                PayOutcome.Failed("Something went wrong. No payment was made.")
                            } finally { busy = false }
                            handle(next, p.req, p.amt)
                        }
                    }) { Text("I'm sure, continue") }
                },
                dismissButton = { TextButton(onClick = { nudge = null }) { Text("Go back") } },
            )
        }
        deviceWarning?.let { w ->
            AlertDialog(
                onDismissRequest = { deviceWarning = null },
                title = { Text("Your phone may be vulnerable") },
                text = { DeviceFindingsText(w.report) },
                confirmButton = {
                    TextButton(onClick = { deviceWarning = null; graph.deviceCheck.acknowledge(w.report); startPayment(w.req, w.amt) }) { Text("Continue to payment") }
                },
                dismissButton = { TextButton(onClick = { deviceWarning = null }) { Text("Go back") } },
            )
        }
        error?.let { Notice(it, MaterialTheme.colorScheme.errorContainer, MaterialTheme.colorScheme.onErrorContainer) }
        held?.let { reasons ->
            val on = MaterialTheme.colorScheme.onErrorContainer
            Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Payment on hold", style = MaterialTheme.typography.titleMedium, color = on)
                    Text("Satark did not send this payment. Nothing was paid.", color = on)
                    holdStatus?.let { Text(it, color = on, style = MaterialTheme.typography.labelLarge) }
                    Reasons(reasons, on)
                    ReportFraudButton(reasons, heldAmountInr, on)
                    PlaybookCard(reasons)
                    // Closing stops waiting for the contact here. The payment stays unsent, and "Continue anyway" on the Stop screen is gone with it.
                    OutlinedButton(
                        onClick = { holdJob?.cancel(); holdJob = null; held = null; holdStatus = null; graph.payments.pendingHold = null },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Close this and start over", color = on) }
                }
            }
        }
        status?.let { Notice(it, MaterialTheme.colorScheme.secondaryContainer, MaterialTheme.colorScheme.onSecondaryContainer) }
        Text(
            "Satark can hold payments started here. Payments started directly in other UPI apps can only be warned about.",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (com.satark.app.ui.DevMode.open) AttestationExportButton(graph)
    }
}

@Composable
private fun Notice(text: String, container: Color, content: Color) {
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = container)) {
        Text(text, Modifier.padding(16.dp), color = content)
    }
}

@Composable
private fun ProtectionLink(onOpen: () -> Unit) {
    Card(
        onClick = onOpen, modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest),
    ) {
        Row(
            Modifier.padding(horizontal = 16.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(Icons.Filled.Settings, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Column(Modifier.weight(1f)) {
                Text("Protection and trusted contact", style = MaterialTheme.typography.titleSmall)
                Text("Permissions, and who is told if you may be at risk", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun ToolLink(title: String, subtitle: String, icon: androidx.compose.ui.graphics.vector.ImageVector, onOpen: () -> Unit) {
    Card(
        onClick = onOpen, modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest),
    ) {
        Row(
            Modifier.padding(horizontal = 16.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleSmall)
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** Rung 3 of the friction ladder: the countdown, then the sentence typed once. */
@Composable
private fun PauseCard(state: PaymentPause.State, pause: PaymentPause) {
    if (state == PaymentPause.State.Clear) return
    val on = MaterialTheme.colorScheme.onTertiaryContainer
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            when (state) {
                is PaymentPause.State.Waiting -> {
                    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
                    LaunchedEffect(state.untilMs) {
                        while (true) {
                            now = System.currentTimeMillis()
                            if (now >= state.untilMs) { pause.refresh(); break }
                            delay(1_000)
                        }
                    }
                    Text("Payments are paused", style = MaterialTheme.typography.titleMedium, color = on)
                    Text(Friction.clock(Friction.remainingMs(state.untilMs, now)), style = MaterialTheme.typography.displaySmall, color = on)
                    Text(
                        "Satark saw signs of a scam. Hang up any call with someone you don't know, and talk to someone you trust before you pay.",
                        color = on,
                    )
                }
                PaymentPause.State.PhraseOwed -> {
                    var typed by rememberSaveable { mutableStateOf("") }
                    var wrong by remember { mutableStateOf(false) }
                    Text("Before your next payment", style = MaterialTheme.typography.titleMedium, color = on)
                    Text("Type this sentence. Only continue if it is true:", color = on)
                    Text("“${Friction.PHRASE}”", style = MaterialTheme.typography.titleSmall, color = on)
                    OutlinedTextField(
                        typed, { typed = it; wrong = false }, modifier = Modifier.fillMaxWidth(),
                        label = { Text("Type the sentence") }, isError = wrong, singleLine = true,
                    )
                    if (wrong) Text("The words do not match yet.", color = MaterialTheme.colorScheme.error)
                    Button(onClick = { wrong = !pause.confirm(typed) }) { Text("Confirm") }
                }
                PaymentPause.State.Clear -> Unit
            }
            if (com.satark.app.BuildConfig.DEBUG) TextButton(onClick = { pause.clearForTesting() }) { Text("End pause (debug build only)", color = on) }
        }
    }
}

@OptIn(ExperimentalGetImage::class)
@Composable
fun QrScanScreen(onResult: (String) -> Unit, onCancel: () -> Unit) {
    val ctx = LocalContext.current
    val owner = LocalLifecycleOwner.current
    var granted by remember { mutableStateOf(ContextCompat.checkSelfPermission(ctx, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted = it }

    Column(Modifier.fillMaxSize()) {
        if (!granted) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                SatarkHeader("Scan a UPI QR code")
                Text("Satark needs the camera only to read a payment QR code.")
                Button(onClick = { ask.launch(Manifest.permission.CAMERA) }) { Text("Allow camera") }
                OutlinedButton(onClick = onCancel) { Text("Back") }
            }
            return
        }
        Text("Point the camera at a UPI QR code", Modifier.padding(16.dp), style = MaterialTheme.typography.titleMedium)
        AndroidView(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            factory = { c ->
                val view = PreviewView(c)
                val executor = Executors.newSingleThreadExecutor()
                val scanner = BarcodeScanning.getClient(BarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build())
                var done = false
                val future = ProcessCameraProvider.getInstance(c)
                future.addListener({
                    val provider = runCatching { future.get() }.getOrNull() ?: return@addListener
                    val preview = Preview.Builder().build().also { it.setSurfaceProvider(view.surfaceProvider) }
                    val analysis = ImageAnalysis.Builder().setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).build()
                    analysis.setAnalyzer(executor) { proxy ->
                        val media = proxy.image
                        if (media == null || done) { proxy.close(); return@setAnalyzer }
                        scanner.process(InputImage.fromMediaImage(media, proxy.imageInfo.rotationDegrees))
                            .addOnSuccessListener { codes ->
                                codes.firstNotNullOfOrNull { it.rawValue?.takeIf { v -> v.startsWith("upi://", true) } }?.let {
                                    if (!done) { done = true; onResult(it) }
                                }
                            }
                            .addOnCompleteListener { proxy.close() }
                    }
                    runCatching {
                        provider.unbindAll()
                        provider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
                    }
                }, ContextCompat.getMainExecutor(c))
                view
            },
        )
        OutlinedButton(onClick = onCancel, Modifier.padding(16.dp).fillMaxWidth()) { Text("Cancel") }
    }
}

/** Debug builds only: capture this phone's attestation chain for M4 (see ui/debug/AttestationExport.kt). */
@Composable
private fun AttestationExportButton(graph: AppGraph) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var msg by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("Developer (debug build only)", style = MaterialTheme.typography.labelLarge)
        OutlinedButton(enabled = !busy, onClick = {
            busy = true; msg = null
            scope.launch {
                val r = runCatching { withContext(Dispatchers.IO) { com.satark.app.ui.debug.AttestationExport.capture(ctx, graph.api) } }
                busy = false
                r.onSuccess {
                    msg = "Key level: ${it.level}. Saved to ${it.file?.absolutePath ?: "(not saved)"}"
                    runCatching { ctx.startActivity(com.satark.app.ui.debug.AttestationExport.shareIntent(it)) }
                }.onFailure { msg = "Could not capture the attestation chain: ${it.message}" }
            }
        }) { Text(if (busy) "Capturing…" else "Export attestation chain for M4") }
        msg?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        // Starts a demo again from a clean state: the usual payment, known payees, the repeat-alert memory and the history.
        var confirmReset by remember { mutableStateOf(false) }
        OutlinedButton(onClick = {
            if (!confirmReset) confirmReset = true
            else scope.launch { graph.resetDemoState(); android.os.Process.killProcess(android.os.Process.myPid()) }
        }) { Text(if (confirmReset) "Tap again: clear demo data and close Satark" else "Reset demo state") }
    }
}

private const val SHOWN_FINDINGS = 6

/** What the device check found, in plain words, for the dialog before a payment. */
@Composable
private fun DeviceFindingsText(report: DeviceReport) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            if (report.severity == Severity.HIGH)
                "Apps like these can let a scammer watch your screen or make payments in your name. Remove any you do not recognise before you pay."
            else "These apps were not installed from an official store. If you installed them yourself and trust them, you can continue.",
        )
        report.findings.take(SHOWN_FINDINGS).forEach { Text("• ${it.label} ${it.sentence}.", style = MaterialTheme.typography.bodyMedium) }
        if (report.findings.size > SHOWN_FINDINGS) Text("…and ${report.findings.size - SHOWN_FINDINGS} more.", style = MaterialTheme.typography.bodyMedium)
    }
}

/** On the Pay screen: what is on this phone that makes a payment less safe, with a way to remove each app. */
@Composable
private fun DeviceCheckCard(report: DeviceReport) {
    if (report.severity == Severity.NONE) return
    val ctx = LocalContext.current
    val high = report.severity == Severity.HIGH
    val container = if (high) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.secondaryContainer
    val on = if (high) MaterialTheme.colorScheme.onErrorContainer else MaterialTheme.colorScheme.onSecondaryContainer
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = container)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Icon(Icons.Filled.Warning, contentDescription = null, tint = on)
                Text(if (high) "Your phone may be vulnerable" else "Apps from outside an official store", style = MaterialTheme.typography.titleSmall, color = on)
            }
            report.findings.take(SHOWN_FINDINGS).forEach { f ->
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("${f.label} ${f.sentence}.", Modifier.weight(1f), color = on, style = MaterialTheme.typography.bodyMedium)
                    if (f.removable) TextButton(onClick = {
                        runCatching { ctx.startActivity(Intent(Intent.ACTION_DELETE, Uri.parse("package:${f.pkg}"))) }
                    }) { Text("Remove", color = on) }
                }
            }
            if (report.findings.size > SHOWN_FINDINGS) Text("…and ${report.findings.size - SHOWN_FINDINGS} more.", color = on, style = MaterialTheme.typography.bodyMedium)
            Text(
                if (high) "Remove any you do not recognise before you pay." else "Fine if you installed them yourself and trust them.",
                color = on, style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}
