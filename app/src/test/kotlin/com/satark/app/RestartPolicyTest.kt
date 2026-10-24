package com.satark.app

import android.content.Intent
import com.satark.app.signals.RestartPolicy
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class RestartPolicyTest {
    @Test fun restartsOnRebootAndOnUpdate() {
        assertTrue(RestartPolicy.shouldRestart(Intent.ACTION_BOOT_COMPLETED))
        assertTrue(RestartPolicy.shouldRestart(Intent.ACTION_MY_PACKAGE_REPLACED))
    }

    @Test fun ignoresEveryOtherBroadcast() {
        assertFalse(RestartPolicy.shouldRestart(null))
        assertFalse(RestartPolicy.shouldRestart("android.intent.action.SCREEN_ON"))
        assertFalse(RestartPolicy.shouldRestart("com.example.FAKE_BOOT"))
    }

    @Test fun neverStartsWithoutSetupAndConsent() {
        assertTrue(RestartPolicy.mayRun(onboarded = true, consent = true))
        assertFalse(RestartPolicy.mayRun(onboarded = true, consent = false), "the person said Not now")
        assertFalse(RestartPolicy.mayRun(onboarded = false, consent = true), "setup was never finished")
        assertFalse(RestartPolicy.mayRun(onboarded = false, consent = false))
    }
}
