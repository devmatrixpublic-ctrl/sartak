package com.satark.app.push

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Debug builds only: show the trusted-contact alert exactly as an incoming push would, without Firebase.
 *   adb shell am broadcast -n com.satark.app/.push.DebugFakePushReceiver --es type alarm
 *   adb shell am broadcast -n com.satark.app/.push.DebugFakePushReceiver --es type long_session
 * Guarded by the DUMP permission, which only the shell and the system hold.
 */
class DebugFakePushReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        val data = intent.getStringExtra("type")?.let { mapOf("type" to it) } ?: emptyMap()
        ContactAlertNotifier.show(ctx, ContactAlert.from(data))
    }
}
