package com.satark.app

import com.satark.app.ui.debug.AttestationExport
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse

/** The export's shape is what M4's server tests read; keep it stable and free of secrets. */
class AttestationExportTest {
    @Test fun exportHasTheFieldsAuthMdNeedsAndNoSecrets() {
        val json = AttestationExport.buildJson(
            capturedAt = "2026-10-22T00:00:00Z",
            device = mapOf("manufacturer" to "Google", "model" to "Pixel 6", "sdk_int" to 35),
            app = mapOf("package" to "com.satark.app", "build_type" to "debug", "signing_cert_sha256" to listOf("ab".repeat(32))),
            challenge = "Fyr27yyhZYnpxlTIjhjWvrBz6YzAWMbv7G-lgBAye98", challengeSource = "server",
            publicKey = "MFkw", chain = listOf("leaf", "intermediate", "root"), level = "TEE",
        )
        val o = JSONObject(json)
        assertEquals(AttestationExport.FORMAT, o.getString("format"))
        assertEquals(listOf("leaf", "intermediate", "root"), (0 until 3).map { o.getJSONArray("attestation_chain").getString(it) })
        assertEquals("TEE", o.getString("key_security_level"))
        assertEquals("com.satark.app", o.getJSONObject("app").getString("package"))
        assertEquals(64, o.getJSONObject("app").getJSONArray("signing_cert_sha256").getString(0).length)
        for (k in listOf("challenge", "challenge_source", "public_key", "captured_at", "device")) assertFalse(o.isNull(k), k)
        for (secret in listOf("access_token", "refresh_token", "payee", "salt")) assertFalse(json.contains(secret), secret)
    }
}
