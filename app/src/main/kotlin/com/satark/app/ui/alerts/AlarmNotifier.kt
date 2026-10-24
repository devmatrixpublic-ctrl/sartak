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

    /** Several texts from strangers in a short time, while the person is in another app (usually their messages). */
    fun showTextBurst() {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val open = PendingIntent.getActivity(
            ctx, 1,
            Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val text = ctx.getString(R.string.notif_text_burst_text)
        val n = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .setContentTitle(ctx.getString(R.string.notif_text_burst_title))
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(ID_TEXTS, n) }
    }

    /** Protection went off after the waiting time, possibly while Satark was closed: the person should not find out by accident. */
    fun showProtectionOff() = simple(ID_PROTECTION_OFF, R.string.notif_protection_off_title, R.string.notif_protection_off_text)

    /** The guard against removal was switched off in Settings. */
    fun showRemovalGuardOff() = simple(ID_REMOVAL_GUARD_OFF, R.string.notif_removal_guard_off_title, R.string.notif_removal_guard_off_text)

    private fun simple(id: Int, title: Int, text: Int) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val open = PendingIntent.getActivity(
            ctx, id,
            Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val body = ctx.getString(text)
        val n = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .setContentTitle(ctx.getString(title))
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(id, n) }
    }

    companion object {
        private const val ID_PROTECTION_OFF = 4
        private const val ID_REMOVAL_GUARD_OFF = 5
        private const val ID_TEXTS = 3
        private const val CHANNEL = "satark_alarm"
        private const val ID = 2
    }
}
