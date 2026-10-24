package com.satark.app.signals

import com.satark.detector.InstallSource

/**
 * What Satark actually saw, in words, for the warning to show: who got in touch and which unsafe app arrived, with how long
 * ago. Kept in memory only, never stored or sent. App names come from the phone's own app list.
 */
class Evidence(
    private val now: () -> Long = System::currentTimeMillis,
    private val labelOf: (String) -> String? = { null },
) {
    private var contact: String? = null
    private var contactMs = 0L
    private val apps = LinkedHashMap<String, Long>()
    private val packages = HashMap<String, String>() // app name -> package, to offer "Remove"

    @Synchronized fun record(s: RawSignal) {
        when (s) {
            is RawSignal.UnknownMessage -> { contact = "texted you"; contactMs = s.tMs }
            is RawSignal.CallStarted -> if (s.callerKnown == false) { contact = "called you"; contactMs = s.tMs }
            is RawSignal.AppInstalled -> if (s.source == InstallSource.SIDELOAD) {
                val name = labelOf(s.appPackage)?.takeIf { it.isNotBlank() } ?: s.appPackage
                apps.remove(name); apps[name] = s.tMs; packages[name] = s.appPackage
            }
            else -> Unit
        }
    }

    /** The newest unsafe app still inside the window: (name shown to the person, package), for a "Remove" button. */
    @Synchronized fun lastRisky(): Pair<String, String>? {
        val t = now()
        val e = apps.entries.lastOrNull { t - it.value in 0..WINDOW_MS } ?: return null
        return packages[e.key]?.let { e.key to it }
    }

    /** Up to three short lines, newest evidence still inside the last two hours. */
    @Synchronized fun lines(): List<String> {
        val t = now()
        val out = mutableListOf<String>()
        contact?.let { if (t - contactMs in 0..WINDOW_MS) out += "Someone not in your contacts $it ${ago(t - contactMs)}" }
        apps.entries.filter { t - it.value in 0..WINDOW_MS }.takeLast(2)
            .forEach { out += "\"${it.key}\" was installed from outside Google Play ${ago(t - it.value)}" }
        return out
    }

    companion object {
        const val WINDOW_MS = 2 * 3600_000L
        fun ago(ms: Long): String = when {
            ms < 60_000 -> "just now"
            ms < 3600_000 -> "${ms / 60_000} min ago"
            else -> "${ms / 3600_000} h ago"
        }
    }
}
