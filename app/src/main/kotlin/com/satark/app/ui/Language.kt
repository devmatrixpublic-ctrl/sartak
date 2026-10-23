package com.satark.app.ui

import android.content.Context
import android.content.res.Configuration
import java.util.Locale

/**
 * The language of the warning reasons: English or Hindi (or the phone's own setting). Stored in a plain preference, because
 * it is read before the encrypted store can be opened and is not sensitive. Only the reason sentences are translated.
 * The Hindi text is machine-drafted and needs native review (ops/strings/PROVENANCE.md).
 */
object Language {
    const val ENGLISH = "en"
    const val HINDI = "hi"
    private const val PREFS = "satark_language"

    /** The Locale for a stored code, or null to follow the phone. Anything unknown follows the phone. */
    fun localeFor(code: String?): Locale? = when (code) {
        ENGLISH -> Locale.ENGLISH
        HINDI -> Locale.forLanguageTag("hi")
        else -> null
    }

    fun get(ctx: Context): String? = runCatching { ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString("code", null) }.getOrNull()
    fun set(ctx: Context, code: String?) { runCatching { ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString("code", code).apply() } }

    /** A context whose resources use the chosen language; the same context when the phone's language is followed. */
    fun wrap(base: Context): Context {
        val locale = localeFor(get(base)) ?: return base
        val conf = Configuration(base.resources.configuration).apply { setLocale(locale) }
        return base.createConfigurationContext(conf)
    }
}
