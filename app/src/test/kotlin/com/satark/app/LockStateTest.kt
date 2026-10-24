package com.satark.app

import androidx.biometric.BiometricManager
import com.satark.app.ui.lock.FingerprintLock
import com.satark.app.ui.lock.LockState
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class LockStateTest {
    private val ok = BiometricManager.BIOMETRIC_SUCCESS
    private val none = BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED
    private val noSensor = BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE

    @Test fun anEnrolledFingerprintIsAlwaysUsed_evenWithAScreenLock() {
        assertEquals(LockState.FINGERPRINT, LockState.of(ok, hasScreenLock = true))
        assertEquals(LockState.FINGERPRINT, LockState.of(ok, hasScreenLock = false))
        assertFalse(LockState.FINGERPRINT.usesPin)
    }

    @Test fun aPhoneWithNoFingerprintFallsBackToItsScreenLock() {
        assertEquals(LockState.PIN_FINGERPRINT_NOT_SET, LockState.of(none, hasScreenLock = true))
        assertEquals(LockState.PIN_NO_SENSOR, LockState.of(noSensor, hasScreenLock = true))
        assertEquals(LockState.PIN_NO_SENSOR, LockState.of(BiometricManager.BIOMETRIC_ERROR_UNSUPPORTED, hasScreenLock = true))
        assertTrue(LockState.PIN_FINGERPRINT_NOT_SET.ready && LockState.PIN_FINGERPRINT_NOT_SET.usesPin)
        assertTrue(LockState.PIN_NO_SENSOR.ready && LockState.PIN_NO_SENSOR.usesPin)
    }

    @Test fun noFingerprintAndNoScreenLockCannotBeChecked() {
        assertEquals(LockState.NO_SCREEN_LOCK, LockState.of(none, hasScreenLock = false))
        assertEquals(LockState.NO_SCREEN_LOCK, LockState.of(noSensor, hasScreenLock = false))
        assertFalse(LockState.NO_SCREEN_LOCK.ready)
    }

    @Test fun aTemporaryProblemNeverFallsBackToAPin() {
        // A busy or failing sensor must not become a way round the fingerprint on a phone that has one.
        for (code in listOf(
            BiometricManager.BIOMETRIC_ERROR_HW_UNAVAILABLE,
            BiometricManager.BIOMETRIC_ERROR_SECURITY_UPDATE_REQUIRED,
            BiometricManager.BIOMETRIC_STATUS_UNKNOWN,
            12345,
        )) for (lock in listOf(true, false)) {
            val s = LockState.of(code, lock)
            assertEquals(LockState.UNAVAILABLE, s, "code $code, screen lock $lock")
            assertFalse(s.ready)
        }
    }

    @Test fun theFingerprintCheckAcceptsOnlyAStrongBiometric() {
        assertEquals(BiometricManager.Authenticators.BIOMETRIC_STRONG, FingerprintLock.STRONG)
        assertEquals(0, FingerprintLock.STRONG and BiometricManager.Authenticators.DEVICE_CREDENTIAL, "no PIN inside the fingerprint check")
        assertEquals(BiometricManager.Authenticators.DEVICE_CREDENTIAL, FingerprintLock.SCREEN_LOCK)
    }
}
