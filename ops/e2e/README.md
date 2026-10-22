# Cross-module end-to-end run

`python ops/e2e/run_e2e.py` (or `RUN_E2E=1 pytest ops/e2e`) proves the modules work **together**, with nothing between the
detector and the server mocked:

1. `detector/src/test/.../E2EDecisionsExport.kt` runs the real Kotlin detector (bundled `model.json`) over hand-built scam and
   clean scenarios plus two real SatarkSim vectors, asserts each decision, and writes `detector/build/e2e/decisions.json`.
2. The script applies the Alembic migrations to an **empty** database, starts the real FastAPI server, and walks the app's flow
   with those decisions: dev-token registration, trusted-contact link, `/risk-check` (HARD -> HOLD, clean -> ALLOW),
   `upi_intent` hand-off and app-reported result, `checkout` with a signed Razorpay webhook (forged, duplicate and stale events),
   `/alert`, `/signature` with the detector's own 16 feature names, and attacks (no token, IDOR, mass assignment, oversize body).

57 checks. It does **not** cover the Android app, a phone, real Razorpay/Firebase, Render or real Key Attestation (those
need hardware, credentials or a deployed domain). `--skip-gradle` reuses an existing `decisions.json`.

What it found the first time it ran: `/risk-check` and `/payments/*` returned `"order_id": null` where the contract says the key
is absent, and `api.yaml` promised 400 for `/signature` validation errors while the server (like every endpoint) returns 422.
Both fixed; `server/tests/test_contract_shapes.py` pins them.
