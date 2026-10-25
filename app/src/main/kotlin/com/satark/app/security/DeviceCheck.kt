package com.satark.app.security

import android.content.Context
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.Build
import java.io.File
import java.security.MessageDigest

/**
 * The device check: when the person goes to pay, look at the apps on the phone and say so if the phone is a weaker place to pay from.
 * It is a warning beside the detector, like the nudge. It never holds a payment and never reaches the detector, so it cannot make Satark quieter.
 *
 * What it looks for, strongest first:
 *  - an app that can let someone see or control the phone (remote access, screen share);
 *  - root or hooking tools, which give other apps deep control;
 *  - a known modified copy of a popular app;
 *  - a well-known payment app that arrived through a file installer or a browser, so it may have been tampered with;
 *  - any other app installed from outside an official store (the weakest signal: many people do this on purpose).
 *
 * The package lists below are a curated starting point, not a complete catalogue, and are meant to be extended.
 */
enum class Severity { NONE, MEDIUM, HIGH }

enum class FindingKind(val high: Boolean) {
    REMOTE_ACCESS(true),
    ROOT_OR_HOOK_TOOL(true),
    MODDED_APP(true),
    PAYMENT_APP_FROM_UNOFFICIAL_SOURCE(true),
    SIDELOADED(false),
}

/** One installed app, as the scanner saw it. [installer] is the package that installed it, or null (a file install, adb, or unknown). */
data class InstalledApp(val pkg: String, val label: String, val installer: String?, val isSystem: Boolean)

data class Finding(val pkg: String, val label: String, val kind: FindingKind) {
    /** False for a finding that is not an app the person can uninstall (a root binary). */
    val removable: Boolean get() = pkg.contains('.')

    /** What is wrong with it, in plain words, to follow the app's name. */
    val sentence: String get() = when (kind) {
        FindingKind.REMOTE_ACCESS -> "can let someone see or control your phone"
        FindingKind.ROOT_OR_HOOK_TOOL -> "gives other apps deep control of your phone"
        FindingKind.MODDED_APP -> "is a modified copy of a popular app"
        FindingKind.PAYMENT_APP_FROM_UNOFFICIAL_SOURCE -> "is a payment app installed from outside an official store, so it may have been tampered with"
        FindingKind.SIDELOADED -> "was not installed from an official app store"
    }
}

data class DeviceReport(val findings: List<Finding>) {
    val severity: Severity
        get() = when {
            findings.isEmpty() -> Severity.NONE
            findings.any { it.kind.high } -> Severity.HIGH
            else -> Severity.MEDIUM
        }

    /** The same set of findings always gives the same value, in any order, so a repeat can be recognised without storing app names. */
    val fingerprint: String
        get() = MessageDigest.getInstance("SHA-256")
            .digest(findings.map { "${it.pkg}:${it.kind}" }.sorted().joinToString("|").toByteArray())
            .joinToString("") { "%02x".format(it) }.take(16)
}

object DeviceRules {
    /** Stores whose apps are reviewed by someone. Installs from anywhere else (a downloaded file, adb) count as outside an official store. */
    val TRUSTED_STORES = setOf(
        "com.android.vending",                 // Google Play
        "com.sec.android.app.samsungapps",     // Samsung Galaxy Store
        "com.xiaomi.mipicks", "com.xiaomi.market", // Xiaomi GetApps
        "com.huawei.appmarket",                // Huawei AppGallery
        "com.vivo.appstore",                   // vivo / iQOO
        "com.heytap.market", "com.oppo.market", // realme / OPPO
        "com.amazon.venezia",                  // Amazon Appstore
    )

    val REMOTE_ACCESS = setOf(
        "com.anydesk.anydeskandroid", "com.anydesk.adcontrol.ad1",
        "com.teamviewer.teamviewer.market.mobile", "com.teamviewer.quicksupport.market", "com.teamviewer.host.market",
        "com.google.chromeremotedesktop", "com.rustdesk.rustdesk",
        "com.sand.airdroid", "com.sand.airmirror",
    )

    val ROOT_OR_HOOK_TOOLS = setOf(
        "com.topjohnwu.magisk", "io.github.vvb2060.magisk", "me.weishu.kernelsu",
        "org.lsposed.manager", "de.robv.android.xposed.installer",
        "eu.chainfire.supersu", "com.noshufou.android.su", "com.koushikdutta.superuser", "com.thirdparty.superuser",
    )

    /** Known modified copies of popular apps: messaging clones, and patched Google apps and their stand-ins for Google services. */
    val MODDED_APPS = setOf(
        "com.gbwhatsapp", "com.yowhatsapp", "com.fmwhatsapp", "com.obwhatsapp", "com.whatsapp.plus",
        "com.mgoogle.android.gms",
    )

    /** Whole families of patched apps (ReVanced, Vanced). */
    val MODDED_PREFIXES = listOf("app.revanced.", "com.vanced.")

    /**
     * Installers that are not stores but are not suspicious: a phone maker's or social app's own preload tool. Their apps show up as
     * "third party" on many budget phones.
     */
    val PRELOAD_INSTALLERS = setOf("com.facebook.system", "com.facebook.appmanager")

    /**
     * Parts of the phone maker's own software that some phones list as ordinary apps with no installer. With no installer only, so a file
     * install under one of these names is still reported.
     */
    val PHONE_MAKER_PREFIXES = listOf(
        "com.coloros.", "com.oplus.", "andes.oplus.", "com.heytap.", "com.oppo.", "com.realme.",
        "com.vivo.", "com.iqoo.", "com.bbk.", "com.samsung.", "com.sec.android.", "com.miui.", "com.xiaomi.", "com.huawei.",
    )

    /** Well-known payment apps. Their real copies come from a store; one that did not may have been changed. */
    val PAYMENT_APPS = setOf(
        "com.phonepe.app", "com.google.android.apps.nbu.paisa.user", "net.one97.paytm", "in.org.npci.upiapp",
        "com.dreamplug.androidapp", "com.freecharge.android", "com.mobikwik_new", "in.amazon.mShop.android.shopping",
    )

    /** The packages the scanner needs a display name for even when they are system apps. */
    private val LISTED = REMOTE_ACCESS + ROOT_OR_HOOK_TOOLS + MODDED_APPS + PAYMENT_APPS

    fun isListed(pkg: String) = pkg in LISTED || MODDED_PREFIXES.any { pkg.startsWith(it) }

    private fun isModded(pkg: String) = pkg in MODDED_APPS || MODDED_PREFIXES.any { pkg.startsWith(it) }

    /** One finding per app (the strongest), worst first. [selfPackage] is Satark itself, which a developer may have installed from a file. */
    fun evaluate(apps: List<InstalledApp>, selfPackage: String, rootBinaryFound: Boolean = false): DeviceReport {
        val out = mutableListOf<Finding>()
        for (a in apps) {
            if (a.pkg == selfPackage) continue
            val trusted = a.installer in TRUSTED_STORES || a.installer in PRELOAD_INSTALLERS
            val kind = when {
                a.pkg in REMOTE_ACCESS -> FindingKind.REMOTE_ACCESS
                a.pkg in ROOT_OR_HOOK_TOOLS -> FindingKind.ROOT_OR_HOOK_TOOL
                isModded(a.pkg) -> FindingKind.MODDED_APP
                a.isSystem || trusted -> null
                a.installer == null && PHONE_MAKER_PREFIXES.any { a.pkg.startsWith(it) } -> null
                // No installer at all is ambiguous (adb, a backup restore, a phone-clone tool), so it is only the weak finding. A payment app that
                // arrived through a file installer or a browser is the serious one: that is how a tampered copy is usually delivered.
                a.pkg in PAYMENT_APPS && a.installer != null -> FindingKind.PAYMENT_APP_FROM_UNOFFICIAL_SOURCE
                else -> FindingKind.SIDELOADED
            } ?: continue
            out += Finding(a.pkg, a.label, kind)
        }
        if (rootBinaryFound) out += Finding("root", "Root access", FindingKind.ROOT_OR_HOOK_TOOL)
        return DeviceReport(out.sortedWith(compareByDescending<Finding> { it.kind.high }.thenBy { it.label.lowercase() }))
    }
}

/** When to bother the person. It remembers only a short fingerprint of what was shown, never app names. */
interface DeviceCheckStore {
    var ackFingerprint: String?
    var ackAtMs: Long
    var notifiedFingerprint: String?
    var notifiedAtMs: Long
}

class DevicePolicy(private val store: DeviceCheckStore) {
    /**
     * Ask before a payment. A serious finding asks every time. The weakest one (apps from outside a store) asks once, then stays quiet
     * for a week for the same set of apps, because many people sideload on purpose and a dialog every payment would be ignored.
     */
    fun shouldAsk(r: DeviceReport, nowMs: Long): Boolean = when (r.severity) {
        Severity.NONE -> false
        Severity.HIGH -> true
        Severity.MEDIUM -> !(store.ackFingerprint == r.fingerprint && nowMs - store.ackAtMs in 0 until ACK_MS)
    }

    fun acknowledge(r: DeviceReport, nowMs: Long) {
        if (r.severity == Severity.MEDIUM) { store.ackFingerprint = r.fingerprint; store.ackAtMs = nowMs }
    }

    /** At most one notification a day for the same set of apps. A different set notifies again. */
    fun shouldNotify(r: DeviceReport, nowMs: Long): Boolean =
        r.severity != Severity.NONE && !(store.notifiedFingerprint == r.fingerprint && nowMs - store.notifiedAtMs in 0 until NOTIFY_MS)

    fun markNotified(r: DeviceReport, nowMs: Long) { store.notifiedFingerprint = r.fingerprint; store.notifiedAtMs = nowMs }

    companion object {
        const val ACK_MS = 7L * 24 * 60 * 60 * 1000
        const val NOTIFY_MS = 24L * 60 * 60 * 1000
    }
}

/** Where the list of apps comes from. A fake in tests. */
interface PhoneScanner {
    fun installedApps(): List<InstalledApp>
    fun rootBinaryFound(): Boolean
}

class AndroidPhoneScanner(private val ctx: Context) : PhoneScanner {
    override fun installedApps(): List<InstalledApp> {
        val pm = ctx.packageManager
        val infos = if (Build.VERSION.SDK_INT >= 33) pm.getInstalledApplications(PackageManager.ApplicationInfoFlags.of(0))
        else @Suppress("DEPRECATION") pm.getInstalledApplications(0)
        return infos.map { ai ->
            val system = ai.flags and (ApplicationInfo.FLAG_SYSTEM or ApplicationInfo.FLAG_UPDATED_SYSTEM_APP) != 0
            // A name is needed only for what could be reported; asking for every system app's label is wasted work.
            val label = if (!system || DeviceRules.isListed(ai.packageName)) runCatching { pm.getApplicationLabel(ai).toString() }.getOrDefault(ai.packageName) else ai.packageName
            InstalledApp(ai.packageName, label, installerOf(pm, ai.packageName), system)
        }
    }

    private fun installerOf(pm: PackageManager, pkg: String): String? = runCatching {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) pm.getInstallSourceInfo(pkg).installingPackageName
        else @Suppress("DEPRECATION") pm.getInstallerPackageName(pkg)
    }.getOrNull()

    /** A cheap, imperfect root check: a `su` binary in a usual place. Absence proves nothing; presence is a strong sign. */
    override fun rootBinaryFound(): Boolean = SU_PATHS.any { runCatching { File(it).exists() }.getOrDefault(false) }

    private companion object {
        val SU_PATHS = listOf("/system/bin/su", "/system/xbin/su", "/sbin/su", "/su/bin/su", "/system/sd/xbin/su", "/data/local/xbin/su", "/data/local/bin/su")
    }
}

/** What the Pay screen calls. Not being able to scan (an OEM that strips the permission) is quiet, never a warning. */
class DeviceCheck(
    private val scanner: PhoneScanner,
    private val policy: DevicePolicy,
    private val selfPackage: String,
    private val notify: (DeviceReport) -> Unit,
    private val shadow: () -> Boolean = { false },
    private val now: () -> Long = System::currentTimeMillis,
) {
    fun scan(): DeviceReport = runCatching { DeviceRules.evaluate(scanner.installedApps(), selfPackage, scanner.rootBinaryFound()) }
        .getOrElse { DeviceReport(emptyList()) }

    /** Scan, and send the notification if one is due. Shadow mode shows nothing. */
    fun checkAndNotify(): DeviceReport {
        val r = scan()
        if (!shadow() && policy.shouldNotify(r, now())) { policy.markNotified(r, now()); runCatching { notify(r) } }
        return r
    }

    fun shouldAsk(r: DeviceReport): Boolean = !shadow() && policy.shouldAsk(r, now())

    fun acknowledge(r: DeviceReport) = policy.acknowledge(r, now())

    /** The card on the Pay screen is hidden in shadow mode. */
    val visible: Boolean get() = !shadow()
}
