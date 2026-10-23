# LLM scam-script variants: provenance

Variants of scam scripts, generated offline by `ops/eval/gen_variants.py`, **for the red-team report only**.

- They are kept apart from SatarkSim's train, validation and calibration data and from the sealed held-out set (`heldout/`, untouched).
- They are never used to train, calibrate, tune or choose a threshold, and never appear in the decision path.
- Each real run appends a row below: file, generator model, UTC date, the first 16 characters of the SHA-256 of the prompt template
  plus playbook descriptions, and the number of variants kept (outlines containing a link, address or long number are dropped).

**Status: no run has been made yet.** The script exists and is tested, but there was no `ANTHROPIC_API_KEY` in the environment, so
`data/llm_variants/` holds no variants. Nothing in the repo depends on them.

| File | Generator | Date | Prompt hash | Variants kept |
|---|---|---|---|---|
