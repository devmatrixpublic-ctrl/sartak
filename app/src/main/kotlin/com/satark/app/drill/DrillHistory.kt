package com.satark.app.drill

/** Where finished rehearsals are kept (an encrypted preference in the app). */
interface DrillStore {
    var records: List<DrillRecord>
}

/**
 * Which rehearsals the person has done and how they went, on this phone only. It never changes a payment decision or what Satark warns about:
 * it only lets the home screen say “last practised 2 weeks ago” and suggest a scenario not tried yet.
 */
class DrillHistory(private val store: DrillStore, private val now: () -> Long = System::currentTimeMillis) {
    val records: List<DrillRecord> get() = store.records

    fun add(result: DrillResult) {
        val r = DrillRecord(result.script.id, now(), result.spotted, result.total)
        store.records = (listOf(r) + store.records).take(MAX_RECORDS)
    }

    fun last(): DrillRecord? = store.records.firstOrNull()
    fun lastFor(scriptId: String): DrillRecord? = store.records.firstOrNull { it.scriptId == scriptId }

    /** The first scenario the person has not done yet, or the one done longest ago when they have done them all. */
    fun suggested(scripts: List<DrillScript> = DrillScripts.all): DrillScript {
        scripts.firstOrNull { lastFor(it.id) == null }?.let { return it }
        return scripts.minBy { lastFor(it.id)?.atMs ?: 0L }
    }

    /** One line for the home screen. */
    fun summary(): String {
        val l = last() ?: return "Rehearse a scam call safely, before a real one happens"
        val days = ((now() - l.atMs) / DAY_MS).coerceAtLeast(0)
        val ago = when {
            days < 1 -> "today"
            days == 1L -> "yesterday"
            days < 60 -> "$days days ago"
            else -> "${days / 30} months ago"
        }
        return if (days >= REFRESH_DAYS) "Last practised $ago. Time for a refresher" else "Last practised $ago: ${l.spotted} of ${l.total} spotted"
    }

    companion object {
        const val MAX_RECORDS = 30
        const val REFRESH_DAYS = 30
        private const val DAY_MS = 86_400_000L
    }
}
