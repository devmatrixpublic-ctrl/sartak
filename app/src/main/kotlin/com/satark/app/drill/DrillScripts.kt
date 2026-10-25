package com.satark.app.drill

/**
 * The rehearsals. They are written from the scripts scam callers are reported to use in India, with invented names and no real number, agency
 * officer, account or payee. Each beat has exactly one safe choice; the other two are the moves a frightened person really makes
 * (go along, or bargain). Keep caller lines short: the whole rehearsal should take about a minute and a half.
 */
object DrillScripts {

    private val SAID_NEVER = "A real caller would never say this."

    val digitalArrest = DrillScript(
        id = "digital-arrest",
        title = "The “digital arrest” call",
        blurb = "A caller says he is a police officer and that a case is registered against you.",
        callerName = "Inspector Vikram Rao",
        callerRole = "Says he is from the Cyber Crime Branch",
        steps = listOf(
            DrillStep(
                tactic = Tactic.AUTHORITY,
                caller = "This is Inspector Rao, Cyber Crime Branch. Listen carefully. A parcel in your name had illegal items. A case is registered against you.",
                ask = "Your heart is racing. What do you do?",
                choices = listOf(
                    DrillChoice("a1-go", "Say it is a mistake and answer his questions", false,
                        "Good. Cooperate and this ends quickly. First, confirm your full name and your bank."),
                    DrillChoice("a1-id", "Ask him to send his ID card", false,
                        "Sending my ID now. See, it is genuine. Do not waste my time."),
                    DrillChoice("a1-hang", "Say you will hang up and call the police yourself", true,
                        "If you hang up, a warrant goes out in ten minutes!"),
                ),
                headline = SAID_NEVER,
                why = "Police do not announce a case by phone. A photo of an ID proves nothing, because anyone can fake one. " +
                    "The angry reply when you offer to check is the giveaway.",
            ),
            DrillStep(
                tactic = Tactic.STAY_ON_VIDEO,
                caller = "You are under digital arrest. Join this video call and keep your camera on. Do not disconnect. Do not tell anyone.",
                ask = "He says you cannot leave the call. What do you do?",
                choices = listOf(
                    DrillChoice("a2-stay", "Join the video call and stay on", false,
                        "Good. Sit still and keep the phone facing you. I am watching you the whole time."),
                    DrillChoice("a2-ask", "Join, but ask how long it will take", false,
                        "As long as it takes. Hours, if needed. Nobody can know."),
                    DrillChoice("a2-end", "End the call and tell someone near you", true,
                        "Do not hang up! Stay on the line! You will make it worse for yourself!"),
                ),
                why = "“Digital arrest” does not exist in Indian law. Nobody can arrest you through a screen. Keeping you on camera has one purpose: " +
                    "to stop you talking to someone who would spot the scam.",
                satarkNote = "Satark warns you when you have been on an unknown video call for a long time.",
            ),
            DrillStep(
                tactic = Tactic.INSTALL_APP,
                caller = "Do not worry, this is routine. To verify your phone, install AnyDesk now and read me the nine-digit code it shows.",
                ask = "He sounds very sure. What do you do?",
                choices = listOf(
                    DrillChoice("a3-do", "Install it and read him the code", false,
                        "Good. Now I can see your screen and verify everything."),
                    DrillChoice("a3-careful", "Install it, but promise not to open your bank app", false,
                        "That is fine. Just keep the app open and do as I say."),
                    DrillChoice("a3-no", "Refuse to install anything", true,
                        "Then we cannot clear your name. This is your last chance, and I will not repeat it."),
                ),
                why = "Screen-sharing apps let the caller see your screen, read your codes and use your UPI app as if the phone were in his hand. " +
                    "No agency needs this to “verify” you.",
                satarkNote = "When you go to pay, Satark's device check flags remote-access apps like this.",
            ),
            DrillStep(
                tactic = Tactic.SHARE_OTP,
                caller = "Stay calm. A code is coming by SMS. Read it out so I can confirm it is really you.",
                ask = "The SMS has just arrived. What do you do?",
                choices = listOf(
                    DrillChoice("a4-read", "Read out the code", false,
                        "Thank you. That is all I needed."),
                    DrillChoice("a4-half", "Read only the first three digits", false,
                        "Fine. And the rest? I need all six for the record."),
                    DrillChoice("a4-no", "Say you never share codes, and hang up", true,
                        "Without it I cannot protect you. You will be arrested."),
                ),
                why = "An OTP is the key to your money. The bank's own message says never to share it. Whoever asks you to read it out " +
                    "wants to log in as you, or to approve a payment from your account.",
            ),
            DrillStep(
                tactic = Tactic.PAY_NOW,
                caller = "Write this down. To clear your name, move your savings to the RBI safe account right now. It will be refunded after the check.",
                ask = "He gives you an account number. What do you do?",
                choices = listOf(
                    DrillChoice("a5-pay", "Transfer it to clear your name", false,
                        "Good. Do it now and stay on the line until it shows done."),
                    DrillChoice("a5-part", "Pay a part now and the rest later", false,
                        "Half is not enough. The full amount, now."),
                    DrillChoice("a5-report", "Refuse, hang up and call 1930", true,
                        "If you do not pay, your accounts will be frozen today!"),
                ),
                why = "There is no “safe account”. No bank, court or agency asks you to move money to prove you are innocent. " +
                    "If money has already gone, call 1930 at once: the sooner you report, the better the chance of stopping it.",
            ),
        ),
    )

    val bankKyc = DrillScript(
        id = "bank-kyc",
        title = "The “KYC update” call",
        blurb = "A caller from “your bank” says your account will be blocked unless you update KYC.",
        callerName = "Priya from the bank",
        callerRole = "Says she is from the KYC department",
        steps = listOf(
            DrillStep(
                tactic = Tactic.URGENCY,
                caller = "I am calling from your bank's KYC department. This is urgent. Your account will be blocked in two hours unless you update KYC now.",
                ask = "You use this account every day. What do you do?",
                choices = listOf(
                    DrillChoice("b1-ask", "Ask what you need to do to keep it open", false,
                        "Very simple. I only need a few details from you."),
                    DrillChoice("b1-wait", "Say you are busy and ask her to hold", false,
                        "I will stay on the line. We cannot wait. Two hours only."),
                    DrillChoice("b1-bank", "Say you will call the number on your bank card", true,
                        "The branch is closed now. Only I can fix it for you, right now!"),
                ),
                headline = SAID_NEVER,
                why = "Banks do not block an account within hours because of a phone call. KYC is updated at a branch or inside the bank's own app. " +
                    "A countdown is there to stop you thinking.",
            ),
            DrillStep(
                tactic = Tactic.SHARE_CARD,
                caller = "For the update, please confirm your debit card number, the expiry date and the three digits on the back.",
                ask = "She already knows your name. What do you do?",
                choices = listOf(
                    DrillChoice("b2-all", "Read out all of it", false,
                        "Thank you. One moment while I update it."),
                    DrillChoice("b2-most", "Read the number but not the digits on the back", false,
                        "I need the back digits as well, otherwise the update fails."),
                    DrillChoice("b2-no", "Say you will not give card details on a call", true,
                        "Then your KYC cannot be updated and your card will stop working today."),
                ),
                why = "Your card number, expiry and the digits on the back are everything needed to pay online. " +
                    "The bank that issued your card already has them. It never asks you to read them out.",
            ),
            DrillStep(
                tactic = Tactic.SHARE_OTP,
                caller = "You will get a code now. That is for the KYC update. Please read it to me, quickly.",
                ask = "The code arrives while she is talking. What do you do?",
                choices = listOf(
                    DrillChoice("b3-read", "Read her the code", false,
                        "Perfect. Your KYC is almost done."),
                    DrillChoice("b3-check", "Read it, but only after checking the message sender", false,
                        "Yes, it is from the bank. Now read it quickly, it expires."),
                    DrillChoice("b3-no", "Do not read it, and end the call", true,
                        "Sir, madam, please, the code will expire in a minute. Your account will be lost!"),
                ),
                why = "That code is not a KYC code. It is the bank's code to approve a payment or a log-in. " +
                    "KYC is never updated by reading a code to someone who called you.",
            ),
            DrillStep(
                tactic = Tactic.INSTALL_APP,
                caller = "I am sending you a link by message. Install the Bank KYC Update app from it to finish.",
                ask = "A message with a link just arrived. What do you do?",
                choices = listOf(
                    DrillChoice("b4-install", "Tap the link and install the app", false,
                        "Good. Allow everything it asks. It needs those to verify you."),
                    DrillChoice("b4-look", "Tap the link only to have a look", false,
                        "It is safe. Just press install, I will wait."),
                    DrillChoice("b4-no", "Do not tap it, and tell her you will use the bank's own app", true,
                        "The official app is down today. Use this one, it is the same app."),
                ),
                why = "Real banks keep their apps on Google Play. A file sent by message and named like “Bank KYC Update.apk” is a trap: " +
                    "it asks for permissions that let it read your messages and empty your account.",
                satarkNote = "Satark's download guard (optional) catches file names like this and moves them out of reach.",
            ),
            DrillStep(
                tactic = Tactic.ENTER_PIN,
                caller = "Do it quickly. I have sent a request for ₹1 to refund your fee. Open your UPI app and enter your PIN to receive it.",
                ask = "A request shows in your UPI app. What do you do?",
                choices = listOf(
                    DrillChoice("b5-pin", "Enter your PIN to receive the money", false,
                        "Done. Thank you. Your KYC is complete."),
                    DrillChoice("b5-amount", "Check that it says ₹1, then enter your PIN", false,
                        "Yes, it is only one rupee. Enter the PIN now."),
                    DrillChoice("b5-decline", "Decline the request and end the call", true,
                        "It is only one rupee! Why would you refuse a refund? Do it now."),
                ),
                why = "You never enter a UPI PIN to receive money. A PIN is only for paying. A “request” that asks for your PIN " +
                    "is taking money from you, whatever amount it shows.",
            ),
        ),
    )

    val customsParcel = DrillScript(
        id = "customs-parcel",
        title = "The “parcel seized” call",
        blurb = "A caller says customs has seized a parcel in your name and you must pay to release it.",
        callerName = "Sanjay from Customs",
        callerRole = "Says he is from Customs Clearance",
        steps = listOf(
            DrillStep(
                tactic = Tactic.AUTHORITY,
                caller = "This is Customs Clearance. Please listen carefully. A parcel from abroad in your name has been seized. It contains banned goods.",
                ask = "You did not order anything. What do you do?",
                choices = listOf(
                    DrillChoice("c1-listen", "Say you ordered nothing, but listen to what he says", false,
                        "Someone has used your name. Stay on the line and I will help you."),
                    DrillChoice("c1-which", "Ask him which parcel it is", false,
                        "Tracking number ending 4471. It is in our warehouse. Do you see now?"),
                    DrillChoice("c1-check", "Say you will check with the courier's official helpline", true,
                        "There is no time for that. The case is already open and it is in your name!"),
                ),
                headline = SAID_NEVER,
                why = "Customs deals with parcels in writing, through the courier or its official site, not by calling you out of the blue. " +
                    "A made-up tracking number is easy to produce. You ordered nothing, so there is nothing to clear.",
            ),
            DrillStep(
                tactic = Tactic.OPEN_LINK,
                caller = "I am texting you a tracking link. Tap it and confirm your address and card to release the parcel. It takes one minute.",
                ask = "The text arrives. What do you do?",
                choices = listOf(
                    DrillChoice("c2-fill", "Tap the link and fill in your details", false,
                        "Good. Now enter the card number and press submit."),
                    DrillChoice("c2-look", "Tap the link, but only to look", false,
                        "See, it is the official page. Now enter your details."),
                    DrillChoice("c2-ignore", "Ignore the link and look up the courier's site yourself", true,
                        "Why are you not opening it? Open it now!"),
                ),
                why = "A link in a text can open a copy of a real website, built to collect your card and UPI details. " +
                    "Open official sites by typing the address yourself, or use the company's own app.",
            ),
            DrillStep(
                tactic = Tactic.PAY_NOW,
                caller = "Pay a customs fee of ₹38,500 to this UPI ID right now, or the parcel is destroyed and an FIR is filed.",
                ask = "He reads out a UPI ID. What do you do?",
                choices = listOf(
                    DrillChoice("c3-pay", "Pay it to avoid the FIR", false,
                        "Good. Send the screenshot to me as soon as it is done."),
                    DrillChoice("c3-half", "Offer to pay half now", false,
                        "The full amount. The parcel will not be released otherwise."),
                    DrillChoice("c3-no", "Refuse and hang up", true,
                        "Then the FIR will be filed against you today, and the police will come to your door!"),
                ),
                why = "Government fees are paid on official portals or at a counter, never to a person's UPI ID. " +
                    "“Pay now or else” is pressure, not a process.",
            ),
            DrillStep(
                tactic = Tactic.SHARE_OTP,
                caller = "Your bank will send a code to approve the fee. Read it out so I can confirm the payment. Be quick.",
                ask = "A code arrives from your bank. What do you do?",
                choices = listOf(
                    DrillChoice("c4-read", "Read out the code", false,
                        "Received. Payment confirmed. Thank you for cooperating."),
                    DrillChoice("c4-delay", "Say you will read it in a minute", false,
                        "Read it now, it expires in thirty seconds."),
                    DrillChoice("c4-no", "Do not share it, and hang up", true,
                        "Without it the payment fails and the penalty doubles!"),
                ),
                why = "A code that approves a payment is never something to read to a stranger. " +
                    "If you did not start a payment, that code is the scammer starting one with your money.",
            ),
            DrillStep(
                tactic = Tactic.SECRECY,
                caller = "This is a sensitive customs matter. Do not tell your family or your bank, or they will be charged as well.",
                ask = "He lowers his voice. What do you do?",
                choices = listOf(
                    DrillChoice("c5-agree", "Agree to keep it secret", false,
                        "Wise. Keep this between us until I tell you otherwise."),
                    DrillChoice("c5-later", "Agree, but plan to tell them later", false,
                        "Not even later. I will call you again tomorrow to check."),
                    DrillChoice("c5-tell", "Hang up and tell someone in your family now", true,
                        "Do not hang up! You are putting them at risk too!"),
                ),
                headline = SAID_NEVER,
                why = "Only someone who needs you alone asks for secrecy. Talking to family or the bank is the quickest way to break a scam, " +
                    "so do it first, not later.",
            ),
        ),
    )

    val all: List<DrillScript> = listOf(digitalArrest, bankKyc, customsParcel)

    fun byId(id: String): DrillScript? = all.firstOrNull { it.id == id }

    /** Printed at the end: what to do on a real call. */
    val realCallRules: List<String> = listOf(
        "Hang up. You are allowed to end any call, and a real caller will still be reachable on an official number.",
        "Check for yourself: call the number on your bank card, or find the office's number on its own website. Never use a number the caller gave you.",
        "Never read out an OTP, PIN or card digits, and never install an app or tap a link because a caller asked.",
        "Tell someone you trust straight away, even if the caller told you not to.",
        "If money has gone or you have shared a code, call 1930 (the national cyber crime helpline) at once, or report at cybercrime.gov.in.",
    )
}
