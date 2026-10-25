package com.satark.app.guard

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
import com.satark.app.ui.MainActivity

/** The scam warning for a file. Tapping it opens Satark's Protection screen, where the file can be reviewed. */
class DownloadGuardNotifier(private val ctx: Context) {
    init {
        if (Build.VERSION.SDK_INT >= 26) runCatching {
            ctx.getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(CHANNEL, "Scam files", NotificationManager.IMPORTANCE_HIGH)
                    .apply { description = "Warns when a downloaded file has a name that scam files often use." },
            )
        }
    }

    fun show(e: GuardEvent) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val open = PendingIntent.getActivity(
            ctx, 3,
            Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                .putExtra(MainActivity.EXTRA_OPEN, MainActivity.OPEN_PROTECTION),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val (title, text) = words(e)
        val n = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(e.record.id.hashCode(), n) }
    }

    companion object {
        const val CHANNEL = "satark_download_guard"

        /** The title and the one paragraph, written for the person who just downloaded the file. */
        fun words(e: GuardEvent): Pair<String, String> {
            val r = e.record
            return when (e) {
                is GuardEvent.Quarantined -> "Scam warning: file blocked" to
                    "“${r.name}” looks like a ${r.category} scam. Satark moved it out of your Downloads so it cannot be opened or installed. Do not install it. Nobody legitimate sends this as a file."
                is GuardEvent.Stopped -> "Scam warning: download stopped" to
                    "Satark stopped the download of “${r.name}”. It looks like a ${r.category} scam. Do not try to download it again."
                is GuardEvent.Warned -> "Scam warning: suspicious file" to
                    "“${r.name}” has a name often used in ${r.category} scams. Do not open it, or tap any link in it, unless you were expecting it from someone you trust."
            }
        }
    }
}
