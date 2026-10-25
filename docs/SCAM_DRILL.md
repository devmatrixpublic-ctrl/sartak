# Scam Inoculation Mode

A short, optional rehearsal of a scam call, played inside the app, so a real scam call is not the first time the person hears one.

Satark plays the caller for a little over a minute on the line (about two minutes in all, with the pauses to choose and read the explanations). At each point where a real scammer would push for something (a code, an app, staying on video, paying) the call **pauses**, the person
chooses what to do, and the screen explains: *A real caller would never need this. Here's why.* It is practice. No call is made, nothing is sent anywhere, and the screen
never asks for a real OTP, PIN or card number: every choice is a button.

Open it from the home screen: **Practice a scam call**.

## The three rehearsals

| Rehearsal | The caller | The moves rehearsed |
|---|---|---|
| **The "digital arrest" call** | "Inspector Vikram Rao", says he is from the Cyber Crime Branch | fake authority, being kept on video, installing AnyDesk, reading out an OTP, paying to a "safe account" |
| **The "KYC update" call** | "Priya from the bank" | a two-hour countdown, reading out card details, reading out an OTP, a "KYC app" sent as a file, entering a UPI PIN to "receive" money |
| **The "parcel seized" call** | "Sanjay from Customs" | fake authority, a tracking link, paying a "customs fee" to a UPI ID, reading out an OTP, "tell no one" |

Together they cover ten moves: fake authority, a countdown, secrecy, being kept on the line, asking for a code, asking for card details, installing an app, a link to tap, a PIN
"to receive" money, and paying to fix it. Each move has one rule the person can carry into a real call (`Tactic.rule` in `DrillModel.kt`), shown under the explanation and again in the summary
for any move that was missed.

## How a rehearsal runs

Each beat has three stages:

1. **Caller.** The caller speaks. The words appear at about the pace of speech, and the call clock runs. A tap on the words shows them all.
2. **Decide.** The call is **paused** (the clock stops, the panel says *ON HOLD*). The person picks one of three choices. The choices are shuffled every time, so the safe one is not always
   in the same place. Two are the things a frightened person really does (go along, or bargain); one is the safe move.
3. **Lesson.** The caller's reply is shown. A real scammer pushes back when refused, so the safe choice also gets an angry reply: the push-back is part of the lesson. Then the headline
   (*A real caller would never need this.* or *…never say this.*), **Here's why**, what Satark itself does about this move where it does something, and the rule to remember.

The bar at the top shows **pressure from the caller** climbing with each beat, as it does in a real call. At the end there is a summary: how many moves were resisted, which were missed
and the rule for each, and what to do on a real call (hang up, check on an official number, never share a code or install an app, tell someone, call 1930 or report at cybercrime.gov.in).
The verdict is never a pass or a fail.

## Safety rules the feature keeps

- **Always labelled.** A *PRACTICE · This is not a real call* banner stays on screen for the whole rehearsal, and the caller's number is shown as "Unknown number". Nothing in a script is a real number, link, UPI ID, account, officer or agency
  employee (`ScamDrillTest.nothingInARehearsalLooksLikeARealNumberAccountOrPerson`).
- **No real input.** There is no text box. A rehearsal never asks the person to type or read out anything real (`aRehearsalNeverAsksForTheRealThing`).
- **Local only.** What is kept is which rehearsals were finished, when, and how many moves were resisted (`DrillRecord`), in the app's encrypted storage, so the home screen can say
  *Last practised 2 weeks ago: 4 of 5 spotted* and suggest a rehearsal not yet tried. It is wiped with *Delete all my data*. Nothing is uploaded.
- **Beside the detector, never inside it.** Practising does not change what Satark warns about and never relaxes a payment decision. The rehearsal runs on its own screen and emits no signal
  to the detector, and the speech it plays does not set the phone's call audio mode, so it cannot be mistaken for a real call.
- **A real warning still wins.** If Satark raises a real alarm while a rehearsal is open, the alarm shows over it as usual.

## Voice

*Hear the caller* (off by default, so the phone does not speak in public) reads the call aloud with the phone's own speech engine: the caller in a lower, slightly slower voice, Satark's
explanations in a plain one. Nothing is recorded and nothing leaves the phone. The caller's words are always on screen too, for anyone who cannot hear or prefers to read. If the phone has no speech engine, the rehearsal works silently.

## Accessibility

Large type, 56 dp choice buttons, the caller's line is announced as one sentence (not letter by letter) to a screen reader, and the typing and pulsing animation is skipped when the person
has turned animations off in the phone's settings.

## Adding or changing a rehearsal

Scripts are plain data in `app/src/main/kotlin/com/satark/app/drill/DrillScripts.kt`. A new `DrillScript` needs:

- a caller line of 26 words or fewer for each beat, an explanation of 45 words or fewer, and exactly **one** safe choice out of three;
- a reply for every choice. The reply to the safe choice must be the caller pushing back, never pleased;
- no real number, link, UPI ID, e-mail address, account or person.

`ScamDrillTest` checks all of this for every script, and checks that the call itself runs 60 to 90 seconds (words spoken at 2.5 a second) and the whole rehearsal, including reading, stays under
two and a half minutes. The current scripts measure 61 to 65 seconds on the line and about two minutes in all. Add the script to `DrillScripts.all` and it appears in the list.

## Limits

- The scripts are in English only. The app's Hindi covers only the warning reasons so far, and Hindi scripts need a native speaker to write and review, not a machine draft.
- The facts in the explanations (that "digital arrest" is not a thing in Indian law, that banks never ask for an OTP, that 1930 is the national cyber crime helpline) follow public
  advisories from the Indian government, the Reserve Bank of India and banks, but they have not been reviewed by a lawyer or by the agencies. Check them before relying on them in public material.
- A rehearsal teaches the moves; it has not been tested for whether it changes behaviour in a real call. That would need a study with real participants, which has not been done.
- The score is a self-check, not a measurement. Choosing the safe button in practice is easier than refusing a frightening voice at 10 p.m.
- Leaving a rehearsal part-way records nothing. Turning the phone does not end it (the running rehearsal is kept in memory and resumes, with the caller's current line starting again), but if Android
  closes Satark in the background the rehearsal is lost.
