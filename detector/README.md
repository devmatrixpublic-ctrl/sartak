# detector (M2): on-device scam detector

Kotlin/JVM library plus Python export tools. Owner: M2.

| Path | What |
|---|---|
| `src/main/kotlin/com/satark/detector/` | `Detector`, `SessionState`, `FeatureExtractor` (16 features), `Scorer`, `ConformalThreshold`, `Rules`, `Baseline`, `Explainer` |
| `src/main/resources/model.json` | trained weights, scaler, per-cohort conformal thresholds, constants, watch-list (generated) |
| `tools/export_model.py` | retrains the reference, writes `model.json`, proves the export is lossless (<= 1e-9), writes golden test files |
| `tools/test_schema.py`, `tools/upi_mapping.py` | contract tests for `contracts/schema.json` and the `upi://pay` mapping |
| `reference/` | the Python reference detector and SatarkSim generator (the executable spec) |
| `detector_report.md` | results, honest caveats, open items |
| `../contracts/schema.json`, `../contracts/reason_codes.json` | contracts owned by M2 |
| `../data/satarksim/` | SatarkSim data, the 36 test vectors (`detector_test_vectors_*.csv`) |

## API

```kotlin
val model = ModelConfig.loadBundled()
val detector = Detector(model, ageBand = "36-59", baseline = Baseline.coldStart(model))
val decision = detector.onEvent(event)      // events in timestamp order; Decision{level, score, reasons}
detector.onTick(nowMs)                      // periodically: lets a 2 h unknown video call alarm without a new event
detector.finish()                           // at session end
baseline.observe(amountInr)                 // only for payments that COMPLETED, never for held attempts
```

Deterministic: no wall-clock reads, no randomness. `age_band` only selects the alarm threshold; it is never a feature.
Levels emitted: `NONE`, `HARD`. Reasons are stable codes from `contracts/reason_codes.json` (1-3 per alarm).

## Commands (from repo root)

```bash
python detector/tools/export_model.py            # retrain + export model.json + golden files
python -m pytest detector/tools/test_schema.py   # schema / UPI mapping contract tests
cd detector && gradle test                       # 36 vectors, 732-session parity, fuzz, explainer, baseline
```

If Maven Central answers 429, retry with `gradle --max-workers=1 test`; Gradle keeps what it already downloaded.
