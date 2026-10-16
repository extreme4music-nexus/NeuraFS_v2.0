
### Fix 10 — preserve original audio duration on full-file decode

**Changed:** Full-file resynthesis now accepts the original sample count and trims codec output to that exact length. The encoder's reconstruction metrics, Python SDK decode, and API HCS streaming route pass the sample count already stored in the HCS manifest. Added a regression test proving padded stereo output is trimmed to the requested source length.

**Verification:** Focused regression test passed (`1 passed`). Python compilation for the engine, SDK, API, and core test file passed. `git diff --check` passed. The test isolates the engine boundary with a padded fake codec; a full neural encode/decode fidelity run was not part of this focused regression.
