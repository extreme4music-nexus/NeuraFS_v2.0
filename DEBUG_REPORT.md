
### Fix 10 — preserve original audio duration on full-file decode

**Changed:** Full-file resynthesis now accepts the original sample count and trims codec output to that exact length. The encoder's reconstruction metrics, Python SDK decode, and API HCS streaming route pass the sample count already stored in the HCS manifest. Added a regression test proving padded stereo output is trimmed to the requested source length.

**Verification:** The focused engine regression passed (`1 passed`), and an actual SIREN encode/decode round trip using a temporary 0.25-second WAV passed (`1 passed in 30.64s`), producing exactly 11,025 samples at 44.1 kHz. Python compilation for the engine, SDK, API, and core test file passed. `git diff --check` passed. Codec fidelity and compression quality remain separate open findings.

