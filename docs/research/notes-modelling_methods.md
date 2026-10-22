# Methods note: tiny deterministic rare-event detector (logistic regression + per-cohort split-conformal thresholds, Kotlin port)

Research caveat: WebFetch could not reach arxiv.org, scikit-learn.org or Wikipedia from this environment (DNS failure), so only search-result summaries were available. Claims in "Cited Findings" are what those summaries state. Standard-theory facts and my own arithmetic are in "Inferences" and are marked as not source-verified; the report writer should treat them as derivations to be checked by the golden-vector / simulation tests, not as cited facts.

## 1. Split-conformal / one-class (novelty) thresholds at alpha = 0.001, small cohorts

### Takeaway
Use the legitimate-only calibration scores of each cohort, set the alarm threshold at the ceil((n+1)(1-alpha))-th smallest score, and refuse to issue a cohort-specific threshold unless n >= 999 (otherwise fall back to a pooled/hierarchical threshold or an inflated one). The guarantee is marginal and its realised variance at n ~ 1,000-10,000 is large.

### Cited Findings
- Angelopoulos & Bates, "A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification" (arXiv 2107.07511; Foundations and Trends monograph) is the practical tutorial; it describes split conformal as fitting the model once but needing a held-out calibration set, trading statistical efficiency for computation — [arXiv PDF](https://arxiv.org/pdf/2107.07511); [monograph summary](https://nowpublishers.com/article/DownloadSummary/MAL-101)
- Search could not retrieve the exact quantile sentence; it is previewed in Section 1.2 of the tutorial — [arXiv PDF](https://arxiv.org/pdf/2107.07511). The later book "Theoretical Foundations of Conformal Prediction" (Angelopoulos, Barber, Bates) has a split-conformal section and the coverage proof — [arXiv 2411.11824](https://arxiv.org/pdf/2411.11824v5)
- Bates, Candès, Lei, Romano, Sesia, "Testing for outliers with conformal p-values", Annals of Statistics 51(1):149-178 (2023), DOI 10.1214/22-AOS2244: frames outlier detection as testing whether new points come from the same distribution as a reference set; conformal p-values are marginally valid but dependent across test points, are positively dependent (PRDS), which gives exact FDR control (Benjamini-Hochberg) in a weak marginal sense; also gives a conditionally valid (training-conditional) variant with independent p-values using concentration inequalities, and a uniform confidence bound on the false positive rate of any outlier detector as a function of the threshold — [Project Euclid](https://projecteuclid.org/journals/annals-of-statistics/volume-51/issue-1/Testing-for-outliers-with-conformal-p-values/10.1214/22-AOS2244.full); [ar5iv of arXiv 2104.08279](https://ar5iv.labs.arxiv.org/html/2104.08279)
- Mondrian conformal prediction (Vovk et al., 2005, ch. 4.5; one source cites 2003, year not verified) splits calibration data by a discrete category and runs conformal in each; validity holds per category if data are exchangeable within the category; X-conditional coverage is impossible in general — [Class-Conditional Conformal Prediction with Many Classes](https://arxiv.org/pdf/2306.09335)
- Per-group splitting is overly conservative when groups have little calibration data; "clustered conformal" (Ding et al., 2023) and "Kandinsky" overlapping-group conformal are the published fixes — [arXiv 2306.09335](https://arxiv.org/pdf/2306.09335); [Kandinsky CP](https://arxiv.org/html/2502.17264v1)

### Inferences
(Standard conformal theory; not retrieved verbatim — verify with simulation.)
- Rule: let n = number of legitimate calibration scores in the cohort, score s = logit or probability (higher = more suspicious). k = ceil((n+1)(1-alpha)). If k <= n, threshold t = k-th smallest score; alarm iff s_new > t (strict, or >= with tie handling—pick one and test it). If k > n, the threshold is +infinity (no alarm possible). Compute k in integer arithmetic to avoid float error: with alpha = 1/1000, k = ((n+1)*999 + 999) // 1000. Do not use floor(0.999*(n+1)) or float ceil.
- Minimum n: need (n+1)(1-alpha) <= n, i.e. n >= (1-alpha)/alpha = 999. Check: n=999 gives k=ceil(1000*0.999)=999=n (threshold = max calibration score); n=998 gives k=ceil(999*0.999)=999>998 (infinite). At n=999 the threshold is the maximum, so it is noisy and highly sensitive to a single outlier; treat 999 as a hard floor and about 3,000-10,000 as a practical target.
- The guarantee is marginal over calibration draw + test point: P(false alarm) <= alpha, and exactly in [alpha - 1/(n+1)... alpha] for continuous no-tie scores. Conditional on a given calibration set the realised false-alarm rate is Beta-distributed: the exceedance mass is about Beta(n+1-k, k). With n=999 (k=999) the realised rate is ~Beta(1,999): mean 0.001 but the 95th percentile is about 0.003. With n=10,000 (k=9,991) exceedance count parameter is 10, so relative sd about 1/sqrt(10) = 32%. This is why the Bates et al. training-conditional (PAC-style) variant exists; if a "no more than 0.1% with 95% confidence" statement is required, inflate the quantile level (use a higher order statistic) or use that variant.
- Small cohorts, in order of preference: (1) hierarchical fallback: cohort threshold if n_cohort >= n_min (e.g. 2,000); else pooled-all-legit threshold; (2) conservative inflation: use a higher-order statistic or add a safety margin so that the Beta upper bound, not the mean, equals alpha; (3) cluster similar cohorts (clustered conformal) before pooling; (4) never silently use a cohort threshold with k > n. Record in the exported JSON: n_cal, k, method used ("cohort"/"pooled"/"inf") per cohort, so the Kotlin app can display and audit it.
- Because a pooled fallback only guarantees marginal validity over the pooled population, per-cohort false-alarm rates can still differ; report them (section 5).
- Calibration scores must come from users disjoint from training (section 6) and exchangeable with deployment legitimate sessions; any drift breaks the guarantee, so monitor the alarm rate in production.
- Ties: scores are continuous after standardisation, but if clipping/rounding creates ties at the threshold, use strict ">" and add a test with a tied calibration set.

### Gaps
- Exact wording of the quantile formula and its coverage theorem could not be fetched (arxiv.org unreachable); the writer should cite Angelopoulos & Bates Section 1.2 / Appendix and Vovk et al. (2005) without quoting.
- Training-conditional (PAC) calibration constants for alpha=0.001 were not retrieved.

## 2. Logistic regression on heavily imbalanced data; shifted scores; PPV at the real base rate

### Takeaway
Class weighting (or resampling) only shifts the logit by a roughly constant amount, so ranking and the conformal threshold on legitimate-only scores are unaffected; but the model's output is not a real-world probability, so PPV must be computed by Bayes with the 1-in-147,000 base rate, which makes PPV tiny at alpha = 0.001.

### Cited Findings
- scikit-learn `class_weight='balanced'` uses n_samples / (n_classes * bincount(y)); `sample_weight` multiplies on top of class weights; the intercept is a synthetic feature scaled by `intercept_scaling` and is penalised like other coefficients unless that is raised — [scikit-learn LogisticRegression docs](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html)
- King & Zeng (2001), "Logistic Regression in Rare Events Data", Political Analysis 9:137-163 argue standard logit underestimates rare-event probabilities and propose prior correction of the intercept plus small-sample bias correction (ReLogit); critics (Allison) prefer Firth penalisation, and a 2021 comparison finds King-Zeng estimators bias average predicted probabilities — [JSS ReLogit](https://www.jstatsoft.org/article/view/v008i02); [Firth vs King-Zeng, arXiv 2101.07620](https://arxiv.org/pdf/2101.07620)
- On BAF-style data, a trivial "always legitimate" classifier is ~99% accurate, so accuracy is meaningless; use recall at fixed FPR — [FairGBM](https://arxiv.org/pdf/2209.07850)

### Inferences
(Derivations; not from a retrieved source.)
- Prior shift: with training prevalence pi_tr and target prevalence pi_real, the correct logit is z_corrected = z_model + log(pi_real/(1-pi_real)) - log(pi_tr/(1-pi_tr)) for unweighted training. For balanced weighting the model already behaves as if pi_tr = 0.5, so the shift is log(pi_real/(1-pi_real)) = about -11.9 for pi_real = 1/147,000. This is a monotone, constant shift: the alarm decision "score > conformal quantile of legit scores" is identical whether you use raw logits or shifted logits, provided the threshold is computed on the same scale. That is why the conformal step is unaffected by weighting.
- Weighting vs resampling: for plain LogisticRegression with a few % positives, either works; weights are deterministic and avoid duplicated-row leakage across folds. Prefer no resampling/SMOTE (synthetic rows make the simulator circularity worse). Weights change coefficients only mildly except the intercept when the model is well-specified; under misspecification they change the slope too, so evaluate recall at the conformal threshold, not AUC alone.
- PPV by Bayes: PPV = r*pi / (r*pi + f*(1-pi)), r = recall at threshold, f = false-alarm rate on legitimate sessions, pi = 1/147,000 = 6.8e-6. Example r=0.8, f=0.001: PPV = 5.4e-6/(5.4e-6+1.0e-3) = 0.54%, i.e. about 1 true alert per 185 alerts; per 147,000 sessions expect ~147 false alarms vs ~0.8 true alarms. To reach PPV 50% need f ≈ r*pi ≈ 5.4e-6 (alpha ≈ 1 in 185,000, requiring n_cal in the hundreds of thousands). State clearly: "alpha = 0.001 is not a precision target". Report PPV at several base rates (1e-5, 1/147,000, 1e-4, training rate) with CI propagated from recall and FPR intervals. Also report alerts per 100k sessions.
- Hence either tolerate alerts as a soft "review/step-up" signal, or use a much smaller alpha with a cohort-pooled calibration set large enough (n >= 1/alpha - 1).

### Gaps
- Original scikit-learn calibration guide and prior-shift papers (Saerens et al. 2002 EM prior adjustment; Elkan 2001) were not retrieved; cite from memory only after verification.
- The 1-in-1.47 lakh base rate is from the task brief; its source is not verified here.

## 3. Feature engineering: ratio vs rolling median, median/MAD z-score, cold start, interactions, ordered-sequence boolean

### Takeaway
Use robust statistics (median, MAD x 1.4826) with explicit MAD=0 handling, shrink toward a global/cohort prior when a user has fewer than ~20 observations, and keep every feature a pure deterministic function of past events only.

### Cited Findings
- No retrieved source covers these items; the search for MAD/1.4826 (Wikipedia) failed on DNS. See Gaps.

### Inferences
(Standard practice; derived, to be pinned by golden tests.)
- Log amount ratio: x = ln((amount + eps)/(median_past + eps)) with amount and median in the same unit, eps small (e.g. 1.0 rupee) to avoid log(0); median over the user's last W prior transactions, excluding the current one (no look-ahead). Clip to a fixed range (e.g. [-5, 5]) so one extreme cannot dominate logistic scores; the clip bounds are part of the exported spec.
- Robust z: z = (x - median)/(1.4826 * MAD). The constant is 1/Phi^-1(0.75) = 1.482602..., making MAD a consistent estimator of sigma for normal data (value computed from definition, not source-cited). Use the full-precision constant in both languages. MAD=0 (more than half the values identical, common for repeated fixed payments): fall back to a floor, e.g. scale = max(1.4826*MAD, s_min) with s_min from the global/cohort prior (or 1.253314 * mean absolute deviation), never divide by zero; clip z to [-z_max, z_max] (e.g. 10). Document which branch fired as a test case.
- Cold start (n_obs < ~20): blend location and scale with a prior using weight w = n/(n+n0) (n0 = 20): median_eff = w*median_user + (1-w)*median_prior; likewise for scale. Prior is cohort-level (e.g. by age band is allowed only for the threshold, see section 4; use an age-free global prior for features). For n = 0 use prior only. Test n = 0, 1, 19, 20, 21.
- Median of an even number of elements: average the two middle values (numpy default); implement identically in Kotlin (sort a copy of doubles, deterministic).
- Interactions: add only a few pre-specified products (e.g. log_ratio * new_payee, z * night_flag); centre/standardise after multiplication; the scaler sees the interaction column as its own feature. Avoid automatic polynomial expansion: it enlarges the exported spec and the Kotlin surface area.
- Ordered-sequence boolean (OCSS): flag is true iff events e1, e2, ..., ek occur in that order within the same session/user with each consecutive gap in [g_min, g_max] (seconds, inclusive bounds stated). Use integer epoch milliseconds, stable sort by (timestamp, event index) so equal timestamps are deterministic; define whether non-matching events may interleave (subsequence) or must be adjacent, and test both. Convert to 0/1 float before scaling.
- Fixed output feature order and names in the JSON so Kotlin never depends on map iteration order.

### Gaps
- No source found for the cold-start shrinkage weight n0 = 20 or the clip constants; these are design choices to tune via simulation sensitivity analysis.
- Wikipedia MAD page (1.4826 relation) could not be fetched.

## 4. Fairness check across age bands; age used only to select the threshold

### Takeaway
Compare alarm rates and false-alarm rates (on legitimate sessions) per age band with confidence intervals; gate on a ratio of 1.5x; keep age out of the feature vector and use it only to pick the cohort's conformal threshold, which equalises the legitimate false-alarm rate by construction.

### Cited Findings
- The BAF suite (Jesus et al., NeurIPS 2022 Datasets & Benchmarks, "Turning the Tables") is designed with built-in biases for fairness stress-testing; code and data at feedzai/bank-account-fraud — [NeurIPS abstract](https://proceedings.neurips.cc/paper_files/paper/2022/hash/d9696563856bd350e4e7ac5e5812f23c-Abstract.html); [arXiv 2211.13358](https://arxiv.org/pdf/2211.13358.pdf)
- Models trained on BAF raise more false alerts for applicants aged 50+; fairness work splits groups at age 50; operating point is a fixed FPR (5%) maximising recall, and fairness is the FPR ratio across groups — [FiFAR](https://arxiv.org/pdf/2312.13218); [terazi BAF demo](https://terazi.yigitsever.com/baf.html); [FairGBM](https://arxiv.org/pdf/2209.07850)

### Inferences
- Per-cohort conformal thresholds make the legitimate false-alarm rate approximately alpha in every age band (Mondrian validity), which directly targets the false-positive-rate parity that BAF-style audits measure. Using age as a model feature could let the model learn age-linked score shifts and is a protected-attribute use; as a threshold selector it is transparent and auditable. Document this explicitly.
- Fairness gate: compute for each band b the alarm rate on legitimate validation sessions (FPR_b) and on scams (recall_b); gate passes if max FPR_b / min FPR_b <= 1.5. With 0.1% target and few thousand sessions per band, FPR_b is estimated from a handful of events (section 5), so the ratio is extremely noisy: gate on the CI (e.g. upper CI of the worst band over the pooled alpha) or use a one-sided test, otherwise the gate flips randomly. Also report the raw alarm rate across all sessions (legit + scam), which depends on the scam mix per band, labelled as such.
- Recall parity is a separate, descriptive metric; equalising FPR can leave unequal recall, so report both.

### Gaps
- The 1.5x gate has no cited origin (resembles the four-fifths-style rule of thumb but not verified); treat as a project policy.
- BAF sections on fairness metrics were seen only via secondary summaries.

## 5. Splitting, seeds, and confidence intervals (Wilson / Clopper-Pearson / rule of three)

### Takeaway
Split by user (or session group), never by row; assign train / calibration / validation with fixed seeds; report exact or Wilson intervals, and for zero observed false alarms use the rule of three (and note that 0.1% of 10,000 is only ~10 events).

### Cited Findings
- Rule of three: with zero events in n subjects, the 95% upper confidence limit is about 3/n (good for n > 30); from Hanley & Lippman-Hand, "If nothing goes wrong, is everything all right?", JAMA 1983; 3 ~ -ln(0.05) — [Rule of three, Wikipedia](https://en.wikipedia.org/wiki/Rule_of_three_(statistics)); [JAMA abstract](https://jamanetwork.com/journals/jama/article-abstract/389714)
- Exact methods are advised when event counts are small (< ~6 events) — [Rule of 3 in critical appraisal](https://jmgamble.substack.com/p/the-rule-of-3-in-critical-appraisal)
- A modified rule of three for the one-sided binomial CI exists — [Int. J. Biostat.](https://www.degruyterbrill.com/document/doi/10.1515/ijb-2022-0061/html)
- The Bates et al. paper offers a training-conditional uniform bound on the false positive rate as a function of threshold, useful for validating the threshold — [Project Euclid](https://projecteuclid.org/journals/annals-of-statistics/volume-51/issue-1/Testing-for-outliers-with-conformal-p-values/10.1214/22-AOS2244.full)

### Inferences
(Formulas are standard; the search did not retrieve Wilson/Clopper-Pearson text.)
- Splitting: group key = user_id (and any shared device/household id if present). Assign each user wholly to one of train / calibration / validation (e.g. 50/25/25) with a seeded hash or `GroupShuffleSplit(random_state=...)`; stratify at user level by "has any scam" and by age band so each split has scams and every cohort has calibration users; scams must never appear in calibration (conformal uses legitimate only), but scam users can be used in train/validation. Rolling-median features must be computed from within-user history only and calibration must see the same feature pipeline as deployment. Record all seeds (split seed, simulator seed, model random_state) in the output spec; lbfgs is deterministic, but fix `random_state` anyway.
- Calibration must be disjoint from the validation set used to report false alarms, otherwise reported FPR is optimistically biased.
- Intervals: Wilson 95% for p-hat = x/n: centre (p + z^2/2n)/(1+z^2/n), half-width z*sqrt(p(1-p)/n + z^2/4n^2)/(1+z^2/n), z=1.96. Clopper-Pearson: Beta quantiles; for x=0, one-sided 95% upper = 1 - 0.05^(1/n) (~2.996/n); two-sided 97.5% upper = 1 - 0.025^(1/n) (~3.69/n). Rule of three: need n >= 3,000 legitimate validation sessions with zero alarms just to bound the rate below 0.1% at 95% confidence. Count for scale: 10 expected false alarms in 10,000 legit sessions has an exact Poisson 95% interval of roughly 4.8 to 18.4 events (0.048%-0.18%), so a measured 0.15% is consistent with 0.1%. Multiple cohorts: n per band is smaller still; do not over-interpret per-band rates.
- Recall CI: Wilson or Clopper-Pearson on x scams detected of N scams in validation; with few hundred scams the interval is +-4-5 percentage points. Also bootstrap by user (cluster bootstrap) if sessions within user are correlated, since row-level binomial intervals understate the variance.
- scikit-learn has no Clopper-Pearson; implement via scipy.stats.beta.ppf (offline evaluation only; Kotlin needs only the thresholds).

### Gaps
- No source retrieved for Wilson/Clopper-Pearson formulas (search gave only rule-of-three material); derive from standard texts (Brown, Cai, DasGupta 2001 is the usual reference for comparing them, not retrieved here).
- Group-aware CV guidance from scikit-learn docs not retrieved.

## 6. Exporting LogisticRegression + StandardScaler to JSON and reproducing scores in Kotlin to 1e-9

### Takeaway
Export float64 values with repr-exact decimal strings, fold or keep scaler and coefficients explicitly, evaluate the linear logit in a fixed order, use a piecewise-stable sigmoid (or just alarm on the logit), and verify with golden vectors at a 1e-9 absolute / relative tolerance.

### Cited Findings
- Sigmoid pitfalls: the naive 1/(1+exp(-x)) overflows for large negative x; use the sign-split form (standard for x >= 0, exp(x)/(1+exp(x)) for x < 0); clipping (e.g. to +-500) alters extremes; float64 exp overflows near 709.78 — [Daily Dose of DS](https://blog.dailydoseofds.com/p/sigmoid-and-softmax-are-not-implemented); [overflow thread](https://forums.fast.ai/t/overflow-with-exp-in-kaggle-when-increasing-sizes/36053)

### Inferences
(Engineering judgement; no JVM-parity writeup was found.)
- Export: `scaler.mean_`, `scaler.scale_` (note: zero-variance features get scale 1.0 in sklearn), `clf.coef_[0]`, `clf.intercept_[0]`, feature names in order, conformal thresholds (on the logit scale) per cohort with n_cal / k / method, MAD constant and clip bounds, and the library versions. Write JSON with Python `json.dumps` of Python floats (repr gives shortest round-trip float64); never `float32`, never rounded `%.6f`. Kotlin `String.toDouble()` / kotlinx.serialization parse the same IEEE-754 value; ensure the parser is not reading into Float.
- Compute logit = intercept + sum_i coef_i * ((x_i - mean_i)/scale_i) in feature order with a simple sequential loop in Double. numpy's dot may use pairwise/BLAS/FMA ordering so differences around 1e-16 relative are expected; that is far inside 1e-9, but do not expect bit equality. Avoid pre-folding the scaler into the coefficients unless the golden test is for the folded form (folding changes rounding).
- Decide on the logit rather than the probability: because sigmoid is strictly monotone, thresholds on the logit are equivalent and avoid saturation (probability 1.0 for large logits makes distinct scores tie). If probabilities are shown, use the stable form: p = 1/(1+exp(-z)) for z >= 0 else exp(z)/(1+exp(z)); use `Math.exp`, and `Math.log1p` style helpers if computing log-odds. Kotlin's `kotlin.math.exp` delegates to `StrictMath`/`Math` and may differ from numpy by 1 ulp, fine at 1e-9. Use `strictfp`-like determinism is default on modern JVMs (JDK 17+).
- Determinism: sort with explicit comparators on (timestamp, id); do not rely on HashMap order; parse/format numbers with `Locale.ROOT` (a comma-decimal default locale breaks `String.format` and `toDouble` on formatted text); read JSON as UTF-8; avoid `Float` and `Math.round`.
- Tests: generate 200-1000 golden vectors in Python (random plus edge cases: zeros, MAD=0, cold start n=0/19/20, very large amounts where |z| is 700+, exact threshold tie, empty history) containing raw inputs, intermediate features, logit, probability, and alarm; Kotlin unit tests assert abs(diff) <= 1e-9 (use relative tolerance 1e-9 for large magnitudes) on features and logits, and exact equality on the alarm boolean except when |logit - threshold| < 1e-9 (assert such near-tie vectors explicitly with the intended behaviour). Include the end-to-end test: raw event list -> features -> alarm. Keep the golden file in the repo and regenerate by a script with a fixed seed.

### Gaps
- No Kotlin/JVM numerical-parity writeup was found; the guidance above is general engineering knowledge, not sourced.
- scikit-learn serialisation guidance (model persistence docs) was not retrieved.

## 7. Honest-evaluation pitfalls when the simulator creates both train and test data

### Takeaway
A model evaluated on data from the same generator and assumptions it was trained on mostly measures the simulator's own rules, so results are an optimistic upper bound; mitigate with independent seeds and generator variants, out-of-distribution test sets, and sensitivity sweeps, and say so in the report.

### Cited Findings
- BAF (Jesus et al., NeurIPS 2022) is explicitly built with dynamic, biased and imbalanced variants (distribution shift across months, group-specific biases) to stress-test models beyond a single i.i.d. split — [NeurIPS abstract](https://proceedings.neurips.cc/paper_files/paper/2022/hash/d9696563856bd350e4e7ac5e5812f23c-Abstract.html); [arXiv 2211.13358](https://arxiv.org/pdf/2211.13358.pdf)
- Conformal guarantees require exchangeability between calibration and test; they do not protect against shift — [Gentle Introduction](https://arxiv.org/pdf/2107.07511)

### Inferences
- Circularity: if scam rules in the simulator (e.g. "scam amounts are 5-20x median") are what the features encode, high recall is by construction. Mitigations: (1) use separate generator seeds for train/calibration/validation/test, and a final test seed never touched during tuning; (2) a test generator with perturbed parameters (different scam amount distributions, new behaviours not in training, different cohort mixes, drifting legit behaviour); (3) sensitivity analysis: sweep key simulator parameters (scam prevalence, amount multiplier, legit variability, MAD=0 rate, cold-start share) on a grid or Latin hypercube and report recall at the conformal threshold as a range, not a point; (4) report false-alarm rate under shifted legit distributions to show where the 0.1% guarantee breaks (exchangeability violated); (5) a baseline comparison (simple rule or z-score only) so the lift attributable to modelling is visible; (6) label all numbers "simulated" and never present simulated recall or PPV as expected real-world performance; (7) plan a shadow-mode check on real legitimate data to validate the false-alarm rate, since only legitimate scores are needed for that check.
- Document simulator assumptions, parameter ranges and seeds alongside every result table.

### Gaps
- No paper found specifically on circularity of simulator-based fraud evaluation; the guidance is methodological reasoning.
- Fraud Dataset Benchmark (Grover et al. 2022) was not retrieved.

## Reference list (for citation)
- Angelopoulos & Bates, Gentle Introduction to Conformal Prediction: https://arxiv.org/pdf/2107.07511
- Angelopoulos, Barber, Bates, Theoretical Foundations of Conformal Prediction: https://arxiv.org/pdf/2411.11824v5
- Bates et al. 2023, Testing for outliers with conformal p-values: https://projecteuclid.org/journals/annals-of-statistics/volume-51/issue-1/Testing-for-outliers-with-conformal-p-values/10.1214/22-AOS2244.full
- Class-conditional / Mondrian conformal: https://arxiv.org/pdf/2306.09335
- Jesus et al. 2022, BAF: https://arxiv.org/pdf/2211.13358.pdf
- King & Zeng 2001 (ReLogit): https://www.jstatsoft.org/article/view/v008i02
- scikit-learn LogisticRegression: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html
- Hanley & Lippman-Hand 1983 (rule of three): https://jamanetwork.com/journals/jama/article-abstract/389714
