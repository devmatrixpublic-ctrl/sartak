package com.satark.app.signals

import android.Manifest
import android.app.Notification
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.ContactsContract
import android.provider.Telephony
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.satark.app.SatarkApp

/**
 * Notices that a message arrived from someone who is not in the contacts. Only the sender is judged. The message text is
 * never read, the number is never stored, and nothing is sent anywhere: the only thing passed on is "an unknown person
 * got in touch, at this time".
 *
 * Two doors, because Android hides notification content from apps for messages it marks sensitive:
 *  - [SmsReceiver] gets the sending number of every text (needs the SMS permission).
 *  - [MessageWatcher] reads the sender label of WhatsApp-style notifications (needs Notification access).
 */
class MessageWatcher : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        runCatching { if (MessageSender.isMessageFromStranger(this, sbn)) MessageSender.report(this) }
            .onFailure { Log.w(MessageSender.TAG, "notification check failed", it) }
    }

    companion object {
        /** True when the person has switched Satark on under Settings > Notification access. */
        fun enabled(ctx: Context) = NotificationManagerCompat.getEnabledListenerPackages(ctx).contains(ctx.packageName)
    }
}

class SmsReceiver : BroadcastReceiver() {
    override fun onReceive(c: Context, i: Intent) {
        if (i.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return
        runCatching {
            // The sending number only. messageBody is never touched.
            val from = Telephony.Sms.Intents.getMessagesFromIntent(i).firstOrNull()?.originatingAddress
            if (MessageSender.isStrangerNumber(c, from)) MessageSender.report(c)
        }.onFailure { Log.w(MessageSender.TAG, "sms check failed", it) }
    }

    companion object {
        fun granted(ctx: Context) =
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECEIVE_SMS) == PackageManager.PERMISSION_GRANTED
    }
}

object MessageSender {
    const val TAG = "Satark.messages"
    private const val MIN_GAP_MS = 60_000L
    @Volatile private var lastReportMs = 0L

    private val MESSAGING_APPS = setOf(
        "com.google.android.apps.messaging", "com.samsung.android.messaging", "com.android.mms", "com.android.messaging",
        "com.whatsapp", "com.whatsapp.w4b", "org.telegram.messenger",
    )

    /** An unsaved sender shows up as a phone number. Names, business sender ids ("VM-HDFCBK") and group titles do not. */
    fun looksLikePhoneNumber(label: String?): Boolean {
        val s = label?.trim().orEmpty()
        if (s.isEmpty() || !s.all { it.isDigit() || it in "+-()  " }) return false
        return s.count { it.isDigit() } >= 7
    }

    fun isStrangerNumber(ctx: Context, number: String?): Boolean = looksLikePhoneNumber(number) && inContacts(ctx, number!!) == false

    fun isMessageFromStranger(ctx: Context, sbn: StatusBarNotification): Boolean {
        if (sbn.packageName == ctx.packageName) return false
        val apps = MESSAGING_APPS + setOfNotNull(runCatching { Telephony.Sms.getDefaultSmsPackage(ctx) }.getOrNull())
        if (sbn.packageName !in apps) return false
        val n = sbn.notification ?: return false
        if (n.flags and (Notification.FLAG_GROUP_SUMMARY or Notification.FLAG_ONGOING_EVENT) != 0) return false
        // Only the sender label. The message text is never read.
        return isStrangerNumber(ctx, n.extras?.getCharSequence(Notification.EXTRA_TITLE)?.toString())
    }

    /** Passes "an unknown person got in touch" to the detector, at most once a minute and only while protection is on. */
    fun report(ctx: Context) {
        val graph = (ctx.applicationContext as SatarkApp).graph
        if (!graph.capturing) return
        val t = System.currentTimeMillis()
        if (t - lastReportMs < MIN_GAP_MS) return
        lastReportMs = t
        val signal = RawSignal.UnknownMessage(t)
        graph.evidence.record(signal)
        graph.dispatcher.submit(signal, "message")
    }

    /** null when contacts cannot be checked: no evidence either way, so no signal. */
    private fun inContacts(ctx: Context, number: String): Boolean? {
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) return null
        return runCatching {
            val uri = Uri.withAppendedPath(ContactsContract.PhoneLookup.CONTENT_FILTER_URI, Uri.encode(number))
            ctx.contentResolver.query(uri, arrayOf(ContactsContract.PhoneLookup._ID), null, null, null)?.use { it.count > 0 }
        }.getOrNull()
    }
}
