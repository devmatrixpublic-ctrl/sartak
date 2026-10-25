package com.satark.app.guard

import android.os.FileObserver
import kotlinx.serialization.Serializable
import java.io.File
import java.util.UUID

/** One thing the guard did, kept so the person can review it and, for a held file, restore or delete it. Names are shown to the person only. */
@Serializable
data class GuardRecord(
    val id: String,
    val name: String,
    val category: String,
    val atMs: Long,
    /** The folder it came from. */
    val dir: String,
    /** True when the file was moved into quarantine; false when the person was only warned and the file was left alone. */
    val held: Boolean,
)

interface GuardStore {
    var records: List<GuardRecord>

    /** Files the person chose to restore: "<dir>/<name>". The guard never touches these again. */
    var allowed: Set<String>
}

sealed interface GuardEvent {
    val record: GuardRecord

    /** An installable file was moved out of reach. */
    data class Quarantined(override val record: GuardRecord) : GuardEvent

    /** A download still in progress was removed, so it cannot finish. */
    data class Stopped(override val record: GuardRecord) : GuardEvent

    /** A document with a scam-like name; it was left where it is. */
    data class Warned(override val record: GuardRecord) : GuardEvent
}

/**
 * Watches the folders where downloaded and received files land. When a file's name looks like a common scam file (see [ScamFileRules]), an
 * installable file is moved into a private quarantine before it can be opened or installed, and the person is warned. Only names are read:
 * the guard never opens a file or looks inside it.
 *
 * Android does not let an app cancel another app's download, so this is the nearest thing: a download still in progress under a scam-like name
 * is deleted (the browser then reports it as failed), and a finished one is quarantined within moments of appearing.
 */
class DownloadGuard(
    private val watchedDirs: () -> List<File>,
    private val quarantineDir: File,
    private val store: GuardStore,
    private val enabled: () -> Boolean,
    private val onEvent: (GuardEvent) -> Unit,
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val observers = mutableListOf<FileObserver>()
    private val recent = LinkedHashMap<String, Long>() // "<dir>/<name>" -> when it was handled

    val records: List<GuardRecord> get() = store.records

    // ---- watching

    /** (Re)starts the watchers. Safe to call often: it does nothing while the guard is off, and replaces the watchers otherwise. */
    @Synchronized
    fun refresh() {
        stopWatching()
        if (!enabled()) return
        for (dir in watchedDirs()) {
            if (!dir.isDirectory) continue
            @Suppress("DEPRECATION") // the File constructor needs API 29; this works on every supported version
            val o = object : FileObserver(dir.absolutePath, CREATE or MOVED_TO or CLOSE_WRITE) {
                override fun onEvent(event: Int, path: String?) { if (path != null) handle(dir, path) }
            }
            o.startWatching()
            observers += o
        }
    }

    @Synchronized
    fun stop() = stopWatching()

    private fun stopWatching() { observers.forEach { runCatching { it.stopWatching() } }; observers.clear() }

    /** Looks at what is already there: files that arrived while the guard was not watching. */
    fun sweep() {
        if (!enabled()) return
        for (dir in watchedDirs()) dir.listFiles()?.forEach { if (it.isFile) handle(dir, it.name) }
    }

    // ---- deciding

    /** One file name in one folder, from a watcher or a sweep. */
    @Synchronized
    fun handle(dir: File, name: String) {
        if (!enabled()) return
        val m = ScamFileRules.check(name) ?: return
        val key = "${dir.absolutePath}/${m.displayName}"
        if (key in store.allowed || "${dir.absolutePath}/$name" in store.allowed) return
        val t = now()
        recent.entries.removeAll { t - it.value > DEDUPE_MS }
        // One download makes several events (create, write, rename). Handle the name once.
        if (recent.put("${dir.absolutePath}/$name", t) != null) return
        val file = File(dir, name)
        if (!file.isFile) return

        val id = UUID.randomUUID().toString()
        val base = GuardRecord(id, m.displayName, m.category.label, t, dir.absolutePath, held = false)
        when {
            m.action == Action.QUARANTINE && m.inProgress -> {
                // The download is still being written: there is no finished file to keep, so remove it and the download fails.
                if (runCatching { file.delete() }.getOrDefault(false)) emit(GuardEvent.Stopped(base))
            }
            m.action == Action.QUARANTINE -> {
                if (moveToQuarantine(file, id, m.displayName)) emit(GuardEvent.Quarantined(base.copy(held = true)))
            }
            else -> emit(GuardEvent.Warned(base))
        }
    }

    private fun emit(e: GuardEvent) {
        store.records = (listOf(e.record) + store.records).take(MAX_RECORDS)
        runCatching { onEvent(e) }
    }

    private fun moveToQuarantine(file: File, id: String, displayName: String): Boolean = runCatching {
        val target = File(File(quarantineDir, id).apply { mkdirs() }, displayName)
        if (!file.renameTo(target)) { // different volumes: copy, then remove the original
            file.copyTo(target, overwrite = true)
            if (!file.delete()) { target.delete(); return false }
        }
        true
    }.getOrDefault(false)

    // ---- what the person can do with a held file

    /** Puts a held file back where it came from, and tells the guard never to touch it again. */
    @Synchronized
    fun restore(id: String): Boolean {
        val r = store.records.firstOrNull { it.id == id && it.held } ?: return false
        val held = File(File(quarantineDir, id), r.name)
        if (!held.isFile) { drop(id); return false }
        var target = File(r.dir, r.name)
        var n = 1
        while (target.exists()) { target = File(r.dir, "${r.name.substringBeforeLast('.')} ($n).${r.name.substringAfterLast('.', "")}"); n++ }
        val ok = runCatching {
            if (!held.renameTo(target)) { held.copyTo(target, overwrite = false); held.delete() }
            true
        }.getOrDefault(false)
        if (!ok) return false
        store.allowed = store.allowed + "${r.dir}/${r.name}" + "${r.dir}/${target.name}"
        drop(id)
        return true
    }

    /** Removes a held file for good. */
    @Synchronized
    fun delete(id: String): Boolean {
        if (store.records.none { it.id == id }) return false
        File(quarantineDir, id).deleteRecursively()
        drop(id)
        return true
    }

    /** Forgets a record without touching any file (a warning the person has read). */
    @Synchronized
    fun dismiss(id: String) = drop(id)

    private fun drop(id: String) { store.records = store.records.filterNot { it.id == id } }

    companion object {
        const val DEDUPE_MS = 30_000L
        const val MAX_RECORDS = 50
    }
}
