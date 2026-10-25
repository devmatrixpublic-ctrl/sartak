package com.satark.app

import com.satark.app.account.DevPhoneAuth
import com.satark.app.account.PhoneNumber
import com.satark.app.account.VerifyResult
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

class PhoneNumberTest {
    @Test fun aTenDigitIndianMobileIsAccepted() {
        assertEquals("9876543210", PhoneNumber.normalize("9876543210"))
        assertEquals("9876543210", PhoneNumber.normalize("98765 43210"))
        assertEquals("6000000000", PhoneNumber.normalize("6000000000"))
    }

    @Test fun aPastedCountryCodeOrTrunkZeroIsDropped() {
        assertEquals("9876543210", PhoneNumber.normalize("+91 98765 43210"))
        assertEquals("9876543210", PhoneNumber.normalize("919876543210"))
        assertEquals("9876543210", PhoneNumber.normalize("09876543210"))
    }

    @Test fun anythingElseIsRefused() {
        assertNull(PhoneNumber.normalize(""))
        assertNull(PhoneNumber.normalize("98765"))
        assertNull(PhoneNumber.normalize("12345678901"))
        assertNull(PhoneNumber.normalize("5876543210"), "Indian mobiles start with 6 to 9")
        assertNull(PhoneNumber.normalize("98765432101"))
    }

    @Test fun theE164FormIsWhatTheServerSees() {
        assertEquals("+919876543210", PhoneNumber.e164("9876543210"))
    }

    @Test fun theMaskedNumberHidesAllButTheLastFourDigits() {
        val m = PhoneNumber.masked("+919876543210")
        assertTrue(m.endsWith("3210") && m.startsWith("+91"))
        assertFalse("9876" in m)
        assertEquals("+91", PhoneNumber.masked("+91"))
    }

    @Test fun aCodeIsExactlySixDigits() {
        assertTrue(PhoneNumber.isCode("123456"))
        assertFalse(PhoneNumber.isCode("12345"))
        assertFalse(PhoneNumber.isCode("1234567"))
        assertFalse(PhoneNumber.isCode("12345a"))
    }

    @Test fun aNameIsTidiedAndLimited() {
        assertEquals("Ved R", PhoneNumber.cleanName("  Ved    R "))
        assertNull(PhoneNumber.cleanName("   "))
        assertEquals(PhoneNumber.NAME_MAX, PhoneNumber.cleanName("x".repeat(100))!!.length)
    }

    @Test fun theDevelopmentSignInAcceptsOnlyItsFixedCode() = runBlocking {
        val auth = DevPhoneAuth()
        assertTrue(auth.isTestMode)
        assertIs<VerifyResult.Failed>(auth.verify("123456"), "no code was requested yet")
        auth.begin("+919876543210")
        assertIs<VerifyResult.Failed>(auth.verify("000000"))
        assertEquals(VerifyResult.Ok("dev:+919876543210"), auth.verify(DevPhoneAuth.TEST_CODE))
    }
}
