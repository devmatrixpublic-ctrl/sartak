package com.satark.app

import com.satark.app.vectors.Vectors
import com.satark.detector.ModelConfig
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** M2's 36 test vectors on the JVM, both straight into the detector and through the app's own event pipeline. */
class VectorsJvmTest {
    private val dir = File("../data/satarksim")
    private val data = Vectors.parse(
        File(dir, "detector_test_vectors_events.csv").readText(),
        File(dir, "detector_test_vectors_users.csv").readText(),
        File(dir, "detector_test_vectors_expected.csv").readText(),
    )
    private val model = ModelConfig.loadBundled()

    @Test fun thirtySixVectors() = assertEquals(36, data.expected.size)

    @Test fun detectorMatchesAll36() {
        val bad = Vectors.check(data, model, Vectors.Path.DETECTOR)
        assertTrue(bad.isEmpty(), "${36 - bad.size}/36 match:\n" + bad.joinToString("\n"))
    }

    @Test fun appPipelineMatchesAll36() {
        val bad = Vectors.check(data, model, Vectors.Path.APP_PIPELINE)
        assertTrue(bad.isEmpty(), "${36 - bad.size}/36 match through the app pipeline:\n" + bad.joinToString("\n"))
    }
}
