# M4 evaluation run (SatarkSim v2, validation split)

Simulated data: this shows the logic separates the simulated playbooks, not real-world accuracy.

**Gate: FAIL** (recall >= 93% and false alarms <= 0.1%, point estimates, alpha = 0.1%)

- FAIL: false-alarm rate 0.111% is above the 0.1% target

| Metric | Result | 95% CI |
|---|---|---|
| Scam recall | 540/578 = 93.4% | 91.1% - 95.3% |
| Interdicted before first payment | 487/578 = 84.3% | |
| False alarms (legit) | 11/9887 = 0.111% | 0.056% - 0.199% |
| Median lead time | 19.1 min | |
| Naive baseline | recall 53.1%, false alarms 3.9% | |

Matches committed `detector/detector_report.md`: **yes** (shipped: 540/578 scams, 11/9887 false alarms).

## Input hashes (SHA-256)

- `data/satarksim/detector_test_vectors_events.csv`: `b80245f1687b42fb98a19672d007cc7de83afbc6c46faed26c3b0041f38c069b`
- `data/satarksim/detector_test_vectors_expected.csv`: `a6b1e33ca630e6488978073528c983eee8d03aa5e4b976eeffcb126d9df94158`
- `data/satarksim/detector_test_vectors_users.csv`: `a3fbb1feee7b74fe0ad2cfe5fd3a96e142d620beda6888bae5dbafd46bec6eed`
- `data/satarksim/satarksim_events.csv`: `c272e332273efc1818c485575f12dce8cac49c2e6759414f930f46c7d9f35fcc`
- `data/satarksim/satarksim_sessions.csv`: `930e2175181547faf323bbffe87a86d34c8174b13db7258a9fca42b22a3d963d`
- `data/satarksim/satarksim_users.csv`: `6a56c9b4f9af16e55e2126d2dd8c06cdef061739a57da7477fea74f6375fc94a`
- `data/satarksim/params.json`: `9849b9c324eeb080e5101b568b4d346bb6bf222ee4f9096d57811db35ca43721`
- `detector/reference/params.json`: `1d04bba931a25a15800b3c6edfd39a4f0fdf27975015665c083421b7cd9ad3fe`
- `detector/reference/satark_detector.py`: `311f1ad0ceb7e6bdb6518cb5e264e08b16bbb318179eca4799b7cd533e1f07fc`

BAF and IEEE-CIS are run locally only; see `ops/eval/input_hashes.json` for their recorded hashes.
