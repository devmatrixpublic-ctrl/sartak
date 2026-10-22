# Indian coached-payment / digital-arrest / remote-access UPI scam playbooks: timing and sequence

Method caveat: WebFetch failed in this environment (DNS errors), so all findings come from search-result summaries (about 16 calls). Primary documents (PIB, Sansad, RBI PDFs) were NOT opened; official figures are quoted as relayed by news outlets and flagged as such. Many case details (call length, per-transfer timing) are absent from the snippets and are listed as gaps rather than guessed. Case dates are often not shown in snippets.

## What are the main playbooks and how common is each?

### Takeaway
Digital arrest is the only playbook with official per-year counts (about 1.24 lakh complaints and Rs 1,935.51 crore in 2024). The other playbooks (remote-access KYC/bank-official, APK-based e-challan/RTO, courier) have no official per-playbook split found; only anecdotes, vendor reports and police advisories exist.

### Cited Findings
- Playbook sequence (digital arrest, anecdotal): unknown call (DHL/courier/TRAI/telecom regulator) -> transfer to fake police/CBI/NIA/ATS -> Skype/WhatsApp video call with fake warrant/documents -> "verification" transfers via RTGS/UPI to "safe/RBI" accounts. Bengaluru case began with a call claiming a DHL Andheri parcel containing credit cards, passports and MDMA — [DT Next](https://www.dtnext.in/news/national/bengaluru-woman-loses-rs-3183-cr-in-months-long-digital-arrest-scam-involving-fake-cbi-officers-853424)
- Hebbal engineer case: fraudsters posed first as telecom regulator official, then police, claiming a businessman opened an account on the victim's Aadhaar for Rs 6 crore of transactions — [The News Minute](https://www.thenewsminute.com/karnataka/bengaluru-software-engineer-loses-rs-118-crore-in-digital-arrest-scam) (via search summary)
- Fake bank/KYC + remote-access playbook: caller poses as bank/telecom/SBI support, demands "KYC", has victim install QuickSupport/TeamViewer/AnyDesk, then drains accounts. Telangana (QuickSupport, fake SBI support) — [Zee5](https://zee5.com/articles/two-arrested-for-cyber-fraud-through-fake-kyc-links-in-telangana); Mumbai 70-year-old (card photo sent, then TeamViewer, series of transactions, Rs 63k) — [Free Press Journal](https://www.freepressjournal.in/mumbai/70-yr-old-duped-of-rs-63k-in-card-kyc-fraud); Kashmir police warning about telecom-customer-care pretext and QuickSupport/TeamViewer — [Kashmir Despatch](https://kashmirdespatch.com/cyber-police-saves-rs-7-lakh-of-gullible-people-in-past-week-police/)
- APK playbook: fake RTO/e-challan and gas-bill "APK" files via SMS/WhatsApp; CERT-In reportedly issued an alert on an active Android campaign impersonating RTO/e-challan notices — [Moneylife](https://moneylife.in/article/fraud-alert-from-echallan-gas-bill-updates-to-apk-traps-how-malware-scams-are-draining-bank-accounts/79996.html); J&K Crime Branch advisory (Dec 2025) on "RTO Challan.apk" — [Greater Kashmir](https://m.greaterkashmir.com/article/crime-branch-warns-public-against-fake-rto-challan-apk-scam-circulating-via-sms-whatsapp/462710); Cyfirma technical report: two-stage dropper, OTP interception, fake Rs 1 challan page asking UPI PIN/card — [Cyfirma](https://www.cyfirma.com/research/rto-challan-fraud-a-technical-report-on-apk-based-financial-and-identity-theft)
- Digital arrest enforcement scale: I4C blocked 3,962 Skype IDs and 83,668 WhatsApp accounts used for digital arrest (as of reply of 12 Mar 2025); 7.81 lakh SIMs and 2,08,469 IMEIs blocked (all cybercrime) till 28.02.2025 — [Free Press Journal](https://www.freepressjournal.in/india/3962-skype-ids-83668-whatsapp-accounts-used-for-digital-arrest-blocked-so-far-ministry-of-home-affairs-to-rajya-sabha); primary: [Rajya Sabha PQ 267, 12-03-2025](https://rsdebate.nic.in/bitstream/123456789/757409/1/PQ_267_12032025_U1523_p341_p345.pdf) (not opened)
- The platforms named for digital-arrest contact are Skype and WhatsApp (the blocking figures above), i.e. victims are moved to video-capable consumer apps.
- Money-laundering layer: ED said an "RTGS agent" network's accounts figure in 300+ victim complaints and 160+ FIRs across 20+ states, about Rs 417 crore — [Bhaskar Live](https://bhaskarlive.in/others/ed-arrests-rtgs-agent-involved-in-rs-26-crore-digital-arrest-of-goa-woman-2154780)

### Inferences
- Digital-arrest payments are mostly bank transfers (RTGS/NEFT/IMPS) to mule accounts, not UPI P2M, per case reports below; UPI-specific modelling should treat these as large P2P-like account-to-account transfers. This is an inference from anecdotes, not an official split.
- Remote-access KYC cases involve smaller amounts (Rs 63k to about Rs 9.5 lakh in the cases found) than digital arrest (Rs 5 lakh to Rs 31.8 crore).

### Gaps
- No official or survey-based share of complaints by playbook (digital arrest vs. KYC/remote-access vs. APK vs. courier vs. investment/task) was found.
- No evidence retrieved on electricity-bill, investment/task or fake customer-care volumes beyond generic mention.

## Official aggregate losses and counts (2022-2026)

### Takeaway
Government-reported digital arrest complaints rose from 39,925 (2022) to 1,23,672 (2024); total cyber financial fraud on NCRP was Rs 22,848 crore in 2024 and Rs 22,495 crore in 2025 per secondary reports. These are complaint-based losses, not verified.

### Cited Findings
- Digital arrest (MHA reply, Rajya Sabha, 12 Mar 2025): 39,925 cases / Rs 91.14 crore (2022); 60,676 / Rs 339.03 crore (2023); 1,23,672 / Rs 1,935.51 crore (2024); 17,718 / Rs 210.21 crore (Jan-Feb 2025) — [Free Press Journal](https://www.freepressjournal.in/india/3962-skype-ids-83668-whatsapp-accounts-used-for-digital-arrest-blocked-so-far-ministry-of-home-affairs-to-rajya-sabha); also [Inc42](https://inc42.com/?p=504907); primary [PQ 267](https://rsdebate.nic.in/bitstream/123456789/757409/1/PQ_267_12032025_U1523_p341_p345.pdf)
- Implied mean loss per digital-arrest complaint: Rs 91.14 cr/39,925 = about Rs 22.8k (2022); Rs 339.03 cr/60,676 = about Rs 55.9k (2023); Rs 1,935.51 cr/1,23,672 = about Rs 1.57 lakh (2024); Rs 210.21 cr/17,718 = about Rs 1.19 lakh (Jan-Feb 2025). (Computed by me from the cited figures; the mean is far above the median because of crore-level tail cases.)
- Jan-Apr 2024: Rs 120.30 crore lost to digital arrest — [The Wire](https://thewire.in/news/indians-lost-rs-120-crore-in-digital-arrest-frauds-in-first-quarter-of-2024-report) (via search summary; figure attributed to government data)
- First nine months of 2024: Rs 1,616 crore from 63,481 complaints (Indian Express via The Wire; note this conflicts in complaint count with the 1.24 lakh full-year figure, so definitions may differ) — [The Wire](https://thewire.in/tech/india-lost-rs-11333-crore-to-cyber-fraud-in-2024)
- NCRP financial fraud complaints: 13,10,357 (2023), 19,18,835 (2024), 24,02,579 (2025); losses Rs 7,465 crore (2023), Rs 22,848 crore (2024), Rs 22,495 crore (2025) — [Dynamite News](https://www.dynamitenews.com/national/cyber-frauds-mount-to-rs22495-crore-in-2025-over-rs8000-crore-saved-through-rapid-response-system/amp); [News Karnataka](https://newskarnataka.com/india/over-24-lakh-cyber-fraud-complaints-reported-in-2025/21022026/). Another headline gives Rs 11,333 crore for 2024 — [The Wire](https://thewire.in/tech/india-lost-rs-11333-crore-to-cyber-fraud-in-2024) — which conflicts with Rs 22,848 crore; not reconciled (possibly different scope or period).
- CFCFRMS: saved over Rs 8,189 crore across 23.61 lakh complaints (to Dec 2025); over Rs 11,158 crore from 32.80 lakh complaints (to 30 Jun 2026) — [Outlook Money](https://www.outlookmoney.com/retirement/cyber-fraud-rs-11158-crore-saved-across-328-million-complaints-how-to-report-financial-fraud-on-cybercrime-portal); [Superkalam/PIB summary](https://superkalam.com/current-affairs/29-07-2026/cfcfrms-2-0-platform-27181ced-b1eb-4f42-acee-14b9c920682f)
- Supreme Court suo motu hearing, 3 Nov 2025: about Rs 3,000 crore reportedly extorted via digital arrest; court said victims were mostly elderly; trigger was an elderly couple (Rs 1.5 crore, 1-16 Sept, fake CBI/IB/judiciary, forged SC orders) — [Free Press Journal](https://www.freepressjournal.in/india/digital-arrest-scams-cbi-crackdown-widens-as-supreme-court-keeps-up-pressure); [The Wire](https://m.thewire.in/article/law/will-take-stringent-action-sc-expresses-shock-over-rs-3000-crore-lost-to-digital-arrest-scams). The Rs 3,000 crore appears to be a court/government-submitted figure, not reconciled with the MHA Rs 1,935.51 crore for 2024.
- UPI fraud (Finance Ministry, Lok Sabha Unstarred Q 2481, 15 Dec 2025): FY22 4.07 lakh cases / Rs 242 crore; FY23 Rs 573 crore; FY24 13.42 lakh / Rs 1,087 crore; FY25 12.64 lakh / Rs 981 crore; FY26 to Nov 10.64 lakh / Rs 805 crore — [IANS](https://ianslive.in/upi-frauds-worth-rs-805-crore-witnessed-this-fiscal-so-far-minister--20251215175703); primary [Sansad AU2481](https://eparlib.sansad.in/bitstream/123456789/3018042/1/AU2481_5bIzKk.pdf) (not opened). Implied mean = about Rs 7.8k per UPI fraud case in FY25 (computed), i.e. UPI fraud overall is dominated by small cases; coached large-value digital arrest is a different regime.
- RBI Annual Report 2024-25: card/internet frauds 13,516 cases / Rs 1,457 crore (FY25) vs 29,082 / Rs 520 crore (FY24); covers frauds of Rs 1 lakh and above — [Deccan Chronicle](https://www.deccanchronicle.com/amp/nation/bank-fraud-amount-triples-to-36014-cr-in-fy25-despite-fewer-cases-rbi-1882116). RBI Trend & Progress of Banking Dec 2025: card/internet 7,756 incidents (66.8%), Rs 252 crore (7.2%) — [Medianama](https://www.medianama.com/2025/12/223-cards-internet-fraud-66-in-fy25-decline-banking-rbi/). The two RBI publications give different totals; not reconciled.

### Inferences
- Rapid growth 2022-2024 in mean loss per complaint (about 7x) suggests a shift toward high-value coached cases; a simulator's amount distribution should be heavy-tailed (lognormal/Pareto) rather than anchored to the mean.

### Gaps
- No official 2025 full-year digital-arrest-only count found. No official age distribution of victims. No official P2P vs P2M split for coached cases. RBI/NPCI do not appear to publish call-duration or time-gap data.

## Timing: call length, digital arrest session length, 2-hour threshold

### Takeaway
Reported "digital arrest" durations in news are mostly many hours to days (55 hours, 2 days, 3 days, 12 days, 18 days, about 2 weeks, up to months), far above 2 hours; but the retrievable evidence does not measure the unknown initial call length or how long continuous video stays active, so a 2-hour threshold is consistent with, but not directly tested by, the evidence. All are single-article anecdotes.

### Cited Findings
- Retired Air Force sergeant, Faridabad: 55 hours under "digital arrest", Rs 5 lakh — [Deccan Herald](https://www.deccanherald.com/amp/story/india%2Fharyana%2Fduped-of-rs-5-lakhs-retired-air-force-personnel-becomes-victim-of-digital-arrest-in-faridabad-3293885) (anecdote)
- Delhi retired engineer: at least 8 hours on Skype, Rs 10.3 crore — [The Week/PTI, 14 Nov 2024](https://www.theweek.in/wire-updates/national/2024/11/14/des85-dl-digital-arrest.html) (anecdote)
- Bengaluru retired professor handed over savings within 5 hours — reported in a search summary, source not individually identified (anecdote; treat as weak)
- Pinjore (Chandigarh) 83-year-old: told to stay on camera for 3 days, sent Rs 57.90 lakh in those 3 days — [Tribune](https://www.tribuneindia.com/news/chandigarh/third-accused-held-in-57-9l-digital-arrest-fraud) (anecdote)
- Amritsar retired SMO: nearly 2 days, all funds via RTGS, Rs 23 lakh — [Tribune](https://www.tribuneindia.com/news/amritsar/retired-smo-in-amritsar-loses-rs-23-lakh-in-digital-arrest-scam) (anecdote)
- Delhi retired officer: 3 days virtual custody, Rs 48.5 lakh — [Tribune](https://www.tribuneindia.com/news/delhi/digital-arrest-scam-delhi-cyber-police-arrest-3-after-retired-officer-cheated-of-rs-48-5-lakh/amp) (anecdote)
- Kolkata businessman: 12 days (Feb-Mar 2025), Rs 75.5 lakh — reported in search summary via ISACA-adjacent results, [ISACA overview](https://www.isaca.org/resources/news-and-trends/industry-news/2025/trapped-virtually-understanding-digital-arrest-scams) (primary article not identified; anecdote)
- Hebbal engineer: held 11 Nov - 12 Dec 2024 per police (other reports: 25 Nov - 12 Dec) — [Deccan Herald](https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Fbengaluru%2Fengineer-loses-rs-11-8-cr-in-city-s-biggest-digital-arrest-scam-3330130) / [The News Minute](https://www.thenewsminute.com/karnataka/bengaluru-software-engineer-loses-rs-118-crore-in-digital-arrest-scam) (anecdote)
- A blog claims victims face "70-hour video interrogations" — [everybodylovesyourmoney.com](https://www.everybodylovesyourmoney.com/2026/02/19/the-digital-arrest-terror-how-scammers-legally-intimidate-victims-into-70-hour-video-interrogations.html) (low-quality secondary source; not used for parameters)

### Inferences
- "Digital arrest" durations are bimodal in reports: a short-fuse mode (hours, 5-55 h) and a long mode (days to weeks/months). Reports report total custody window, not continuous call time; victims may be on intermittent video check-ins.
- Because most reported cases span >2 hours total, a 2-hour long-session feature would flag nearly all digital-arrest cases, but would also need hard negatives (see below) to avoid false positives. Evidence for the 2-hour cut-off specifically is absent.

### Gaps
- No source gave the length of the initial unknown call before the switch to video. No source gave the continuous-session distribution. Police FIR text (which may state call logs) was not accessed.

## Remote-access apps, delay to install, install-to-payment gap, payments during the call, Play vs sideloaded

### Takeaway
Named apps in retrievable cases: AnyDesk, TeamViewer, QuickSupport (TeamViewer QuickSupport). No evidence found for RustDesk, Chrome Remote Desktop, AirDroid, Mobizen or Zoho Assist in Indian cases within this search budget. Delay-to-install and install-to-payment figures were not found.

### Cited Findings
- RBI cyber security cell alert (14 Feb 2019) warned fraudsters lure victims to download AnyDesk and noted similar apps exist; AnyDesk denied its app steals money — [BloombergQuint](https://www.bloombergquint.com/business/rbi-cautions-against-fraudulent-transactions-on-upi-platform) (old, pre-2024; official-origin warning relayed by press)
- Badlapur (Thane): caller posing as customer service had man install AnyDesk; Rs 9,53,363 moved; case under cheating and IT Act — [Udayavani](https://english.udayavani.com/article/thane-man-loses-rs-9-5-lakh-in-online-banking-fraud/1206415) (anecdote; year not shown)
- Telangana: QuickSupport at fake SBI-support request for "KYC" and "refund" — [Zee5](https://zee5.com/articles/two-arrested-for-cyber-fraud-through-fake-kyc-links-in-telangana) (anecdote)
- Mumbai 70-year-old: TeamViewer after card photo; "series of transactions", Rs 63k — [Free Press Journal](https://www.freepressjournal.in/mumbai/70-yr-old-duped-of-rs-63k-in-card-kyc-fraud) (anecdote)
- Delhi Police and security blogs describe screen-sharing pretexts (fake UPI-app support) — [Delhi Police cyber](https://cyber.delhipolice.gov.in/Appkyc.html), [Digital Wealth Safety](https://digitalwealthsafety.in/screen-sharing-scams-in-india-2026-how-anydesk-and-teamviewer-fraud-works-and-how-to-stop-it/) (blog; "Rs 5,000-50,000 per session" claim is uncited, do not use)
- Sideloaded APKs: RTO challan APK campaign delivered by SMS/WhatsApp (sideloaded, not Play) — Cyfirma, Greater Kashmir, Moneylife links above. Prevalence among UPI frauds: not found.

### Inferences
- Remote-access apps in the named cases (AnyDesk, QuickSupport, TeamViewer) are legitimate Play Store apps; the fraud is social engineering, so Play-install vs sideload cannot be told apart by app identity. Malicious APKs are a separate path (sideloaded via messaging links).
- Whether payment occurs during active call: in digital arrest, victims are instructed to keep the call/camera on while transferring (Pinjore: stay on camera 3 days; Hebbal: held under surveillance), which supports "payment while call active" for that playbook; for remote-access KYC cases it is implied (the caller controls the screen) but no timing data was found.

### Gaps
- No documented minutes-to-install or minutes-to-payment distributions. No data on RustDesk, Chrome Remote Desktop, AirDroid, Mobizen, Zoho Assist in Indian cases found. No share of sideloaded vs Play installs. No McAfee/Kaspersky/Zimperium/CloudSEK numbers retrieved.

## Case table (anecdotal unless noted; every row is single-article)

Columns: # | Date | City | Victim | Duration | Amount | Apps / channel | Transfers | Source. "n/r" = not reported in what I retrieved.

| # | Date | City | Victim | Duration | Amount | Apps/channel | Transfers | Source |
|---|---|---|---|---|---|---|---|---|
| 1 | 11 Nov-12 Dec 2024 (alt. 25 Nov start) | Bengaluru (Hebbal) | 39 y, software engineer | about 18-31 days | Rs 11.8 cr | Telecom/police impersonation, call/video (app n/r) | at least 2 reported: Rs 75 L, then Rs 3.41 cr | [TNM](https://www.thenewsminute.com/karnataka/bengaluru-software-engineer-loses-rs-118-crore-in-digital-arrest-scam) |
| 2 | from 15 Sep 2024, complaint 2025 | Bengaluru | 57 y, software engineer (woman) | about 6 months | Rs 31.83 cr | Skype, DHL/CBI pretext | 187 | [DT Next](https://www.dtnext.in/news/national/bengaluru-woman-loses-rs-3183-cr-in-months-long-digital-arrest-scam-involving-fake-cbi-officers-853424) |
| 3 | Nov 2024 | Delhi | retired engineer | at least 8 h | Rs 10.3 cr | Skype | "separate accounts" (n/r) | [The Week](https://www.theweek.in/wire-updates/national/2024/11/14/des85-dl-digital-arrest.html) |
| 4 | n/r (FIR 18 Nov) | Bengaluru | retired colonel | about 2 weeks | Rs 56.05 L | video calls, fake RBI verification | n/r | [Deccan Herald](https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Fbengaluru%2Fbengaluru-retired-colonel-cheated-of-rs-56-lakh-under-digital-arrest-for-two-weeks-3805014) |
| 5 | n/r | Faridabad | retired labour dept official (woman) | 18 days | Rs 40 L | TRAI/Mumbai Police, video + WhatsApp warrant | n/r | [Tribune](https://www.tribuneindia.com/news/haryana/retired-govt-official-becomes-victim-of-digital-arrest-duped-of-rs-40-lakh/) |
| 6 | n/r | Faridabad | retired IAF sergeant | 55 h | Rs 5 L | TRAI/CBI | n/r | [Deccan Herald](https://www.deccanherald.com/amp/story/india%2Fharyana%2Fduped-of-rs-5-lakhs-retired-air-force-personnel-becomes-victim-of-digital-arrest-in-faridabad-3293885) |
| 7 | n/r | Pune | 84 y and wife | n/r | Rs 50.5 L | ATS/CID impersonation | n/r | [Outlook Money](https://www.outlookmoney.com/news/digital-arrest-scam-how-fraudsters-trapped-a-pune-retiree-into-transferring-rs-50-lakh) |
| 8 | n/r | Nagpur | 70 y retired professor | n/r | Rs 16.5 L | digital arrest | n/r | [FPJ](https://www.freepressjournal.in/mumbai/70-year-old-retired-professor-from-nagpur-loses-165-lakh-in-digital-arrest-scam) |
| 9 | reported Aug 2026 (per search summary; verify) | Chh. Sambhajinagar | retired police officer | n/r | Rs 19 L | fake NIA, video call | several accounts | [FPJ](https://www.freepressjournal.in/mumbai/retired-police-officer-loses-19-lakh-in-digital-arrest-scam-after-fake-nia-officials-threaten-terror-link-probe) |
| 10 | Aug 2025 (article date) | Delhi | ex-govt official | n/r | Rs 9 L | digital arrest | n/r | [The Week](https://www.theweek.in/wire-updates/national/2025/08/23/des51-dl-digital-arrest-held.html) |
| 11 | 2025 | Pinjore/Chandigarh | 83 y retired HMT employee | 3 days | Rs 57.9 L | WhatsApp video, fake Hyderabad police | n/r (within 3 days) | [Tribune](https://www.tribuneindia.com/news/chandigarh/third-accused-held-in-57-9l-digital-arrest-fraud) |
| 12 | Feb-Mar 2025 | Kolkata | businessman | 12 days | Rs 75.5 L | digital arrest | n/r | [ISACA](https://www.isaca.org/resources/news-and-trends/industry-news/2025/trapped-virtually-understanding-digital-arrest-scams) (weak) |
| 13 | n/r | Bengaluru | retired professor | within 5 h | n/r | digital arrest | n/r | search summary (weak) |
| 14 | n/r | Amritsar | retired SMO | about 2 days | Rs 23 L | RTGS on instruction | n/r (all funds) | [Tribune](https://www.tribuneindia.com/news/amritsar/retired-smo-in-amritsar-loses-rs-23-lakh-in-digital-arrest-scam) |
| 15 | n/r | Delhi | retired officer | 3 days | Rs 48.5 L | WhatsApp video, TRAI/CBI/fake judges | n/r | [Tribune](https://www.tribuneindia.com/news/delhi/digital-arrest-scam-delhi-cyber-police-arrest-3-after-retired-officer-cheated-of-rs-48-5-lakh/amp) |
| 16 | May 2025 | Delhi | 92 y | n/r | Rs 2 cr+ recovered (loss n/r) | digital arrest | n/r | [AIR](https://www.newsonair.gov.in/delhi-police-busts-digital-arrest-scam-recovers-₹2-crore-duped-from-92-year-old) |
| 17 | n/r | Goa | woman | n/r | Rs 2.6 cr | digital arrest | n/r | [Bhaskar Live](https://bhaskarlive.in/others/ed-arrests-rtgs-agent-involved-in-rs-26-crore-digital-arrest-of-goa-woman-2154780) (ED) |
| 18 | 1-16 Sep 2025 | Ambala region (per SC reports; city not in my snippets) | elderly couple | 16 days | Rs 1.5 cr | phone + video, forged SC orders | n/r | [FPJ](https://www.freepressjournal.in/india/digital-arrest-scams-cbi-crackdown-widens-as-supreme-court-keeps-up-pressure) (court-record derived) |
| 19 | n/r | Badlapur, Thane | n/r | n/r | Rs 9,53,363 | AnyDesk, fake customer service | n/r | [Udayavani](https://english.udayavani.com/article/thane-man-loses-rs-9-5-lakh-in-online-banking-fraud/1206415) |
| 20 | n/r | Mumbai | 70 y | n/r | Rs 63k | TeamViewer, card KYC | series | [FPJ](https://www.freepressjournal.in/mumbai/70-yr-old-duped-of-rs-63k-in-card-kyc-fraud) |
| 21 | n/r | Telangana | n/r | n/r | n/r | QuickSupport, fake SBI KYC | n/r | [Zee5](https://zee5.com/articles/two-arrested-for-cyber-fraud-through-fake-kyc-links-in-telangana) |

Only 21 rows (below the 25 target), and most lack call duration, transfer count and app. The note does not pad this with invented rows. Victim age: 8 of the 21 rows give an age or "retired" (all digital-arrest victims in this sample are retirees/elderly, 39 y being the exception); the Supreme Court bench described victims as mostly elderly (source above). This sample is selected by what the search engine returned (retirees and large amounts) and is biased toward big-ticket cases.

### Inferences
- Payment count ranges from 1-2 (Hebbal first two reported) to 187 (Bengaluru); mean transfers is not estimable from this sample.
- Amounts in this sample range Rs 63k to Rs 31.83 cr; digital arrest median in sample is about Rs 40-50 L, but sample is biased upward.

## Hard negatives (legitimate look-alikes)

### Takeaway
No source in this search quantified how often legitimate long calls, bank-support calls or IT remote sessions occur around UPI payments in India.

### Cited Findings
- None found with figures. Only generic guidance (e.g., advice to disconnect from video calls that last hours) exists in blogs, e.g. [savdhaan.in](https://savdhaan.in/scams/digital-arrest-scam) (non-authoritative).

### Inferences
- Hard negatives (family call while paying a known payee, own-bank support call, IT-support session) must be synthesised by the team from assumptions and labelled as assumed; the primary discriminators evidenced here are a new/unknown payee, a high-value transfer, and a sustained call with an official-sounding caller.

### Gaps
- No frequency data for legitimate scenarios; this would require telecom/bank telemetry or surveys. No data found on RustDesk/Chrome Remote Desktop/AirDroid/Mobizen/Zoho Assist; no sideloaded-APK prevalence; no P2P vs P2M split; no initial-call-length data. Recommended next steps: open Sansad AU2481, Rajya Sabha PQ 267, RBI Annual Report 2024-25 and I4C advisories directly (this session's fetch tool failed), and mine court/FIR-derived reports for call logs.
