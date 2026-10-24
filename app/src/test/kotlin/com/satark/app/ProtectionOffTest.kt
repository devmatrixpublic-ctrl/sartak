package com.satark.app

import com.satark.app.protection.ProtectionOff
import com.satark.app.push.ContactAlert
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ProtectionOffTest {
    private val min = 60_000L

    private class Mem : ProtectionOff.Store {
        override var dueAtMs = 0L
        override var startedUptimeMs = 0L
    }

    private class Rig {
        var wall = 1_000_000_000L
        var uptime = 5_000_000L
        val store = Mem()
        val told = mutableListOf<String>()
        var off = 0
        val scheduled = mutableListOf<Long>()
        val guard = ProtectionOff(store, { wall }, { uptime }, { told += it }, { off++ }, { scheduled += it })

        /** Time passes normally on both clocks. */
        fun pass(ms: Long) { wall += ms; uptime += ms }
    }

    @Test fun askingToTurnOffTellsTheContactAtOnceAndKeepsProtectionOn() = runBlocking {
        val r = Rig()
        assertTrue(r.guard.request())
        assertEquals(listOf("protection_off_requested"), r.told)
        assertEquals(0, r.off, "still on during the wait")
        assertEquals(listOf(ProtectionOff.WAIT_MS), r.scheduled)
        assertEquals(30 * min, r.guard.remainingMs())
    }

    @Test fun aSecondRequestDuringTheWaitDoesNothingNew() = runBlocking {
        val r = Rig()
        r.guard.request()
        r.pass(5 * min)
        assertFalse(r.guard.request())
        assertEquals(1, r.told.size)
        assertEquals(25 * min, r.guard.remainingMs())
    }

    @Test fun nothingHappensBeforeTheWaitEnds() = runBlocking {
        val r = Rig()
        r.guard.request()
        r.pass(29 * min)
        assertFalse(r.guard.completeIfDue())
        assertEquals(0, r.off)
        assertEquals(listOf("protection_off_requested"), r.told)
    }

    @Test fun whenTheWaitEndsProtectionGoesOffAndTheContactIsToldAgain() = runBlocking {
        val r = Rig()
        r.guard.request()
        r.pass(30 * min)
        assertTrue(r.guard.completeIfDue())
        assertEquals(1, r.off)
        assertEquals(listOf("protection_off_requested", "protection_off"), r.told)
        assertNull(r.guard.remainingMs(), "nothing pending any more")
        assertFalse(r.guard.completeIfDue(), "it cannot fire twice")
    }

    @Test fun cancellingKeepsProtectionOnAndNothingFiresLater() = runBlocking {
        val r = Rig()
        r.guard.request()
        r.pass(10 * min)
        r.guard.cancel()
        r.pass(60 * min)
        assertFalse(r.guard.completeIfDue())
        assertEquals(0, r.off)
        assertNull(r.guard.remainingMs())
    }

    @Test fun movingThePhonesDateForwardDoesNotSkipTheWait() = runBlocking {
        val r = Rig()
        r.guard.request()
        r.wall += 2 * 60 * min // the date is set two hours ahead; only a minute really passes
        r.uptime += min
        assertFalse(r.guard.completeIfDue(), "the uptime clock has not run the whole wait")
        assertEquals(0, r.off)
        assertTrue(r.guard.remainingMs()!! > 0)
        assertTrue(r.scheduled.size >= 2, "it asks to be called again for the rest of the wait")
        r.uptime += 29 * min // the rest of the wait really passes
        assertTrue(r.guard.completeIfDue())
    }

    @Test fun movingTheDateBackwardsDoesNotEndItEarlyEither() = runBlocking {
        val r = Rig()
        r.guard.request()
        r.wall -= 3 * 60 * min
        r.uptime += 31 * min // the wait really passed, but the wall clock says it did not
        assertFalse(r.guard.completeIfDue())
        r.wall += 3 * 60 * min + 31 * min // the date comes back
        assertTrue(r.guard.completeIfDue())
    }

    @Test fun aRestartDuringTheWaitFallsBackToTheWallClock() = runBlocking {
        val r = Rig()
        r.guard.request()
        r.pass(10 * min)
        r.uptime = 2 * min // the phone restarted: the uptime clock began again
        assertEquals(20 * min, r.guard.remainingMs())
        r.wall += 20 * min
        assertTrue(r.guard.completeIfDue())
        assertEquals(1, r.off)
    }

    @Test fun theContactSideKnowsTheNewAlertTypes() {
        for (t in listOf("protection_off_requested", "protection_off", "removal_guard_off")) {
            val a = ContactAlert.from(mapOf("type" to t, "owner_device_id" to "x"))
            assertEquals(t, a.type)
            assertTrue(a.isProtectionChange)
            assertFalse(a.canDecide, "there is no payment to decide")
            assertFalse(a.isLongSession || a.isLinkRequest)
            assertTrue(a.text().contains("Call them now"), t)
        }
        assertEquals("Someone you protect asked to turn Satark off", ContactAlert(ProtectionOff.TYPE_REQUESTED).title())
        assertEquals("Satark was turned off on their phone", ContactAlert(ProtectionOff.TYPE_OFF).title())
        assertEquals("Satark can now be removed from their phone", ContactAlert(ProtectionOff.TYPE_REMOVAL_GUARD_OFF).title())
        assertFalse(ContactAlert.from(mapOf("type" to "alarm")).isProtectionChange)
        assertEquals(ContactAlert.ALARM, ContactAlert.from(mapOf("type" to "protection_off_now")).type, "an unknown type is still just an alarm")
    }
}
