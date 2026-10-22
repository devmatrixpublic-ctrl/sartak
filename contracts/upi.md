# UPI URI handling (owner: M1)

Consumers: M2 (event mapping), M3 (`/risk-check`, `/payments/{id}/result`).

## `upi://pay` parameters
| Param | Use |
|---|---|
| `pa` | Payee VPA (`name@handle`). Required. Hashed before storage or sending; never sent raw. |
| `pn` | Payee name. Display only; never stored or sent. |
| `am` | Amount in rupees, decimal, max 2 places, > 0. Missing -> user types the amount. Malformed -> URI rejected. |
| `cu` | Currency. Absent or `INR` accepted; anything else rejected. |
| `tn` | Note. Display only. |
| `mc` | Merchant code. Non-blank -> P2M, otherwise P2P (`is_p2p = true`). |

Rejected: non-`upi` scheme, host other than `pay`, missing/invalid `pa`, bad `am`/`cu`. Parameter names are case-insensitive; values are URL-decoded.

## Hashing
`payee_hash = lowercase hex SHA-256( install_salt || lowercase(trim(pa)) )`, 64 hex chars (matches `schema.json` `payee_id`). The salt is a random 32-byte value generated once per install and kept in encrypted storage.

## Event mapping (`schema.json`)
- New payee (hash not in `known_payee`) -> `NEW_PAYEE{payee_id}` emitted before the attempt.
- `PAYMENT_ATTEMPT{payee_id, amount_inr, payment_type: P2P|P2M, payee_is_new, source: qr|manual}`.

## Returned result (`upi_intent`)
Intent result extras (any may be absent): `Status` (`SUCCESS`/`FAILURE`/`SUBMITTED`, case-insensitive), `txnId`, `txnRef`, `responseCode`. Mapped to `POST /payments/{id}/result` `{status: success|failure, txn_ref}`. `SUBMITTED`, unknown or no result -> nothing posted (server marks `no_result` on timeout). Always app-reported, never verified.
