package com.satark.app.ui.alerts

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.padding
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * "Report fraud": a summary prepared ON THIS PHONE to help the person tell 1930 or the cybercrime portal what happened.
 * It is never submitted anywhere by Satark and never claims to be a complaint. It holds the time, the kinds of signal
 * that fired, the reason codes and a coarse amount band, and no phone number, UPI ID, name or exact amount.
 */
object FraudReport {
    const val LABEL = "Prepared summary; not submitted to NCRP"
    const val HELPLINE = "1930"

    /** Reason code -> the kind of signal behind it, in plain words (no numbers or names are ever involved). */
    private val FAMILY = mapOf(
        "F_UNK_CONTACT_RECENT" to "call from someone not in contacts", "F_UNK_CALL_ACTIVE" to "call from someone not in contacts",
        "F_MINS_SINCE_UNK_LOG" to "call from someone not in contacts", "RULE_LONG_SESSION" to "long video call with someone unknown",
        "F_UNK_VIDEO_ACTIVE" to "video call with someone unknown",
        "F_INSTALL_PLAY_DURING_UNK" to "app install", "F_INSTALL_SIDELOAD_DURING_UNK" to "app install from outside the Play Store",
        "RULE_SIDELOAD_DURING_CALL" to "app install from outside the Play Store", "F_WATCHLIST_APP" to "remote-access or screen-share app",
        "F_NEW_PAYEE" to "payment to a new payee", "F_PAYEE_ADDED_AFTER_UNK" to "payment to a new payee", "F_UNK_X_NEWPAYEE" to "payment to a new payee",
        "F_LOG_AMT_RATIO" to "unusually large amount", "F_ROBUST_Z_POS" to "unusually large amount", "F_NEWPAYEE_X_AMT" to "unusually large amount",
        "F_REPEAT_TO_PAYEE" to "repeated payments to one payee", "F_IS_P2P" to "person-to-person payment",
        "F_OCSS_ORDERED" to "events in the usual scam order",
    )

    fun signalTypes(reasons: List<String>): List<String> = reasons.mapNotNull { FAMILY[it] }.distinct()

    /** A coarse band, never the exact amount. Matches the server's bands (rupees). */
    fun amountBand(amountInr: Double?): String = when {
        amountInr == null || amountInr.isNaN() -> "not applicable"
        amountInr < 500 -> "under Rs 500"
        amountInr < 2_000 -> "Rs 500 to 2,000"
        amountInr < 10_000 -> "Rs 2,000 to 10,000"
        amountInr < 50_000 -> "Rs 10,000 to 50,000"
        amountInr < 200_000 -> "Rs 50,000 to 2,00,000"
        else -> "over Rs 2,00,000"
    }

    fun summary(nowMs: Long, reasonCodes: List<String>, reasonSentences: List<String>, amountInr: Double?): String {
        val time = SimpleDateFormat("d MMM yyyy, HH:mm", Locale.ENGLISH).format(Date(nowMs))
        val types = signalTypes(reasonCodes).ifEmpty { listOf("not recorded") }
        return buildString {
            appendLine("Satark summary ($LABEL)")
            appendLine("Time: $time")
            appendLine("What Satark noticed: " + types.joinToString("; "))
            if (reasonSentences.isNotEmpty()) appendLine("Warnings shown: " + reasonSentences.joinToString(" "))
            appendLine("Reason codes: " + reasonCodes.joinToString(", ").ifEmpty { "none" })
            appendLine("Payment amount band: ${amountBand(amountInr)}")
            append("This was prepared on my phone. Satark has not filed a complaint or sent this to anyone.")
        }
    }

    fun shareIntent(summary: String): Intent =
        Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, summary), "Share summary")

    fun dial1930(): Intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:$HELPLINE"))
}

/** "Report fraud" on the hold and alert screens: shows the prepared summary and offers Share and Call 1930. */
@Composable
fun ReportFraudButton(reasonCodes: List<String>, amountInr: Double? = null, color: Color = Color.Unspecified) {
    val ctx: Context = LocalContext.current
    var open by remember { mutableStateOf(false) }
    if (!open) {
        OutlinedButton(onClick = { open = true }, Modifier.fillMaxWidth()) { Text("Report fraud", color = color) }
        return
    }
    val text = remember(reasonCodes, amountInr) {
        FraudReport.summary(System.currentTimeMillis(), reasonCodes, reasonCodes.map { ReasonText.of(ctx, it) }, amountInr)
    }
    Column(Modifier.padding(vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(FraudReport.LABEL, style = MaterialTheme.typography.labelLarge, color = color)
        Text(text, style = MaterialTheme.typography.bodySmall, color = color)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { runCatching { ctx.startActivity(FraudReport.shareIntent(text)) } }) { Text("Share summary") }
            OutlinedButton(onClick = { runCatching { ctx.startActivity(FraudReport.dial1930()) } }) { Text("Call 1930", color = color) }
        }
    }
}
