package com.satark.app

import com.satark.app.ui.alerts.AlertController
import com.satark.app.ui.alerts.OpenReminder
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class OpenReminderTest {
    private val reasons = listOf("RULE_SIDELOAD_DURING_CALL")

    @Test fun noReminderWithoutAnAlarm() {
        assertNull(OpenReminder { 1_000_000 }.due())
    }

    @Test fun openingAUpiAppSoonAfterAnAlarmRemindsOnceThenWaits() {
        var now = 1_000_000L
        val r = OpenReminder { now }
        r.alarmed(reasons)
        now += 10_000
        assertEquals(reasons, r.due())
        now += 30_000
        assertNull(r.due(), "not again within 2 minutes")
        now += 2 * 60_000
        assertEquals(reasons, r.due())
    }

    @Test fun noReminderAfterThirtyMinutes() {
        var now = 1_000_000L
        val r = OpenReminder { now }
        r.alarmed(reasons)
        now += OpenReminder.WINDOW_MS + 1
        assertNull(r.due())
    }

    @Test fun aFreshAlarmRestartsTheClock() {
        var now = 1_000_000L
        val r = OpenReminder { now }
        r.alarmed(reasons)
        assertEquals(reasons, r.due())
        now += 1_000
        r.alarmed(listOf("F_WATCHLIST_APP"))
        assertEquals(listOf("F_WATCHLIST_APP"), r.due())
    }

    @Test fun theMainUpiAppsAreCovered() {
        listOf("com.google.android.apps.nbu.paisa.user", "com.phonepe.app", "net.one97.paytm", "in.amazon.mShop.android.shopping")
            .forEach { assertTrue(it in AlertController.UPI_APPS, it) }
    }
}
