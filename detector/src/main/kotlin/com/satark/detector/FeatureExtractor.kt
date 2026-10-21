package com.satark.detector

import kotlin.math.ln
import kotlin.math.ln1p
import kotlin.math.max
import kotlin.math.min

/** The 16 features, computed at a PAYMENT_ATTEMPT from the session evidence and the user's baseline. */
class FeatureExtractor(private val model: ModelConfig) {
    private val c = model.constants
    private val contactMs = (c.contactWindowS * 1000).toLong()
    private val ocssMs = (c.ocssWindowS * 1000).toLong()
    private val clipLo = c.amountRatioClip[0]
    private val clipHi = c.amountRatioClip[1]

    private val computers: List<(Ctx) -> Double> = model.features.map { name ->
        when (name) {
            "unk_contact_recent" -> { x -> b(x.recent) }
            "unk_call_active" -> { x -> b(x.s.callActive && x.s.unkT != null) }
            "unk_video_active" -> { x -> b(x.s.videoActive && x.s.videoUnkT != null) }
            "mins_since_unk_log" -> { x -> x.s.unkT?.let { ln1p(max(x.t - it, 0L) / 1000.0 / 60.0) } ?: 0.0 }
            "install_play_during_unk" -> { x -> b(x.installDuring(InstallSource.PLAY_STORE)) }
            "install_sideload_during_unk" -> { x -> b(x.installDuring(InstallSource.SIDELOAD)) }
            "watchlist_app" -> { x -> b(x.s.watchlistSeen) }
            "new_payee" -> { x -> b(x.new) }
            "payee_added_after_unk" -> { x -> b(x.afterUnk) }
            "log_amt_ratio" -> { x -> x.ratio }
            "robust_z_pos" -> { x -> ln1p(min(x.rz, c.robustZCap)) }
            "repeat_to_payee" -> { x -> min(x.rep, c.repeatCap).toDouble() }
            "is_p2p" -> { x -> b(x.e.paymentType == PaymentType.P2P) }
            "ocss_ordered" -> { x -> b(x.ordered) }
            "newpayee_x_amt" -> { x -> b(x.new) * x.ratio }
            "unk_x_newpayee" -> { x -> b(x.recent && x.new) }
            else -> error("unknown feature in model.json: $name")
        }
    }

    /** Features in model.features order. Pure function of its arguments (no clock, no randomness). */
    fun extract(s: SessionState, e: Event, baselineMedian: Double, baselineMad: Double): DoubleArray {
        val ctx = Ctx(s, e, baselineMedian, baselineMad)
        return DoubleArray(computers.size) { computers[it](ctx) }
    }

    private fun b(v: Boolean) = if (v) 1.0 else 0.0

    private inner class Ctx(val s: SessionState, val e: Event, med: Double, mad: Double) {
        val t = e.tMs
        private val unk = s.unkT
        val recent = unk != null && (t - unk) in 0..contactMs
        val amt = e.amountInr?.takeIf { it.isFinite() && it >= 0 } ?: 0.0
        val ratio = ln((amt + 1) / (med + 1)).coerceIn(clipLo, clipHi)
        val rz = max(0.0, (amt - med) / (c.robustZMadScale * max(mad, c.robustZMadFloor)))
        val new = e.payeeIsNew == true
        private val pa: Long? = e.payeeId?.let { s.payeeAddedT[it] }
        val afterUnk = new && unk != null && pa != null && pa >= unk
        val rep = e.payeeId?.let { s.paidTo[it] } ?: 0
        val ordered: Boolean = run {
            if (!afterUnk) return@run false
            val firstInst = s.installs.filter { it.tMs >= unk!! }.minOfOrNull { it.tMs }
            (t - unk!!) <= ocssMs && (firstInst == null || firstInst <= pa!!)
        }

        fun installDuring(src: InstallSource): Boolean =
            unk != null && s.installs.any { it.source == src && it.tMs >= unk && it.tMs <= t }
    }
}
