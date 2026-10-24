package com.satark.app

import androidx.biometric.BiometricManager
import com.satark.app.ui.lock.FingerprintLock
import com.satark.app.ui.lock.LockState
import kotlin.test.Test
import kotlin.test.assertEquals

class LockStateTest {
    @Test fun onlyASuccessfulCheckMeansTheLockIsReady() {
        assertEquals(LockState.READY, LockState.fromCode(BiometricManager.BIOMETRIC_SUCCESS))
        assertEquals(LockState.NONE_ENROLLED, LockState.fromCode(BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED))
        assertEquals(LockState.NO_HARDWARE, LockState.fromCode(BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE))
    }

    @Test fun temporaryAndUnknownProblemsAreNeverReady() {
        for (code in listOf(
            BiometricManager.BIOMETRIC_ERROR_HW_UNAVAILABLE,
            BiometricManager.BIOMETRIC_ERROR_SECURITY_UPDATE_REQUIRED,
            BiometricManager.BIOMETRIC_ERROR_UNSUPPORTED,
            BiometricManager.BIOMETRIC_STATUS_UNKNOWN,
            12345,
        )) assertEquals(LockState.UNAVAILABLE, LockState.fromCode(code), "code $code")
    }

    @Test fun onlyAStrongBiometricIsAccepted_noScreenLockFallback() {
        // BIOMETRIC_STRONG alone: DEVICE_CREDENTIAL (the screen-lock PIN) must not be part of it.
        assertEquals(BiometricManager.Authenticators.BIOMETRIC_STRONG, FingerprintLock.AUTHENTICATORS)
        assertEquals(0, FingerprintLock.AUTHENTICATORS and BiometricManager.Authenticators.DEVICE_CREDENTIAL)
    }
}
