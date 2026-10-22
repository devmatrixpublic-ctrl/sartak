package com.satark.app

import android.os.Bundle
import android.util.Base64
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.satark.app.ui.debug.AttestationExport
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The "Export attestation chain for M4" button, run from a command (app/tools/phone_check.py) instead of a tap.
 * Uses the app's own key alias for exports, so the registration key is untouched. The JSON comes back to the computer
 * as an instrumentation status line (attestation_b64=...), and is also saved on the phone like the button does.
 */
@RunWith(AndroidJUnit4::class)
class AttestationExportOnDeviceTest {
    @Test fun captureAttestationChainForM4() {
        val instr = InstrumentationRegistry.getInstrumentation()
        val ctx = instr.targetContext
        val graph = (ctx.applicationContext as SatarkApp).graph
        val r = runBlocking { AttestationExport.capture(ctx, graph.api) }

        val o = JSONObject(r.json)
        val chain = o.getJSONArray("attestation_chain")
        assertTrue("a chain has at least a leaf and a root", chain.length() >= 2)
        assertTrue(o.getString("public_key").isNotEmpty())

        instr.sendStatus(STATUS_EXPORT, Bundle().apply {
            putString("attestation_b64", Base64.encodeToString(r.json.toByteArray(), Base64.NO_WRAP))
            putString("key_level", r.level)
        })
        Log.i("Satark.attest", "key level ${r.level}, ${chain.length()} certificates, saved to ${r.file}")
    }

    private companion object {
        /** Not one of AndroidJUnitRunner's own codes (1, 0, -1 to -4). */
        const val STATUS_EXPORT = 2
    }
}
