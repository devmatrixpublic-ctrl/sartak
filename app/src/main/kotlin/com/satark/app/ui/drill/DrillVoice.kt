package com.satark.app.ui.drill

import android.content.Context
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.delay
import java.util.Locale

/**
 * Reads the practice call aloud with the phone's own speech engine. Nothing is recorded and nothing leaves the phone. The caller gets a
 * lower, slightly slower voice and Satark's explanations a plain one, so the person can hear who is speaking. Optional, and off by default.
 */
class DrillVoice(ctx: Context) {
    private var engine: TextToSpeech? = null
    private var ready = false
    private var failed = false
    /** A line asked for before the speech engine had started: spoken as soon as it is ready. */
    private var pending: Pair<String, Boolean>? = null
    private var counter = 0
    @Volatile private var lastId = ""

    /** True from the moment a line is handed over until it has been spoken (or stopped). Read by the screen. */
    var speaking by mutableStateOf(false)
        private set

    val available: Boolean get() = ready

    init {
        engine = TextToSpeech(ctx.applicationContext) { status ->
            val e = engine
            ready = status == TextToSpeech.SUCCESS && e != null
            failed = !ready
            if (!ready) { pending = null; speaking = false }
            if (ready && e != null) {
                val wanted = Locale.Builder().setLanguage("en").setRegion("IN").build()
                val r = e.setLanguage(wanted)
                if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) e.setLanguage(Locale.ENGLISH)
                e.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) {}
                    override fun onDone(utteranceId: String?) { if (utteranceId == lastId) speaking = false }
                    @Deprecated("Deprecated in Java") override fun onError(utteranceId: String?) { if (utteranceId == lastId) speaking = false }
                    override fun onStop(utteranceId: String?, interrupted: Boolean) { if (utteranceId == lastId) speaking = false }
                })
                pending?.let { (text, asCaller) -> pending = null; say(text, asCaller) }
            }
        }
    }

    /** Speaks [text], replacing anything still being spoken. [asCaller] picks the caller's voice. Does nothing if the engine is not ready. */
    fun say(text: String, asCaller: Boolean) {
        val e = engine
        if (e != null && !ready && !failed && text.isNotBlank()) { pending = text to asCaller; speaking = true; return }
        if (!ready || e == null || text.isBlank()) { speaking = false; return }
        e.setPitch(if (asCaller) CALLER_PITCH else 1.0f)
        e.setSpeechRate(if (asCaller) CALLER_RATE else 1.0f)
        val id = "drill-${counter++}"
        lastId = id
        speaking = true
        if (e.speak(text, TextToSpeech.QUEUE_FLUSH, null, id) != TextToSpeech.SUCCESS) speaking = false
    }

    /** Waits until the current line has been spoken, but never longer than [maxMs]: a stuck engine must not stall the rehearsal. */
    suspend fun finish(maxMs: Long = 15_000) {
        var waited = 0L
        while (speaking && waited < maxMs) { delay(100); waited += 100 }
        if (speaking) stop()
    }

    fun stop() {
        runCatching { engine?.stop() }
        speaking = false
    }

    fun shutdown() {
        runCatching { engine?.stop(); engine?.shutdown() }
        engine = null
        speaking = false
    }

    private companion object {
        const val CALLER_PITCH = 0.8f
        const val CALLER_RATE = 0.95f
    }
}
