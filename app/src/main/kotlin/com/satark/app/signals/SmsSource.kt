package com.satark.app.signals

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.ContactsContract
import android.provider.Telephony
import android.util.Log
import androidx.core.content.ContextCompat
import com.satark.app.SatarkApp

/**
 * Notices that a text arrived from someone who is not in the contacts. Only the sending number is judged. The message text
 * is never read, the number is never stored, and nothing is sent anywhere. A stranger text never changes whether a payment is
 * nudged or held: it is kept as a line of evidence for a Stop screen and counted towards the burst warning (TextBurst).
 * Needs the SMS permission; without it this does nothing.
 */
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

    /** An unsaved sender shows up as a phone number. Names, business sender ids ("VM-HDFCBK") and short codes do not. */
    fun looksLikePhoneNumber(label: String?): Boolean {
        val s = label?.trim().orEmpty()
        if (s.isEmpty() || !s.all { it.isDigit() || it in "+-()  " }) return false
        return s.count { it.isDigit() } >= 7
    }

    fun isStrangerNumber(ctx: Context, number: String?): Boolean = looksLikePhoneNumber(number) && inContacts(ctx, number!!) == false

    /** Counts a stranger text and keeps it as evidence, only while protection is on. It does not go to the detector. */
    fun report(ctx: Context) {
        val graph = (ctx.applicationContext as SatarkApp).graph
        if (!graph.capturing) return
        val t = System.currentTimeMillis()
        if (graph.textBurst.record(t)) graph.alerts.strangerTextBurst()
        graph.evidence.record(RawSignal.UnknownMessage(t))
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
