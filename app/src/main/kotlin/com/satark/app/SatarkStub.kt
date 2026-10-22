package com.satark.app

/** Marks temporary code. The release build (M4 CI) fails while any usage remains. */
@Retention(AnnotationRetention.SOURCE)
@Target(AnnotationTarget.CLASS, AnnotationTarget.FUNCTION, AnnotationTarget.PROPERTY, AnnotationTarget.FILE)
annotation class SatarkStub(val reason: String)
