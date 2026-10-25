# Satark: working notes

## Status and what is left (25 Oct, after the iQOO and Realme tests)
**Built and pushed to `role_1`:** detector and app pipeline; Stop screen on every held payment; "Take a moment" step before an allowed payment;
Rs 25,000 rule (Rs 10,000 under 22, an assumption); split guard; stranger-text warning; owner check (fingerprint, screen-lock PIN fallback)
on Continue anyway / protection off / trusted-contact and age changes / delete data; protection-off wait with the contact told at once;
removal guard (device admin); three new server alert types; Firebase config in place (`app/google-services.json`, service key in
`~/.satark-secrets/firebase-admin.json`, both outside git); real hardware sign-in worked once on a Realme against a
production-mode server on the laptop; judges' Q&A PDF (`~/Downloads/JUDGES_QNA.pdf`).

**1. Backend (order agreed: A deploy, B push, C accounts)**
- [ ] **Pin the Google attestation roots.** A person compares the SHA-256 fingerprints in `server/certs/CANDIDATE_ROOTS.md` with Google's page
      in a browser; then they go into `server/certs/google_attestation_roots.pem`. Today only a scratch copy was used for the local test.
- [ ] **Deploy.** Render (blueprint exists, never run) or a public tunnel to the laptop. Needs the release signing digest, `SATARK_TRUSTED_PROXY_HOPS`,
      the DB role script, and `ops/e2e/smoke_deployed.py`. Decision wanted.
- [ ] **Push to a second physical phone.** Service key and app config are ready; the contact phone must show "Show my pairing code" with a real code.
- [ ] **Razorpay test checkout.** Needs the key id (public), key secret and webhook secret in a file outside the repo, and a public webhook URL.
- [ ] **Accounts (C), see the next section.**

**2. Features not built:** login page with phone number and OTP; names in alerts; WhatsApp message flags (approved design below).

**3. Decisions waiting:** a smaller amount to the same payee after a Stop (allow with the nudge, or keep stopping); keep or drop the Rs 10,000 under-22 rule.

**4. On-device checks still to do:** the 5 demo cases and "payment right after the call ends" on a phone; the real iQOO fingerprint sensor; whether Funtouch OS
blocks uninstall while the removal guard is on; USB keeps dropping, so use wireless debugging.

**5. Evidence gaps:** sealed held-out run (needs the 36 vectors on two physical phones and the `detector-freeze` tag); 100 ms on-device scoring target unmeasured;
false alarms 0.152% against the 0.100% target after the Rs 25,000 rule; Hindi text needs a native speaker; family-emergency recall 43.9%.

**6. Housekeeping:** a production-mode test server may still be running on the laptop (port 8000); stop it when done.

### WhatsApp message flags (agreed design, not built)
Read WhatsApp notification text through notification access, match a short keyword list, ignore saved contacts and group chats, store only the time
and category, never let a message change a payment decision. Needs a "WhatsApp messages: Off, needs notifications" status row and updated consent text.

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
