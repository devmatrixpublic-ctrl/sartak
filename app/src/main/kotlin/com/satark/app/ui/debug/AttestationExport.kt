package com.satark.app.ui.debug

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.util.Base64
import com.satark.app.BuildConfig
import com.satark.app.net.SatarkApi
import com.satark.app.security.KeyAttestor
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.security.SecureRandom
import java.time.Instant

/**
 * Debug builds only: capture this phone's Key Attestation chain for M4's server tests (contracts/auth.md asks for
 * chains from both test phones). Uses its own Keystore alias, so the app's registration key is never replaced, and
 * never calls /auth/device. Contains no tokens, phone numbers or payee data.
 */
object AttestationExport {
    private const val ALIAS = "satark_attestation_export"
    const val FORMAT = "satark-attestation-export/1"

    class Result(val json: String, val file: File?, val level: String)

    /** Gets a fresh challenge from the server if it answers, else a random local one (recorded in the export). */
    suspend fun capture(ctx: Context, api: SatarkApi): Result {
        check(BuildConfig.DEBUG) { "attestation export is debug-only" }
        val (challengeB64, source) = runCatching { api.challenge().challenge to "server" }.getOrElse {
            val b = ByteArray(32).also(SecureRandom()::nextBytes)
            Base64.encodeToString(b, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP) to "local"
        }
        val att = try {
            KeyAttestor.attest(ctx, Base64.decode(challengeB64, Base64.URL_SAFE or Base64.NO_PADDING), ALIAS)
        } finally {
            KeyAttestor.delete(ALIAS)
        }
        val json = buildJson(
            capturedAt = Instant.now().toString(),
            device = mapOf(
                "manufacturer" to Build.MANUFACTURER, "model" to Build.MODEL, "sdk_int" to Build.VERSION.SDK_INT,
                "release" to Build.VERSION.RELEASE, "security_patch" to Build.VERSION.SECURITY_PATCH,
                "strongbox_feature" to (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P &&
                    ctx.packageManager.hasSystemFeature(PackageManager.FEATURE_STRONGBOX_KEYSTORE)),
            ),
            app = mapOf(
                "package" to ctx.packageName, "version_name" to BuildConfig.VERSION_NAME, "build_type" to BuildConfig.BUILD_TYPE,
                "signing_cert_sha256" to signingDigests(ctx),
            ),
            challenge = challengeB64, challengeSource = source,
            publicKey = att.publicKeyB64, chain = att.chainB64, level = att.level,
        )
        val file = runCatching {
            val dir = ctx.getExternalFilesDir(null) ?: ctx.filesDir
            File(dir, "attestation_${Build.MODEL.replace(Regex("[^A-Za-z0-9]+"), "_")}_${System.currentTimeMillis()}.json")
                .apply { writeText(json) }
        }.getOrNull()
        return Result(json, file, att.level)
    }

    /** Pure, so it is unit-tested: the shape M4's tests read. */
    fun buildJson(
        capturedAt: String, device: Map<String, Any?>, app: Map<String, Any?>, challenge: String, challengeSource: String,
        publicKey: String, chain: List<String>, level: String,
    ): String = JSONObject().apply {
        put("format", FORMAT)
        put("captured_at", capturedAt)
        put("device", JSONObject(device))
        put("app", JSONObject(app.mapValues { (_, v) -> if (v is List<*>) JSONArray(v) else v }))
        put("key_security_level", level)
        put("challenge", challenge) // base64url, as /auth/challenge returns it
        put("challenge_source", challengeSource) // "server" (one-time, now expired) or "local"
        put("public_key", publicKey) // standard base64 SPKI DER, as /auth/device expects
        put("attestation_chain", JSONArray(chain)) // standard base64 DER, leaf first
    }.toString(2)

    fun shareIntent(r: Result): Intent = Intent.createChooser(
        Intent(Intent.ACTION_SEND).setType("text/plain")
            .putExtra(Intent.EXTRA_SUBJECT, "Satark attestation chain: ${Build.MANUFACTURER} ${Build.MODEL} (${r.level})")
            .putExtra(Intent.EXTRA_TEXT, r.json),
        "Send attestation chain to M4",
    )

    @Suppress("DEPRECATION")
    private fun signingDigests(ctx: Context): List<String> = runCatching {
        val sigs = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val info = ctx.packageManager.getPackageInfo(ctx.packageName, PackageManager.GET_SIGNING_CERTIFICATES).signingInfo
                ?: return@runCatching emptyList()
            if (info.hasMultipleSigners()) info.apkContentsSigners else info.signingCertificateHistory
        } else {
            ctx.packageManager.getPackageInfo(ctx.packageName, PackageManager.GET_SIGNATURES).signatures
        }
        sigs.orEmpty().map { s -> MessageDigest.getInstance("SHA-256").digest(s.toByteArray()).joinToString("") { "%02x".format(it) } }
    }.getOrDefault(emptyList())
}
