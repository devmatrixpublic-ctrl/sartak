# Progress (branch feat/small-features, stacked on feat/app-contact-approval)

Builds: JDK 21 (`~/.gradle/jdks/eclipse_adoptium-21-amd64-windows.2`) and `ANDROID_HOME=~/AppData/Local/Android/Sdk`.

## Done
1-11 as listed in the earlier summary (Hard-screen buttons, override, amount_band, dial contact, LOG + shadow mode,
string validator, 7-day purge, 300 ms timeout, consent + delete, read-aloud, repeat-alert merging).
Closing work: `DELETE /device` (server erases its rows; the app's Delete my data calls it), alert counters and a debug-only
shadow switch in Protection settings, item 14 timing test (max 0.2 ms per event), item 12 as a red-team masking test and
report (`detector/experiments/red_team_masking.md`).

## Not done, on purpose
- Item 13, hard-negative vectors: adding vectors changes the frozen 36 and needs the detector re-freeze (tag, held-out
  hash). The existing SatarkSim hard negatives are already reported in `detector/detector_report.md`. Needs your decision.
- Item 12 as written ("red-team masking in sensitivity.py"): that script needs the raw Kaggle/NPCI files, which are not in
  the repo. The masking analysis was done on the golden sessions instead.
- Roadmap detector-side pillars (Hawkes/GBDT, new sensors, adaptive conformal, federated updates): they change the frozen model.

## Needs a device or account (cannot be done here)
- Room v1 -> v2 upgrade on a phone/emulator (no emulator image is installed).
- Everything on real phones, Firebase push, Razorpay, Render, real attestation chains (see README "Status").

## Merge order
`feat/app-contact-approval` first, then `feat/small-features`. `gh` is not installed here, so PRs are opened from the GitHub links.
