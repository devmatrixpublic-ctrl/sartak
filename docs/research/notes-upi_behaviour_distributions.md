# UPI behaviour distributions for calibrating a legitimate-session simulator (India)

Method caveat: npci.org.in, worldline.com, arxiv.org and most news hosts were not directly fetchable from the research sandbox (DNS/proxy 403). Almost every figure below comes from a web-search summary of the cited page, not from my reading of the primary document. Treat every number as "secondhand, verify against primary" unless stated otherwise. Only the PhonePe Pulse README/licence was read directly. Figures marked [INFERRED] are my own arithmetic.

## 1. Overall volumes, ticket size, P2P vs P2M

### Takeaway
UPI runs at roughly 21-24 bn transactions and Rs 28-30 lakh crore per month in 2026. P2M is about 63% of count; P2P is about 71-72% of value. Mean ticket is about Rs 1,300 overall, about Rs 590 for P2M and about Rs 2,600 for P2P.

### Cited Findings
- Jan 2026: 21.7 bn txns, Rs 28.33 lakh cr (Dec 2025: 21.63 bn, Rs 27.97 lakh cr) — [Entrackr](https://entrackr.com/news/upi-sets-new-monthly-record-with-217-bn-transactions-in-january-11063663) (NPCI data as reported; secondhand)
- Feb 2026: 20,394 mn txns — [Meetanshi](https://meetanshi.com/blog/upi-statistics/) (blog, secondhand)
- May 2026: 23.20 bn, about Rs 29.90 trn — [Adda247](https://currentaffairs.adda247.com/upi-hits-record-high-in-may-2026-with-₹29-90-trillion-worth-transactions/) (secondhand)
- Jul 2026: 23.66 bn, Rs 29.88 lakh cr, record; source notes these are industry-reported, not NPCI-confirmed — [StartupTalky](https://startuptalky.com/india-upi-transactions-july-2026/)
- FY2025-26: >24,162 crore (about 241.6 bn) txns, about Rs 314 lakh cr — Finance Ministry statement as reported at [YourStory](https://yourstory.com/2026/08/upi-completes-10-years-clocks-nearly-13000-fold-rise-transaction-volume)
- Calendar 2025: 228.5 bn txns; overall ATS fell 9% to Rs 1,314; P2M ATS Rs 592; P2M volume 143.82 bn (+34%) — [Worldline press release](https://worldline.com/en-in/home/top-navigation/media-relations/press-releases/worldline-reports-that-india-digital-payments-cross-new-milestones-as-upi-reaches-228-billion-transactions-in-2025). Another blog gives ATS Rs 1,293 ([Meetanshi](https://meetanshi.com/blog/upi-statistics/)); the two conflict slightly.
- H1 2025 (Worldline): overall ATS Rs 1,348 (H1 2024: Rs 1,478); P2P 39.35 bn txns, P2M 67.01 bn; P2P value Rs 103.86 trn, P2M Rs 39.48 trn; P2M ATS Rs 589 — [Worldline 1H 2025 PDF](https://worldline.com/content/dam/worldline/local/en-in/documents/main-page11111/Worldline-India-Digital-Payment-Report-1H-2025-1.pdf) (via search summary; the Rs 589 was from a third-party summary)
- H2 2024 (Worldline): P2P ATS Rs 2,666, P2M ATS Rs 627 — [Worldline 2H 2024 PDF](https://worldline.com/content/dam/worldline/local/en-in/documents/main-page11111/Worldline-India-Digital-Payments-Report-2H-2024.pdf)
- P2M about 63% of volume, P2P about 71% of value (H1 2025, NPCI data) — [TaxTMI](https://www.taxtmi.com/news?id=72606)

### Inferences
- [INFERRED] H1 2025 P2P mean = 103.86e12 / 39.35e9 = about Rs 2,640; P2M = 39.48e12 / 67.01e9 = about Rs 589. P2M count share = 67.01/106.36 = 63%; P2P value share = 72.5%. Consistent with the published 63%/71%.
- Mean tickets are drifting down about 7-9% per year (small-ticket growth), so use 2025-26 values, not 2022-23 ones.

### Gaps
- NPCI product-statistics page not reachable; monthly figures and any official P2P/P2M split are only secondhand. No published median ticket size found.

## 2. Amount distributions (share under Rs 100/500/1000/5000/10000/1 lakh)

### Takeaway
Only one published band exists: about 86% of P2M and about 59% of P2P transactions are below Rs 500. No published shares for the other thresholds and no published fitted family or parameters were found.

### Cited Findings
- FY2025-26: 86% of P2M txns below Rs 500; 59% of P2P below Rs 500 (41% above) — [Vision IAS](https://visionias.in/blog/current-affairs/upi-at-10-how-india-built-the-worlds-largest-real-time-payments-platform) and [TaxTMI](https://www.taxtmi.com/tmi_blog_details?id=918741). Period and primary source unverified; reported by other outlets from government-cited releases.
- A "recent report" says txns below Rs 200 are nearly 70% of volume — same search result set ([IIMB/Forbes India piece](https://www.iimb.ac.in/cdpg/pdf/digital-public-infrastructure-truly-scalable.pdf)); not verified, and plausibly in tension with the 86%/59% figures only if blended (blend = 0.63*86 + 0.37*59 = about 76% below Rs 500 [INFERRED]).
- 2022: nearly 7 in 10 UPI txns were under Rs 500 — [Business Standard](https://www.business-standard.com/amp/article/economy-policy/statsguru-six-charts-explain-the-rise-of-upi-digitisation-challenges-122082800820_1.html) (older)

### Inferences
- [INFERRED] Lognormal moment/quantile fit using (mean, P(<500)): 
  - P2M: mean 589, P(<500)=0.86 gives mu=3.73, sigma=2.30 (median about Rs 42). Model-implied CDF: <100 about 0.65; <1000 about 0.92; <5000 about 0.98; <10000 about 0.993; <1 lakh about 0.9996.
  - P2P: mean 2,640, P(<500)=0.59 gives mu=5.74, sigma=2.07 (median about Rs 311). Implied CDF: <100 about 0.29; <1000 about 0.71; <5000 about 0.91; <10000 about 0.95; <1 lakh about 0.997.
  - These are NOT published fits. Sigma is likely overstated because a real mean is inflated by round-number large transfers and a hard Rs 1 lakh cap, and real amounts cluster on round numbers (10, 20, 50, 100, 500, 1000...). Median P2M of about Rs 42 is also unvalidated.
- Recommendation: model log-amount as a mixture rather than one lognormal: e.g. P2M lognormal(mu about 3.7-4.2, sigma about 1.6-2.3) with a round-number snap; P2P lognormal(mu about 5.7-6.0, sigma about 1.8-2.1) truncated at Rs 1 lakh (UPI per-txn cap). Fit-check against 86%/59% below Rs 500 and mean ATS.

### Gaps
- No paper or report giving fitted parameters, medians, or shares at Rs 100/1000/5000/10000/1 lakh.

## 3. Per-user frequency, payees, time of day, age bands

### Takeaway
Real user-level distributions (new-payee rate, top-N concentration, per-user counts by age) were not found in any public source. Only coarse survey and aggregate proxies exist.

### Cited Findings
- RBI deputy governor: about 400 mn active UPI users (cited in the search summary of [Meetanshi](https://meetanshi.com/blog/upi-statistics/)); secondhand.
- LocalCircles survey: 1 in 2 UPI users do more than 10 transactions per month — [Deccan Herald](https://www.deccanherald.com/business/economy/majority-of-users-to-stop-using-upi-if-it-attracts-transaction-fee-survey-2920091)
- UPI-on-credit-card users average 40 txns per month; 78% of that base under age 40 — [Business Standard / Kiwi](https://www.business-standard.com/amp/industry/news/upi-enabled-credit-cards-see-20-monthly-growth-users-avg-40-transactions-125012201030_1.html) (skewed sample)
- Time of day (Gen Z-focused report, undated, source data unclear): metro peaks 6-11 am (groceries) and 6-11 pm (restaurants), minor midnight-6 am bump (food delivery); Friday 7-8 pm highest weekly count — [Outlook Money](https://www.outlookmoney.com/spend/gen-z-leads-high-frequency-small-value-digital-payments-says-report)
- NPCI operational peak windows 10 am-1 pm and 5 pm-9:30 pm — [BoomLive](https://www.boomlive.in/web-stories/news/npci-rolls-out-new-limits-on-upi-balance-checks-among-other-guidelines-2463)
- Card-spending analogue (not UPI): average ticket rises roughly 2x from age 18 to 60, counts peak in the 30s — [arXiv 1505.03854](https://arxiv.org/pdf/1505.03854)
- Academic UPI work found is survey/aggregate only: CSCW'24 UPI spending-behaviour study [arXiv 2401.09937](https://arxiv.org/html/2401.09937v2) (not read; method presumed survey); seniors adoption thesis [JYU](https://jyx.jyu.fi/jyx/Record/jyx_123456789_95943/Details) (adoption barriers only).
- PhonePe Pulse (read directly): aggregated/map/top data at country/state/district level, quarterly Q1 2018-Q2 2026; transaction categories P2P, Utilities, Business (merchant); registered users and merchants; no age bands, no time of day, no amount distribution; licence CDLA-Permissive-2.0 — [GitHub PhonePe/pulse](https://github.com/PhonePe/pulse)

### Inferences
- [INFERRED] 20.4-23.7 bn monthly txns / about 400 mn active users = about 50-59 txns per active user per month on average (mean, heavy-tailed; many users have multiple apps/accounts and "active" definitions differ). The LocalCircles median is >10, consistent with a skewed distribution (mean well above median).
- Recommended count model: negative binomial or lognormal per user per month, median about 15-25, mean about 50, heavy right tail (dispersion high). Uncertainty: factor of 2 on both median and mean; the shape is a modelling choice, not published.
- New-payee probability and top-N concentration: no data. Use an explicit assumption: P2M repeat-heavy (Zipf-like payee popularity), P2P new-payee share a tunable parameter (suggest sweep 5-25% of P2P, 20-40% of P2M for first-contact merchants such as QR shops) and flag as ASSUMED. Do not present as sourced.
- Age: no 60+ vs 18-35 UPI numbers found. Only the directional card analogue (older: fewer, larger). Treat as ASSUMED.

### Gaps
- New-payee rate, top-N payee concentration, per-user payments per day/week, age-band behaviour, hour-by-hour national curve: not found in any public source I could reach. Internal PSP data (PhonePe, GPay, Paytm) would be required.

## 4. Fraud base rates

### Takeaway
Reported UPI fraud is about 1 in 1.47 lakh transactions by count (matches design docs), with average reported loss around Rs 7,500-7,800; by value, small-count high-value cases dominate.

### Cited Findings
- FY2024-25: 12.64 lakh UPI fraud cases, Rs 981 cr; FY2023-24: 13.42 lakh, Rs 1,087 cr; FY2025-26 to Nov: 10.64 lakh, Rs 805 cr (Lok Sabha reply, from CPFIR complaints) — [IANS](https://ianslive.in/upi-frauds-worth-rs-805-crore-witnessed-this-fiscal-so-far-minister--20251215175703), [BoomLive](https://www.boomlive.in/web-stories/india/upi-fraud-cases-and-losses-rise-over-five-years-finance-ministry-tells-lok-sabha-2755)
- H1 FY25: UPI frauds Rs 485 cr — [Inc42](https://inc42.com/buzz/india-saw-upi-frauds-worth-inr-485-cr-in-h1-fy25)
- 30 months: 27 lakh cases worth Rs 2,145 cr — [Moneylife](https://moneylife.in/article/upi-frauds-27-lakh-cases-worth-rs2145-crore-registered-in-30-months-govt/75709.html)
- RBI April 2026 discussion paper (NCRP data, all digital frauds, not UPI-only): txns above Rs 10,000 are about 45% of fraud cases by count but about 98.5% by value; cases rose from 2.6 lakh (2021) to 28 lakh (2025), value Rs 551 cr to Rs 22,931 cr — [Outlook Business](https://www.outlookbusiness.com/economy-and-policy/rbi-proposes-1-hour-delay-for-transactions-above-10000-to-fight-digital-fraud), [Moneylife](https://moneylife.in/article/digital-payment-frauds-under-watch-rbi-proposes-1hour-delay-transaction-caps-and-kill-switch-to-counter-scams/80179.html). Proposal only (1-hour delay for APP txns >= Rs 10,000; whitelisted payees and merchants exempt).
- Underreporting: LocalCircles found 51% of victims filed no complaint — [Business Standard](https://www.business-standard.com/finance/news/upi-transaction-fraud-india-survey-one-in-five-users-hit-localcircles-125062601141_1.html); 2023 Praxis: about 50% of fraud txns under Rs 10,000 — same search result set (older).
- RBI AR 2024-25: 13,516 digital-payment fraud cases (56.5% of bank frauds), about Rs 520 cr — Business Standard link above (labelling inconsistent across outlets; bank-reported, different scope).

### Inferences
- [INFERRED] Base rate: 12.64 lakh / about 185.9 bn FY25 UPI txns (FY25 volume from my background knowledge, not verified here) = about 1 in 1.47 lakh (about 6.8e-6 per transaction). With FY26: 10.64 lakh in 8 months vs about 160 bn txns = about 1 in 1.5 lakh. Average reported loss: 981 cr / 12.64 lakh = about Rs 7,760; 805 cr / 10.64 lakh = about Rs 7,570 (mean; median is likely much lower).
- Because reported-only and 51% non-reporting in one survey, true rate may be higher; for a simulator, treat 6.8e-6 as a floor for fraud prevalence among attempts that reach the rail, and oversample for training.
- Amount band share for UPI fraud: only the RBI 45%/98.5% split above Rs 10,000 (all digital) — [INFERRED] about 55% of cases are at or below Rs 10,000.

### Gaps
- No UPI-specific amount-band table by year; RBI AR band table not accessed.

## 5. Open datasets

### Cited Findings
- PhonePe Pulse, CDLA-Permissive-2.0, aggregates only — [GitHub](https://github.com/PhonePe/pulse)
- NPCI monthly P2P/P2M aggregate series (India Data Portal; licence not stated) — [IndiaDataPortal](https://ckandev.indiadataportal.com/dataset/150fe363-f61f-41f2-9215-15f61358f427/resource/64589755-cfaa-4c0e-a8ef-3ac243327360)
- Synthetic only (not real): Kaggle "UPI Transactions" (willianoliveiragibin) [Baselight mirror](https://baselight.app/u/kaggle/dataset/willianoliveiragibin_upi_payment); Mendeley "Digital Payments 2025" (synthetic, aggregate) [DOI 10.17632/7c6pwhj2h6](https://data.mendeley.com/datasets/7c6pwhj2h6); AgamiAI Indian-Bank-Statements, Apache-2.0, synthetic [HF](https://huggingface.co/datasets/AgamiAI/Indian-Bank-Statements/blob/main/README.md). Licences for Kaggle sets unchecked.

### Gaps
- No open dataset of real or anonymised user-level UPI transactions was found.

## 6. Parameter recommendations and uncertainty (summary)

| Item | Recommended | Basis | Uncertainty |
|---|---|---|---|
| P2M share (count / value) | 63% / about 28% | Worldline/NPCI via TaxTMI | Low (+-2pp) |
| P2M log-amount | LogN(mu 3.7, sigma 2.3) fit; 86% < Rs 500; mean about Rs 590 | [INFERRED] from published mean + band | High on sigma and median |
| P2P log-amount | LogN(mu 5.74, sigma 2.07), truncated at Rs 1 lakh; 59% < Rs 500; mean about Rs 2,640 | [INFERRED] | High; round-number clustering missing |
| Txns per active user/month | Heavy-tailed, mean about 50, median about 15-25 | [INFERRED] from volume / 400 mn users; LocalCircles median >10 | Factor ~2 |
| New-payee rate | ASSUMED (P2P 5-25%, P2M first-visit 20-40%) | no data | Unknown |
| Top-N payee concentration | ASSUMED Zipf-like | no data | Unknown |
| Age effects (60+) | ASSUMED fewer/larger txns | card analogue only | Unknown |
| Fraud base rate | about 6.8e-6 per txn (1 in 1.47 lakh), mean loss about Rs 7.6k | Lok Sabha replies + FY25 volume (unverified) | Underreported; true rate higher |
