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
import com.satark.app.security.DeviceReport
import com.satark.app.security.Severity
import com.satark.app.ui.MainActivity

/** "Your phone may be vulnerable": posted when the device check finds something as the person goes to pay. Tapping it opens Satark. */
class DeviceCheckNotifier(private val ctx: Context) {
    init {
        if (Build.VERSION.SDK_INT >= 26) runCatching {
            ctx.getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(CHANNEL, "Phone safety check", NotificationManager.IMPORTANCE_HIGH)
                    .apply { description = "Warns when apps on this phone make a payment less safe." },
            )
        }
    }

    fun show(report: DeviceReport) {
        if (report.severity == Severity.NONE) return
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val open = PendingIntent.getActivity(
            ctx, 2,
            Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val text = text(report)
        val n = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .setContentTitle("Your phone may be vulnerable")
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(ID, n) }
    }

    companion object {
        const val CHANNEL = "satark_device_check"
        private const val ID = 8

        /** One short line. The worst finding by name, then how many more. */
        fun text(report: DeviceReport): String {
            val first = report.findings.firstOrNull() ?: return ""
            val more = report.findings.size - 1
            val tail = if (more > 0) " and $more more" else ""
            return if (report.severity == Severity.HIGH) "${first.label} ${first.sentence}$tail. Open Satark to review before you pay."
            else "${report.findings.size} app${if (report.findings.size == 1) " was" else "s were"} installed from outside an official store. Open Satark to review."
        }
    }
}
