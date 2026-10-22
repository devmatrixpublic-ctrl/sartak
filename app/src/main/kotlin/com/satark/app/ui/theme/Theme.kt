package com.satark.app.ui.theme

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** Satark colours: a deep teal for trust, amber for "take a moment", red only for a real stop. */
private val Light = lightColorScheme(
    primary = Color(0xFF0B5D59), onPrimary = Color.White,
    primaryContainer = Color(0xFFA7F0E8), onPrimaryContainer = Color(0xFF00201E),
    secondary = Color(0xFF4A6360), onSecondary = Color.White,
    secondaryContainer = Color(0xFFCCE8E3), onSecondaryContainer = Color(0xFF05201D),
    tertiary = Color(0xFF7A5900), onTertiary = Color.White,
    tertiaryContainer = Color(0xFFFFDEA6), onTertiaryContainer = Color(0xFF261900),
    error = Color(0xFFBA1A1A), onError = Color.White,
    errorContainer = Color(0xFFFFDAD6), onErrorContainer = Color(0xFF410002),
    background = Color(0xFFF5FAF8), onBackground = Color(0xFF171D1C),
    surface = Color(0xFFF5FAF8), onSurface = Color(0xFF171D1C),
    surfaceVariant = Color(0xFFDAE5E2), onSurfaceVariant = Color(0xFF3F4947),
    surfaceContainerLowest = Color.White, surfaceContainerLow = Color(0xFFEFF5F3),
    surfaceContainer = Color(0xFFE9EFED), surfaceContainerHigh = Color(0xFFE4E9E7),
    surfaceContainerHighest = Color(0xFFDEE4E2),
    outline = Color(0xFF6F7977), outlineVariant = Color(0xFFBEC9C6),
)

private val Dark = darkColorScheme(
    primary = Color(0xFF8BD4CC), onPrimary = Color(0xFF003735),
    primaryContainer = Color(0xFF00504D), onPrimaryContainer = Color(0xFFA7F0E8),
    secondary = Color(0xFFB0CCC7), onSecondary = Color(0xFF1B3532),
    secondaryContainer = Color(0xFF324B48), onSecondaryContainer = Color(0xFFCCE8E3),
    tertiary = Color(0xFFF0BF48), onTertiary = Color(0xFF402D00),
    tertiaryContainer = Color(0xFF5C4300), onTertiaryContainer = Color(0xFFFFDEA6),
    error = Color(0xFFFFB4AB), onError = Color(0xFF690005),
    errorContainer = Color(0xFF93000A), onErrorContainer = Color(0xFFFFDAD6),
    background = Color(0xFF0F1514), onBackground = Color(0xFFDEE4E2),
    surface = Color(0xFF0F1514), onSurface = Color(0xFFDEE4E2),
    surfaceVariant = Color(0xFF3F4947), onSurfaceVariant = Color(0xFFBEC9C6),
    surfaceContainerLowest = Color(0xFF0A0F0E), surfaceContainerLow = Color(0xFF171D1C),
    surfaceContainer = Color(0xFF1B2120), surfaceContainerHigh = Color(0xFF252B2A),
    surfaceContainerHighest = Color(0xFF303635),
    outline = Color(0xFF899390), outlineVariant = Color(0xFF3F4947),
)

private val Base = Typography()
private val SatarkType = Base.copy(
    headlineMedium = Base.headlineMedium.copy(fontWeight = FontWeight.SemiBold),
    headlineSmall = Base.headlineSmall.copy(fontWeight = FontWeight.SemiBold),
    titleLarge = Base.titleLarge.copy(fontWeight = FontWeight.SemiBold),
    titleMedium = Base.titleMedium.copy(fontWeight = FontWeight.SemiBold),
    titleSmall = Base.titleSmall.copy(fontWeight = FontWeight.SemiBold),
)

@Composable
fun SatarkTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, typography = SatarkType) {
        Surface(color = MaterialTheme.colorScheme.background, content = content)
    }
}

// The Satark mark: a shield with a tick (same shapes as the launcher icon), drawn in theme colours.
private const val SHIELD = "M12,1L3,5v6c0,5.55 3.84,10.74 9,12 5.16,-1.26 9,-6.45 9,-12V5l-9,-4z"
private const val TICK = "M10,17l-4,-4 1.41,-1.41L10,14.17l6.59,-6.59L18,9l-8,8z"

@Composable
fun SatarkMark(size: Dp = 32.dp, shield: Color = MaterialTheme.colorScheme.primary, tick: Color = MaterialTheme.colorScheme.onPrimary) {
    val shieldPath = remember { PathParser().parsePathString(SHIELD).toPath() }
    val tickPath = remember { PathParser().parsePathString(TICK).toPath() }
    Canvas(Modifier.size(size)) {
        scale(this.size.width / 24f, pivot = Offset.Zero) {
            drawPath(shieldPath, shield)
            drawPath(tickPath, tick)
        }
    }
}

/** Top of every main screen: the mark, "Satark", and the screen's title. */
@Composable
fun SatarkHeader(title: String, subtitle: String? = null, trailing: (@Composable () -> Unit)? = null) {
    Column(Modifier.padding(top = 8.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SatarkMark(28.dp)
            Text("Satark", style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.weight(1f))
            trailing?.invoke()
        }
        Text(title, style = MaterialTheme.typography.headlineMedium)
        subtitle?.let { Text(it, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}
