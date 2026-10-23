package com.satark.app

import com.satark.app.ui.onboarding.ConsentText
import kotlin.test.Test
import kotlin.test.assertTrue

class ConsentTest {
    @Test fun consentTextNamesWhatIsWatchedAndWhatIsNot() {
        assertTrue(ConsentText.watches.size >= 4 && ConsentText.never.size >= 3)
        assertTrue(ConsentText.never.any { it.contains("say", ignoreCase = true) }, "says calls are not listened to")
    }

    @Test fun consentTextDoesNotPromiseWhatTheAppDoesNot() {
        // The app does read the call log and contacts to tell unknown callers apart, so it must not claim it never reads contacts.
        assertTrue(ConsentText.never.none { it.contains("contacts", ignoreCase = true) && !it.contains("list", ignoreCase = true) })
    }
}
