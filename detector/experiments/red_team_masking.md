# Red team: hiding a signal

What happens to detection if one signal source is hidden (an attacker blocks it, a phone maker withholds it, or the person
denies the permission)? Replayed with `detector/src/test/kotlin/com/satark/detector/RedTeamMaskingTest.kt` on the golden
sessions (`detector/src/test/resources/golden/`: 170 scam and 562 legitimate sessions). The unmasked row equals the frozen
reference decisions; the test fails if it does not.

| Signal hidden | Scam recall | False alarms on legitimate sessions |
|---|---|---|
| none (baseline) | 91.2% | 0.71% |
| call state | 75.3% | 0.36% |
| video state | 81.2% | 0.71% |
| install events | 81.8% | 0.71% |
| app foreground | 91.2% | 0.71% |
| call, video and installs together | 67.1% | 0.36% |

Reading it:
- **Hiding call state costs the most single-signal recall (about 16 points).** Unknown-call state is the strongest cue, so the
  "signal unavailable" banner in the app matters, and so does the fallback to amount, payee and install cues.
- **Hiding all three leaves about two thirds of scams still caught**, from the payment cues alone (new payee, amount, repeat).
- **App foreground adds nothing here**: hiding it changes no decision on this set.
- **No mask raises false alarms.** Removing a risk signal can only lower the score, which is the intended direction: a scammer
  who talks a victim into blocking a signal makes detection weaker, never noisier, so the app must warn when a source is unavailable.

Caveats: the golden set is 23% scams (a test set, not real traffic); the baseline here (0.71% false alarms) is higher than the
validation figure in `detector_report.md` (0.071%) because the golden set deliberately over-represents hard cases. This is a
robustness picture on simulated data, not a measured real-world result. It does not re-freeze anything: the detector, the model
and the 36 vectors are unchanged.
