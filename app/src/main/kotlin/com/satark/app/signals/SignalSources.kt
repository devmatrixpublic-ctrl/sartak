package com.satark.app.signals

import android.Manifest
import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Process
import android.provider.ContactsContract
import android.net.Uri
import android.telephony.TelephonyCallback
import android.telephony.TelephonyManager
import android.util.Log
import androidx.core.content.ContextCompat
import com.satark.detector.InstallSource
import java.security.MessageDigest

/** Every source reports availability and never throws into the caller. */
interface SignalSource {
    val name: SourceName
    fun state(): SourceState
    fun start(emit: (RawSignal) -> Unit)
    fun stop()
}

private const val TAG = "Satark.signals"

private fun Context.granted(p: String) = ContextCompat.checkSelfPermission(this, p) == PackageManager.PERMISSION_GRANTED

/**
 * Call start/end via TelephonyCallback (API 31+) or the phone-state broadcast.
 * Whether the other party is in contacts needs the number: the phone-state broadcast carries it only with READ_CALL_LOG,
 * and only for incoming calls. The number is looked up in contacts and discarded at once, so nothing but a boolean
 * leaves this class. When the number or READ_CONTACTS is missing, callerKnown = null (detector: no unknown-contact evidence).
 */
class CallSignalSource(private val ctx: Context, private val now: () -> Long = System::currentTimeMillis) : SignalSource {
    override val name = SourceName.CALL
    private var receiver: BroadcastReceiver? = null
    private var callback: TelephonyCallback? = null
    private var lastState = TelephonyManager.CALL_STATE_IDLE
    @Volatile private var pendingKnown: Boolean? = null
    // CALL_START waits briefly for the number: the state callback usually fires before the broadcast that carries it.
    private val main = android.os.Handler(android.os.Looper.getMainLooper())
    private var pendingStart: Runnable? = null

    override fun state() = when {
        !ctx.packageManager.hasSystemFeature(PackageManager.FEATURE_TELEPHONY) -> SourceState.UNSUPPORTED
        !ctx.granted(Manifest.permission.READ_PHONE_STATE) -> SourceState.DENIED
        else -> SourceState.AVAILABLE
    }

    override fun start(emit: (RawSignal) -> Unit) {
        if (state() != SourceState.AVAILABLE) return
        runCatching {
            // The broadcast gives the number (when READ_CALL_LOG is granted); the callback gives reliable state changes.
            val r = object : BroadcastReceiver() {
                override fun onReceive(c: Context, i: Intent) {
                    @Suppress("DEPRECATION")
                    val number = i.getStringExtra(TelephonyManager.EXTRA_INCOMING_NUMBER)
                    if (number != null) {
                        pendingKnown = isInContacts(number)
                        pendingStart?.let { main.removeCallbacks(it); it.run() }
                    }
                    // Below Android 12 there is no TelephonyCallback: drive call state from this broadcast.
                    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
                        when (i.getStringExtra(TelephonyManager.EXTRA_STATE)) {
                            TelephonyManager.EXTRA_STATE_RINGING -> handle(TelephonyManager.CALL_STATE_RINGING, emit)
                            TelephonyManager.EXTRA_STATE_OFFHOOK -> handle(TelephonyManager.CALL_STATE_OFFHOOK, emit)
                            TelephonyManager.EXTRA_STATE_IDLE -> handle(TelephonyManager.CALL_STATE_IDLE, emit)
                        }
                    }
                }
            }
            ContextCompat.registerReceiver(ctx, r, IntentFilter(TelephonyManager.ACTION_PHONE_STATE_CHANGED), ContextCompat.RECEIVER_EXPORTED)
            receiver = r

            val tm = ctx.getSystemService(TelephonyManager::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val cb = object : TelephonyCallback(), TelephonyCallback.CallStateListener {
                    override fun onCallStateChanged(state: Int) = handle(state, emit)
                }
                tm.registerTelephonyCallback(ContextCompat.getMainExecutor(ctx), cb)
                callback = cb
            }
            // Report "no call now" at start: closes a call restored from before a restart whose end was missed.
            @Suppress("DEPRECATION")
            if (tm.callState == TelephonyManager.CALL_STATE_IDLE) emit(RawSignal.CallEnded(now()))
        }.onFailure { Log.w(TAG, "call source failed to start", it) }
    }

    private fun handle(state: Int, emit: (RawSignal) -> Unit) {
        if (state == lastState) return
        val t = now()
        if (lastState == TelephonyManager.CALL_STATE_IDLE && state != TelephonyManager.CALL_STATE_IDLE) {
            val start = object : Runnable {
                override fun run() { if (pendingStart === this) { pendingStart = null; emit(RawSignal.CallStarted(t, pendingKnown)) } }
            }
            if (pendingKnown != null) start.also { pendingStart = it }.run()
            else { pendingStart = start; main.postDelayed(start, NUMBER_WAIT_MS) }
        } else if (state == TelephonyManager.CALL_STATE_IDLE) {
            pendingStart?.let { main.removeCallbacks(it); it.run() } // keep START before END
            emit(RawSignal.CallEnded(t))
            pendingKnown = null
        }
        lastState = state
    }

    private fun isInContacts(number: String): Boolean? {
        if (!ctx.granted(Manifest.permission.READ_CONTACTS)) return null
        return runCatching {
            val uri = Uri.withAppendedPath(ContactsContract.PhoneLookup.CONTENT_FILTER_URI, Uri.encode(number))
            ctx.contentResolver.query(uri, arrayOf(ContactsContract.PhoneLookup._ID), null, null, null)?.use { it.count > 0 }
        }.getOrNull()
    }

    override fun stop() {
        pendingStart?.let(main::removeCallbacks); pendingStart = null
        runCatching { receiver?.let(ctx::unregisterReceiver) }
        receiver = null
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            runCatching { callback?.let { ctx.getSystemService(TelephonyManager::class.java).unregisterTelephonyCallback(it) } }
        }
        callback = null
    }

    companion object {
        private const val NUMBER_WAIT_MS = 2000L
        /** One-way digest, for any place that must refer to a number without storing it. Not used for detector input. */
        fun digest(number: String) = MessageDigest.getInstance("SHA-256").digest(number.toByteArray()).joinToString("") { "%02x".format(it) }
    }
}

/**
 * Foreground app and video-app sessions from UsageStatsManager (polled; there is no push API).
 * Video apps are calling apps only; whether the other party is unknown cannot be read, so callerKnown = null here.
 * The dispatcher marks a session unknown when it follows an unknown call (events/VideoOrigin.kt).
 */
class UsageSignalSource(
    private val ctx: Context,
    private val videoApps: Set<String> = DEFAULT_VIDEO_APPS,
    private val pollMs: Long = 3000,
    private val graceMs: Long = 30_000,
    private val now: () -> Long = System::currentTimeMillis,
) : SignalSource {
    override val name = SourceName.USAGE
    private var thread: Thread? = null
    @Volatile private var running = false

    override fun state(): SourceState {
        val ops = ctx.getSystemService(AppOpsManager::class.java)
        val mode = ops.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), ctx.packageName)
        return if (mode == AppOpsManager.MODE_ALLOWED) SourceState.AVAILABLE else SourceState.DENIED
    }

    override fun start(emit: (RawSignal) -> Unit) {
        if (state() != SourceState.AVAILABLE || running) return
        running = true
        thread = Thread({
            val usm = ctx.getSystemService(UsageStatsManager::class.java)
            var cursor = now()
            val video = VideoSessionTracker(videoApps, graceMs, emit)
            // Current state at start: if a video app is in front, track it; otherwise report "no video now"
            // (package null) so a session restored from before a restart is closed.
            runCatching {
                val start = now()
                val ev = usm.queryEvents(start - 10 * 60_000L, start)
                val e = UsageEvents.Event()
                var front: String? = null; var frontT = 0L
                while (ev.hasNextEvent()) {
                    ev.getNextEvent(e)
                    when (e.eventType) {
                        UsageEvents.Event.ACTIVITY_RESUMED -> { front = e.packageName; frontT = e.timeStamp }
                        UsageEvents.Event.ACTIVITY_PAUSED -> if (e.packageName == front) front = null
                    }
                }
                val f = front
                if (f != null && f in videoApps) video.resumed(f, frontT) else emit(RawSignal.VideoEnded(start, null))
            }
            while (running) {
                runCatching {
                    val end = now()
                    val ev = usm.queryEvents(cursor, end)
                    val e = UsageEvents.Event()
                    while (ev.hasNextEvent()) {
                        ev.getNextEvent(e)
                        when (e.eventType) {
                            UsageEvents.Event.ACTIVITY_RESUMED -> {
                                emit(RawSignal.AppForeground(e.timeStamp, e.packageName))
                                video.resumed(e.packageName, e.timeStamp)
                            }
                            UsageEvents.Event.ACTIVITY_PAUSED -> video.paused(e.packageName, e.timeStamp)
                        }
                    }
                    video.poll(end)
                    cursor = end
                }.onFailure { Log.w(TAG, "usage poll failed", it) }
                runCatching { Thread.sleep(pollMs) }
            }
        }, "satark-usage").apply { isDaemon = true; start() }
    }

    override fun stop() { running = false; thread = null }

    companion object {
        val DEFAULT_VIDEO_APPS = setOf(
            "com.whatsapp", "us.zoom.videomeetings", "com.google.android.apps.tachyon",
            "com.skype.raider", "org.telegram.messenger", "org.thoughtcrime.securesms",
        )
    }
}

/**
 * Video session = from the first time a video app comes to the front until it has been off-screen for [graceMs].
 * Staying in the call (no new events) keeps the session open; before, it was closed after ~2 min of silence, so the
 * 2 h long-session rule could never be reached.
 */
class VideoSessionTracker(
    private val videoApps: Set<String>,
    private val graceMs: Long,
    private val emit: (RawSignal) -> Unit,
) {
    private var sessionPkg: String? = null
    private var foreground: String? = null
    private var lastSeen = 0L

    fun resumed(pkg: String, t: Long) {
        if (pkg in videoApps) {
            if (sessionPkg == null) emit(RawSignal.VideoStarted(t, pkg, null))
            sessionPkg = sessionPkg ?: pkg
            foreground = pkg
            lastSeen = t
        } else {
            if (foreground != null) lastSeen = t
            foreground = null
            endIfIdle(t)
        }
    }

    fun paused(pkg: String, t: Long) {
        if (pkg == foreground) { foreground = null; lastSeen = t }
    }

    fun poll(now: Long) {
        if (foreground != null) lastSeen = now else endIfIdle(now)
    }

    private fun endIfIdle(now: Long) {
        val pkg = sessionPkg ?: return
        if (foreground == null && now - lastSeen > graceMs) { emit(RawSignal.VideoEnded(lastSeen, pkg)); sessionPkg = null }
    }
}

/** Package-added events with the install source: Play vs sideload. */
class InstallSignalSource(private val ctx: Context, private val now: () -> Long = System::currentTimeMillis) : SignalSource {
    override val name = SourceName.INSTALL
    private var receiver: BroadcastReceiver? = null

    // QUERY_ALL_PACKAGES is a manifest permission; if the OEM strips it the lookups fail and the source is reported as unsupported.
    override fun state() = if (ctx.granted("android.permission.QUERY_ALL_PACKAGES") || Build.VERSION.SDK_INT < 30) SourceState.AVAILABLE
    else SourceState.UNSUPPORTED

    override fun start(emit: (RawSignal) -> Unit) {
        if (receiver != null) return
        val r = object : BroadcastReceiver() {
            override fun onReceive(c: Context, i: Intent) {
                if (i.getBooleanExtra(Intent.EXTRA_REPLACING, false)) return
                val pkg = i.data?.schemeSpecificPart ?: return
                emit(RawSignal.AppInstalled(now(), pkg, installSource(pkg)))
            }
        }
        val f = IntentFilter(Intent.ACTION_PACKAGE_ADDED).apply { addDataScheme("package") }
        runCatching { ContextCompat.registerReceiver(ctx, r, f, ContextCompat.RECEIVER_EXPORTED); receiver = r }
            .onFailure { Log.w(TAG, "install source failed to start", it) }
    }

    /** play_store = installer is com.android.vending; any other installer or none = sideload; lookup failure = null. */
    internal fun installSource(pkg: String): InstallSource? = runCatching {
        val installer = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) ctx.packageManager.getInstallSourceInfo(pkg).installingPackageName
        else @Suppress("DEPRECATION") ctx.packageManager.getInstallerPackageName(pkg)
        if (installer == "com.android.vending") InstallSource.PLAY_STORE else InstallSource.SIDELOAD
    }.getOrNull()

    override fun stop() { runCatching { receiver?.let(ctx::unregisterReceiver) }; receiver = null }
}

/** Remote-access / screen-share packages from contracts/watchlist.json (bundled into assets). */
class WatchlistSource(private val ctx: Context) : SignalSource {
    override val name = SourceName.WATCHLIST
    val packages: Set<String> by lazy {
        runCatching {
            val text = ctx.assets.open("watchlist.json").bufferedReader().use { it.readText() }
            Regex("\"(com\\.[a-z0-9._]+)\"").findAll(text).map { it.groupValues[1] }.toSet()
        }.getOrElse { Log.w(TAG, "watchlist.json missing", it); emptySet() }
    }

    override fun state() = if (packages.isEmpty()) SourceState.UNSUPPORTED else SourceState.AVAILABLE

    /** Watch-listed packages installed right now (visible through the manifest <queries> entries). */
    fun installed(): Set<String> = packages.filterTo(HashSet()) {
        runCatching { ctx.packageManager.getPackageInfo(it, 0); true }.getOrDefault(false)
    }

    // The watch-list does not emit on its own: installs and foreground events carry the package, the detector matches it.
    override fun start(emit: (RawSignal) -> Unit) = Unit
    override fun stop() = Unit
}

/** Owns all sources and reports their combined status. */
class SignalHub(ctx: Context) {
    val watchlist = WatchlistSource(ctx)
    val sources: List<SignalSource> = listOf(CallSignalSource(ctx), UsageSignalSource(ctx), InstallSignalSource(ctx), watchlist)

    val screenRecording = ScreenRecordingSource()

    fun status() = SignalStatus(sources.associate { it.name to it.state() }, screenRecording.state())

    fun start(emit: (RawSignal) -> Unit) = sources.forEach { s ->
        runCatching { s.start(emit) }.onFailure { Log.w(TAG, "${s.name} failed", it) }
    }

    fun stop() = sources.forEach { runCatching { it.stop() } }
}
