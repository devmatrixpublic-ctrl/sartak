package com.satark.app.net

import android.content.Context
import android.util.Base64
import android.util.Log
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import com.satark.app.SatarkStub
import com.satark.app.events.QueuedCall
import com.satark.app.events.SatarkDao
import com.satark.app.security.KeyAttestor
import com.satark.app.security.TokenStore
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.Authenticator
import okhttp3.CertificatePinner
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route
import retrofit2.Retrofit
import java.io.IOException
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.sync.withLock

val NetJson = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

/**
 * Registers the device (Key Attestation via /auth/challenge + /auth/device, contracts/auth.md) and refreshes tokens.
 * Debug builds fall back to M4's dev-only /auth/dev-token when attestation is refused (an emulator's key is software).
 */
class DeviceSession(private val ctx: Context, private val store: TokenStore, private val bare: () -> SatarkApi) {
    // One registration at a time: startup and a 401 retry used to register concurrently, each with its own device id,
    // leaving the token of one and the device id of the other (server then answers 403 on /alert).
    private val registering = kotlinx.coroutines.sync.Mutex()

    /** Idempotent; call from a background coroutine (it may hit the network). */
    suspend fun ensureRegistered() {
        if (store.accessToken != null && store.deviceId != null) return
        register()
    }

    suspend fun register() = registering.withLock {
        // Startup asks from two places at once (MainActivity and AppGraph). Whoever waited for the lock must not
        // register again: with real attestation each registration is a new key and a new device id on the server.
        // (recover() clears the session before calling this, so a deliberate re-registration still happens.)
        if (store.accessToken != null && store.deviceId != null) return@withLock
        val api = bare()
        val ch = api.challenge()
        try {
            val att = KeyAttestor.attest(ctx, Base64.decode(ch.challenge, Base64.URL_SAFE or Base64.NO_PADDING))
            Log.i("Satark.auth", "attestation level: ${att.level}") // StrongBox / TEE / software (plan 1.7)
            val t = api.registerDevice(DeviceAuthRequest(ch.challenge, att.publicKeyB64, att.chainB64))
            store.setSession(t.deviceId, t.accessToken, t.refreshToken)
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            // An emulator's chain never roots at Google (400 chain_untrusted / software_only). Debug builds then use
            // M4's /auth/dev-token, which the server only answers in dev with SATARK_AUTH_ENABLE_DEV_TOKEN=1.
            Log.w("Satark.auth", "attestation registration failed: ${(e as? retrofit2.HttpException)?.code() ?: e}")
            if (!com.satark.app.BuildConfig.DEBUG || !registerWithDevTokenRoute(api)) throw e
        }
    }

    @SatarkStub("M4's /auth/dev-token: debug builds only, until attestation registers on a real phone")
    private suspend fun registerWithDevTokenRoute(api: SatarkApi): Boolean = runCatching {
        val t = api.devToken(DevTokenRequest(store.deviceId ?: UUID.randomUUID().toString()))
        store.setSession(t.deviceId, t.accessToken, t.refreshToken)
    }.isSuccess

    /** Called on 401: refresh, and if that fails register again. Returns the new access token or null. */
    @Synchronized
    fun recover(stale: String?): String? {
        if (store.accessToken != stale && store.accessToken != null) return store.accessToken // someone else already refreshed
        return runCatching {
            runBlockingCall {
                val rt = store.refreshToken
                val refreshed = rt != null && runCatching { bare().refresh(RefreshRequest(rt)) }.onSuccess {
                    store.accessToken = it.accessToken; store.refreshToken = it.refreshToken
                }.isSuccess
                if (!refreshed) { store.clearSession(); register() }
            }
            store.accessToken
        }.getOrNull()
    }

    private fun <T> runBlockingCall(block: suspend () -> T): T = kotlinx.coroutines.runBlocking { block() }
}

private class AuthInterceptor(private val store: TokenStore) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val tok = store.accessToken ?: return chain.proceed(chain.request())
        return chain.proceed(chain.request().newBuilder().header("Authorization", "Bearer $tok").build())
    }
}

private class Reauth(private val session: DeviceSession, private val store: TokenStore) : Authenticator {
    override fun authenticate(route: Route?, response: Response): Request? {
        if (response.request.url.encodedPath.startsWith("/auth/") || response.priorResponse != null) return null
        val stale = response.request.header("Authorization")?.removePrefix("Bearer ")
        val tok = session.recover(stale) ?: return null
        return response.request.newBuilder().header("Authorization", "Bearer $tok").build()
    }
}

/** Exponential backoff for IOExceptions and 5xx, only on calls marked idempotent with [RETRY_HEADER]. */
private class RetryInterceptor(private val tries: Int = 3, private val baseMs: Long = 400) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val req = chain.request()
        if (req.header(RETRY_HEADER) == null) return chain.proceed(req)
        val clean = req.newBuilder().removeHeader(RETRY_HEADER).build()
        var last: IOException? = null
        for (i in 0 until tries) {
            try {
                val r = chain.proceed(clean)
                if (r.code < 500 || i == tries - 1) return r
                r.close()
            } catch (e: IOException) {
                last = e
                if (i == tries - 1) throw e
            }
            Thread.sleep(baseMs shl i)
        }
        throw last ?: IOException("retry exhausted")
    }
}

object NetworkModule {
    /** pins: "sha256/AAAA...=,sha256/BBBB...=" (primary + backup, supplied by M4 in contracts/pins.txt). Empty = no pinning (debug only). */
    fun client(store: TokenStore, session: () -> DeviceSession, host: String, pins: String): OkHttpClient {
        val b = OkHttpClient.Builder()
            .connectTimeout(8, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS).writeTimeout(15, TimeUnit.SECONDS)
            .addInterceptor(RetryInterceptor())
            .addInterceptor(AuthInterceptor(store))
            .apply {
                // Debug builds only: log method, path, status and bodies (hashed ids only, no raw numbers or VPAs).
                if (com.satark.app.BuildConfig.DEBUG) addInterceptor(okhttp3.logging.HttpLoggingInterceptor { android.util.Log.d("Satark.http", it) }
                    .apply { level = okhttp3.logging.HttpLoggingInterceptor.Level.BODY; redactHeader("Authorization") })
            }
            .authenticator(object : Authenticator {
                override fun authenticate(route: Route?, response: Response) = Reauth(session(), store).authenticate(route, response)
            })
        val list = pins.split(',').map { it.trim() }.filter { it.startsWith("sha256/") }
        if (list.isNotEmpty()) b.certificatePinner(CertificatePinner.Builder().apply { list.forEach { add(host, it) } }.build())
        return b.build()
    }

    fun api(client: OkHttpClient, baseUrl: String): SatarkApi = Retrofit.Builder()
        .baseUrl(baseUrl).client(client)
        .addConverterFactory(NetJson.asConverterFactory("application/json".toMediaType()))
        .build().create(SatarkApi::class.java)
}

/** Offline queue for /alert and /signature: failed calls are stored and flushed later. */
class OfflineQueue(private val dao: SatarkDao, private val api: () -> SatarkApi) {
    suspend fun alert(r: AlertRequest) = send("alert", NetJson.encodeToString(r)) { api().alert(r) }
    suspend fun signature(r: SignatureRequest) = send("signature", NetJson.encodeToString(r)) { api().signature(r) }

    private suspend fun send(kind: String, body: String, call: suspend () -> Unit) {
        try { call() } catch (e: Exception) { dao.enqueue(QueuedCall(kind = kind, body = body)) }
    }

    private val flushing = kotlinx.coroutines.sync.Mutex()

    /** One flush at a time (startup and reconnect can overlap); a queued call is never sent twice. */
    suspend fun flush() { flushing.withLock { flushLocked() } }

    private suspend fun flushLocked() {
        for (q in dao.queued()) {
            try {
                when (q.kind) {
                    "alert" -> api().alert(NetJson.decodeFromString(q.body))
                    "signature" -> api().signature(NetJson.decodeFromString(q.body))
                }
                dao.dequeue(q.id)
            } catch (e: IOException) {
                dao.bump(q.id); return // still offline: keep order, try again later
            } catch (e: retrofit2.HttpException) {
                if (e.code() in 400..499 && e.code() != 401) dao.dequeue(q.id) else { dao.bump(q.id); return }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                dao.dequeue(q.id) // unreadable row: drop it rather than block the queue forever
            }
        }
    }
}
