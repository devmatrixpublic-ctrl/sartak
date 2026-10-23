package com.satark.app.ui.alerts

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.ContactsContract

/**
 * "Call trusted contact": ACTION_DIAL to the contact the person chose. Only a pointer to the phone's own contact
 * (its content URI) is kept; the number is read from the contacts provider at the moment of dialling and is never
 * stored. ACTION_DIAL opens the dialler with the number filled in; the person still presses call, so no call
 * permission is needed. Without a chosen contact, or without READ_CONTACTS, it opens the dialler empty.
 */
object ContactDialer {
    /** `tel:` URI for [number], or null when there are no digits. Spaces, dashes and brackets are dropped. */
    fun telUri(number: String?): String? {
        val cleaned = number.orEmpty().filterIndexed { i, c -> c.isDigit() || (c == '+' && i == 0) }
        return if (cleaned.count(Char::isDigit) >= 3) "tel:$cleaned" else null
    }

    fun intent(ctx: Context, contactUri: String?): Intent {
        val tel = contactUri?.let { number(ctx, it) }?.let(::telUri)
        return if (tel != null) Intent(Intent.ACTION_DIAL, Uri.parse(tel)) else Intent(Intent.ACTION_DIAL)
    }

    private fun number(ctx: Context, contactUri: String): String? = runCatching {
        val id = Uri.parse(contactUri).lastPathSegment ?: return null
        ctx.contentResolver.query(
            ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
            arrayOf(ContactsContract.CommonDataKinds.Phone.NUMBER),
            ContactsContract.CommonDataKinds.Phone.CONTACT_ID + " = ?", arrayOf(id), null,
        )?.use { if (it.moveToFirst()) it.getString(0) else null }
    }.getOrNull()
}
