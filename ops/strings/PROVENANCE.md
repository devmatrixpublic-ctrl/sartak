# Where the reason strings came from

| File | Language | How it was produced | Status |
|---|---|---|---|
| `reason_strings_en.json` | English | Written by hand (Sarvam-30B access was not available). | Reviewed in the repo. |
| `reason_strings_hi.json` | Hindi | **Machine-drafted** by Claude (an AI model) on 2026-10-24, from the English sentences. Sarvam-30B was **not** used: there is no access to it from this build environment. | **Needs native review.** Not checked by a Hindi speaker; do not claim accuracy beyond "machine-drafted". |

Both are checked by `validate_strings.py`: every reason code has a string in each language, none contains a link, and none
mentions a PIN or OTP (in English or in the Hindi spellings of those words). The check cannot judge whether the Hindi reads
naturally or means the same thing; only a native speaker can.

Only the warning reasons are translated. The rest of the app's screens are still English.
