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
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import com.satark.app.AppGraph
import com.satark.app.payments.PayOutcome
import com.satark.app.payments.UpiParseResult
import com.satark.app.payments.UpiRequest
import com.satark.app.payments.UpiUriParser
import com.satark.app.ui.alerts.ReasonText
import com.satark.app.ui.onboarding.ProtectionBanners
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.math.BigDecimal
import java.util.concurrent.Executors

/**
 * Home: Pay via Satark. Satark can hold only payments started here; payments started directly in GPay or PhonePe can
 * only be warned about, and a UPI hand-off result is reported by the UPI app, not verified.
 */
@Composable
fun PayHome(graph: AppGraph, status: String?, onOutcome: (PayOutcome, UpiRequest, BigDecimal) -> Unit) {
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
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current

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

    Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Pay via Satark", style = MaterialTheme.typography.headlineSmall)
        ProtectionBanners(graph.hub.status())
        OutlinedButton(onClick = { error = null; scanning = true }, Modifier.fillMaxWidth()) { Text("Scan UPI QR") }
        OutlinedTextField(vpa, { vpa = it; source = "manual"; merchantCode = null; scannedName = null; scannedNote = null }, label = { Text("Payee UPI ID") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(amount, { amount = it }, label = { Text("Amount (₹)") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        Column {
            Text("Pay with")
            androidx.compose.foundation.layout.Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(method == "upi_intent", { method = "upi_intent" }, label = { Text("My UPI app") })
                FilterChip(method == "checkout", { method = "checkout" }, label = { Text("Satark checkout (test)") })
            }
        }
        Button(enabled = !busy, modifier = Modifier.fillMaxWidth(), onClick = {
            error = null; held = null
            val uri = "upi://pay?pa=${java.net.URLEncoder.encode(vpa.trim(), "UTF-8")}&am=${amount.trim()}" +
                (merchantCode?.let { "&mc=" + java.net.URLEncoder.encode(it, "UTF-8") } ?: "")
            val typed = (UpiUriParser.parse(uri) as? UpiParseResult.Ok)?.request
            val amt = typed?.amountInr
            val req = typed?.copy(payeeName = scannedName, note = scannedNote)
            if (req == null || amt == null) { error = "Enter a valid UPI ID and an amount."; return@Button }
            busy = true
            scope.launch {
                val o = try {
                    withContext(Dispatchers.IO) { graph.payments.start(req, amt, source, method) }
                } catch (e: kotlinx.coroutines.CancellationException) {
                    throw e
                } catch (e: Exception) {
                    PayOutcome.Failed("Something went wrong. No payment was made.")
                } finally { busy = false }
                when (o) {
                    is PayOutcome.Held -> held = ArrayList(o.reasons) // saveable type
                    is PayOutcome.Failed -> error = o.message
                    else -> onOutcome(o, req, amt)
                }
            }
        }) { Text(if (busy) "Checking…" else "Check and pay") }

        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        held?.let { reasons ->
            Text("Payment on hold", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.error)
            Text("Satark did not send this payment. Nothing was paid.")
            reasons.take(3).forEach { Text("• " + ReasonText.of(ctx, it)) }
        }
        status?.let { Text(it) }
        Text(
            "Satark can hold payments started here. Payments started directly in other UPI apps can only be warned about.",
            style = MaterialTheme.typography.bodySmall,
        )
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
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Satark needs the camera only to read a payment QR code.")
                Button(onClick = { ask.launch(Manifest.permission.CAMERA) }) { Text("Allow camera") }
                OutlinedButton(onClick = onCancel) { Text("Back") }
            }
            return
        }
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
        OutlinedButton(onClick = onCancel, Modifier.padding(16.dp)) { Text("Cancel") }
    }
}
