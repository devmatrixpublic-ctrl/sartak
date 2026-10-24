package com.satark.app

import com.satark.app.events.EventMapper
import com.satark.app.events.SessionPolicy
import com.satark.app.signals.MessageSender
import com.satark.app.signals.RawSignal
import com.satark.detector.EventType
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Messages from strangers: only the sender label is judged, and the detector gets an instant unknown contact. */
class MessageSignalTest {
    @Test fun anUnsavedSenderShowsAsAPhoneNumber() {
        assertTrue(MessageSender.looksLikePhoneNumber("+91 98765 00011"))
        assertTrue(MessageSender.looksLikePhoneNumber("9876500011"))
        assertTrue(MessageSender.looksLikePhoneNumber("(555) 010-9999"))
    }

    @Test fun namesBusinessIdsAndGroupsAreNotStrangers() {
        assertFalse(MessageSender.looksLikePhoneNumber("Amma"))
        assertFalse(MessageSender.looksLikePhoneNumber("VM-HDFCBK"))
        assertFalse(MessageSender.looksLikePhoneNumber("Family group (5 new messages)"))
        assertFalse(MessageSender.looksLikePhoneNumber("12345")) // a short code, not a person
        assertFalse(MessageSender.looksLikePhoneNumber(""))
        assertFalse(MessageSender.looksLikePhoneNumber(null))
    }

    @Test fun aMessageIsAnInstantUnknownContactWithNoCallLeftOpen() {
        val events = EventMapper.mapAll(RawSignal.UnknownMessage(1_000))
        assertEquals(listOf(EventType.CALL_START, EventType.CALL_END), events.map { it.type })
        assertEquals(false, events[0].callerKnown)
        assertTrue(events[1].tMs > events[0].tMs)

        val policy = SessionPolicy()
        events.forEach { assertNotNull(policy.prepare(it)) }
        assertFalse(policy.unknownCallActive, "no call is active after the message")
        assertFalse(policy.callIsOpen)
    }

    @Test fun otherSignalsStayOneToOne() {
        assertEquals(1, EventMapper.mapAll(RawSignal.CallEnded(5)).size)
        assertNull(EventMapper.mapAll(RawSignal.CallEnded(5)).first().callerKnown)
    }
}
