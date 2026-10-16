
### Fix 10 — preserve original audio duration on full-file decode

**Changed:** Full-file resynthesis now accepts the original sample count and trims codec output to that exact length. The encoder's reconstruction metrics, Python SDK decode, and API HCS streaming route pass the sample count already stored in the HCS manifest. Added a regression test proving padded stereo output is trimmed to the requested source length.

**Verification:** The focused engine regression passed (`1 passed`), and an actual SIREN encode/decode round trip using a temporary 0.25-second WAV passed (`1 passed in 30.64s`), producing exactly 11,025 samples at 44.1 kHz. Python compilation for the engine, SDK, API, and core test file passed. `git diff --check` passed. Codec fidelity and compression quality remain separate open findings.


### Fix 11 — train SIREN on each chunk's real audio span

**Changed:** SIREN training no longer includes artificial zero padding at the end of short/final chunks. Each encoded unit records its real sample span; decode evaluates the model over that same span and restores the fixed chunk shape before overlap-add. Raised the minimum training budget from 50 to 200 steps because controlled short-tone runs showed 53 steps produced near-zero reconstructions even after removing padded silence.

**Verification:** Added an epoch-floor unit test and strengthened the actual 0.25-second SIREN round-trip test to require exact duration and positive SI-SDR. Both passed (`2 passed in 22.20s`); Python compilation and `git diff --check` passed. Controlled tests on the same 440 Hz mono input measured SI-SDR/MSE of `20.36 dB / 0.001151` at 200 iterations and `21.45 dB / 0.000932` at 400, compared with `-41.64 dB / 0.125359` at the old 53-iteration padded baseline.

**Tradeoff / remaining issue:** The minimum training floor increases encode time for low-complexity signals. The 0.25-second SIREN container remains about 45 KB versus a 22 KB WAV, so short-file compression overhead is still unresolved.

### Follow-up codec validation — current configured default

The Z: checkout's configured default is DAC. Its 44.1 kHz 8 kbps weights were already present in the local cache, so no download was performed. Temporary DAC encode/decode checks passed for both 0.25-second and 2.5-second 440 Hz mono tones; both outputs had exact source sample counts. The 0.25-second case measured 24.81 dB SI-SDR, 0.001306 MSE, and an 856-byte HCS file versus a 22,094-byte WAV. The 2.5-second case measured 25.71 dB SI-SDR, 0.001288 MSE, and a 1,868-byte HCS file versus a 220,544-byte WAV.

The earlier low-fidelity and expansion measurements are isolated to the optional SIREN codec in this source tree. SIREN remains poor on a 2.5-second tone even at 400 training steps (about -14.85 dB SI-SDR); its long-clip fidelity is still unresolved. The installed product and this source checkout may therefore differ in codec behavior. Do not treat SIREN output as archival-quality based on these tests.

### Safe repository-suite verification

Ran the repository tests excluding only `test_vfs_file_illusion_and_watchdog_immunity`, because that test writes records into the user's global `~/.neurafs/state.db`. Result: `17 passed, 1 deselected` in 166.89 seconds. The three warnings were PyTorch's upstream `torch.nn.utils.weight_norm` deprecation warnings. Mocked service-orchestrator, mount-state, API health, and Samba tests all passed; the DAC end-to-end and channel-layout tests passed.

### Fix 12 — wait for API readiness before reporting startup

**Changed:** Background API startup now writes combined output to `~/.neurafs/logs/api.log`, waits for the API's `/health` response, checks for early child exit, and records the PID only after readiness. Failed startup terminates the spawned process, clears PID state, and includes the log path and error in the exception. Existing PID state is treated as running only when the requested API endpoint responds.

**Verification:** Four isolated tests passed (`4 passed in 10.49s`): health response validation, wildcard/IPv6 probe URL construction, PID creation only after readiness, and failed-start process/PID cleanup. Python compilation and `git diff --check` passed. Tests mocked subprocess creation and did not start or modify actual NeuraFS services.

### Prior repairs confirmed in the Z: checkout

Before continuing with the audio and API-manager issues, the Z: branch was checked against the C: repair log. The existing Z: history already contains the same first nine fixes; no duplicate patching was needed: `235022f` installer path independence, `e7fd815` Windows-safe installer output, `ed7f887` API health route, `7af447f` declared web dependencies, `d57d6c9` web readiness/logging, `84ba94e` truthful orchestration status, `14a4b8a` verified VFS mount state, `f6c587d` truthful VFS autostart status, and `1ea2d3b` Samba host guard. The C: copy was not modified.

## Cross-platform roadmap logged

Added `CROSS_PLATFORM_ROADMAP.md` to define the staged Windows/Linux/macOS readiness work, acceptance evidence, and the rule that unverified host-specific behavior must remain labeled unverified. The authoritative working checkout is Z:\Documents\NeuraFS; the C: copy is frozen. First implementation target: make package metadata and setup imports safe for non-Windows hosts. No implementation change is claimed by this roadmap entry.


### Cross-platform Step 1 — make package metadata safe for non-Windows hosts

**Changed:** `setup.py` now imports `winreg` only on Windows. The custom PyInstaller install and uninstall commands fail with explicit Windows-only messages when invoked on another OS instead of crashing on a Windows-only API. `pyproject.toml` now installs `winfspy` only on Windows, so Linux and macOS package resolution will not request the Windows VFS binding.

**Verification:** Python 3.12.4 compiled `setup.py` successfully. A Linux-platform simulation imported `setup.py` with no `winreg`, verified the explicit guard on both custom commands, and confirmed the project root remains anchored to the installer file. Parsed `pyproject.toml` and evaluated the `winfspy` environment marker: excluded on Linux and macOS, included on Windows. `git diff --check` passed.

**Limitations:** This was a platform simulation on a Windows host, not an installation on Linux or macOS. It validates only packaging-time import/metadata behavior; it does not establish a complete Linux/macOS installer, runtime dependencies, service startup, or native VFS support. Those remain in the roadmap.


## Windows reinstall and service validation — initial cleanup findings

**Requested sequence:** Stop/unmount all NeuraFS services and virtual partitions, uninstall, reinstall from the Z: project, run `init` and `start`, then verify CLI and services. C: remains frozen.

**Pre-clean findings:** The Python-installed CLI resolves to an editable install from `Z:\Documents\NeuraFS` (metadata version 2.0.0) and `--help` works. The separate `C:\Program Files\NeuraFS\neurafs.exe` fails before CLI startup with `[PYI-ERROR] Failed to load Python DLL ... _internal\python312.dll`; that DLL is absent. PATH also resolves first to a zero-byte `C:\Windows\System32\neurafs`, so bare `neurafs` produces no useful help. The executable at the Python Scripts path is currently the functioning CLI. No NeuraFS API/web listener or NeuraFS-named task was found; the CLI status reported API/web stopped and VFS unmounted.

**Cleanup actions/results:** Ran the Python-installed CLI's global `stop` (exit code 0); it warned that boot-persistence removal requires Administrator rights. Its status claimed unmounted, but `subst` revealed V:, W:, and X: still mapped to `C:\Users\tonic\.neurafs\storage` with no VFS state file. Deleted only these three NeuraFS-targeting mappings; each `subst /d` returned 0, and the subsequent mapping query showed none. No NeuraFS ports were listening afterward. Unrelated Codex Node processes were left running.

**Issue opened:** NeuraFS can leave virtual drive mappings active while its status reports `UNMOUNTED`; the ordinary stop path also cannot unregister system boot persistence without elevation. These findings will be debugged after the requested reinstall/start verification. The broken Program Files bundle and zero-byte PATH entry are also recorded for diagnosis.

**Reinstall safety note:** The project already contains `build/` and untracked `dist/` outputs. The custom PyInstaller installer deletes both after deployment, so it must not be run until those existing artifacts are preserved or the package-only install route is selected.


**Elevated uninstall attempt:** The custom Program Files uninstaller was launched with `RunAs` from the project UNC path. It did not produce `neurafs_uninstall.log`, and `C:\Program Files\NeuraFS` remains present. The current session is not Administrator. Windows elevation must be completed by the user; I will continue with the authorized per-user Python uninstall/reinstall and service validation, while clearly leaving the custom bundle uninstall unresolved until elevation is available.


**Per-user reinstall attempt:** After `pip uninstall`, pip reports a `neurafs` 2.3.0 distribution, but `pip show -f` says it cannot locate RECORD, `import neurafs` raises `ModuleNotFoundError`, and no Python Scripts `neurafs.exe` exists. Pip also warns about an invalid `~eurafs` distribution. This is a failed/incomplete installation, not a passing reinstall. Repairing the per-user install is required before running `init`/`start`.


## Windows reinstall/init/start verification — first run

**Package reinstall:** The per-user Python package was rebuilt from `Z:\Documents\NeuraFS` after the first uninstall/reinstall sequence left incomplete metadata. The repaired install imports from `C:\Users\tonic\AppData\Local\Programs\Python\Python312\Lib\site-packages\neurafs`; metadata reports the repository's pyproject version 2.0.0. The Python Scripts console command exists and its full `--help` output succeeds. Pip continues to warn about the leftover invalid `~eurafs` distribution from the previous installation.

**`init` result:** Ran the installed CLI's `init`. Its dependency scan reported PyTorch, NumPy, SciPy, FastAPI, Uvicorn, Pydantic, psutil, WinFsp bindings, FFmpeg, Node.js, Windows SMB availability, WinFsp and all listed codecs as present. Storage setup then failed with `PermissionError: [Errno 13] Permission denied` while opening `C:\Users\tonic\.neurafs\config.json` for writing. No successful initialization is claimed; `start` has not yet been run.

**Next diagnostic:** Inspect the existing config file and parent-directory ACL/attributes, determine whether the prior installation or user profile permissions are responsible, and retry only after identifying a safe, logged remedy. Do not replace an existing config or change its ACL without review.


**Correction after deeper process inspection:** A `Win32_Process` query found three still-running NeuraFS WinFSP driver processes despite the earlier CLI status and simple process-name checks: PID 28220 for X:, PID 29148 for W:, and PID 30036 for V:. Their command lines point to this checkout's `neurafs\vfs\drivers\windows_winfsp.py` and the NeuraFS storage root. This corrects the earlier observation that no NeuraFS-named service process was found; the driver processes were Python-named and escaped that filter. They are being stopped as part of the requested full cleanup.


### Windows package and CLI smoke checks

**Install result:** A forced, non-editable wheel reinstall from `Z:\Documents\NeuraFS` completed successfully (`neurafs-2.0.0-py3-none-any.whl`, 136,158 bytes). The imported package is in the Python 3.12 site-packages directory and the Python Scripts CLI was restored. The initial pip operation had left incomplete metadata; the forced wheel build/reinstall repaired that state. A warning about the old `~eurafs` invalid distribution remains.

**CLI verification:** The installed CLI `--help` succeeded. In-process argparse checks passed for all 25 registered top-level commands. Eleven non-mutating operations also completed: global status, codec get/list, list-codecs, API status, web status, service status, watchdog status, VFS status, storage check, and log. Samba behavior was not tested, per the Windows scope; its help parser was included in the 25 help checks.

**Initialization:** The first `init` attempt failed with `PermissionError` while saving config. After the three orphan WinFSP processes and their V:/W:/X: SUBST mappings were stopped/removed, retrying `init` succeeded: all detected dependencies were ready, storage directories were verified/created, config was saved, and the CLI reported initialization complete. This temporal association does not prove the orphan drivers caused the original write error.

**Still unresolved before startup:** The separate Program Files bundle remains because its uninstaller requires Windows administrator elevation. Its executable is still broken due the missing bundled Python DLL, and the zero-byte System32 `neurafs` path entry still shadows the working Python Scripts command when using bare `neurafs`. Use the explicit Python Scripts executable for subsequent checks until that is resolved.


## Windows `start` verification — partial startup and failures

**Command:** Ran the reinstalled Python Scripts CLI `start`; it returned exit code 0.

**Verified running:** FastAPI child PID 25544 listens on `127.0.0.1:8000`; a direct request to `/health` returned HTTP 200 with `{"status":"ok"}`. Watcher child PID 25844 was launched.

**Failed components:** VFS tried target X: and timed out before it became visible; state was correctly saved as `unmounted` with `autostart_enabled: false`. The Web process exited with code 1 because `neurafs/web/app.js` could not resolve `../sdk/node/hyper-compress-sdk`; port 3000 is not listening. Task Scheduler registration was skipped because this session is not elevated.

**Reporting defect:** Despite the returned startup result identifying VFS and Web failures, `handle_start` printed “All NeuraFS background services are active & operational” and returned exit code 0. This contradicts the service orchestrator's partial-failure report.

**Package diagnosis underway:** The failing web require points to a Node SDK JavaScript file present in the source project but apparently omitted from the installed Python wheel. Node dependency resolution from the installed package must also be checked. VFS drive selection will be investigated separately after the web packaging issue.


### Web startup diagnosis — wheel omitted the Node SDK

Compared the source checkout with the newly installed wheel: `neurafs/sdk/node/hyper-compress-sdk.js` exists in `Z:\Documents\NeuraFS\neurafs\sdk\node` but is absent from the installed `site-packages\neurafs\sdk\node` path, while the installed web `app.js` is present and requires that relative file. `MANIFEST.in` includes only `neurafs/web`; package metadata has no explicit SDK JavaScript package-data rule. Node resolves Express, Multer and lzma-native only from the user's separate `C:\Users\tonic\node_modules` directory in this environment, so a clean installation cannot rely on that ambient copy. The immediate reproducible web failure is the omitted SDK module; runtime npm dependency installation on clean hosts remains a separate packaging gap.


### Fix 13 — include the Node SDK in Python wheel installs

**Changed:** Added setuptools package-data rules and source-manifest inclusion for the web assets, Node SDK JavaScript, and the package's Node manifest/lockfile. This ensures the relative SDK module required by installed `web/app.js` is actually shipped in the Python wheel.

**Verification:** Built a wheel from the Z: source (`neurafs-2.0.0-py3-none-any.whl`, 149,318 bytes) into a temporary directory and verified it contains `neurafs/web/app.js`, `neurafs/web/public/index.html`, `neurafs/sdk/node/hyper-compress-sdk.js`, `neurafs/package.json`, and `neurafs/package-lock.json` (5/5). Force-installed that wheel. `neurafs web start --daemon` reached ready state (PID 28048). HTTP checks passed: web `/health` 200, `/` 200, `/api/fs/tree` 200; API `/health` 200.

**Limitations:** Node resolved Express/Multer/lzma-native from `C:\Users\tonic\node_modules` on this PC. A clean-host setup still needs to install or locate these npm dependencies deliberately; this fix only ships the missing project JS/manifests. The VFS remains unmounted and is investigated separately.


### VFS startup diagnosis — mount readiness timeout is shorter than driver startup

A transient Windows integration probe launched the same installed Python WinFSP driver command used by the VFS manager. The child remained alive, but X: was not visible at t=1, 2, 3, or 4 seconds; it became visible at t=5 and stayed visible through t=12. The probe then terminated its child and removed X: automatically. The manager's `_wait_for_mount()` default timeout is only 3 seconds, after which it kills the process and records an unmounted state. This reproduces and explains the `start` VFS timeout on this PC. Fix: give the driver a conservative startup window and add a regression test simulating delayed readiness.


**VFS fix install retry:** The first force-reinstall of the rebuilt wheel was blocked by Windows `WinError 32`: the running Node web process was using files under the installed `neurafs\web` directory. No package replacement completed. Stop the Web service before reinstalling, then restart it after the wheel is applied.


### Fix 14 — allow enough time for the Windows VFS driver to mount

**Changed:** Increased the mount readiness wait from 3 seconds to 15 seconds, and added a regression test in which the Windows mount becomes visible after five simulated seconds. This matches the measured startup delay and leaves a safety margin.

**Verification:** The focused VFS mount suite passed (`4 passed in 6.42s`) against the Z: source, including the delayed-readiness regression. Built and installed the revised Z: wheel. A full `neurafs start` then mounted X: successfully (RW); the API health endpoint and Web health/dashboard returned HTTP 200. Watcher was already active. Task Scheduler autostart failed with `Access is denied` because this session is not elevated; the service state correctly records `autostart_enabled: false`.

**New issue found during integrated check:** Web `GET /api/fs/tree` returns HTTP 500 with `ENOENT: scandir 'X:\\'` when configured to use the mounted SUBST root, while `/health` and `/` return 200. PowerShell and Python can enumerate X: root, as can Node enumerate its physical backing directory and X:\media, so this is narrowed to Node root enumeration of the SUBST drive. Investigate separately; do not treat the whole Web service as fully functional yet.
