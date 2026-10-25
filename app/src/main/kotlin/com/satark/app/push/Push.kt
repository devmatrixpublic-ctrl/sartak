package com.satark.app.push

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
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.satark.app.SatarkApp
import com.satark.app.ui.MainActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import java.security.MessageDigest
import kotlin.coroutines.resume

/**
 * Firebase Cloud Messaging for trusted-contact alerts. Firebase is only initialised when the build has
 * app/google-services.json; without it [isConfigured] is false and nothing here touches Firebase.
 *
 * Privacy: auto-init is off in the manifest, so this phone is registered with Firebase only after the user taps
 * "Get an invite code" (they chose to be someone's trusted contact) or signs in. From then on the token is kept fresh.
 */
object Push {
    fun isConfigured(ctx: Context): Boolean = runCatching { FirebaseApp.getApps(ctx).isNotEmpty() }.getOrDefault(false)

    /** This phone's push token, or null (no Firebase config, no Google Play services, offline, timeout). */
    suspend fun token(ctx: Context, timeoutMs: Long = 20_000): String? {
        if (!isConfigured(ctx)) return null
        return runCatching {
            val fm = FirebaseMessaging.getInstance()
            fm.isAutoInitEnabled = true
            withTimeoutOrNull(timeoutMs) {
                suspendCancellableCoroutine<String?> { c ->
                    fm.token.addOnCompleteListener { t -> if (c.isActive) c.resume(if (t.isSuccessful) t.result else null) }
                }
            }
        }.getOrNull()
    }

    /** One-way hash, to notice that the token changed after it was shared (the token itself is never stored). */
    fun hash(token: String): String =
        MessageDigest.getInstance("SHA-256").digest(token.toByteArray()).joinToString("") { "%02x".format(it) }
}

/** Notifications on the trusted contact's phone. */
object ContactAlertNotifier {
    const val CHANNEL = "satark_contact_alert"
    private const val ID_ALARM = 3
    private const val ID_LONG_SESSION = 4
    private const val ID_LINK_REQUEST = 6
    private const val ID_PROTECTION = 7

    fun ensureChannel(ctx: Context) {
        runCatching {
            ctx.getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(CHANNEL, "Alerts about people you protect", NotificationManager.IMPORTANCE_HIGH)
                    .apply { description = "Sent when Satark on the phone of someone you protect sees signs of a scam." },
            )
        }
    }

    fun show(ctx: Context, alert: ContactAlert) =
        post(ctx, if (alert.isLinkRequest) ID_LINK_REQUEST else if (alert.isProtectionChange) ID_PROTECTION else if (alert.isLongSession) ID_LONG_SESSION else ID_ALARM, alert.title(), alert.text(), openProtection = alert.isLinkRequest,
            decidePaymentId = alert.paymentId.takeIf { alert.canDecide })

    private fun post(ctx: Context, id: Int, title: String, text: String, openProtection: Boolean, decidePaymentId: String? = null) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        ensureChannel(ctx)
        val open = Intent(ctx, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .apply {
                if (openProtection) putExtra(MainActivity.EXTRA_OPEN, MainActivity.OPEN_PROTECTION)
                if (decidePaymentId != null) putExtra(MainActivity.EXTRA_DECIDE_PAYMENT, decidePaymentId)
            }
        // A different request code per payment, so two held payments do not share one PendingIntent extra.
        val pi = PendingIntent.getActivity(ctx, if (decidePaymentId != null) decidePaymentId.hashCode() else id, open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setContentIntent(pi)
            .setAutoCancel(true)
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(id, n) }
    }
}

/**
 * Receives pushes while Satark is in the foreground (and data-only pushes always). A push with a `notification`
 * payload that arrives while Satark is in the background is shown by Android itself, using the server's title/body
 * and this app's default channel (manifest).
 */
class SatarkMessagingService : FirebaseMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        ContactAlertNotifier.show(this, ContactAlert.from(message.data))
    }

    /** Google changed this phone's push address: tell the server, so alerts keep reaching it. Nothing for the person to do. */
    override fun onNewToken(token: String) {
        val graph = runCatching { (application as SatarkApp).graph }.getOrNull() ?: return
        CoroutineScope(Dispatchers.IO).launch { graph.accounts.refreshPush(token) }
    }
}
