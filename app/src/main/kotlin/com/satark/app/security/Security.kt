package com.satark.app.security

import android.content.Context
import android.content.pm.PackageManager
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.os.Build
import android.util.Base64
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.security.spec.ECGenParameterSpec

/** JWT, refresh token, device id and the payee-hash salt live in EncryptedSharedPreferences, never in plain text. */
class TokenStore(ctx: Context) {
    private val prefs = EncryptedSharedPreferences.create(
        ctx, "satark_secure",
        MasterKey.Builder(ctx).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    var accessToken: String? get() = prefs.getString("access", null); set(v) = prefs.edit().putString("access", v).apply()
    var refreshToken: String? get() = prefs.getString("refresh", null); set(v) = prefs.edit().putString("refresh", v).apply()
    var deviceId: String? get() = prefs.getString("device_id", null); set(v) = prefs.edit().putString("device_id", v).apply()
    var ageBand: String? get() = prefs.getString("age_band", null); set(v) = prefs.edit().putString("age_band", v).apply()
    var onboarded: Boolean get() = prefs.getBoolean("onboarded", false); set(v) = prefs.edit().putBoolean("onboarded", v).apply()
    /** Consent to watch for scam signals on this phone. Not asked yet = no protection runs. Revocable in Protection settings. */
    val consentAsked: Boolean get() = prefs.contains("consent")
    var consent: Boolean get() = prefs.getBoolean("consent", false); set(v) = prefs.edit().putBoolean("consent", v).apply()
    /** "Delete my data": forget everything this app keeps on the phone (tokens, device id, salt, flags). */
    fun wipe() = prefs.edit().clear().apply()
    /** Device id (not a phone number) of the trusted contact this person asked, so they can remove them later. */
    var linkedContactId: String? get() = prefs.getString("linked_contact", null); set(v) = prefs.edit().putString("linked_contact", v).apply()
    /** Shadow mode: the detector still scores and the app logs it, but nothing is shown, paused, pushed or held. */
    var shadowMode: Boolean get() = prefs.getBoolean("shadow", false); set(v) = prefs.edit().putBoolean("shadow", v).apply()
    /** Pointer (content URI) to the phone contact "Call trusted contact" dials. Never the number itself. */
    var dialContactUri: String? get() = prefs.getString("dial_contact", null); set(v) = prefs.edit().putString("dial_contact", v).apply()
    /** SHA-256 of the push token last shown as this phone's pairing code (to notice it changed). Not the token. */
    var sharedPushTokenHash: String? get() = prefs.getString("push_shown", null); set(v) = prefs.edit().putString("push_shown", v).apply()
    /** Payment pause after a scam warning (ui/alerts/Friction.kt): when it ends, and whether the phrase is still owed. */
    var pauseUntilMs: Long get() = prefs.getLong("pause_until", 0L); set(v) = prefs.edit().putLong("pause_until", v).apply()
    var pausePhraseOwed: Boolean get() = prefs.getBoolean("pause_phrase", false); set(v) = prefs.edit().putBoolean("pause_phrase", v).apply()

    /** Per-install random salt for payee hashes (contracts/upi.md). Generated once. */
    val payeeSalt: ByteArray
        get() {
            prefs.getString("salt", null)?.let { return Base64.decode(it, Base64.NO_WRAP) }
            val s = ByteArray(32).also(SecureRandom()::nextBytes)
            prefs.edit().putString("salt", Base64.encodeToString(s, Base64.NO_WRAP)).apply()
            return s
        }

    fun clearSession() = prefs.edit().remove("access").remove("refresh").apply()

    /** Device id and tokens are written together so a reader never sees a mix of two registrations. */
    fun setSession(deviceId: String, access: String, refresh: String?) {
        prefs.edit().putString("device_id", deviceId).putString("access", access).putString("refresh", refresh).commit()
    }
}

/** Result of key attestation: the public key plus the certificate chain (leaf first), both base64 DER. */
class Attestation(val publicKeyB64: String, val chainB64: List<String>, val level: String)

/**
 * Android Keystore EC key with an attestation challenge from POST /auth/challenge. StrongBox is requested first
 * and TEE is the fallback. The attestation level is logged by the caller. Play Integrity is NOT used (stated limitation).
 */
object KeyAttestor {
    const val ALIAS = "satark_device_key"

    /** [alias]: the registration key by default; the debug export uses its own alias so it never replaces that key. */
    fun attest(ctx: Context, challenge: ByteArray, alias: String = ALIAS): Attestation {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        ks.deleteEntry(alias) // a new challenge needs a new key: the challenge is bound at generation time
        var strongBox = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P && ctx.packageManager.hasSystemFeature(PackageManager.FEATURE_STRONGBOX_KEYSTORE)
        try {
            generate(alias, challenge, strongBox)
        } catch (e: Exception) {
            if (!strongBox) throw e
            strongBox = false
            generate(alias, challenge, false)
        }
        val chain = ks.getCertificateChain(alias).map { Base64.encodeToString(it.encoded, Base64.NO_WRAP) }
        val pub = Base64.encodeToString((ks.getCertificate(alias) as X509Certificate).publicKey.encoded, Base64.NO_WRAP)
        return Attestation(pub, chain, levelOf(ks, alias, strongBox))
    }

    fun delete(alias: String) = runCatching { KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry(alias) }

    /** Where the key actually lives: "StrongBox", "TEE", "software" or "unknown" (plan 1.7: log the level). */
    private fun levelOf(ks: KeyStore, alias: String, strongBox: Boolean): String = runCatching {
        val key = ks.getKey(alias, null) as java.security.PrivateKey
        val info = java.security.KeyFactory.getInstance(key.algorithm, "AndroidKeyStore")
            .getKeySpec(key, android.security.keystore.KeyInfo::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) when (info.securityLevel) {
            KeyProperties.SECURITY_LEVEL_STRONGBOX -> "StrongBox"
            KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT -> "TEE"
            KeyProperties.SECURITY_LEVEL_SOFTWARE -> "software"
            else -> "unknown"
        } else {
            @Suppress("DEPRECATION")
            if (!info.isInsideSecureHardware) "software" else if (strongBox) "StrongBox" else "TEE"
        }
    }.getOrDefault("unknown")

    private fun generate(alias: String, challenge: ByteArray, strongBox: Boolean) {
        val spec = KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setAttestationChallenge(challenge)
            // setIsStrongBoxBacked exists from Android 9; calling it on 8.x (minSdk 26) throws NoSuchMethodError.
            .apply { if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) setIsStrongBoxBacked(strongBox) }
            .build()
        KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore").apply { initialize(spec) }.generateKeyPair()
    }
}
