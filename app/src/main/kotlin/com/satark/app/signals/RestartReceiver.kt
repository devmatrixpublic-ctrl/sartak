package com.satark.app.signals

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.satark.app.SatarkApp

/**
 * Protection must come back by itself after the phone restarts or Satark is updated. Without this it stayed off until the
 * person happened to open the app, and a scam in that gap was missed with no warning that protection was off.
 */
class RestartReceiver : BroadcastReceiver() {
    override fun onReceive(c: Context, i: Intent) {
        if (!RestartPolicy.shouldRestart(i.action)) return
        runCatching {
            val graph = (c.applicationContext as SatarkApp).graph
            if (RestartPolicy.mayRun(graph.store.onboarded, graph.store.consent)) SignalService.start(c)
        }.onFailure { Log.w("Satark.restart", "could not restart protection", it) }
    }
}

object RestartPolicy {
    private val ACTIONS = setOf(Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED)

    fun shouldRestart(action: String?) = action in ACTIONS

    /** Only after the person finished setup and agreed on the consent screen. Never before, and never after "Not now". */
    fun mayRun(onboarded: Boolean, consent: Boolean) = onboarded && consent
}
