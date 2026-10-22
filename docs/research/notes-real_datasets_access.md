# Real (non-synthetic) datasets reachable from the sandbox for UPI / coached-payment scam detection

Probe date: 2026-10-21, from the sandbox via the egress proxy, TLS verification on. Probes are curl `HTTP code` results. Bold entries marked "[sandbox-tested]" were requested from the container; everything else comes from web search and was not fetched from the container.

## Which candidate datasets can be downloaded without login from this container?

### Takeaway
Almost nothing useful is downloadable here. The proxy allows `raw.githubusercontent.com`, `pypi.org`, `repo.anaconda.com`, `bitbucket.org` and `s3.amazonaws.com` (307), and denies Kaggle, Hugging Face, Zenodo, UCI, data.gov.in, NPCI, RBI, IEEE DataPort, arXiv, archive.org, OpenML, figshare, OSF, Mendeley, jsDelivr and unpkg. None of the target data is hosted on an allowed host. The only real record-level data pulled was the 5,574-row UCI SMS Spam Collection through a GitHub mirror, plus the BAF paper and datasheet PDFs. Neither of those helps with UPI features.

### Cited Findings
- **Host reachability [sandbox-tested]**
  - Denied (`CONNECT tunnel failed, response 403`, recorded in `/__agentproxy/status`): `www.kaggle.com`, `huggingface.co`, `zenodo.org`, `archive.ics.uci.edu`, `data.gov.in`, `www.npci.org.in`. Per-host status for the other denied hosts is not individually broken out here.
  - Connection failed (curl code `000`): `ieee-dataport.org`, `unb.ca`, `androzoo.uni.lu`, `arxiv.org`, `rbi.org.in`, `pib.gov.in`, `sansad.in`, `ncrb.gov.in`, `openml.org`, `figshare.com`, `osf.io`, `data.mendeley.com`, `archive.org`, `drive.google.com`, `dropbox.com`, `cdn.jsdelivr.net`, `unpkg.com`, `indiadataportal.com`, `api.crossref.org`, `api.openalex.org`, `en.wikipedia.org`.
  - `github.com` (pages, codeload zips) and the `gh`/`api.github.com` repo endpoints return 403 "GitHub access to this repository is not enabled for this session. Use add_repo". I did not call `add_repo` (see Gaps).
  - Reachable: `raw.githubusercontent.com` (200 for public repos), `pypi.org`, `repo.anaconda.com`, `bitbucket.org`. `s3.amazonaws.com` (307) was not probed any further.
- **IEEE-CIS Fraud Detection (Kaggle competition)** [sandbox-tested]. The Kaggle competition URL returns 403 from the proxy. Amazon's Fraud Dataset Benchmark (FDB) loader pulls it from Kaggle and requires a Kaggle token plus joining the competition; otherwise it fails with ApiException 403. [FDB README](https://raw.githubusercontent.com/amazon-science/fraud-dataset-benchmark/main/README.md). FDB's class ratio for ieeecis is 3.50% (561,013 train / 28,527 test, 67 features in FDB's reduced set), from the same README. The FDB repository does not hold the data. No Hugging Face or GitHub mirror was found (search found only model repos and notebooks, e.g. [github.com/fariha123/IEEE-CIS-Fraud-Detection](https://github.com/fariha123/IEEE-CIS-Fraud-Detection)). The `fdb` name on PyPI is an unrelated Firebird package, and `fraud-dataset-benchmark` is 404 on PyPI. Verdict: not downloadable here.
- **Bank Account Fraud (Feedzai, NeurIPS 2022)** [sandbox-tested]. The data is distributed via [Kaggle](https://www.kaggle.com/datasets/sgpjesus/bank-account-fraud-dataset-neurips-2022) only; the GitHub repo holds code, notebooks and documents, not the CSVs ([README](https://raw.githubusercontent.com/feedzai/bank-account-fraud/main/README.md)). The Kaggle download endpoint returns a proxy 403. The datasheet says "tarball on GitHub and Kaggle", but I did not find the data files on GitHub raw. Downloaded the documents:
  - `/home/user/sartak/data_raw/baf_docs/datasheet.pdf` (222,883 bytes)
  - `/home/user/sartak/data_raw/baf_docs/BAF_paper.pdf` (413,661 bytes)
  - Source: raw.githubusercontent.com/feedzai/bank-account-fraud/main/documents/
  - Dataset licence: not confirmed (Kaggle page not reachable).
- **UCI SMS Spam Collection (English, real)** [sandbox-tested]. Downloaded a mirror, `/home/user/sartak/data_raw/sms_spam_uci_mirror/sms.tsv` (477,907 bytes, 5,574 rows: 4,827 ham, 747 spam; HTTP 200 from `https://raw.githubusercontent.com/justmarkham/pycon-2016-tutorial/master/data/sms.tsv`). This is a third-party mirror of the UCI file; UCI itself is blocked. Licence on the original is CC BY 4.0 per the UCI page, which I did not fetch, so treat it as unverified. UK/Singapore-era English SMS, not Indian, not payments.
- **Hinglish & English Financial Scam/Fraud Text Dataset** — [huggingface.co/bolewara/hinglish-scam-text-dataset](https://huggingface.co/bolewara/hinglish-scam-text-dataset). Blocked in the sandbox (ENOTFOUND/403). Per web search only: 3,787 rows, with just 35 hand-written Hinglish scam and 28 benign messages; the English part is UCI SMS Spam. Not real in-the-wild Hinglish data, and too small to train on.
- **Spam SMS in Hindi (IEEE DataPort)** — [ieee-dataport.org/node/14326](https://ieee-dataport.org/node/14326). 3,894 labelled Hindi messages (columns: Message, Label) per search; host unreachable here, and the page listed no files, so access likely needs login or the author. A Dravidian SMS spam dataset (Tamil/Telugu/Kannada/Malayalam/English) exists per search; no downloadable URL was verified.
- **ICFD-31k (IJCAI-ECAI 2026), Indian conversational fraud calls** — [GitHub repo, raw README fetched](https://raw.githubusercontent.com/SPELLAILab/ICFD-31k/main/README.md). The data itself is at Hugging Face `rishia2220/icfd-31k` (blocked). Its [DATASET_CARD.md](https://raw.githubusercontent.com/SPELLAILab/ICFD-31k/main/DATASET_CARD.md) says it is a synthetic Indian conversational fraud dataset and "The conversations are synthetic and do not replace validation on real calls". 31,000 conversations, 1,111,071 streaming chunks, English/Hinglish. [LICENSE-DATA.md](https://raw.githubusercontent.com/SPELLAILab/ICFD-31k/main/LICENSE-DATA.md): defensive research only, commercial deployment needs written permission. This is not real data.
- **UPI transaction datasets on GitHub/Kaggle**
  - [djdurga/upi-transactions-eda](https://raw.githubusercontent.com/djdurga/upi-transactions-eda/main/README.md) (README fetched [sandbox-tested]): columns Date, Category, RefNo, Withdrawal, Deposit, Balance. This looks like one individual's bank statement for 2023. The README states no fraud labels, no counterparties, no CSV in the repo (guessed filenames 404).
  - Kaggle "UPI Transactions 2024" (skullagos5246) and a 1,000-row Kaggle UPI set (willianoliveiragibin) are described as simulated, per [search results](https://baselight.app/u/kaggle/dataset/willianoliveiragibin_upi_payment). A DataCamp notebook shows a `fraud_flag` column in the former. Treat both as synthetic. Neither was reachable.
  - [NPCI P2P/P2M aggregate monthly series on India Data Portal](https://ckandev.indiadataportal.com/dataset/150fe363-f61f-41f2-9215-15f61358f427/resource/64589755-cfaa-4c0e-a8ef-3ac243327360): real but aggregate only, no fraud labels. Host unreachable from the sandbox.
- **Android RAT / banking trojan APK datasets**
  - [CICMalDroid 2020](https://unb.ca/cic/datasets/maldroid-2020.html): about 17,341 APKs in 5 classes (Adware, Banking, SMS, Riskware, Benign), per search.
  - [CIC-AndMal2020](https://unb.ca/cic/datasets/andmal2020.html): about 400k apps, with Trojan-Banker, Trojan-Dropper, Trojan-SMS and Trojan-Spy among its categories, per search.
  - AndroZoo: requires an API key and is not labelled by family.
  - AMD: reportedly no longer distributed (survey note via search).
  - All hosts were unreachable here, and no source I found confirms a dedicated RAT class or a list of legitimate remote-access apps such as AnyDesk, TeamViewer or QuickSupport. A watch-list of remote-access package names would have to be hand-curated.

### Inferences
- For the sandbox as configured, record-level downloads are limited to what sits on `raw.githubusercontent.com`. Any of the above can be unblocked only by allow-listing hosts or by the user downloading files and placing them in `/home/user/sartak/data_raw/`.
- Every Indian UPI and Hinglish scam text resource found is either synthetic, tiny, aggregate-only, or not scam-specific.

### Gaps
- I did not call `add_repo` for `feedzai/bank-account-fraud`, `amazon-science/fraud-dataset-benchmark` or `SPELLAILab/ICFD-31k`; it would not unblock Kaggle or Hugging Face anyway.
- I could not enumerate GitHub (search API and tree API are blocked), so repos that host UPI or Hinglish CSVs could be missed. I only know of repos surfaced by web search.
- Dataset licences for BAF, IEEE-CIS (Kaggle competition rules, non-commercial) and the Kaggle UPI sets were not verified.

## Which of these real datasets contain fields mapping onto our features?

### Takeaway
Only IEEE-CIS and BAF are plausible partial donors, and neither has call, install or payee data. None of the 16 features (unknown-contact call, unknown video, install during call, remote-access app, payee newness, payee added after call, sequence flag) exist in any public dataset I found. Only amount-based features (log amount ratio, robust z, repeat-to-payee) could be validated, and only on IEEE-CIS (not downloadable here).

### Cited Findings
- **BAF fields, verified from the [datasheet](https://raw.githubusercontent.com/feedzai/bank-account-fraud/main/documents/datasheet.pdf)** (downloaded here). Each row is a bank account opening application, not a payment. Columns include:
  - Amount-like: `intended_balcon_amount`, `proposed_credit_limit`, `income`
  - Velocity and history: `velocity_6h`, `velocity_24h`, `velocity_4w`, `zip_count_4w`, `bank_branch_count_8w`
  - Device and session: `source` (INTERNET or TELEAPP), `device_os`, `session_length_in_minutes`, `keep_alive_session`, `device_distinct_emails`, `device_fraud_count`, `foreign_request`
  - Label: `fraud_bool`, with `month` (0 to 7)
  - Prevalence: 1.1% per the [paper](https://raw.githubusercontent.com/feedzai/bank-account-fraud/main/documents/BAF_paper.pdf), eight months February to September.
  - Provenance: the instances are CTGAN-generated, trained on an anonymized real bank account opening dataset (datasheet Q4: "synthetic, feature-engineered bank account opening application"). So BAF is synthetic-from-real, not raw real. It is useful for temporal drift, class-imbalance and per-cohort (e.g. age group) conformal experiments. It is not payments, so no payee features.
- **IEEE-CIS columns (from my own knowledge of the Kaggle competition; not verified in this session, since the page was unreachable).** `TransactionAmt`, `TransactionDT` (seconds offset), `ProductCD`, `card1`-`card6`, `addr1`/`addr2`, `dist1`/`dist2`, `P_emaildomain`/`R_emaildomain`, `C1`-`C14` (counts, e.g. addresses linked to a card), `D1`-`D15` (time deltas), `M1`-`M9`, `V1`-`V339`, `isFraud`, plus an identity table with `DeviceType`, `DeviceInfo`, `id_01`-`id_38`. FDB reports a 3.5% fraud rate and 590,540 transactions in total (561,013 + 28,527 from the README). Fields are masked, so there is no real "new payee" flag. Closest proxies are `D` time-delta columns and `C` count columns, which are poor substitutes. The amount-ratio and robust z-score need a stable user key; `card1` plus `addr1` is a common (imperfect) pseudo-user key.
- **ICFD-31k** fields (`transcript`, `key_entities`, `chunk_level_analysis`, `final_verdict`) are text-only, synthetic ([DATASET_CARD.md](https://raw.githubusercontent.com/SPELLAILab/ICFD-31k/main/DATASET_CARD.md)). It has no call metadata or payment fields.
- **UCI SMS spam and Hindi SMS** are text only. Their use is an SMS-content feature, not part of the 16 on-device features.

### Inferences
- Realistic use of real data: (1) amount features and robust z-score distribution shape from IEEE-CIS `TransactionAmt`, if the user supplies the file; (2) cohort and drift conformal-calibration mechanics from BAF (flagged as synthetic-from-real); (3) nothing for call/install/payee interactions.
- Every call, install, payee-newness and ordered-sequence feature must stay simulated, with parameters taken from the published aggregates below.

### Gaps
- No Indian UPI per-user transaction history with fraud labels, no payee or beneficiary-age field, and no device or app-install event data were found.

## Real aggregate statistics usable to calibrate a simulator

### Takeaway
Government and RBI aggregates give base rates and amounts. All figures are from secondary reports of official documents surfaced by web search; none were fetched from primary sources (sansad.in, rbi.org.in and npci.org.in are blocked here). The `sansad.in` PDF link was returned by search but not opened.

### Cited Findings
- **UPI scale, September 2026**: 24.07 billion transactions worth Rs 29.37 lakh crore; average 802 million per day; volume about +23% and value about +18% year on year. Secondary reports of NPCI data: [StartupTalky](https://startuptalky.com/upi-transactions-september-2026/), [FinTech BizNews](https://fintechbiznews.com/fintech-digital-payment-/upi-txn-volume-value-fell-in-sept26-aeps-imps-volume-too-down).
- **UPI scale, FY25**: 185.8 billion transactions, Rs 261 lakh crore (RBI annual report, per [IANS](https://ianslive.in/upi-share-surges-to-837-pc-in-digital-transactions-for-fy25--20250530153004) and [MediaNama](https://www.medianama.com/2025/05/223-upi-84-india-fy25-retail-payment-volume-rbi/)). Another outlet gives Rs 260.6 lakh crore, so exact value varies slightly.
- **UPI fraud incidents (Finance Ministry, Lok Sabha Unstarred Q 2481, 15 Dec 2025)**:
  - FY2023-24: 13.42 lakh incidents, Rs 1,087 crore
  - FY2024-25: 12.64 lakh incidents, Rs 981 crore
  - FY2025-26 through November 2025: 10.64 lakh incidents, Rs 805 crore
  - Sources: [sansad.in PDF](https://eparlib.sansad.in/bitstream/123456789/3018042/1/AU2481_5bIzKk.pdf) (link seen in search, not opened), [Madhyamam](https://madhyamamonline.com/amp/india/upi-linked-frauds-amount-to-rs-805-crore-far-fy26-govt-1477281).
  - April to September 2024: 6.32 lakh cases, Rs 485 crore ([CyberPeace](https://www.cyberpeace.org/resources/blogs/domestic-upi-frauds-finance-ministry-presented-data-in-loksabha)).
- **Digital-payment fraud reported by banks (RBI data, Lok Sabha)**: FY2024-25 had 1,44,855 cases worth Rs 821.88 crore; FY2023-24 had 2,93,239 cases worth Rs 2,060.75 crore. The drop follows revised RBI fraud-reporting rules of 15 July 2024, so the series are not comparable. [ThePrint](https://theprint.in/india/banks-reported-rs-4457-cr-worth-of-digital-payment-fraud-over-11-yrs-close-to-half-of-it-was-in-2023-24/3004402/).
- **Fraud amount, FY2024**: Rs 14.57 billion digital payment fraud (more than fivefold), 10.4% of total fraud amount versus 1.1% in FY2023 ([Bloomberg via GulfNews](https://gulfnews.com/business/banking/online-payment-frauds-jump-over-400-in-india-rbi-data-shows-1.1717079200678)).
- **Derived (my arithmetic, not from a source)**: using the FY2024-25 figures above, UPI fraud incidents per transaction are about 12.64e5 / 185.8e9 = 6.8e-6 (about 0.0007%), and the mean fraud ticket is about Rs 981e7 / 12.64e5 = Rs 7,760. This mixes two sources (Finance Ministry fraud counts, RBI UPI volume) and the reporting bases may differ. Treat as an order-of-magnitude prior (fraud is extremely rare per transaction), not a calibrated rate.
- **IEEE-CIS fraud rate 3.5%** and **BAF prevalence 1.1%** are available as benchmark-level imbalance references, but both are non-Indian, and BAF is not payments.

### Inferences
- A deployed on-device prior should be around 1e-5 per transaction in the general population; any evaluation set with 1% to 3.5% positives is an enriched sample, and precision at deployment will be far lower than on that sample.
- The mean ticket (about Rs 7,760) is a useful anchor for the "log amount ratio vs user median" range in simulation, but it is an average across all fraud types, not coached scams.

### Gaps
- No source found giving the share of UPI fraud involving remote-access apps, payee-newness, or time between call and payment. Searches for RBI Payment Systems Report mode breakdowns and AnyDesk statistics returned nothing usable.
- Median/percentile victim loss, per-user transaction-count distribution, and P2P versus P2M fraud split were not found.
- Figures were not confirmed against primary documents; one outlet's UPI FY25 value differs slightly.

## Is there any public dataset of real coached/remote-access scam event sequences (call + install + payment)?

### Takeaway
No. I found none, and I looked for it specifically. The nearest public resources are synthetic scam-call transcripts (ICFD-31k), Hinglish/Hindi SMS corpora, generic Android malware APK datasets, and aggregate government statistics. Such sequences would be held privately by banks, NPCI, I4C or telcos.

### Cited Findings
- ICFD-31k states its conversations are synthetic ([DATASET_CARD.md](https://raw.githubusercontent.com/SPELLAILab/ICFD-31k/main/DATASET_CARD.md)) and has no install or payment events.
- Android malware datasets (CICMalDroid, CIC-AndMal2020) are static or dynamic app-behaviour data, not victim event timelines ([search results](https://unb.ca/cic/datasets/maldroid-2020.html)).
- Web searches for UPI, remote-access scam, Hinglish scam and call-metadata datasets returned no dataset linking call, install and payment events.

### Inferences
- The ordered-sequence feature (call -> install -> new payee -> pay) and its interactions can only be trained on simulated sequences. Report the model as validated against simulation plus public aggregates, not against real coached-scam data.
- Realistic route to real data: a data-sharing agreement with a bank/NPCI/I4C, or a labelled opt-in pilot.

### Gaps
- Absence of evidence only: I could not search GitHub, Kaggle, Hugging Face, IEEE DataPort or data.gov.in directly from the sandbox, so a niche dataset could exist that web search missed.
