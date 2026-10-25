package com.satark.app

import android.app.Application
import com.satark.app.events.EventDispatcher
import com.satark.app.events.TextBurst
import com.satark.app.events.SatarkDb
import com.satark.app.net.DeviceSession
import com.satark.app.net.NetworkModule
import com.satark.app.net.OfflineQueue
import com.satark.app.net.SatarkApi
import com.satark.app.payments.PayeeHasher
import com.satark.app.payments.PaymentRepository
import com.satark.app.security.TokenStore
import com.satark.app.signals.SignalHub
import com.satark.app.ui.alerts.AlertController
import com.satark.detector.ModelConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import java.net.URI

class SatarkApp : Application() {
    lateinit var graph: AppGraph
        private set

    override fun onCreate() {
        super.onCreate()
        graph = AppGraph(this)
        graph.start()
    }
}

/** Hand-wired dependency graph (small app; no DI framework). */
class AppGraph(private val app: Application) {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    /** True while one of Satark's own screens is in front: its Stop screen is then the alert, so no banner or notification is added. */
    @Volatile var appVisible = false
    val store = TokenStore(app)
    val model: ModelConfig = ModelConfig.loadBundled().let { m ->
        if (BuildConfig.DEBUG && BuildConfig.LONG_SESSION_TEST_MIN > 0)
            m.copy(constants = m.constants.copy(longSessionH = BuildConfig.LONG_SESSION_TEST_MIN / 60.0))
        else m
    }
    private val db = SatarkDb.create(app)
    private val dao = db.dao()

    private val host = URI(BuildConfig.BASE_URL).host ?: "localhost"
    val session: DeviceSession by lazy { DeviceSession(app, store) { bareApi } }
    private val client: OkHttpClient by lazy { NetworkModule.client(store, { session }, host, BuildConfig.CERT_PINS) }
    val api: SatarkApi by lazy { NetworkModule.api(client, BuildConfig.BASE_URL) }
    // No auth interceptor: used for /auth/{challenge,device,refresh} so a 401 loop is impossible.
    private val bareApi: SatarkApi by lazy { NetworkModule.api(OkHttpClient.Builder().build(), BuildConfig.BASE_URL) }

    val dispatcher = EventDispatcher(dao, model, store.ageYears, scope)

    /** The person typed or cleared their age (optional, kept on this phone): save it and tell the checks at once. */
    fun setAge(ageYears: Int?) {
        store.ageYears = ageYears
        scope.launch { dispatcher.setAge(ageYears) }
    }
    val hub = SignalHub(app)
    val textBurst = TextBurst(textStore(app))
    /** One instance for the whole sign-in, so a screen rotation does not lose the code Firebase is waiting for. */
    val phoneAuth: com.satark.app.account.PhoneAuth by lazy {
        when {
            BuildConfig.DEBUG && BuildConfig.DEV_OTP -> com.satark.app.account.DevPhoneAuth()
            com.satark.app.push.Push.isConfigured(app) -> com.satark.app.account.FirebasePhoneAuth()
            else -> com.satark.app.account.UnavailablePhoneAuth()
        }
    }
    val accounts = com.satark.app.account.AccountRepository({ api }, store, ready = { runCatching { session.ensureRegistered() } })
    val queue = OfflineQueue(dao) { api }
    val payments = PaymentRepository({ api }, dao, dispatcher, PayeeHasher(store.payeeSalt), shadow = { store.shadowMode },
        ready = { runCatching { session.ensureRegistered() } })
    val pause = com.satark.app.ui.alerts.PaymentPause(object : com.satark.app.ui.alerts.PaymentPause.Store {
        override var untilMs: Long by store::pauseUntilMs
        override var phraseOwed: Boolean by store::pausePhraseOwed
    })
    private val alarmNotifier by lazy { com.satark.app.ui.alerts.AlarmNotifier(app) }

    /** Tell the trusted contact (queued if offline). Nothing to do when this phone has no linked contact. */
    private suspend fun tellContact(type: String) {
        if (store.linkedContactId == null) return
        val id = store.deviceId ?: return
        queue.alert(com.satark.app.net.AlertRequest(id, type))
    }

    /** Turning protection off waits 30 minutes and tells the contact at once (protection/ProtectionOff). */
    val protectionOff = com.satark.app.protection.ProtectionOff(
        store = object : com.satark.app.protection.ProtectionOff.Store {
            override var dueAtMs: Long by store::protectionOffDueMs
            override var startedUptimeMs: Long by store::protectionOffStartedUptimeMs
        },
        wallNow = System::currentTimeMillis,
        uptimeNow = android.os.SystemClock::elapsedRealtime,
        tell = ::tellContact,
        turnOff = {
            store.consent = false
            com.satark.app.signals.SignalService.stop(app)
            alarmNotifier.showProtectionOff()
        },
        schedule = { delayMs -> com.satark.app.protection.ProtectionOffWorker.schedule(app, delayMs) },
        waitMs = if (BuildConfig.DEBUG && BuildConfig.PROTECTION_OFF_WAIT_MIN > 0) BuildConfig.PROTECTION_OFF_WAIT_MIN * 60_000L
                 else com.satark.app.protection.ProtectionOff.WAIT_MS,
    )

    /** Android's guard against uninstalling Satark was switched off (protection/SatarkAdminReceiver). */
    suspend fun removalGuardSwitchedOff() {
        alarmNotifier.showRemovalGuardOff()
        tellContact(com.satark.app.protection.ProtectionOff.TYPE_REMOVAL_GUARD_OFF)
    }
    val evidence = com.satark.app.signals.Evidence(labelOf = { pkg ->
        runCatching { app.packageManager.getApplicationLabel(app.packageManager.getApplicationInfo(pkg, 0)).toString() }.getOrNull()
    })
    val alarmOverlay by lazy { com.satark.app.ui.alerts.AlarmOverlay(app, { evidence.lines() }, { evidence.lastRisky() }) }
    val alerts = AlertController(dispatcher, queue, store, model, scope, pause, onContinueAnyway = { scope.launch { payments.continueAnyway() } }, shadow = { store.shadowMode },
        merger = com.satark.app.ui.alerts.AlertMerger(object : com.satark.app.ui.alerts.AlertMerger.Store {
            override suspend fun get(key: String) = dao.alertStat(key)
            override suspend fun put(stat: com.satark.app.events.AlertStat) = dao.putAlertStat(stat)
        }),
        onShown = {
            // One alert per incident. If Satark is already on screen, its own Stop screen is the alert. Otherwise the
            // banner over the open app, or the notification (permission off, or the phone is locked).
            val locked = app.getSystemService(android.app.KeyguardManager::class.java)?.isKeyguardLocked == true
            when {
                appVisible -> Unit
                alarmOverlay.canShow() && !locked -> alarmOverlay.show(it.reasons)
                else -> alarmNotifier.show(it.mechanism)
            }
        },
        onPaymentAppOpened = { alarmOverlay.show(it) },
        onTextBurst = { if (!appVisible) alarmNotifier.showTextBurst() })


    /**
     * "Delete my data": stops protection, asks the server to erase this phone's rows (if it can be reached), empties every
     * local table and forgets tokens, ids and the payee salt.
     */
    suspend fun deleteAllData() {
        // Deleting everything also ends protection, so the contact hears it first. Sent directly, not queued: the queue is emptied below.
        val contact = store.linkedContactId
        val me = store.deviceId
        if (contact != null && me != null) kotlinx.coroutines.withContext(Dispatchers.IO) {
            kotlinx.coroutines.withTimeoutOrNull(5_000) {
                runCatching { api.alert(com.satark.app.net.AlertRequest(me, com.satark.app.protection.ProtectionOff.TYPE_OFF)) }
            }
        }
        com.satark.app.signals.SignalService.stop(app)
        // Best effort, while the sign-in still exists: DELETE /device erases the server's rows for this phone.
        kotlinx.coroutines.withContext(Dispatchers.IO) { runCatching { api.deleteDevice() } }
        kotlinx.coroutines.withContext(Dispatchers.IO) { runCatching { db.clearAllTables() } }
        store.wipe()
    }

    /** Debug tools: empty every local table (events, decisions, payees, payments, alert memory) and the payment pause. */
    suspend fun resetDemoState() {
        kotlinx.coroutines.withContext(Dispatchers.IO) { db.clearAllTables() }
        store.pauseUntilMs = 0L
        store.pausePhraseOwed = false
    }

    /** (alerts shown, repeats merged) since install: simple local counters, nothing leaves the phone. */
    suspend fun alertCounts(): Pair<Int, Int> = dao.alertsShown() to dao.alertsMerged()

    suspend fun recentDecisions(n: Int) = dao.recentDecisions(n)
    suspend fun eventCount() = dao.eventCount()
    suspend fun heldCount() = dao.heldCount()

    /** Called by [com.satark.app.events.EventPurgeWorker]: delete event_queue rows older than 7 days. */
    suspend fun purgeOldEvents(nowMs: Long) = dao.pruneEvents(com.satark.app.events.EventPurgeWorker.cutoff(nowMs))

    fun start() {
        com.satark.app.events.EventPurgeWorker.schedule(app)
        dispatcher.start()
        alerts.start()
        com.satark.app.push.ContactAlertNotifier.ensureChannel(app) // must exist before a background push arrives
        scope.launch { runCatching { session.ensureRegistered(); queue.flush() } }
        flushWhenOnline()
    }

    /** Queued /alert and /signature calls go out as soon as a network with internet comes back. */
    private fun flushWhenOnline() = runCatching {
        val cm = app.getSystemService(android.net.ConnectivityManager::class.java)
        cm.registerDefaultNetworkCallback(object : android.net.ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: android.net.Network) {
                scope.launch { runCatching { session.ensureRegistered(); queue.flush() } }
            }
        })
    }

    /** Begin signal capture (called by SignalService once permissions allow). */
    @Volatile var capturing = false
        private set
    private val upiApps = com.satark.app.ui.alerts.AlertController.UPI_APPS + if (BuildConfig.DEBUG) setOf("t.fakeupi") else emptySet()
    fun startCapture() {
        capturing = true
        hub.start { s ->
            evidence.record(s)
            dispatcher.submit(s)
            if (s is com.satark.app.signals.RawSignal.AppForeground && s.appPackage in upiApps) alerts.paymentAppOpened()
        }
    }
    fun stopCapture() { capturing = false; hub.stop() }
}

/** When stranger texts arrived, kept in plain private prefs (times only: no number, no text). */
private fun textStore(app: android.content.Context) = object : TextBurst.Store {
    private val prefs = app.getSharedPreferences("stranger_texts", android.content.Context.MODE_PRIVATE)
    override var times: List<Long>
        get() = prefs.getString("t", "")!!.split(",").mapNotNull { it.toLongOrNull() }
        set(v) { prefs.edit().putString("t", v.joinToString(",")).apply() }
}
