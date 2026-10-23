package com.satark.app

import com.satark.app.net.Accepted
import com.satark.app.net.AlertRequest
import com.satark.app.net.ChallengeResponse
import com.satark.app.net.DecisionDto
import com.satark.app.net.DeviceAuthRequest
import com.satark.app.net.NetJson
import com.satark.app.net.PaymentDecisionRequest
import com.satark.app.net.PaymentResponse
import com.satark.app.net.PaymentResultRequest
import com.satark.app.net.RefreshRequest
import com.satark.app.net.RiskCheckRequest
import com.satark.app.net.RiskCheckResponse
import com.satark.app.net.SignatureRequest
import com.satark.app.net.TokenResponse
import com.satark.app.net.TrustedContactRequest
import com.satark.app.net.TrustedContactResponse
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.serializer
import org.yaml.snakeyaml.Yaml
import java.io.File
import kotlin.test.Test
import kotlin.test.assertTrue
import kotlin.test.fail

/**
 * The app's client checked against contracts/api.yaml (M3's contract), endpoint by endpoint:
 * - every request body we send validates against its schema (required fields, no unknown fields, enums, types);
 * - every response the schema allows can be decoded by our DTOs, both with only the required fields and with all fields.
 */
@Suppress("UNCHECKED_CAST")
class ApiContractTest {
    private val spec = Yaml().load<Map<String, Any?>>(File("../contracts/api.yaml").readText())
    private val schemas = ((spec["components"] as Map<String, Any?>)["schemas"]) as Map<String, Map<String, Any?>>
    private val paths = spec["paths"] as Map<String, Map<String, Any?>>

    private fun resolve(s: Map<String, Any?>): Map<String, Any?> =
        (s["\$ref"] as? String)?.let { resolve(schemas.getValue(it.substringAfterLast('/'))) } ?: s

    private fun op(path: String, method: String) =
        paths[path]?.get(method) as? Map<String, Any?> ?: fail("api.yaml has no $method $path")

    private fun requestSchema(path: String, method: String): Map<String, Any?> {
        val body = op(path, method)["requestBody"] as Map<String, Any?>
        val json = (body["content"] as Map<String, Any?>)["application/json"] as Map<String, Any?>
        return resolve(json["schema"] as Map<String, Any?>)
    }

    private fun responseSchema(path: String, method: String): Map<String, Any?> {
        val responses = op(path, method)["responses"] as Map<Any?, Any?>
        val ok = (responses["200"] ?: responses[200] ?: responses["201"] ?: responses[201]) as Map<String, Any?>
        val json = (ok["content"] as Map<String, Any?>)["application/json"] as Map<String, Any?>
        return resolve(json["schema"] as Map<String, Any?>)
    }

    /** Minimal JSON-Schema check for the subset api.yaml uses. Returns problems, empty when valid. */
    private fun validate(v: JsonElement, s0: Map<String, Any?>, at: String = "$"): List<String> {
        val s = resolve(s0)
        val out = mutableListOf<String>()
        (s["enum"] as? List<*>)?.let { e ->
            if (v !is JsonPrimitive || v.content !in e.map { it.toString() }) out += "$at: $v not in $e"
        }
        when (s["type"]) {
            "object" -> {
                if (v !is JsonObject) return listOf("$at: expected object")
                val props = (s["properties"] as? Map<String, Map<String, Any?>>) ?: emptyMap()
                (s["required"] as? List<String>)?.forEach { if (it !in v) out += "$at.$it: required but missing" }
                val extra = s["additionalProperties"] as? Map<String, Any?>
                for ((k, x) in v) {
                    val ps = props[k] ?: extra
                    if (ps == null) out += "$at.$k: not in schema (server rejects unknown fields)"
                    else if (x !is JsonNull) out += validate(x, ps, "$at.$k")
                }
            }
            "array" -> {
                if (v !is JsonArray) return listOf("$at: expected array")
                (s["maxItems"] as? Int)?.let { if (v.size > it) out += "$at: ${v.size} items > maxItems $it" }
                v.forEachIndexed { i, x -> out += validate(x, s["items"] as Map<String, Any?>, "$at[$i]") }
            }
            "string" -> if (v !is JsonPrimitive || !v.isString) out += "$at: expected string" else {
                (s["maxLength"] as? Int)?.let { if (v.content.length > it) out += "$at: longer than $it" }
                (s["minLength"] as? Int)?.let { if (v.content.length < it) out += "$at: shorter than $it" }
            }
            "number" -> if (v !is JsonPrimitive || v.isString || v.doubleOrNull == null) out += "$at: expected number" else {
                val x = v.doubleOrNull!!
                (s["maximum"] as? Number)?.let { if (x > it.toDouble()) out += "$at: $x > maximum $it" }
                (s["minimum"] as? Number)?.let {
                    if (s["exclusiveMinimum"] == true && x <= it.toDouble()) out += "$at: $x <= exclusive minimum $it"
                    else if (x < it.toDouble()) out += "$at: $x < minimum $it"
                }
            }
            "integer" -> if (v !is JsonPrimitive || v.isString || v.content.toLongOrNull() == null) out += "$at: expected integer"
            "boolean" -> if (v !is JsonPrimitive || v.isString || v.booleanOrNull == null) out += "$at: expected boolean"
        }
        return out
    }

    /** A schema-valid sample: only required fields, or every field. */
    private fun sample(s0: Map<String, Any?>, all: Boolean): JsonElement {
        val s = resolve(s0)
        (s["enum"] as? List<*>)?.let { return JsonPrimitive(it.first().toString()) }
        return when (s["type"]) {
            "object" -> {
                val props = (s["properties"] as? Map<String, Map<String, Any?>>) ?: emptyMap()
                val req = (s["required"] as? List<String>) ?: emptyList()
                JsonObject(props.filterKeys { all || it in req }.mapValues { (_, p) -> sample(p, all) })
            }
            "array" -> JsonArray(listOf(sample(s["items"] as Map<String, Any?>, all)))
            "number" -> JsonPrimitive(1.5)
            "integer" -> JsonPrimitive(900)
            "boolean" -> JsonPrimitive(true)
            else -> JsonPrimitive(if (s["format"] == "uuid") "00000000-0000-4000-8000-000000000000" else "x")
        }
    }

    private inline fun <reified T> checkRequest(path: String, method: String, body: T) {
        val json = NetJson.encodeToJsonElement(serializer<T>(), body)
        val problems = validate(json, requestSchema(path, method))
        assertTrue(problems.isEmpty(), "$method $path request: $problems\n$json")
    }

    private fun <T> checkResponse(path: String, method: String, ser: KSerializer<T>) {
        val s = responseSchema(path, method)
        for (all in listOf(false, true)) {
            val json = sample(s, all)
            runCatching { NetJson.decodeFromJsonElement(ser, json) }
                .onFailure { fail("$method $path: app cannot read a valid response (${if (all) "all" else "required"} fields) $json: ${it.message}") }
        }
        // A server may also send optional fields as explicit null.
        val withNulls = JsonObject(sample(s, true).jsonObject.mapValues { (k, v) ->
            if (k in ((s["required"] as? List<*>) ?: emptyList<Any>())) v else JsonNull
        })
        runCatching { NetJson.decodeFromJsonElement(ser, withNulls) }
            .onFailure { fail("$method $path: app cannot read optional fields sent as null: ${it.message}") }
    }

    private val uuid = "6abf5a43-0cc2-4520-a433-3156d87d55ac"
    private val hash = "a".repeat(64)

    @Test fun authRequestsMatch() {
        checkRequest("/auth/device", "post", DeviceAuthRequest("ch", "pk", listOf("leaf", "root")))
        checkRequest("/auth/refresh", "post", RefreshRequest("rt"))
    }

    @Test fun riskCheckRequestMatchesForEveryLevelAndMethod() {
        for (level in listOf("NONE", "NUDGE", "HARD", "TRUSTED_CONTACT")) for (m in listOf("upi_intent", "checkout")) {
            checkRequest("/risk-check", "post", RiskCheckRequest(DecisionDto(level, 0.4, listOf("F_NEW_PAYEE")), m, 499.5, hash, true))
        }
    }

    @Test fun paymentResultRequestMatches() {
        checkRequest("/payments/{id}/result", "post", PaymentResultRequest("success", "REF1"))
        checkRequest("/payments/{id}/result", "post", PaymentResultRequest("failure"))
    }

    @Test fun deleteDeviceEndpointExistsInTheContract() {
        val del = op("/device", "delete")
        assertTrue((del["responses"] as Map<Any?, Any?>).keys.any { it.toString() == "204" })
    }

    @Test fun trustedContactAcceptFlowMatchesTheContract() {
        checkRequest("/trusted-contact/respond", "post", com.satark.app.net.TrustedRespondRequest(uuid, "accept"))
        checkRequest("/trusted-contact/respond", "post", com.satark.app.net.TrustedRespondRequest(uuid, "decline"))
        checkResponse("/trusted-contact/respond", "post", TrustedContactResponse.serializer())
        checkResponse("/trusted-contact/requests", "get", com.satark.app.net.TrustedRequestsResponse.serializer())
        op("/trusted-contact/{trusted_device_id}", "delete")
    }

    @Test fun paymentDecisionRequestMatches() {
        checkRequest("/payments/{id}/decision", "post", PaymentDecisionRequest("approve"))
        checkRequest("/payments/{id}/decision", "post", PaymentDecisionRequest("block"))
    }

    @Test fun alertSignatureAndTrustedContactRequestsMatch() {
        checkRequest("/alert", "post", AlertRequest(uuid, "alarm", listOf("F_NEW_PAYEE"), paymentId = uuid))
        checkRequest("/alert", "post", AlertRequest(uuid, "alarm", listOf("RULE_SIDELOAD_DURING_CALL")))
        checkRequest("/alert", "post", AlertRequest(uuid, "long_session"))
        checkRequest("/signature", "post", SignatureRequest("payment_score", mapOf("new_payee" to 1.0, "is_p2p" to 0.0)))
        checkRequest("/trusted-contact", "post", TrustedContactRequest(uuid, "fcm-token"))
    }

    @Test fun appReadsEveryResponse() {
        checkResponse("/auth/challenge", "post", ChallengeResponse.serializer())
        checkResponse("/auth/device", "post", TokenResponse.serializer())
        checkResponse("/auth/refresh", "post", TokenResponse.serializer())
        checkResponse("/trusted-contact", "post", TrustedContactResponse.serializer())
        checkResponse("/risk-check", "post", RiskCheckResponse.serializer())
        checkResponse("/payments/{id}", "get", PaymentResponse.serializer())
        checkResponse("/payments/{id}/result", "post", PaymentResponse.serializer())
        checkResponse("/payments/{id}/decision", "post", PaymentResponse.serializer())
        checkResponse("/alert", "post", Accepted.serializer())
        checkResponse("/signature", "post", Accepted.serializer())
    }

    @Test fun validatorCatchesBadBodies() {
        // Guards the guard: the checks above must be able to fail.
        val s = requestSchema("/risk-check", "post")
        val bad = NetJson.encodeToJsonElement(RiskCheckRequest.serializer(),
            RiskCheckRequest(DecisionDto("MAYBE", 0.0, listOf("a", "b", "c", "d")), "cash", 1.0, hash, true))
        val problems = validate(bad, s)
        assertTrue(problems.any { "MAYBE" in it } && problems.any { "cash" in it } && problems.any { "maxItems" in it }, "$problems")
        assertTrue(validate(JsonObject(mapOf("surprise" to JsonPrimitive(1))), s).any { "not in schema" in it })
    }
}
