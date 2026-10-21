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
    private const val ALIAS = "satark_device_key"

    fun attest(ctx: Context, challenge: ByteArray): Attestation {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        ks.deleteEntry(ALIAS) // a new challenge needs a new key: the challenge is bound at generation time
        var strongBox = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P && ctx.packageManager.hasSystemFeature(PackageManager.FEATURE_STRONGBOX_KEYSTORE)
        try {
            generate(challenge, strongBox)
        } catch (e: Exception) {
            if (!strongBox) throw e
            strongBox = false
            generate(challenge, false)
        }
        val chain = ks.getCertificateChain(ALIAS).map { Base64.encodeToString(it.encoded, Base64.NO_WRAP) }
        val pub = Base64.encodeToString((ks.getCertificate(ALIAS) as X509Certificate).publicKey.encoded, Base64.NO_WRAP)
        return Attestation(pub, chain, if (strongBox) "StrongBox" else "TEE-or-software")
    }

    private fun generate(challenge: ByteArray, strongBox: Boolean) {
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setAttestationChallenge(challenge)
            // setIsStrongBoxBacked exists from Android 9; calling it on 8.x (minSdk 26) throws NoSuchMethodError.
            .apply { if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) setIsStrongBoxBacked(strongBox) }
            .build()
        KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore").apply { initialize(spec) }.generateKeyPair()
    }
}
