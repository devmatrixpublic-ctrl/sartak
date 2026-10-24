package com.satark.app.ui.lock

import android.app.KeyguardManager
import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import android.os.Build
import android.provider.Settings
import android.widget.Toast
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity

/** What the phone can do to check that it is the owner asking, right now. */
enum class LockState {
    /** A fingerprint is enrolled: the check takes only a fingerprint. */
    FINGERPRINT,

    /** The phone has a fingerprint sensor but none is enrolled: the check takes the screen-lock PIN, pattern or password. */
    PIN_FINGERPRINT_NOT_SET,

    /** The phone has no fingerprint sensor: the check takes the screen-lock PIN, pattern or password. */
    PIN_NO_SENSOR,

    /** No fingerprint and no screen lock: nothing can tell the owner from anyone else holding the phone. */
    NO_SCREEN_LOCK,

    /** A temporary problem (sensor busy, security update needed). Never falls back to a PIN, so it cannot be used to dodge the fingerprint. */
    UNAVAILABLE;

    /** The check can be asked for. */
    val ready get() = this == FINGERPRINT || this == PIN_FINGERPRINT_NOT_SET || this == PIN_NO_SENSOR
    val usesPin get() = this == PIN_FINGERPRINT_NOT_SET || this == PIN_NO_SENSOR

    companion object {
        /** From [BiometricManager.canAuthenticate] for a strong biometric, and whether the phone has a screen lock set. */
        fun of(strongCode: Int, hasScreenLock: Boolean): LockState = when (strongCode) {
            BiometricManager.BIOMETRIC_SUCCESS -> FINGERPRINT
            BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED -> if (hasScreenLock) PIN_FINGERPRINT_NOT_SET else NO_SCREEN_LOCK
            BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE,
            BiometricManager.BIOMETRIC_ERROR_UNSUPPORTED -> if (hasScreenLock) PIN_NO_SENSOR else NO_SCREEN_LOCK
            else -> UNAVAILABLE
        }
    }
}

/**
 * The lock. Satark's protection settings, and "Continue anyway" on a Stop screen, need the owner's fingerprint, so that someone
 * controlling the screen through a remote-access app cannot switch Satark off, change who is told, or push a held payment through.
 *
 * A phone with an enrolled fingerprint accepts only a strong biometric: no PIN alternative, because a PIN typed while the screen is
 * being shared is no longer private. A phone with no fingerprint (no sensor, or none enrolled) falls back to its screen-lock PIN,
 * pattern or password: weaker, but better than no check, and the setup screen says so. Android does the matching; Satark never sees
 * the fingerprint or the PIN. (Android cannot be told "fingerprint only": a phone that offers another strong biometric, such as a 3D
 * face unlock, would accept that too. Ordinary face unlock is not a strong one.)
 */
object FingerprintLock {
    const val STRONG = BiometricManager.Authenticators.BIOMETRIC_STRONG
    const val SCREEN_LOCK = BiometricManager.Authenticators.DEVICE_CREDENTIAL

    fun state(ctx: Context): LockState {
        val hasScreenLock = ctx.getSystemService(KeyguardManager::class.java)?.isDeviceSecure == true
        return LockState.of(BiometricManager.from(ctx).canAuthenticate(STRONG), hasScreenLock)
    }

    /** The phone's own screen for adding a fingerprint. */
    fun enrolIntent(): Intent = when {
        Build.VERSION.SDK_INT >= 30 ->
            Intent(Settings.ACTION_BIOMETRIC_ENROLL).putExtra(Settings.EXTRA_BIOMETRIC_AUTHENTICATORS_ALLOWED, STRONG)
        Build.VERSION.SDK_INT >= 28 -> Intent(Settings.ACTION_FINGERPRINT_ENROLL)
        else -> Intent(Settings.ACTION_SECURITY_SETTINGS)
    }

    /** The phone's own screen for setting a PIN, pattern or password. */
    fun setScreenLockIntent(): Intent = Intent(DevicePolicyManager.ACTION_SET_NEW_PASSWORD)

    /**
     * Shows the prompt that [state] allows. [onResult] is true only for a match (a fingerprint, or the screen lock on a phone with
     * no fingerprint); cancelling, a lock-out or an error is false.
     */
    fun ask(activity: FragmentActivity, state: LockState, title: String, onResult: (Boolean) -> Unit) {
        val pin = state.usesPin
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .setSubtitle(if (pin) "Enter your phone's screen lock to confirm it is you" else "Use your fingerprint to confirm it is you")
            .setAllowedAuthenticators(if (pin) SCREEN_LOCK else STRONG)
            .setConfirmationRequired(false)
            // A prompt that allows the screen lock has its own cancel button; one that does not must be given one.
            .apply { if (!pin) setNegativeButtonText("Cancel") }
            .build()
        val callback = object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) = onResult(true)

            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                if (errorCode == BiometricPrompt.ERROR_LOCKOUT || errorCode == BiometricPrompt.ERROR_LOCKOUT_PERMANENT) {
                    Toast.makeText(activity, "Too many wrong tries. Wait a little, then try again.", Toast.LENGTH_LONG).show()
                }
                onResult(false)
            }
            // onAuthenticationFailed (a finger that does not match): the prompt stays open so the person can try again.
        }
        BiometricPrompt(activity, ContextCompat.getMainExecutor(activity), callback).authenticate(info)
    }
}

/** Runs an action only after the lock check. Created with [rememberLockGate]; it also shows the "set a screen lock" explanation. */
class LockGate internal constructor(
    private val ctx: Context,
    private val activity: FragmentActivity?,
    private val problem: MutableState<LockState?>,
) {
    /** [action] runs once the check passes. With no fingerprint and no screen lock it does not run, and the person is told why. */
    fun require(title: String, action: () -> Unit) {
        val a = activity ?: run { problem.value = LockState.UNAVAILABLE; return }
        val s = FingerprintLock.state(ctx)
        if (s.ready) FingerprintLock.ask(a, s, title) { ok -> if (ok) action() } else problem.value = s
    }
}

@Composable
fun rememberLockGate(): LockGate {
    val ctx = LocalContext.current
    val problem = remember { mutableStateOf<LockState?>(null) }
    val gate = remember(ctx) { LockGate(ctx, ctx.findFragmentActivity(), problem) }
    problem.value?.let { LockProblemDialog(it) { problem.value = null } }
    return gate
}

private tailrec fun Context.findFragmentActivity(): FragmentActivity? = when (this) {
    is FragmentActivity -> this
    is ContextWrapper -> baseContext.findFragmentActivity()
    else -> null
}

@Composable
private fun LockProblemDialog(state: LockState, onClose: () -> Unit) {
    val ctx = LocalContext.current
    val (title, text) = when (state) {
        LockState.NO_SCREEN_LOCK -> "Set a screen lock first" to
            "Satark needs to be sure it is you. Set a PIN, pattern, password or fingerprint in your phone's settings, then try again."
        else -> "The lock is not available right now" to "Try again in a moment. If it keeps happening, restart the phone."
    }
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(title) },
        text = { Text(text) },
        confirmButton = {
            if (state == LockState.NO_SCREEN_LOCK) TextButton(onClick = {
                runCatching { ctx.startActivity(FingerprintLock.setScreenLockIntent()) }
                    .onFailure { runCatching { ctx.startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS)) } }
                onClose()
            }) { Text("Set a screen lock") } else TextButton(onClick = onClose) { Text("OK") }
        },
        dismissButton = { if (state == LockState.NO_SCREEN_LOCK) TextButton(onClick = onClose) { Text("Cancel") } },
    )
}
