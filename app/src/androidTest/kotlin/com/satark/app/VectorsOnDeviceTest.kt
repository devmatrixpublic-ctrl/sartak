package com.satark.app

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.satark.app.vectors.Vectors
import com.satark.detector.ModelConfig
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Plan 2.7 / integration checklist "Detector in app": M2's 36 test vectors on the phone, inside the app's process, with
 * the model.json packaged in the APK. Run: ./gradlew :app:connectedDebugAndroidTest
 */
@RunWith(AndroidJUnit4::class)
class VectorsOnDeviceTest {
    private val assets = InstrumentationRegistry.getInstrumentation().context.assets
    private fun read(name: String) = assets.open("vectors/$name").bufferedReader().use { it.readText() }
    private val data = Vectors.parse(
        read("detector_test_vectors_events.csv"), read("detector_test_vectors_users.csv"), read("detector_test_vectors_expected.csv"),
    )
    private val model = ModelConfig.loadBundled() // from the APK, as the app loads it

    @Test fun detectorMatchesAll36OnDevice() = check(Vectors.Path.DETECTOR)

    @Test fun appPipelineMatchesAll36OnDevice() = check(Vectors.Path.APP_PIPELINE)

    private fun check(path: Vectors.Path) {
        assertEquals(36, data.expected.size)
        val bad = Vectors.check(data, model, path)
        Log.i("Satark.vectors", "$path on ${android.os.Build.MODEL} (API ${android.os.Build.VERSION.SDK_INT}): ${36 - bad.size}/36")
        assertTrue("${36 - bad.size}/36 match ($path):\n" + bad.joinToString("\n"), bad.isEmpty())
    }
}
