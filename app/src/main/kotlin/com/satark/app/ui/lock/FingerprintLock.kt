package com.satark.app.ui.lock

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

/** What the phone can do about a fingerprint check right now. */
enum class LockState {
    READY, NONE_ENROLLED, NO_HARDWARE, UNAVAILABLE;

    companion object {
        /** From [BiometricManager.canAuthenticate]. Anything that is not "ready", "none enrolled" or "no sensor" is a temporary problem. */
        fun fromCode(code: Int): LockState = when (code) {
            BiometricManager.BIOMETRIC_SUCCESS -> READY
            BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED -> NONE_ENROLLED
            BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE -> NO_HARDWARE
            else -> UNAVAILABLE
        }
    }
}

/**
 * The fingerprint lock. Satark's protection settings, and "Continue anyway" on a Stop screen, need a fingerprint, so that someone
 * controlling the screen through a remote-access app cannot switch Satark off, change who is told, or push a held payment through.
 *
 * Only a strong biometric is accepted: there is no screen-lock PIN fallback, because a PIN typed while the screen is being shared is
 * no longer private. Android does the matching; Satark never sees the fingerprint. (Android cannot be told "fingerprint only": a phone
 * that offers another strong biometric, such as a 3D face unlock, would accept that too. Ordinary face unlock is not a strong one.)
 */
object FingerprintLock {
    const val AUTHENTICATORS = BiometricManager.Authenticators.BIOMETRIC_STRONG

    fun state(ctx: Context): LockState = LockState.fromCode(BiometricManager.from(ctx).canAuthenticate(AUTHENTICATORS))

    /** The phone's own screen for adding a fingerprint. */
    fun enrolIntent(): Intent = when {
        Build.VERSION.SDK_INT >= 30 ->
            Intent(Settings.ACTION_BIOMETRIC_ENROLL).putExtra(Settings.EXTRA_BIOMETRIC_AUTHENTICATORS_ALLOWED, AUTHENTICATORS)
        Build.VERSION.SDK_INT >= 28 -> Intent(Settings.ACTION_FINGERPRINT_ENROLL)
        else -> Intent(Settings.ACTION_SECURITY_SETTINGS)
    }

    /** Shows the prompt. [onResult] is true only for a matched fingerprint; cancelling, a lock-out or an error is false. */
    fun ask(activity: FragmentActivity, title: String, subtitle: String, onResult: (Boolean) -> Unit) {
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .setSubtitle(subtitle)
            .setAllowedAuthenticators(AUTHENTICATORS)
            .setNegativeButtonText("Cancel")
            .setConfirmationRequired(false)
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

/** Runs an action only after a fingerprint. Created with [rememberLockGate]; it also shows the "add a fingerprint" explanation. */
class LockGate internal constructor(
    private val ctx: Context,
    private val activity: FragmentActivity?,
    private val problem: MutableState<LockState?>,
) {
    /** [action] runs once the fingerprint matches. With no fingerprint set up (or no sensor) it does not run, and the person is told why. */
    fun require(title: String, action: () -> Unit) {
        val a = activity ?: run { problem.value = LockState.UNAVAILABLE; return }
        when (val s = FingerprintLock.state(ctx)) {
            LockState.READY -> FingerprintLock.ask(a, title, "Use your fingerprint to confirm it is you") { ok -> if (ok) action() }
            else -> problem.value = s
        }
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
        LockState.NONE_ENROLLED -> "Add a fingerprint first" to
            "Satark needs your fingerprint for this. Add one in your phone's settings, then try again."
        LockState.NO_HARDWARE -> "No fingerprint sensor" to
            "This needs a fingerprint, and this phone has no fingerprint sensor, so it cannot be done here."
        else -> "Fingerprint not available right now" to "Try again in a moment. If it keeps happening, restart the phone."
    }
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(title) },
        text = { Text(text) },
        confirmButton = {
            if (state == LockState.NONE_ENROLLED) TextButton(onClick = {
                runCatching { ctx.startActivity(FingerprintLock.enrolIntent()) }
                    .onFailure { runCatching { ctx.startActivity(Intent(Settings.ACTION_SECURITY_SETTINGS)) } }
                onClose()
            }) { Text("Add a fingerprint") } else TextButton(onClick = onClose) { Text("OK") }
        },
        dismissButton = { if (state == LockState.NONE_ENROLLED) TextButton(onClick = onClose) { Text("Cancel") } },
    )
}
