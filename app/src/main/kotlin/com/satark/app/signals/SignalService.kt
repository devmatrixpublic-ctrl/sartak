package com.satark.app.signals

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import com.satark.app.R
import com.satark.app.SatarkApp

/** Keeps the receivers and the usage poller alive while protection is on. Started from onboarding / app launch. */
class SignalService : Service() {
    override fun onBind(i: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, getString(R.string.notif_channel_name), NotificationManager.IMPORTANCE_LOW))
        val n = Notification.Builder(this, CHANNEL)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(getString(R.string.notif_running))
            .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
            .setOngoing(true).build()
        if (Build.VERSION.SDK_INT >= 34) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE) else startForeground(1, n)
        (application as SatarkApp).graph.startCapture()
        return START_STICKY
    }

    override fun onDestroy() {
        (application as SatarkApp).graph.stopCapture()
        super.onDestroy()
    }

    companion object {
        private const val CHANNEL = "satark_protection"
        fun stop(ctx: Context) { runCatching { ctx.stopService(Intent(ctx, SignalService::class.java)) } }
        fun start(ctx: Context) {
            val i = Intent(ctx, SignalService::class.java)
            // Never crash if the OS refuses (e.g. background-start limits); protection resumes next app open.
            runCatching { if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i) else ctx.startService(i) }
        }
    }
}
