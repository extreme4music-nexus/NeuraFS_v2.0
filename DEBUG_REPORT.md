
### Fix 10 — preserve original audio duration on full-file decode

**Changed:** Full-file resynthesis now accepts the original sample count and trims codec output to that exact length. The encoder's reconstruction metrics, Python SDK decode, and API HCS streaming route pass the sample count already stored in the HCS manifest. Added a regression test proving padded stereo output is trimmed to the requested source length.

**Verification:** The focused engine regression passed (`1 passed`), and an actual SIREN encode/decode round trip using a temporary 0.25-second WAV passed (`1 passed in 30.64s`), producing exactly 11,025 samples at 44.1 kHz. Python compilation for the engine, SDK, API, and core test file passed. `git diff --check` passed. Codec fidelity and compression quality remain separate open findings.


### Fix 11 — train SIREN on each chunk's real audio span

**Changed:** SIREN training no longer includes artificial zero padding at the end of short/final chunks. Each encoded unit records its real sample span; decode evaluates the model over that same span and restores the fixed chunk shape before overlap-add. Raised the minimum training budget from 50 to 200 steps because controlled short-tone runs showed 53 steps produced near-zero reconstructions even after removing padded silence.

**Verification:** Added an epoch-floor unit test and strengthened the actual 0.25-second SIREN round-trip test to require exact duration and positive SI-SDR. Both passed (`2 passed in 22.20s`); Python compilation and `git diff --check` passed. Controlled tests on the same 440 Hz mono input measured SI-SDR/MSE of `20.36 dB / 0.001151` at 200 iterations and `21.45 dB / 0.000932` at 400, compared with `-41.64 dB / 0.125359` at the old 53-iteration padded baseline.

**Tradeoff / remaining issue:** The minimum training floor increases encode time for low-complexity signals. The 0.25-second SIREN container remains about 45 KB versus a 22 KB WAV, so short-file compression overhead is still unresolved.
