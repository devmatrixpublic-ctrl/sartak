package com.satark.app

import com.satark.app.ui.Language
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class LanguageTest {
    @Test fun codesMapToLocalesAndUnknownFollowsThePhone() {
        assertEquals("en", Language.localeFor("en")?.language)
        assertEquals("hi", Language.localeFor("hi")?.language)
        assertNull(Language.localeFor(null))
        assertNull(Language.localeFor("fr"))
    }

    @Test fun hindiResourceHasEveryReasonString() {
        val en = Regex("name=\"(reason_[a-z0-9_]+)\"").findAll(File("src/main/res/values/strings.xml").readText()).map { it.groupValues[1] }.toSet()
        val hi = Regex("name=\"(reason_[a-z0-9_]+)\"").findAll(File("src/main/res/values-hi/strings.xml").readText()).map { it.groupValues[1] }.toSet()
        assertTrue(en.size >= 18)
        assertEquals(en, hi, "values-hi must have exactly the English reason strings")
    }
}
