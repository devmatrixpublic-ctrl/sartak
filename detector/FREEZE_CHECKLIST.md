# Freezing the detector (M2) and the one-time held-out run (M4)

The held-out set can be run **once**. `ops/heldout/run_heldout.py` refuses unless `HEAD` is exactly the `detector-freeze` commit with no
tracked changes, so the tag must go on the right commit the first time. Do not tag by hand: run the pre-flight.

```bash
python detector/tools/freeze_preflight.py          # add --skip-gradle to skip the 2-minute Kotlin test run
```

It checks, in order: clean tree, HEAD is on `origin/main`, the tag is absent, `model.json` equals a fresh export, the evaluation gate
passes and matches `detector_report.md`, the Kotlin tests pass, and **36/36 on two physical phones is recorded**. It prints the exact
`git tag` command only when all pass, and never tags anything itself.

## What the team must supply (the script cannot)

1. **M1** runs the instrumented 36-vector test on **both physical phones** with the merged detector and records one table row per phone
   in `app/e2e_log.md` containing the word `Physical`, the device and `36/36`, and not the word `emulator`:
   `| 21 | Physical: Pixel 7, Android 15 | App pipeline (instrumented) | 36/36 |`
   (the command is in `app/e2e_log.md`, "Detector in the app: M2's 36 test vectors").
2. **M2** signs off on the report (`detector/detector_report.md`), including that the recall target is borderline (validation 93.1%,
   cross-validated about 91.8%) and that all numbers are simulated.
3. Everything above merged to `main` (the pre-flight checks this).

## After the tag
* **M4** runs `python ops/heldout/run_heldout.py` from a checkout of the tag, once, and writes up every miss by hand before committing
  `heldout_result.md`. The cases are scored as brand-new users (cold-start prior, unknown age band, pooled threshold).
* **Any later change to the detector, model, thresholds or data needs a new freeze, and the held-out set cannot be run again.**
  Treat the tag as final.
