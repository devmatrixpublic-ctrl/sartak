package com.satark.app.signals

import android.os.Build
import android.util.Log
import android.view.WindowManager
import java.util.concurrent.Executor
import java.util.function.Consumer

/**
 * Android 15+ (API 35) tells an app whether ITS OWN window is being recorded. That is all it does: it does NOT detect
 * another app's screen sharing, a remote-access app mirroring the screen, or adb/scrcpy. So this is informational only:
 * it appears in [SignalStatus.screenRecording] and the log, it is never an event, never a detector feature, and never
 * changes a decision. On older phones it reports [SourceState.UNSUPPORTED] (the plan's "unavailable") and does nothing.
 */
class ScreenRecordingSource(private val sdk: Int = Build.VERSION.SDK_INT) {
    @Volatile var lastVisible: Boolean? = null
        private set

    private var callback: Consumer<Int>? = null

    fun state(): SourceState = if (sdk >= MIN_SDK) SourceState.AVAILABLE else SourceState.UNSUPPORTED

    /** Start listening for this app's window. Safe to call anywhere: below API 35, or with no WindowManager, it does nothing. */
    fun register(wm: WindowManager?, executor: Executor) {
        if (sdk < MIN_SDK || wm == null || callback != null) return
        runCatching {
            val cb = Consumer<Int> { s -> record(s) }
            // The call returns the state right now, which a later callback would miss if recording began before the app opened.
            record(wm.addScreenRecordingCallback(executor, cb))
            callback = cb
        }.onFailure { Log.w(TAG, "screen-recording callback unavailable", it) }
    }

    fun unregister(wm: WindowManager?) {
        val cb = callback ?: return
        callback = null
        if (sdk >= MIN_SDK && wm != null) runCatching { wm.removeScreenRecordingCallback(cb) }
    }

    private fun record(stateValue: Int) {
        val visible = stateValue == WindowManager.SCREEN_RECORDING_STATE_VISIBLE
        lastVisible = visible
        Log.i(TAG, "this app's window is being recorded: $visible")
    }

    companion object {
        const val MIN_SDK = 35
        private const val TAG = "Satark.screenrec"
    }
}
