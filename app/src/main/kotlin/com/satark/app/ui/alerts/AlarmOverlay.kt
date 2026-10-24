package com.satark.app.ui.alerts

import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.satark.app.ui.MainActivity

/**
 * A full-screen warning drawn over whatever app is open (a UPI app, the scammer's video call), so a person in the middle
 * of a coached payment sees it. It needs "Display over other apps"; without it the alarm notification is the fallback.
 * It only adds a warning: it never touches, blocks or releases a payment.
 */
class AlarmOverlay(
    private val ctx: Context,
    private val evidence: () -> List<String> = { emptyList() },
    private val riskyApp: () -> Pair<String, String>? = { null },
) {
    private val main = Handler(Looper.getMainLooper())
    private var view: View? = null

    fun canShow(): Boolean = Build.VERSION.SDK_INT < 23 || Settings.canDrawOverlays(ctx)

    /** Shows the small top banner over the current app; its "Fix" button opens the full STOP card. */
    fun show(reasons: List<String>) {
        if (!canShow()) return
        main.post { runCatching { hideNow(); add(banner(reasons), banner = true) } }
    }

    private fun showFull(reasons: List<String>) {
        main.post { runCatching { hideNow(); add(build(Friction.playbook(reasons)), banner = false) } }
    }

    private fun add(v: View, banner: Boolean) {
        val type = if (Build.VERSION.SDK_INT >= 26) WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                   else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE
        val lp = WindowManager.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            if (banner) ViewGroup.LayoutParams.WRAP_CONTENT else ViewGroup.LayoutParams.MATCH_PARENT,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        )
        if (banner) { lp.gravity = Gravity.TOP; lp.y = dp(28) }
        ctx.getSystemService(WindowManager::class.java).addView(v, lp)
        view = v
    }

    /** One short line saying what is unsafe, in everyday words. */
    private fun oneLine(reasons: List<String>): String {
        val c = reasons.map { it.uppercase() }.toSet()
        return when {
            "F_WATCHLIST_APP" in c -> "A screen-sharing app is on your phone"
            "F_UNK_VIDEO_ACTIVE" in c || "RULE_LONG_SESSION" in c -> "A stranger is on a video call with you"
            "F_INSTALL_SIDELOAD_DURING_UNK" in c || "RULE_SIDELOAD_DURING_CALL" in c -> "An unsafe app was installed while a stranger was in touch"
            else -> "Someone you don't know is guiding this"
        }
    }

    private fun banner(reasons: List<String>): View {
        val red = Color.parseColor("#B3261E")
        val seen = evidence()
        val text = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            addView(label("Payment environment is unsafe", 17f, Color.WHITE, bold = true).apply { setPadding(0, 0, 0, 0) })
            // What Satark saw, as short lines. Falls back to a general sentence when nothing specific is known.
            (seen.ifEmpty { listOf(oneLine(reasons)) }).forEach {
                addView(label("• $it", 14f, Color.parseColor("#E6E1E5")).apply { setPadding(0, dp(3), 0, 0) })
            }
        }
        val row = LinearLayout(ctx).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(18), dp(14), dp(14), dp(14))
            background = GradientDrawable().apply { setColor(Color.parseColor("#2B2930")); cornerRadius = dp(24).toFloat(); setStroke(dp(2), red) }
            addView(TextView(ctx).apply { this.text = "!"; textSize = 22f; setTextColor(Color.WHITE); gravity = Gravity.CENTER
                background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(red) }
                layoutParams = LinearLayout.LayoutParams(dp(36), dp(36)).apply { rightMargin = dp(12) } })
            addView(text, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(LinearLayout(ctx).apply {
                orientation = LinearLayout.VERTICAL
                addView(Button(ctx).apply {
                    this.text = "Fix"
                    setOnClickListener { showFull(reasons) }
                })
                // A warning that cannot be waved away becomes noise.
                addView(Button(ctx, null, android.R.attr.borderlessButtonStyle).apply {
                    this.text = "Dismiss"
                    setTextColor(Color.parseColor("#E6E1E5"))
                    setOnClickListener { hide() }
                })
            })
        }
        return FrameLayout(ctx).apply { setPadding(dp(12), 0, dp(12), 0); addView(row) }
    }

    fun hide() { main.post { hideNow() } }

    private fun hideNow() {
        val v = view ?: return
        view = null
        runCatching { ctx.getSystemService(WindowManager::class.java).removeView(v) }
    }

    private fun dp(n: Int) = (n * ctx.resources.displayMetrics.density).toInt()

    private fun label(text: String, sp: Float, color: Int, bold: Boolean = false) = TextView(ctx).apply {
        this.text = text
        textSize = sp
        setTextColor(color)
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
        setPadding(0, dp(6), 0, dp(6))
    }

    private fun build(p: Friction.Playbook): View {
        val red = Color.parseColor("#B3261E")
        val ink = Color.parseColor("#1C1B1F")
        val card = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(22), dp(22), dp(22), dp(18))
            background = GradientDrawable().apply { setColor(Color.WHITE); cornerRadius = dp(20).toFloat(); setStroke(dp(4), red) }
            addView(label("STOP. Do not pay.", 28f, red, bold = true))
            val seen = evidence()
            if (seen.isNotEmpty()) {
                addView(label("What Satark saw", 17f, red, bold = true))
                addView(label(seen.joinToString("\n") { "• $it" }, 16f, ink))
            }
            addView(label(p.title, 19f, ink, bold = true))
            addView(label(p.text, 17f, ink))
            addView(label("Do this now", 17f, red, bold = true))
            addView(label(
                "1. Stop talking to them: hang up, or stop replying.\n2. Do not install or open any app they ask for.\n3. Never tell anyone your UPI PIN or OTP.",
                17f, ink,
            ))
            riskyApp()?.let { (name, pkg) ->
                addView(Button(ctx).apply {
                    text = "Remove \"$name\""
                    setOnClickListener {
                        // Android asks the person to confirm: an app cannot remove another app silently.
                        runCatching {
                            ctx.startActivity(Intent(Intent.ACTION_DELETE, android.net.Uri.parse("package:$pkg")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        }
                        hide()
                    }
                })
            }
            addView(Button(ctx).apply {
                text = "Call 1930 (cyber fraud helpline)"
                setOnClickListener {
                    runCatching { ctx.startActivity(FraudReport.dial1930().addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
                    hide()
                }
            })
            addView(Button(ctx).apply {
                text = "I understand, close"
                setOnClickListener { hide() }
            })
            addView(Button(ctx).apply {
                text = "See more in Satark"
                setOnClickListener {
                    runCatching {
                        ctx.startActivity(Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP))
                    }
                    hide()
                }
            })
        }
        val scroll = ScrollView(ctx).apply { isFillViewport = false; addView(card) }
        return FrameLayout(ctx).apply {
            setBackgroundColor(Color.parseColor("#E6000000"))
            setPadding(dp(16), dp(40), dp(16), dp(24))
            isClickable = true
            addView(scroll, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER))
        }
    }
}
