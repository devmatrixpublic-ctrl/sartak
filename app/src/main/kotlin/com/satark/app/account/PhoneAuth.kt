package com.satark.app.account

import android.app.Activity
import android.util.Log
import com.google.android.gms.tasks.Task
import com.google.firebase.FirebaseException
import com.google.firebase.FirebaseTooManyRequestsException
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseAuthInvalidCredentialsException
import com.google.firebase.auth.PhoneAuthCredential
import com.google.firebase.auth.PhoneAuthOptions
import com.google.firebase.auth.PhoneAuthProvider
import kotlinx.coroutines.suspendCancellableCoroutine
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

sealed interface SendResult {
    data object Sent : SendResult
    /** Android confirmed the number without a typed code (instant verification). */
    data class AutoVerified(val idToken: String) : SendResult
    data class Failed(val message: String) : SendResult
}

sealed interface VerifyResult {
    /** [idToken] proves the phone number to Satark's server; it is not kept on the phone. */
    data class Ok(val idToken: String) : VerifyResult
    data class Failed(val message: String) : VerifyResult
}

/** Sends a one-time code to a phone number and checks the code the person types. */
interface PhoneAuth {
    /** True for the fixed test code used on a local development server. Shown on screen so nobody mistakes it for a real sign-in. */
    val isTestMode: Boolean get() = false
    suspend fun sendCode(activity: Activity, phoneE164: String): SendResult
    suspend fun verify(code: String): VerifyResult
}

/** Firebase Phone Auth: Google sends the SMS; Satark's server later checks Google's signed token. Firebase keeps no Satark session. */
class FirebasePhoneAuth : PhoneAuth {
    private var verificationId: String? = null
    private var resendToken: PhoneAuthProvider.ForceResendingToken? = null

    override suspend fun sendCode(activity: Activity, phoneE164: String): SendResult = suspendCancellableCoroutine { c ->
        val callbacks = object : PhoneAuthProvider.OnVerificationStateChangedCallbacks() {
            override fun onVerificationCompleted(credential: PhoneAuthCredential) {
                // Instant verification: no code to type. After onCodeSent the person is already on the code screen and types it.
                if (!c.isActive) return
                FirebaseAuth.getInstance().signInWithCredential(credential).addOnCompleteListener { t ->
                    if (!c.isActive) return@addOnCompleteListener
                    val user = t.result?.user
                    if (!t.isSuccessful || user == null) { c.resume(SendResult.Failed(describe(t.exception))); return@addOnCompleteListener }
                    user.getIdToken(false).addOnCompleteListener { tt ->
                        FirebaseAuth.getInstance().signOut()
                        if (c.isActive) c.resume(tt.result?.token?.let { SendResult.AutoVerified(it) } ?: SendResult.Failed("Could not verify. Try again."))
                    }
                }
            }

            override fun onVerificationFailed(e: FirebaseException) {
                if (c.isActive) c.resume(SendResult.Failed(describe(e)))
            }

            override fun onCodeSent(id: String, token: PhoneAuthProvider.ForceResendingToken) {
                verificationId = id
                resendToken = token
                if (c.isActive) c.resume(SendResult.Sent)
            }
        }
        val options = PhoneAuthOptions.newBuilder(FirebaseAuth.getInstance())
            .setPhoneNumber(phoneE164)
            .setTimeout(60L, TimeUnit.SECONDS)
            .setActivity(activity)
            .setCallbacks(callbacks)
            .apply { resendToken?.let { setForceResendingToken(it) } }
            .build()
        PhoneAuthProvider.verifyPhoneNumber(options)
    }

    override suspend fun verify(code: String): VerifyResult {
        val id = verificationId ?: return VerifyResult.Failed("Ask for a new code first.")
        return try {
            val auth = FirebaseAuth.getInstance()
            val user = auth.signInWithCredential(PhoneAuthProvider.getCredential(id, code)).awaitTask().user
                ?: return VerifyResult.Failed("Could not verify. Try again.")
            val token = user.getIdToken(false).awaitTask().token
            auth.signOut() // the token is all Satark needs; no Firebase session stays on the phone
            if (token == null) VerifyResult.Failed("Could not verify. Try again.") else VerifyResult.Ok(token)
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            VerifyResult.Failed(describe(e))
        }
    }

    private fun describe(e: Throwable?): String {
        Log.w("Satark.phoneauth", "phone sign-in problem", e)
        return when {
            e is FirebaseAuthInvalidCredentialsException && e.errorCode == "ERROR_INVALID_VERIFICATION_CODE" -> "That code is not right. Check it and try again."
            e is FirebaseAuthInvalidCredentialsException && e.errorCode == "ERROR_SESSION_EXPIRED" -> "That code has expired. Ask for a new one."
            e is FirebaseAuthInvalidCredentialsException -> "That phone number does not look right."
            e is FirebaseTooManyRequestsException -> "Too many tries. Wait a while and try again."
            e is com.google.firebase.auth.FirebaseAuthException && e.errorCode == "ERROR_APP_NOT_AUTHORIZED" ->
                "Phone sign-in is not set up for this build yet."
            else -> "Could not send or check the code. Check your connection and try again."
        }
    }
}

private suspend fun <T> Task<T>.awaitTask(): T = suspendCancellableCoroutine { c ->
    addOnCompleteListener { t ->
        if (t.isSuccessful) c.resume(t.result) else c.resumeWithException(t.exception ?: RuntimeException("task failed"))
    }
}

/** Local development only (debug build with -PsatarkDevOtp=true, against a dev server): the code is always 123456. */
class DevPhoneAuth : PhoneAuth {
    private var phone: String? = null
    override val isTestMode get() = true

    /** What sending a code does here: nothing is sent, the number is just remembered. */
    fun begin(phoneE164: String) { phone = phoneE164 }

    override suspend fun sendCode(activity: Activity, phoneE164: String): SendResult {
        begin(phoneE164)
        return SendResult.Sent
    }

    override suspend fun verify(code: String): VerifyResult {
        val p = phone ?: return VerifyResult.Failed("Ask for a new code first.")
        return if (code == TEST_CODE) VerifyResult.Ok("dev:$p") else VerifyResult.Failed("That code is not right. Check it and try again.")
    }

    companion object { const val TEST_CODE = "123456" }
}

/** A build without Firebase configuration: the screens still work and say why nothing can be sent. */
class UnavailablePhoneAuth : PhoneAuth {
    override suspend fun sendCode(activity: Activity, phoneE164: String) = SendResult.Failed("Phone sign-in is not set up in this build.")
    override suspend fun verify(code: String) = VerifyResult.Failed("Phone sign-in is not set up in this build.")
}
