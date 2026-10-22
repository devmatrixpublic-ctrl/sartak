package com.satark.app.ui.alerts

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.satark.app.R
import com.satark.app.ui.MainActivity
import com.satark.detector.Mechanism

/**
 * Alarms usually fire while the user is in another app (the scammer's video call, the UPI app). The in-app warning
 * alone is then never seen, so every alarm also posts a high-priority notification that opens Satark's warning.
 */
class AlarmNotifier(private val ctx: Context) {
    init {
        if (Build.VERSION.SDK_INT >= 26) runCatching {
            ctx.getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(CHANNEL, ctx.getString(R.string.notif_alarm_channel), NotificationManager.IMPORTANCE_HIGH),
            )
        }
    }

    fun show(mechanism: String?) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val open = PendingIntent.getActivity(
            ctx, 0,
            Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val text = if (mechanism == Mechanism.LONG_SESSION) ctx.getString(R.string.notif_alarm_long_session)
                   else ctx.getString(R.string.notif_alarm_text)
        val n = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .setContentTitle(ctx.getString(R.string.notif_alarm_title))
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(ID, n) }
    }

    companion object {
        private const val CHANNEL = "satark_alarm"
        private const val ID = 2
    }
}
