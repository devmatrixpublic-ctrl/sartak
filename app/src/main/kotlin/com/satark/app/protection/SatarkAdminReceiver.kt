package com.satark.app.protection

import android.app.admin.DeviceAdminReceiver
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import com.satark.app.SatarkApp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Registers Satark as a device administrator with no powers at all (res/xml/device_admin.xml). The only effect is the one we want:
 * Android will not uninstall an active device administrator, so removing Satark takes a deliberate extra step in Settings, which
 * shows [onDisableRequested]'s warning, and Satark learns of it ([onDisabled]) and tells the trusted contact at once.
 *
 * This slows removal down and makes it visible; it does not make it impossible (the step is a few taps in Settings).
 */
class SatarkAdminReceiver : DeviceAdminReceiver() {
    /** Shown by Android on the confirmation screen when someone switches the guard off in Settings. */
    override fun onDisableRequested(context: Context, intent: Intent): CharSequence =
        "Satark protects you from payment scams. If someone on a call is asking you to do this, stop and call a person you trust. " +
            "Your trusted contact will be told that Satark can now be removed."

    override fun onDisabled(context: Context, intent: Intent) {
        val graph = (context.applicationContext as? SatarkApp)?.graph ?: return
        val pending = goAsync() // the process may be cut short as soon as onReceive returns; keep it alive for the one call
        CoroutineScope(Dispatchers.IO).launch {
            try { withTimeoutOrNull(8_000) { graph.removalGuardSwitchedOff() } } finally { pending.finish() }
        }
    }

    companion object {
        fun component(ctx: Context) = ComponentName(ctx, SatarkAdminReceiver::class.java)

        fun isActive(ctx: Context): Boolean =
            ctx.getSystemService(DevicePolicyManager::class.java)?.isAdminActive(component(ctx)) == true

        /** Android's own screen that asks the person to activate the guard. */
        fun activateIntent(ctx: Context): Intent = Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN)
            .putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, component(ctx))
            .putExtra(
                DevicePolicyManager.EXTRA_ADD_EXPLANATION,
                "While this is on, Android will not let Satark be uninstalled until it is switched off here. " +
                    "That gives you time to think if someone is telling you to remove it.",
            )
    }
}
