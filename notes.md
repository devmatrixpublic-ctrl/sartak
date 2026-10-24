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

## Login and trusted-contact notification (decided in discussion, not built)
- Sign-up keeps **phone number + OTP** (chosen over a no-OTP profile). Needs an SMS provider; a Firebase project would serve both OTP and push.
  The onboarding line "Satark never asks for your PIN or OTP" must be reworded (we send one sign-in code; never a bank OTP or UPI PIN),
  and the sign-in SMS must not count as a "stranger text". Link a trusted contact by phone number (server keeps a keyed hash, not the number).
- **Names:** the protected person sees their contact's name; the contact's notification says who may be being scammed
  ("<name> may be being scammed"). Keep the amount and payee off the lock screen; show them only after the contact opens it.
- When a payment is held, the accepted trusted contact gets a push on their phone (built on the server and in the app, only tested with a
  stub push client). Needs: a Firebase project and `app/google-services.json`, server credentials, a server the phones can reach, and a
  second device (the emulator can be the contact if its image has Google Play services).

## Built, to try on the iQOO
- **Turning protection off waits 30 minutes** and tells the trusted contact at once; **removal guard** (device admin, no powers) stops a quiet
  uninstall and tells the contact when it is switched off. For a live demo build with a short wait:
  `./gradlew :app:assembleDebug -PsatarkProtectionOffWaitMin=1` (debug builds only). Server: three new alert types (`protection_off_requested`,
  `protection_off`, `removal_guard_off`) in `contracts/api.yaml`, `server/app/alerts/service.py`, with tests.
- Verified end to end on the emulator with a local dev server and a second registered device as the contact: all three alerts reached the contact
  (push is the stub client; real push still needs Firebase). To confirm on the iQOO: that Funtouch OS also blocks uninstall while the guard is on.
- Not covered: revoking permissions or force-stopping Satark; the delete-data alert is sent once, directly (lost if the phone is offline at that moment).

## Found testing on the iQOO (fixed)
- The nudge was a banner drawn in Satark while the payment handed off to the UPI app in the same second, so on a real phone the chooser
  covered it. It is now a step before the server check and the hand-off (`PayOutcome.Nudged`).
- A repeat of the same kind of alert within an hour was folded away completely, so a second Stop on the same day showed only the small
  "Payment on hold" card. A held payment the person has just tried now always shows the full Stop screen; only the notification and the
  trusted-contact push stay once per hour.
- **Open question:** after a Stop on a new payee, a smaller amount to the SAME payee is also stopped, because the stopped amount counts in the
  running total (split-payment guard) and the detector's own repeat-to-payee signal. Letting it through would need stopped, unpaid attempts to
  stop counting; that weakens the guard against "try a smaller amount". Not changed; decide.
- The iQOO drops off USB often; the tunnel to the laptop server goes with it ("can't reach Satark"). Wireless debugging would avoid that.

## Decisions waiting
- **No server on a real phone.** `BASE_URL` defaults to `10.0.2.2:8000` (emulator only). On the iQOO every payment check falls
  back to offline, trusted-contact alerts are only queued, and the test checkout cannot work. Deploy the server and build with
  `-PsatarkBaseUrl=...`, or demo in offline mode and say so.
- **Rs 25,000 hold threshold costs 8 more genuine sessions held in 9,887** (false alarms 0.071% to 0.152%, over the deck's 0.100%
  target; `ops/eval/reports/high_value_rule.md`). Chosen because "Continue anyway" always lets the person go on. Rs 30,000 would hold
  14 extra scams for 6 extra false holds; the threshold is one constant (`HighValueNewPayee.THRESHOLD_INR`).
- **Rs 10,000 for under-22s: no support in the simulator.** The whole 18-35 band at Rs 10,000 adds 0 scams and 12 genuine holds
  (0.152% to 0.273%, upper bound). It rests on the assumption about students; one constant switches it off
  (`HighValueNewPayee.YOUNG_THRESHOLD_INR`). Decide whether to keep it for the demo.
- The same amount to the same payee again within 2 minutes counts as a retry, not a second piece (`CumulativeNewPayee.RETRY_MS`).
- **Trusted-contact push** needs a Firebase project, `app/google-services.json`, and the server credentials.

## Done recently
- A new payee for Rs 25,000 or more is held for every age band while an unknown call or video is open or ended within 30 minutes
  (`HighValueNewPayee`); the nudge also covers the 30 minutes after a call. Closes the "payment after the call ended" gap and the 60+ gap.
- **Fingerprint lock** (`ui/lock`): Continue anyway, turning protection off, trusted-contact changes, age change and delete-data need a
  matched fingerprint (strong biometric only when one is enrolled). A phone with no fingerprint (no sensor, or none enrolled) falls back to
  its screen-lock PIN; with neither, setup cannot finish. Verified on the emulator: wrong finger, wrong PIN and cancel release nothing; the
  right finger releases the payment to the UPI app; the PIN path shows "On: screen-lock PIN" and "It works".
- Optional age on the Protection screen (kept on the phone, never sent). Under 22 the same hold starts at Rs 10,000. The app never asked
  for an age before, so the detector always used the pooled threshold; now an age also selects its cohort threshold.
- Continue anyway releases the held payment and opens the UPI app.
- Nudge has no cooldown; no automatic 15-minute pause after a hold ("Hold payment 30 minutes" is still offered).
- Warning for 3 texts from strangers in 10 minutes (notification only).
- Stranger texts no longer reach the detector.
- Developer tools hidden behind seven taps on the Satark mark (debug builds only), with a "Reset demo state" button.
- History shows "Payment checked, nothing unusual" for ordinary checks.

## To check on a phone
- **Fingerprint lock on the iQOO 7** (real in-display sensor): "Try it" on Protection, Continue anyway on a Stop screen, turning protection
  off. The "no sensor" PIN fallback and "no screen lock" setup block are unit-tested (the state mapping) but not run on such a phone.
- Reboot and app-update restart of protection (iQOO needs autostart and unrestricted battery).
- Usage-access fix on the iQOO, the stranger-text burst warning, "Continue anyway", and the split-payment hold.
