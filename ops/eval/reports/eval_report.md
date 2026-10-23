# M4 evaluation run (SatarkSim v2, validation split)

Simulated data: this shows the logic separates the simulated playbooks, not real-world accuracy.

**Gate: FAIL** (recall >= 93% and false alarms <= 0.1%, point estimates; thresholds calibrated at alpha = 0.08%)

- FAIL: fairness: false-alarm rate max/min across age band is undefined (a cohort has none) (limit 1.5)
- FAIL: fairness: false-alarm rate max/min across activity tier is undefined (a cohort has none) (limit 1.5)
- FAIL: fairness: false-alarm rate max/min across call-state availability is undefined (a cohort has none) (limit 1.5)

| Metric | Result | 95% CI |
|---|---|---|
| Scam recall | 538/578 = 93.1% | 90.7% - 95.0% |
| Interdicted before first payment | 485/578 = 83.9% | |
| False alarms (legit) | 7/9887 = 0.071% | 0.028% - 0.146% |
| Median lead time | 20.2 min | |
| Naive baseline | recall 53.1%, false alarms 3.9% | |

Matches committed `detector/detector_report.md`: **yes** (shipped: 538/578 scams, 7/9887 false alarms).

## Input hashes (SHA-256)

- `data/satarksim/detector_test_vectors_events.csv`: `b80245f1687b42fb98a19672d007cc7de83afbc6c46faed26c3b0041f38c069b`
- `data/satarksim/detector_test_vectors_expected.csv`: `a6b1e33ca630e6488978073528c983eee8d03aa5e4b976eeffcb126d9df94158`
- `data/satarksim/detector_test_vectors_users.csv`: `a3fbb1feee7b74fe0ad2cfe5fd3a96e142d620beda6888bae5dbafd46bec6eed`
- `data/satarksim/satarksim_events.csv`: `c272e332273efc1818c485575f12dce8cac49c2e6759414f930f46c7d9f35fcc`
- `data/satarksim/satarksim_sessions.csv`: `930e2175181547faf323bbffe87a86d34c8174b13db7258a9fca42b22a3d963d`
- `data/satarksim/satarksim_users.csv`: `6a56c9b4f9af16e55e2126d2dd8c06cdef061739a57da7477fea74f6375fc94a`
- `data/satarksim/params.json`: `9849b9c324eeb080e5101b568b4d346bb6bf222ee4f9096d57811db35ca43721`
- `detector/reference/params.json`: `db9e92c706dfee9a1237192a06e0a11bdad92ffea7602b12a58b1e6321d4ed51`
- `detector/reference/satark_detector.py`: `2510fc108769365542083aaea33915c7d37640486c93093b8a72246752d89a51`

BAF and IEEE-CIS are run locally only; see `ops/eval/input_hashes.json` for their recorded hashes.
