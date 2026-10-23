package com.satark.app.ui.alerts

import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.foundation.layout.fillMaxWidth

object ReadAloud {
    /** What is spoken: the headline, the instruction, then each reason, with a pause (full stop) between them. */
    fun spokenText(title: String, body: String, reasons: List<String>): String =
        (listOf(title, body) + reasons).map { it.trim().trimEnd('.') }.filter { it.isNotEmpty() }.joinToString(". ", postfix = ".")
}

/** "Read aloud" for an alert screen, for people who find it hard to read under stress. Uses the phone's own speech engine. */
@Composable
fun ReadAloudButton(title: String, body: String, reasonCodes: List<String>, color: Color = Color.Unspecified) {
    val ctx = LocalContext.current
    var ready by remember { mutableStateOf(false) }
    var speaking by remember { mutableStateOf(false) }
    val tts = remember {
        var engine: TextToSpeech? = null
        engine = TextToSpeech(ctx) { status ->
            ready = status == TextToSpeech.SUCCESS
            engine?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {}
                override fun onDone(utteranceId: String?) { speaking = false }
                @Deprecated("Deprecated in Java") override fun onError(utteranceId: String?) { speaking = false }
            })
        }
        engine
    }
    DisposableEffect(Unit) { onDispose { runCatching { tts.stop(); tts.shutdown() } } }
    OutlinedButton(enabled = ready, modifier = Modifier.fillMaxWidth(), onClick = {
        if (speaking) { tts.stop(); speaking = false }
        else {
            val text = ReadAloud.spokenText(title, body, reasonCodes.map { ReasonText.of(ctx, it) })
            speaking = tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "satark_alert") == TextToSpeech.SUCCESS
        }
    }) { Text(if (speaking) "Stop reading" else "Read aloud", color = color) }
}
