package com.satark.app

import com.satark.app.guard.Action
import com.satark.app.guard.ScamCategory
import com.satark.app.guard.ScamFileRules
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ScamFileRulesTest {
    private fun cat(name: String) = ScamFileRules.check(name)?.category

    @Test fun everyNameInTheSuppliedListIsCaught() {
        val expected = mapOf(
            ScamCategory.TRAFFIC_FINE to listOf("RTO Challan.apk", "e-Challan.apk", "Traffic Challan.apk", "mParivahan.apk", "Vahan.apk"),
            ScamCategory.BANK_KYC to listOf("SBI KYC Update.apk", "SBI Rewards.apk", "YONO Rewards.apk", "HDFC Reward Points.apk", "Axis Rewards.apk", "ICICI KYC.apk"),
            ScamCategory.GOVERNMENT_SCHEME to listOf("PM Kisan Yojana.apk", "PM Kisan Samman Nidhi.apk", "Ayushman Card.apk", "Ration Card.apk"),
            ScamCategory.ID_UPDATE to listOf("Aadhaar Update.apk", "PAN Update.apk", "PAN Aadhaar Link.apk"),
            ScamCategory.UTILITY_BILL to listOf("Electricity Bill.apk", "Power Bill Update.apk", "Gas Subsidy.apk"),
            ScamCategory.TAX_REFUND to listOf("Income Tax Refund.apk", "ITR Refund.apk", "Tax Refund.apk"),
            ScamCategory.WEDDING_INVITATION to listOf("Wedding Invitation.apk", "Shaadi Card.apk", "Invitation.apk"),
            ScamCategory.TELECOM_SIM to listOf("SIM KYC.apk", "Jio KYC.apk", "Airtel KYC.apk", "TRAI Verification.apk"),
            ScamCategory.PARCEL_OR_ARREST to listOf("Courier Tracking.apk", "DHL Parcel.apk", "Customs Clearance.apk", "CBI Notice.apk", "Police Notice.apk"),
            ScamCategory.FAKE_SUPPORT to listOf("Customer Care.apk", "QuickSupport.apk", "Bank Support.apk"),
            ScamCategory.LOAN_OR_INVESTMENT to listOf("Instant Loan.apk", "Loan Approval.apk", "Trading Pro.apk", "Stock Booster.apk"),
            ScamCategory.PRIZE_OR_RECHARGE to listOf("Free Recharge.apk", "Lucky Draw.apk", "Reward Spin.apk"),
        )
        for ((category, names) in expected) for (n in names) assertNotNull(ScamFileRules.check(n), n)
        // The category is the first that matches; a name can fit two, so check the clear ones exactly.
        assertEquals(ScamCategory.TRAFFIC_FINE, cat("RTO Challan.apk"))
        assertEquals(ScamCategory.BANK_KYC, cat("SBI KYC Update.apk"))
        assertEquals(ScamCategory.ID_UPDATE, cat("PAN Aadhaar Link.apk"))
        assertEquals(ScamCategory.TELECOM_SIM, cat("Jio KYC.apk"))
        assertEquals(ScamCategory.PARCEL_OR_ARREST, cat("CBI Notice.apk"))
        assertEquals(ScamCategory.FAKE_SUPPORT, cat("QuickSupport.apk"))
    }

    @Test fun separatorsCaseAndCamelCaseDoNotHideAName() {
        for (n in listOf("rto_challan.apk", "RTO-Challan.APK", "RTOChallan.apk", "rto.challan.apk", "RTO   Challan  (1).apk", "SBIKYCUpdate.apk", "sbi_kyc_update-final.apk", "mParivahan.apk"))
            assertNotNull(ScamFileRules.check(n), n)
    }

    @Test fun anApkIsQuarantinedAndADocumentIsOnlyWarnedAbout() {
        assertEquals(Action.QUARANTINE, ScamFileRules.check("SBI KYC Update.apk")!!.action)
        for (ext in listOf("apks", "xapk", "apkm")) assertEquals(Action.QUARANTINE, ScamFileRules.check("SBI KYC Update.$ext")!!.action, ext)
        for (ext in listOf("pdf", "docx", "xlsx", "zip", "rar", "txt")) assertEquals(Action.WARN, ScamFileRules.check("SBI KYC Update.$ext")!!.action, ext)
    }

    @Test fun picturesVideosAndUnknownTypesAreIgnored() {
        for (ext in listOf("jpg", "png", "mp4", "mp3", "heic", "bin", "xyz")) assertNull(ScamFileRules.check("SBI KYC Update.$ext"), ext)
    }

    @Test fun ordinaryNamesAreLeftAlone() {
        for (n in listOf("holiday photo.apk", "notes.apk", "invoice_2024.pdf", "company profile.pdf", "video verification.pdf", "Spanish lessons.pdf", "gasket.pdf",
            "trainee schedule.pdf", "visa application.pdf", "simulation.apk", "panda.apk", "resume.docx", "boarding pass.pdf", "WhatsApp Image.jpg", "game.apk", "calculator.apk"))
            assertNull(ScamFileRules.check(n), n)
    }

    @Test fun shortTokensNeedAWordBoundary() {
        assertNull(ScamFileRules.check("company update.pdf"), "pan inside company")
        assertNull(ScamFileRules.check("service verification.pdf"), "vi inside service")
        assertNull(ScamFileRules.check("simple kyc.pdf"), "sim inside simple")
        assertNotNull(ScamFileRules.check("sim kyc.pdf"))
        assertNotNull(ScamFileRules.check("pan update.pdf"))
    }

    @Test fun aDownloadInProgressIsRecognisedByItsRealNameAndFlagged() {
        val a = ScamFileRules.check(".pending-1699999999-SBI KYC Update.apk")!!
        assertTrue(a.inProgress)
        assertEquals("SBI KYC Update.apk", a.displayName)
        assertTrue(ScamFileRules.check("SBI KYC Update.apk.crdownload")!!.inProgress)
        assertTrue(ScamFileRules.check("RTO Challan.apk.part")!!.inProgress)
        assertFalse(ScamFileRules.check("RTO Challan.apk")!!.inProgress)
    }

    @Test fun aBrowsersAnonymousTemporaryNameHasNothingToJudge() {
        assertNull(ScamFileRules.check("Unconfirmed 123456.crdownload"))
        assertNull(ScamFileRules.check("download"))
    }

    @Test fun aFileInTheTrashIsIgnored() {
        assertNull(ScamFileRules.check(".trashed-1699999999-SBI KYC Update.apk"))
    }

    @Test fun aNameWithNoExtensionIsIgnored() {
        assertNull(ScamFileRules.check("SBI KYC Update"))
        assertNull(ScamFileRules.check(".hidden"))
    }
}
