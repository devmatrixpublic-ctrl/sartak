package com.satark.app.events

import com.satark.detector.Event

/**
 * Detector input must be non-decreasing in t_ms. Sources fire on different threads, so events are held for a short
 * reorder window and released sorted (stable for ties). [flush] releases everything (before a payment risk check).
 */
class EventSequencer(private val holdMs: Long = 1500) {
    private val buf = ArrayList<Pair<Long, Event>>() // (arrival seq, event)
    private var seq = 0L
    private var released = Long.MIN_VALUE

    @Synchronized
    fun add(e: Event) {
        // Too late to reorder: clamp so the detector still sees a non-decreasing clock.
        val ev = if (e.tMs < released) e.copy(tMs = released) else e
        buf.add(seq++ to ev)
    }

    @Synchronized
    fun drain(nowMs: Long): List<Event> = release { it.tMs <= nowMs - holdMs }

    @Synchronized
    fun flush(): List<Event> = release { true }

    private fun release(pick: (Event) -> Boolean): List<Event> {
        val out = buf.filter { pick(it.second) }.sortedWith(compareBy({ it.second.tMs }, { it.first })).map { it.second }
        buf.removeAll { pick(it.second) }
        out.lastOrNull()?.let { released = maxOf(released, it.tMs) }
        return out
    }
}
