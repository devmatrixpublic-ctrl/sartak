package com.satark.app.net

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path

// Hand-written mirror of contracts/api.yaml (the plan calls for generation; the schemas are small and the contract
// test in ApiContractTest checks every path and field name against the yaml so drift is caught).

@Serializable class Empty
@Serializable data class ChallengeResponse(val challenge: String, @SerialName("expires_at") val expiresAt: String)
@Serializable data class DeviceAuthRequest(
    val challenge: String,
    @SerialName("public_key") val publicKey: String,
    @SerialName("attestation_chain") val attestationChain: List<String>,
    val role: String = "device",
)
@Serializable data class RefreshRequest(@SerialName("refresh_token") val refreshToken: String)
@Serializable data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("token_type") val tokenType: String,
    @SerialName("expires_in") val expiresIn: Int,
    @SerialName("device_id") val deviceId: String,
)
@Serializable data class TrustedContactRequest(
    @SerialName("trusted_device_id") val trustedDeviceId: String,
    @SerialName("fcm_token") val fcmToken: String,
)
@Serializable data class TrustedContactResponse(val linked: Boolean, val status: String? = null) // pending | accepted | revoked
@Serializable data class TrustedRequest(@SerialName("owner_device_id") val ownerDeviceId: String)
@Serializable data class TrustedRequestsResponse(val requests: List<TrustedRequest>)
@Serializable data class TrustedRespondRequest(@SerialName("owner_device_id") val ownerDeviceId: String, val decision: String) // accept | decline
@Serializable data class DecisionDto(val level: String, val score: Double, val reasons: List<String>)
@Serializable data class RiskCheckRequest(
    val decision: DecisionDto,
    val method: String, // upi_intent | checkout
    val amount: Double,
    @SerialName("payee_hash") val payeeHash: String,
    @SerialName("is_p2p") val isP2p: Boolean,
    /** "Continue anyway": release the caller's own held [paymentId] (server: held -> allowed_by_user). */
    val override: Boolean = false,
    @SerialName("payment_id") val paymentId: String? = null,
)
@Serializable data class RiskCheckResponse(
    val decision: String, // HOLD | ALLOW
    @SerialName("payment_id") val paymentId: String,
    @SerialName("order_id") val orderId: String? = null,
    @SerialName("hold_reason") val holdReason: String? = null,
)
@Serializable data class PaymentResponse(
    val id: String,
    val method: String,
    val state: String,
    /** Coarse band (lt_500 .. gt_2l); the server no longer keeps the rupee amount. */
    @SerialName("amount_band") val amountBand: String,
    @SerialName("payee_hash") val payeeHash: String,
    @SerialName("razorpay_order_id") val razorpayOrderId: String? = null,
    @SerialName("hold_reason") val holdReason: String? = null,
    @SerialName("user_override") val userOverride: Boolean? = null,
    @SerialName("reported_status") val reportedStatus: String? = null,
    @SerialName("reported_txn_ref") val reportedTxnRef: String? = null,
)
@Serializable data class PaymentResultRequest(val status: String, @SerialName("txn_ref") val txnRef: String? = null)
@Serializable data class PaymentDecisionRequest(val decision: String) // approve | block
@Serializable data class AlertRequest(
    @SerialName("device_id") val deviceId: String,
    val type: String, // alarm | long_session
    val reasons: List<String> = emptyList(),
    /** A held payment the trusted contact may approve or block. */
    @SerialName("payment_id") val paymentId: String? = null,
)
@Serializable data class Accepted(val accepted: Boolean)
@Serializable data class SignatureRequest(@SerialName("pattern_id") val patternId: String, val features: Map<String, Double>)
@Serializable data class ApiError(val code: String, val message: String)
/** M4's dev-token stub body (hidden from api.yaml; contracts/auth.md "Dev token stub"). */
@Serializable data class DevTokenRequest(@SerialName("device_id") val deviceId: String)

/** Header that marks a call as safe to retry (idempotent GETs, /alert, /signature). */
const val RETRY_HEADER = "X-Satark-Retry"

interface SatarkApi {
    @POST("auth/challenge") suspend fun challenge(@Body b: Empty = Empty()): ChallengeResponse
    @POST("auth/device") suspend fun registerDevice(@Body b: DeviceAuthRequest): TokenResponse
    @POST("auth/refresh") suspend fun refresh(@Body b: RefreshRequest): TokenResponse
    @POST("auth/dev-token") suspend fun devToken(@Body b: DevTokenRequest): TokenResponse
    @POST("trusted-contact") suspend fun trustedContact(@Body b: TrustedContactRequest): TrustedContactResponse
    @retrofit2.http.GET("trusted-contact/requests") suspend fun trustedRequests(): TrustedRequestsResponse
    @POST("trusted-contact/respond") suspend fun trustedRespond(@Body b: TrustedRespondRequest): TrustedContactResponse
    @DELETE("trusted-contact/{id}") suspend fun removeTrustedContact(@Path("id") id: String): TrustedContactResponse
    @POST("risk-check") suspend fun riskCheck(@Body b: RiskCheckRequest): RiskCheckResponse
    @GET("payments/{id}") suspend fun payment(@Path("id") id: String, @Header(RETRY_HEADER) retry: String = "1"): PaymentResponse
    @POST("payments/{id}/result") suspend fun paymentResult(@Path("id") id: String, @Body b: PaymentResultRequest): PaymentResponse
    @POST("payments/{id}/decision") suspend fun paymentDecision(@Path("id") id: String, @Body b: PaymentDecisionRequest): PaymentResponse
    @DELETE("device") suspend fun deleteDevice(): retrofit2.Response<Unit>
    @POST("alert") suspend fun alert(@Body b: AlertRequest, @Header(RETRY_HEADER) retry: String = "1"): Accepted
    @POST("signature") suspend fun signature(@Body b: SignatureRequest, @Header(RETRY_HEADER) retry: String = "1"): Accepted
}
