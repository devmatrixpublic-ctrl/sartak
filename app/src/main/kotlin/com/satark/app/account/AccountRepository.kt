package com.satark.app.account

import com.satark.app.net.AccountNameRequest
import com.satark.app.net.AccountRequest
import com.satark.app.net.SatarkApi
import com.satark.app.security.TokenStore
import java.io.IOException

/** Signing in and out of a Satark account (a verified phone number and a name). Nothing here is needed to use the app. */
class AccountRepository(
    private val api: () -> SatarkApi,
    private val store: TokenStore,
    /** Registers this phone with the server first, if it has not been. Must not throw. */
    private val ready: suspend () -> Unit = {},
    /** This phone's push address, or null when push is not set up. Asked for only once the person has signed in. */
    private val pushToken: suspend () -> String? = { null },
) {
    sealed interface SignIn {
        /** [created]: a brand-new account, so the person is asked for a name; otherwise they have signed in to an existing one. */
        data class Ok(val name: String?, val created: Boolean) : SignIn
        data class Failed(val message: String) : SignIn
    }

    val signedIn get() = store.signedIn
    val name get() = store.accountName
    val phoneMasked get() = store.phoneMasked

    suspend fun signIn(idToken: String, phoneE164: String): SignIn {
        ready()
        return try {
            val r = api().account(AccountRequest(idToken))
            store.phoneMasked = PhoneNumber.masked(phoneE164)
            store.accountName = r.name
            store.signInSkipped = false
            refreshPush()
            SignIn.Ok(r.name, r.created)
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: retrofit2.HttpException) {
            SignIn.Failed(when (e.code()) {
                401 -> "That sign-in could not be verified. Try again."
                503 -> "Sign-in is not available right now. Try again later."
                else -> "Sign-in failed (error ${e.code()}). Try again later."
            })
        } catch (e: IOException) {
            SignIn.Failed("Can't reach Satark. Check your connection and try again.")
        } catch (e: Exception) {
            SignIn.Failed("Sign-in failed. Try again.")
        }
    }

    /** Lets people who know this phone's number reach it as a trusted contact. Best effort; harmless to repeat. */
    suspend fun refreshPush(token: String? = null) {
        if (!store.signedIn && store.sharedPushTokenHash == null) return // never registered for alerts: nothing to keep fresh
        runCatching {
            val t = token ?: pushToken() ?: return
            api().putPushToken(com.satark.app.net.PushTokenRequest(t))
        }
    }

    /** The name a trusted contact sees. False when it could not be saved. */
    suspend fun setName(input: String): Boolean {
        val name = PhoneNumber.cleanName(input) ?: return true
        return try {
            api().renameAccount(AccountNameRequest(name))
            store.accountName = name
            true
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            false
        }
    }

    /** This phone leaves the account (best effort on the server; always on the phone). */
    suspend fun signOut() {
        runCatching { api().signOut() }
        store.phoneMasked = null
        store.accountName = null
        store.signInSkipped = true
    }

    /** "Continue without an account." */
    fun skip() { store.signInSkipped = true }
}
