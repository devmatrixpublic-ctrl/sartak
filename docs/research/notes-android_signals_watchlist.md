# Android signals and remote-access watch-list for the Satark detector (M1 input events)

NOTE ON VERIFICATION: play.google.com, support.google.com, apkmirror.com and dontkillmyapp.com were unreachable from the research sandbox (DNS failure), and WebFetch of developer.android.com reference pages returned only navigation (page too large), so most reference-page claims could not be quoted verbatim. Items below are tagged [CITED] (supported by a fetched/search result), or [UNVERIFIED-MEMORY] (from model knowledge; must be checked on Play/APKMirror before shipping). Do not ship the watch-list without a manual Play-URL check.

## 1. Remote-access / screen-share apps: package names (watch-list) vs video-call apps

### Takeaway
Only RustDesk (com.carriez.flutter_hbb) and AirDroid Remote Support (com.sand.airsos) were confirmed from fetched sources; all other IDs are unverified recall and must be checked at the Play URLs listed. Keep two separate lists: REMOTE_CONTROL (high-risk when installed/opened during a call) and VIDEO_CALL (used only for 'digital arrest' video session timing; never a risk signal on its own).

### Cited Findings
- RustDesk applicationId is com.carriez.flutter_hbb; listed on F-Droid (GPL-3.0), i.e. also obtainable outside Play — [F-Droid](https://f-droid.org/de/packages/com.carriez.flutter_hbb/), [IzzyOnDroid](https://apt.izzysoft.de/fdroid/index/apk/com.carriez.flutter_hbb?repo=main)
- AirDroid Remote Support is com.sand.airsos (publisher Sand Studio), minSdk 5.0/API 21 on APKMirror listing v1.1.4.0; supportee gets a 9-digit code — [APKMirror](https://www.apkmirror.com/?p=11671934) (as relayed by search result; page itself not fetched)
- AnyDesk scam pattern in India: fraudster has victim install AnyDesk, read out the 9-digit code, grant permissions, then control the device and UPI/mobile-banking; RBI cyber security cell reportedly warned banks (date not given in source) — [Union Bank cyber tips](https://www.unionbankofindia.co.in/english/cyber-security-tips.aspx), [databreaches.net](https://databreaches.net/?p=69307)
- APK-file scams delivered outside Play (fake e-challan, gas bill, KYC lures; SMS-reading/overlay malware; CERT-In alert reported by press) — [Moneylife](https://www.moneylife.in/article/fraud-alert-why-seniors-are-in-the-crosshairs/article/fraud-alert-from-echallan-gas-bill-updates-to-apk-traps-how-malware-scams-are-draining-bank-accounts/79996.html), [ClearIAS](https://www.clearias.com/apk-scam/)
- 'Digital Lutera' UPI fraud toolkit (CloudSEK; ~20 Telegram groups distributing; SMS permissions) — [Digit](https://www.digit.in/news/general/how-to-safeguard-your-upi-account-from-latest-digital-lutera-malware.html/amp/), [Outlook Money](https://www.outlookmoney.com/personal-finance/cyber-fraudsters-bypass-upi-security-check-through-digital-lutera-toolkit-npci-clarifies-safeguards-in-place) — no package names published in what was retrieved.

### Inferences (UNVERIFIED-MEMORY IDs; verify at URL before use)
Group A - REMOTE_CONTROL watch-list (Play URL pattern https://play.google.com/store/apps/details?id=<id>):
- AnyDesk: com.anydesk.anydeskandroid (on Play). Also AnyDesk plugin/add-ons exist (e.g. com.anydesk.adcontrol.ad1 for Samsung/other control add-ons) - verify.
- TeamViewer QuickSupport: com.teamviewer.quicksupport.market (Play). TeamViewer Host: com.teamviewer.host.market (Play). TeamViewer remote-control full app: com.teamviewer.teamviewer.market.mobile (the controller side, lower risk).
- RustDesk: com.carriez.flutter_hbb (Play and F-Droid; confirmed ID).
- Chrome Remote Desktop: com.google.chromeremotedesktop (controller only on Android; the phone cannot be controlled - low relevance).
- AirDroid: com.sand.airdroid; AirDroid Remote Support: com.sand.airsos (confirmed); AirMirror (controller): com.sand.airmirror.
- Mobizen Mirroring: com.rsupport.mvagent (screen mirroring/recording; RSUPPORT also makes RemoteView/'RSupport' agents, e.g. com.rsupport.rv.viewer.* / com.rsupport.remotecall.* - verify).
- Zoho Assist (customer-side agent): com.zoho.assist.customer (mobile 'Zoho Assist - Customer') and com.zoho.assist.agent (technician) - verify which is which.
- Splashtop: Splashtop Business/Personal viewer com.splashtop.remote.pad.v2 / com.splashtop.remote.bs; SOS customer side com.splashtop.sos - verify.
- Vysor: com.koushikdutta.vysor (screen mirroring over ADB; low scam use).
- Other tools seen in scam reporting (names only, IDs not verified): Ammyy, UltraViewer, Supremo, Quick Support (generic), ConnectWise/ScreenConnect, LogMeIn Rescue, RemoteIX, Rescue Assist. Samsung SmartThings: not relevant; exclude.
Group B - VIDEO_CALL apps (digital-arrest timing only; NOT remote-access):
- WhatsApp com.whatsapp; WhatsApp Business com.whatsapp.w4b; Skype com.skype.raider; Zoom us.zoom.videomeetings; Google Meet com.google.android.apps.tachyon; Telegram org.telegram.messenger; Microsoft Teams com.microsoft.teams; Signal org.thoughtcrime.securesms; Google Duo (merged into Meet). Digital-arrest cases are reported mainly on WhatsApp/Skype video - not independently cited here.
- Typical delivery: social-engineered phone call/SMS tells victim to install from Play ("AnyDesk/QuickSupport") and read out the code (Play-available apps => install source = com.android.vending), or to sideload an .apk sent over WhatsApp/SMS (install source = browser/file manager/messenger package or null).
Malicious APK families for UPI: no vendor-published package names retrieved (Digital Lutera toolkit named by CloudSEK press coverage). Treat the watch-list as non-exhaustive and use behavioural signals (sideload + accessibility/SMS permission) too.

### Gaps
- Play store pages unreachable: no package ID on this list except RustDesk and com.sand.airsos has been confirmed on Play/APKMirror/F-Droid.
- No security-vendor primary report with named malicious package IDs for Indian UPI trojans was retrieved (search only returned press).

## 2. Android API semantics for M1 signals

### Takeaway
Call state (IDLE/RINGING/OFFHOOK) is available with READ_PHONE_STATE (runtime) using TelephonyCallback on API 31+ and PhoneStateListener below; the number is only delivered with READ_CALL_LOG (from Android 9) and is empty otherwise; on API 31+ the TelephonyCallback.CallStateListener has no number at all. Video-app sessions are derived from UsageStats events and need the user-granted Usage Access special permission. Install source is reliable only for API 30+. PACKAGE_ADDED cannot be received by manifest receivers on API 26+.

### Cited Findings
- Android 9: apps cannot read phone numbers or phone state without READ_CALL_LOG; without it the number is empty in PHONE_STATE broadcasts and PhoneStateListener; reading numbers from onCallStateChanged needs READ_CALL_LOG only, while the PHONE_STATE broadcast needs READ_CALL_LOG and READ_PHONE_STATE; user may deny so handle gracefully — [Android 9 behaviour changes](https://developer.android.com/about/versions/pie/android-9.0-changes-all)
- PhoneStateListener reference: empty string passed if no READ_CALL_LOG or carrier privileges — [search extract of PhoneStateListener docs](https://developer.xamarin.com/api/field/Android.Telephony.PhoneStateListener.OnCallStateChanged/) (secondary mirror)
- States: RINGING = incoming, OFFHOOK = active or held call (also dialling), IDLE = none — same Android reference, tutorial extract above.
- Fetched docs summary (model-summarised, page body not quoted): TelephonyCallback.CallStateListener added API 31; onCallStateChanged(int state) only, no number; needs READ_PHONE_STATE, SecurityException otherwise — [TelephonyCallback.CallStateListener](https://developer.android.com/reference/android/telephony/TelephonyCallback.CallStateListener) [UNQUOTED]
- Broadcast limits: apps targeting API 26+ cannot register manifest receivers for implicit broadcasts; the exempt list contains ACTION_PACKAGE_FULLY_REMOVED but not ACTION_PACKAGE_ADDED/REPLACED; so PACKAGE_ADDED needs a runtime-registered receiver (or a foreground service / periodic scan) — [Implicit broadcast exceptions](https://developer.android.com/guide/components/broadcast-exceptions)
- QUERY_ALL_PACKAGES: Play permits only if core user-facing functionality needs broad app visibility (examples: device search, antivirus, file managers, browsers); requires Play Console declaration form with description and video; must justify why less intrusive method fails; apps may be removed — [Play policy page (search extract)](https://support.google.com/googleplay/android-developer/answer/10158779?hl=en), [XDA](https://www.xda-developers.com/google-play-store-query-all-packages-rule/)
- Package visibility (Android 11+, targetSdk 30+) filters PackageManager queries; <queries><package android:name=.../></queries> makes named packages visible; getInstallSourceInfo for an invisible package throws NameNotFoundException — [Package visibility overview](https://developer.android.com/about/versions/11/privacy/package-visibility) (page itself only links to detail guide; specifics [UNQUOTED])

### Inferences (UNVERIFIED-MEMORY; check docs)
- Number access on API 29-35 for a non-default dialer: READ_CALL_LOG (+ READ_PHONE_STATE) gives numbers via PhoneStateListener (deprecated API 31; still works but 31+ requires READ_PHONE_STATE). Android 10+ also added READ_PRECISE_PHONE_STATE (system only). Alternatives: query CallLog.Calls with READ_CALL_LOG (number, type, date, duration - gives call_end data robustly after the fact) or CallScreeningService/ROLE_CALL_SCREENING (role prompt; number for incoming only). READ_CONTACTS is only for name resolution. Play restricts READ_CALL_LOG/READ_SMS to default dialer/SMS handlers or permitted exceptions via Permissions Declaration - a Play distribution risk for Satark; consider sideload/NGO distribution or avoid the number and emit only a hashed number from a CallScreening role.
- VoIP: WhatsApp/Meet/Skype calls generally do NOT drive TelephonyManager call state (they use ConnectionService self-managed or audio-only) except an app registered as a managed PhoneAccount; so OFFHOOK will not reliably appear for WhatsApp video. Hence video sessions must come from UsageStats (+ optionally AudioManager mode MODE_IN_COMMUNICATION, which needs no permission). Not verified by an authoritative doc in this research.
- UsageEvents: ACTIVITY_RESUMED(1)/ACTIVITY_PAUSED(2) are API 29 replacements for MOVE_TO_FOREGROUND/MOVE_TO_BACKGROUND (deprecated in 29); ACTIVITY_STOPPED API 29. Session = RESUMED of watched package until next PAUSED/STOPPED for the same package (tolerate activity hops within the app by merging gaps < ~3-5 s; split on screen-off/keyguard events SCREEN_NON_INTERACTIVE). Use queryEvents(begin,end) polling; events are timestamped epoch ms (UsageEvents.Event.getTimeStamp). Requires PACKAGE_USAGE_STATS via Settings > Usage access (AppOpsManager OPSTR_GET_USAGE_STATS); not grantable at runtime. A foreground video call with the app in PiP/background keeps no RESUMED, so duration is underestimated (treat as lower bound).
- getInstallSourceInfo (API 30): getInstallingPackageName() = installer of record (com.android.vending for Play; com.google.android.packageinstaller / com.android.packageinstaller / OEM installers e.g. com.miui.packageinstaller, com.samsung.android.packageinstaller for sideload via installer UI; com.sec.android.app.samsungapps = Galaxy Store; null if adb/unknown). getInitiatingPackageName() = app that started the install (e.g. browser, WhatsApp, file manager) and is the key sideload-source signal; may be null if initiating app uninstalled or package not by session; getOriginatingPackageName() = claimed source URI package, requires installer to set it, often null. API 34 adds getUpdateOwnerPackageName and initiating signing info. Pre-30: only getInstallerPackageName() (deprecated 30) - returns the installer; initiating info absent, so emit initiating=null with status UNAVAILABLE.
- OEM flakiness: Xiaomi (MIUI/HyperOS autostart + battery saver), Oppo/Realme (ColorOS), Vivo (FuntouchOS/OriginOS), Samsung (Sleeping/Deep sleeping apps) and Huawei kill background services and delay/disable runtime-registered receivers; telephony callbacks stop when the process dies; Usage Access OK because it is polled. Mitigation: foreground service with persistent notification (needs FOREGROUND_SERVICE type and Android 14 type declaration), ask user to exempt from battery optimisation (REQUEST_IGNORE_BATTERY_OPTIMIZATIONS is Play-restricted) and autostart; re-sync on boot/app open by diffing PackageManager list, CallLog and UsageEvents so missed events are back-filled with source=BACKFILL. Source for OEM behaviour: dontkillmyapp.com (unreachable in this run) and [Android doze docs](https://developer.android.com/training/monitoring-device-state/doze-standby) [not fetched].
- Also: from Android 13 a sideloaded app may have restricted settings for Accessibility/Notification access; Android 14 limits implicit-intent/FGS types; scoped to M1 only if used.

### Gaps
- Exact quotes for TelephonyCallback.CallStateListener, UsageEvents.Event, InstallSourceInfo and package visibility pages could not be retrieved (page truncation); API-level numbers above are from model memory.
- No authoritative source retrieved on VoIP/WhatsApp vs OFFHOOK; no issue-tracker links for OEM kills (dontkillmyapp.com unreachable).

## 3. Recommended JSON event vocabulary

### Takeaway
Use one envelope with epoch-ms device time plus monotonic ms, a source-status field per signal, and hashed identifiers; unavailable signals emit an explicit status rather than being omitted.

### Cited Findings
- Constraints driving the schema: number empty without READ_CALL_LOG [Android 9 changes](https://developer.android.com/about/versions/pie/android-9.0-changes-all); PACKAGE_ADDED not receivable from manifest [broadcast exceptions](https://developer.android.com/guide/components/broadcast-exceptions); QUERY_ALL_PACKAGES restricted on Play [Play policy](https://support.google.com/googleplay/android-developer/answer/10158779?hl=en).

### Inferences (design proposal)
Envelope (all events): {"schema":1,"event_id":"uuid","type":"...","t_ms":<epoch ms UTC, System.currentTimeMillis or UsageEvents timestamp>,"mono_ms":<SystemClock.elapsedRealtime>,"tz_offset_min":int,"sdk":int,"source":"TELEPHONY_CB|CALL_LOG|USAGE_STATS|PKG_RECEIVER|PKG_SCAN|ACCESSIBILITY|NOTIF|SMS_PARSE|BACKFILL","status":"OK|DEGRADED|UNAVAILABLE","unavail_reason":"PERMISSION_DENIED|API_LEVEL|OEM_KILLED|NOT_VISIBLE|NOT_APPLICABLE|null"}
- call_start: {direction:"IN|OUT|UNKNOWN", number_hash:"hmac-sha256 hex (device-salt) or null", number_class:"CONTACT|UNKNOWN|SHORTCODE|INTL|HIDDEN|null", is_contact:bool|null, medium:"CELLULAR"}  (OFFHOOK or RINGING->OFFHOOK transition)
- call_end: {duration_s:int, number_hash, answered:bool|null, via:"CALL_STATE|CALL_LOG"}
- video_session_start: {pkg:"com.whatsapp", app_group:"VIDEO_CALL", start via UsageEvents ACTIVITY_RESUMED, concurrent_cellular_call:bool}
- video_session_end: {pkg, duration_s, end_reason:"PAUSED|STOPPED|SCREEN_OFF|TIMEOUT", duration_is_lower_bound:true}
- remote_access_app_open: {pkg, app_group:"REMOTE_CONTROL", overlaps_call:bool}  (same UsageStats source)
- app_install: {pkg, app_group:"REMOTE_CONTROL|VIDEO_CALL|OTHER", installer:"com.android.vending|...|null", initiator:string|null, originating:string|null, install_source_class:"PLAY|OEM_STORE|SIDELOAD|UNKNOWN", first_install_time_ms, version_code, requests_accessibility:bool|null}; status DEGRADED on API<30 (initiator unavailable) 
- new_payee: {vpa_hash, bank_handle:"@okaxis" (plain, low-entropy), payee_name_hash|null, source:"NOTIF|ACCESSIBILITY|SMS_PARSE", upi_app_pkg}
- payment_attempt: {upi_app_pkg, amount_paise:int|null, vpa_hash, payee_is_new:bool, mode:"PAY|COLLECT|QR|null"}  (money in integer paise, never float)
- signal_health (periodic): {signals:{call_state:status, call_log:status, usage_stats:status, pkg_receiver:status, notif_listener:status}, battery_opt_exempt:bool, oem:"xiaomi|oppo|vivo|samsung|other", fgs_running:bool}
- Choices forced by Android: epoch ms (UsageEvents and CallLog.DATE are epoch ms; carry mono_ms for ordering because user can change clock); hash numbers/VPAs with a per-install salt (HMAC) and keep a separate on-device salted prefix for matching against a bank-provided list; durations in whole seconds, lower-bound flag for usage-derived sessions; status UNAVAILABLE with reason instead of null when permission denied, so downstream model distinguishes 'no call' from 'cannot see'.

### Gaps
- UPI-app payment/payee signals have no Android-API ground truth (they depend on notification/accessibility parsing, or app-side data); not researched here.
