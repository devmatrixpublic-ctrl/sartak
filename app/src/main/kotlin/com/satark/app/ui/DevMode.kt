package com.satark.app.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.setValue
import com.satark.app.BuildConfig

/**
 * The developer tools (attestation export, shadow mode, reset of demo state) are in debug builds only, and even there they stay
 * hidden until the Satark mark at the top of the pay screen is tapped seven times, so a demo does not show them.
 */
object DevMode {
    private var taps by mutableIntStateOf(0)
    val open: Boolean get() = BuildConfig.DEBUG && taps >= 7
    fun tap() { taps++ }
}
