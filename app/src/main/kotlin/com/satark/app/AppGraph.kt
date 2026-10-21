package com.satark.app

import android.app.Application
import com.satark.app.events.EventDispatcher
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
    val store = TokenStore(app)
    val model: ModelConfig = ModelConfig.loadBundled().let { m ->
        if (BuildConfig.DEBUG && BuildConfig.LONG_SESSION_TEST_MIN > 0)
            m.copy(constants = m.constants.copy(longSessionH = BuildConfig.LONG_SESSION_TEST_MIN / 60.0))
        else m
    }
    private val dao = SatarkDb.create(app).dao()

    private val host = URI(BuildConfig.BASE_URL).host ?: "localhost"
    val session: DeviceSession by lazy { DeviceSession(app, store) { bareApi } }
    private val client: OkHttpClient by lazy { NetworkModule.client(store, { session }, host, BuildConfig.CERT_PINS) }
    val api: SatarkApi by lazy { NetworkModule.api(client, BuildConfig.BASE_URL) }
    // No auth interceptor: used for /auth/{challenge,device,refresh} so a 401 loop is impossible.
    private val bareApi: SatarkApi by lazy { NetworkModule.api(OkHttpClient.Builder().build(), BuildConfig.BASE_URL) }

    val dispatcher = EventDispatcher(dao, model, store.ageBand, scope)
    val hub = SignalHub(app)
    val queue = OfflineQueue(dao) { api }
    val payments = PaymentRepository({ api }, dao, dispatcher, PayeeHasher(store.payeeSalt))
    val alerts = AlertController(dispatcher, queue, store, model, scope)

    fun start() {
        dispatcher.start()
        alerts.start()
        val notifier = com.satark.app.ui.alerts.AlarmNotifier(app)
        scope.launch { dispatcher.alarms.collect { notifier.show(it.decision.mechanism) } }
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
    fun startCapture() = hub.start { dispatcher.submit(it) }
    fun stopCapture() = hub.stop()
}
