package com.satark.app.ui.theme

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Shapes
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.unit.sp
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

/**
 * Satark look (from the Stitch "Sarvam-inspired" screens): a soft lavender-white canvas, white rounded cards, one confident
 * blue for actions, slate text, and rose only for a real stop. Amber stays for "take a moment" (the nudge).
 */
private val Light = lightColorScheme(
    primary = Color(0xFF2563EB), onPrimary = Color.White,
    primaryContainer = Color(0xFFE9EFFD), onPrimaryContainer = Color(0xFF1E3A8A),
    secondary = Color(0xFF475569), onSecondary = Color.White,
    secondaryContainer = Color(0xFFEDF2FE), onSecondaryContainer = Color(0xFF1E293B),
    tertiary = Color(0xFF9A6700), onTertiary = Color.White,
    tertiaryContainer = Color(0xFFFFF1CC), onTertiaryContainer = Color(0xFF3B2A00),
    error = Color(0xFFE11D48), onError = Color.White,
    errorContainer = Color(0xFFFFF1F2), onErrorContainer = Color(0xFF9F1239),
    background = Color(0xFFF8FAFC), onBackground = Color(0xFF161C28),
    surface = Color(0xFFF8FAFC), onSurface = Color(0xFF161C28),
    surfaceVariant = Color(0xFFEDF0F7), onSurfaceVariant = Color(0xFF6E7B8F),
    surfaceContainerLowest = Color.White, surfaceContainerLow = Color(0xFFF4F7FB),
    surfaceContainer = Color(0xFFEFF3F9), surfaceContainerHigh = Color(0xFFE9EEF5),
    surfaceContainerHighest = Color(0xFFE2E8F0),
    outline = Color(0xFF8E9AA8), outlineVariant = Color(0xFFDBE1EA),
)

private val Dark = darkColorScheme(
    primary = Color(0xFF7BA4FF), onPrimary = Color(0xFF0B1F57),
    primaryContainer = Color(0xFF1E3A8A), onPrimaryContainer = Color(0xFFDCE6FF),
    secondary = Color(0xFFB7C3D6), onSecondary = Color(0xFF1E293B),
    secondaryContainer = Color(0xFF2B3548), onSecondaryContainer = Color(0xFFDDE5F2),
    tertiary = Color(0xFFF0BF48), onTertiary = Color(0xFF402D00),
    tertiaryContainer = Color(0xFF5C4300), onTertiaryContainer = Color(0xFFFFE9B0),
    error = Color(0xFFFF8FA6), onError = Color(0xFF5C0020),
    errorContainer = Color(0xFF7A1232), onErrorContainer = Color(0xFFFFD9E0),
    background = Color(0xFF0E131C), onBackground = Color(0xFFE4E9F2),
    surface = Color(0xFF0E131C), onSurface = Color(0xFFE4E9F2),
    surfaceVariant = Color(0xFF2A3342), onSurfaceVariant = Color(0xFFA9B4C4),
    surfaceContainerLowest = Color(0xFF0A0E15), surfaceContainerLow = Color(0xFF151B26),
    surfaceContainer = Color(0xFF1A2130), surfaceContainerHigh = Color(0xFF232B3B),
    surfaceContainerHighest = Color(0xFF2E3748),
    outline = Color(0xFF8793A6), outlineVariant = Color(0xFF2E3748),
)

private val Base = Typography()
private val SatarkType = Base.copy(
    headlineLarge = Base.headlineLarge.copy(fontWeight = FontWeight.Bold),
    headlineMedium = Base.headlineMedium.copy(fontWeight = FontWeight.Bold, letterSpacing = (-0.5).sp),
    headlineSmall = Base.headlineSmall.copy(fontWeight = FontWeight.Bold),
    titleLarge = Base.titleLarge.copy(fontWeight = FontWeight.Bold),
    titleMedium = Base.titleMedium.copy(fontWeight = FontWeight.SemiBold),
    titleSmall = Base.titleSmall.copy(fontWeight = FontWeight.SemiBold),
    labelLarge = Base.labelLarge.copy(fontWeight = FontWeight.SemiBold),
)

/** Big soft corners on cards and sheets, as in the reference screens. Buttons are already pills. */
private val SatarkShapes = Shapes(
    extraSmall = RoundedCornerShape(10.dp),
    small = RoundedCornerShape(14.dp),
    medium = RoundedCornerShape(22.dp),
    large = RoundedCornerShape(26.dp),
    extraLarge = RoundedCornerShape(32.dp),
)

@Composable
fun SatarkTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val scheme = if (dark) Dark else Light
    // A faint lavender bloom from the top-right corner, fading to the plain canvas.
    val bloom = if (dark) Color(0x33645AA8) else Color(0x73CEBEF5)
    MaterialTheme(colorScheme = scheme, typography = SatarkType, shapes = SatarkShapes) {
        Surface(color = scheme.background) {
            Box(
                Modifier.fillMaxSize().background(
                    Brush.radialGradient(
                        colors = listOf(bloom, Color.Transparent),
                        center = Offset(Float.POSITIVE_INFINITY, 0f),
                        radius = 1400f,
                    ),
                ),
                content = { content() },
            )
        }
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
fun SatarkHeader(title: String, subtitle: String? = null, trailing: (@Composable () -> Unit)? = null, onMarkTap: (() -> Unit)? = null) {
    Column(Modifier.padding(top = 8.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(
                if (onMarkTap != null) Modifier.clickable(
                    indication = null,
                    interactionSource = androidx.compose.runtime.remember { androidx.compose.foundation.interaction.MutableInteractionSource() },
                ) { onMarkTap() } else Modifier,
            ) { SatarkMark(28.dp) }
            Text("Satark", style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.weight(1f))
            trailing?.invoke()
        }
        Text(title, style = MaterialTheme.typography.headlineMedium)
        subtitle?.let { Text(it, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

/**
 * The card used on every screen: white, large soft corners, a hairline edge and no shadow, as in the reference screens.
 * A caller can still pass its own colours (the amber nudge, the red hold) or a different border.
 */
@Composable
fun Card(
    modifier: Modifier = Modifier,
    colors: androidx.compose.material3.CardColors = androidx.compose.material3.CardDefaults.cardColors(
        containerColor = MaterialTheme.colorScheme.surfaceContainerLowest,
    ),
    elevation: androidx.compose.material3.CardElevation = androidx.compose.material3.CardDefaults.cardElevation(),
    border: androidx.compose.foundation.BorderStroke? = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
    content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit,
) = androidx.compose.material3.Card(modifier, MaterialTheme.shapes.medium, colors, elevation, border, content)

/** The tappable version, same look. */
@Composable
fun Card(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    colors: androidx.compose.material3.CardColors = androidx.compose.material3.CardDefaults.cardColors(
        containerColor = MaterialTheme.colorScheme.surfaceContainerLowest,
    ),
    elevation: androidx.compose.material3.CardElevation = androidx.compose.material3.CardDefaults.cardElevation(),
    border: androidx.compose.foundation.BorderStroke? = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
    content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit,
) = androidx.compose.material3.Card(onClick, modifier, shape = MaterialTheme.shapes.medium, colors = colors, elevation = elevation, border = border, content = content)
