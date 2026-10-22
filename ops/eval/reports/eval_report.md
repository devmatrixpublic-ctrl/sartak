# M4 evaluation run (SatarkSim v2, validation split)

Simulated data: this shows the logic separates the simulated playbooks, not real-world accuracy.

**Gate: PASS** (recall >= 93% and false alarms <= 0.1%, point estimates; thresholds calibrated at alpha = 0.08%)

- both targets met

| Metric | Result | 95% CI |
|---|---|---|
| Scam recall | 538/578 = 93.1% | 90.7% - 95.0% |
| Interdicted before first payment | 485/578 = 83.9% | |
| False alarms (legit) | 7/9887 = 0.071% | 0.028% - 0.146% |
| Median lead time | 20.2 min | |
| Naive baseline | recall 53.1%, false alarms 3.9% | |

Matches committed `detector/detector_report.md`: **yes** (shipped: 538/578 scams, 7/9887 false alarms).

## Input hashes (SHA-256)

- `data/satarksim/detector_test_vectors_events.csv`: `b6e5a7a57118a5aeae0b84560a91a72c4fb5d8d7242ac4151f0f9ee1865ba308`
- `data/satarksim/detector_test_vectors_expected.csv`: `0c4b18483158ac801ec0d5f22a628854fda56ad1b6fa768adf64ad61771fddca`
- `data/satarksim/detector_test_vectors_users.csv`: `8beefdb6d77f4763f18d6b10f99554e3d81da0bd635b1dcddc72fb1d0177cdd6`
- `data/satarksim/satarksim_events.csv`: `29fa799a1c332bf7bf9e3e7c8f846d9345f075dc631c6da97644389f8bf9ceaa`
- `data/satarksim/satarksim_sessions.csv`: `50a351b3e56f7378738887f27ec25f55cdc3016472dc955f4c96f8e080682de1`
- `data/satarksim/satarksim_users.csv`: `0f4f61176851abbb9b3ce6470717ee4a9a2087b07f209d14677e2f560df02c75`
- `data/satarksim/params.json`: `26e5a787504d4c222e49c9c4154e526ec94178364ebcd24e75966e3c83543d65`
- `detector/reference/params.json`: `e0630e4ad4cca7bd6f96dd39ed62c988773b677297ee4a1ae24deaff5222b39f`
- `detector/reference/satark_detector.py`: `97f06dd0e883605c4b06de5efbcc65bb98d0dace33d4f239e5f9b384a5a9ac76`

BAF and IEEE-CIS are run locally only; see `ops/eval/input_hashes.json` for their recorded hashes.
