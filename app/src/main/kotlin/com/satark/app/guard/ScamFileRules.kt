package com.satark.app.guard

/**
 * File names that scam apps and documents commonly use in India. A name that looks like one of these, on a file that was just downloaded or
 * received, is a strong sign of a scam: nobody legitimate sends an "RTO Challan.apk" or an "SBI KYC Update.apk" as a file.
 *
 * These are heuristics from a list of common names, not proof. A real bill or invitation can match too, which is why only installable files
 * are moved out of reach; documents get a warning and stay where they are (see [Action]).
 *
 * The patterns are the supplied fragments with word boundaries added to the short tokens (rto, vi, pan, sim, gas, itr, cbi), so a name like
 * "video verification" or "company" is not matched by "vi" or "pan".
 */
enum class ScamCategory(val label: String, pattern: String) {
    TRAFFIC_FINE("traffic fine (RTO challan)", "(rto(?![a-z])|e.?challan|traffic.?challan|parivahan|vahan)"),
    BANK_KYC("bank KYC or rewards", "(sbi|yono|hdfc|axis|icici|pnb|kotak).{0,15}(kyc|reward|point|update)"),
    GOVERNMENT_SCHEME("government scheme", "(pm.?kisan|yojana|ayushman|ration.?card|subsidy)"),
    ID_UPDATE("Aadhaar or PAN update", "(aadhaar|aadhar|pan(?![a-z])).{0,12}(update|link|verify)"),
    UTILITY_BILL("electricity or gas bill", "(electric|power|light|gas(?![a-z])).{0,10}(bill|subsidy|update)"),
    TAX_REFUND("tax refund", "(income.?tax|itr(?![a-z])|tax).{0,10}refund"),
    WEDDING_INVITATION("wedding invitation", "(wedding|shaadi|invitation|invite)"),
    TELECOM_SIM("SIM or telecom KYC", "(sim(?![a-z])|jio|airtel|vi(?![a-z])|trai(?![a-z])).{0,10}(kyc|verif|block)"),
    PARCEL_OR_ARREST("parcel, customs or police notice", "(courier|parcel|dhl|fedex|customs|cbi(?![a-z])|police.?notice)"),
    FAKE_SUPPORT("fake customer support", "(customer.?care|helpdesk|quick.?support|bank.?support)"),
    LOAN_OR_INVESTMENT("instant loan or investment", "(instant.?loan|loan.?approv|trading|stock.?(tip|boost))"),
    PRIZE_OR_RECHARGE("prize or free recharge", "(free.?recharge|lucky.?draw|spin.?win|reward)");

    /** Matches only at the start of a word, so "pan" is not found inside "company". */
    val regex: Regex = Regex("(?<![a-z0-9])$pattern", RegexOption.IGNORE_CASE)
}

/** What to do about a matching file. */
enum class Action {
    /** Move it out of reach into quarantine, and warn. For files that can install something. */
    QUARANTINE,

    /** Leave it where it is and warn. For documents: a real bill or invitation can have the same name. */
    WARN,
}

data class ScamMatch(
    /** The file name as the person would read it, without a download's temporary wrapping. */
    val displayName: String,
    val category: ScamCategory,
    val action: Action,
    /** True when the name carries a download's temporary marker, so the file is probably still being written. */
    val inProgress: Boolean,
)

object ScamFileRules {
    /** Files that can install an app. These are quarantined. */
    val INSTALLABLE = setOf("apk", "apks", "xapk", "apkm")

    /** Documents and archives that phishing and fake-notice scams use. These get a warning only. */
    val DOCUMENTS = setOf("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "zip", "rar", "7z", "txt")

    /** Set to true to quarantine documents as well. Off by default: it can move a genuine bill or invitation the person was expecting. */
    const val QUARANTINE_DOCUMENTS = false

    private val TEMP_SUFFIXES = listOf(".crdownload", ".part", ".tmp", ".download", ".opdownload")
    private val PENDING_PREFIX = Regex("^\\.(pending|trashed)-\\d+-")

    /** Android's download manager hides a file in progress as `.pending-<time>-<name>`; browsers add `.crdownload` or `.part`. */
    private data class Unwrapped(val name: String, val inProgress: Boolean, val trashed: Boolean)

    private fun unwrap(fileName: String): Unwrapped {
        var name = fileName
        var inProgress = false
        PENDING_PREFIX.find(name)?.let {
            if (it.groupValues[1] == "trashed") return Unwrapped(name, false, true)
            name = name.removePrefix(it.value); inProgress = true
        }
        for (s in TEMP_SUFFIXES) if (name.endsWith(s, ignoreCase = true)) { name = name.dropLast(s.length); inProgress = true }
        return Unwrapped(name, inProgress, false)
    }

    /** "RTOChallan_v2.apk" -> "rto challan v2": camel-case split, every separator to a space, lower case. */
    fun normalize(baseName: String): String =
        baseName
            .replace(Regex("([a-z0-9])([A-Z])"), "$1 $2")
            .replace(Regex("([A-Z]+)([A-Z][a-z])"), "$1 $2")
            .replace(Regex("[^A-Za-z0-9]+"), " ")
            .trim()
            .lowercase()

    /** The decision for one file name, or null when nothing about it looks like a scam. */
    fun check(fileName: String): ScamMatch? {
        val u = unwrap(fileName)
        if (u.trashed) return null
        val dot = u.name.lastIndexOf('.')
        if (dot <= 0) return null // no extension: a folder, or a temporary name with nothing to judge
        val ext = u.name.substring(dot + 1).lowercase()
        val action = when {
            ext in INSTALLABLE -> Action.QUARANTINE
            ext in DOCUMENTS -> if (QUARANTINE_DOCUMENTS) Action.QUARANTINE else Action.WARN
            else -> return null
        }
        val base = normalize(u.name.substring(0, dot))
        val category = ScamCategory.values().firstOrNull { it.regex.containsMatchIn(base) } ?: return null
        return ScamMatch(u.name, category, action, u.inProgress)
    }
}
