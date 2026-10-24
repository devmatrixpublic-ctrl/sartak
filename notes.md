# Satark: working notes

## Still to build
- [ ] **Login page.** Not started. Needs a decision first: what a person signs in with (phone number and OTP, or a UPI-linked
      identity), and whether sign-in stays optional (today the app registers the device silently and works without any login).
      The Stitch reference screens are in `~/Downloads/stitch_sarvam_inspired_unique_interface_design*.zip`; use the same theme
      as the rest of the app (`ui/theme/Theme.kt`).
- [ ] **WhatsApp message flags** (agreed design): read WhatsApp notification text on the phone through notification access,
      match a short keyword list, ignore saved contacts and group chats, store only the time and category, and never let a
      message change a payment decision. Needs a "WhatsApp messages: Off, needs notifications" status row and an updated
      consent and privacy text.

## Decisions waiting
- **No server on a real phone.** `BASE_URL` defaults to `10.0.2.2:8000` (emulator only). On the iQOO every payment check falls
  back to offline, trusted-contact alerts are only queued, and the test checkout cannot work. Deploy the server and build with
  `-PsatarkBaseUrl=...`, or demo in offline mode and say so.
- **Rs 25,000 hold threshold costs 8 more genuine sessions held in 9,887** (false alarms 0.071% to 0.152%, over the deck's 0.100%
  target; `ops/eval/reports/high_value_rule.md`). Chosen because "Continue anyway" always lets the person go on. Rs 30,000 would hold
  14 extra scams for 6 extra false holds; the threshold is one constant (`HighValueNewPayee.THRESHOLD_INR`).
- The same amount to the same payee again within 2 minutes counts as a retry, not a second piece (`CumulativeNewPayee.RETRY_MS`).
- **Trusted-contact push** needs a Firebase project, `app/google-services.json`, and the server credentials.

## Done recently
- A new payee for Rs 25,000 or more is held for every age band while an unknown call or video is open or ended within 30 minutes
  (`HighValueNewPayee`); the nudge also covers the 30 minutes after a call. Closes the "payment after the call ended" gap and the 60+ gap.
- Continue anyway releases the held payment and opens the UPI app.
- Nudge has no cooldown; no automatic 15-minute pause after a hold ("Hold payment 30 minutes" is still offered).
- Warning for 3 texts from strangers in 10 minutes (notification only).
- Stranger texts no longer reach the detector.
- Developer tools hidden behind seven taps on the Satark mark (debug builds only), with a "Reset demo state" button.
- History shows "Payment checked, nothing unusual" for ordinary checks.

## To check on a phone
- Reboot and app-update restart of protection (iQOO needs autostart and unrestricted battery).
- Usage-access fix on the iQOO, the stranger-text burst warning, "Continue anyway", and the split-payment hold.
