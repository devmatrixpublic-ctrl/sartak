package com.satark.app.payments

import java.security.MessageDigest

/** payee_hash = hex SHA-256(salt || lowercase(trim(vpa))). The salt is per install (contracts/upi.md). */
class PayeeHasher(private val salt: ByteArray) {
    fun hash(vpa: String): String {
        val md = MessageDigest.getInstance("SHA-256")
        md.update(salt)
        md.update(vpa.trim().lowercase().toByteArray(Charsets.UTF_8))
        return md.digest().joinToString("") { "%02x".format(it) }
    }
}
