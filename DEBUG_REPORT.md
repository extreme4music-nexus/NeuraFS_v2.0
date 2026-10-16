
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


### Web tree error diagnosis — Node 22 root path normalization for SUBST drives

Reproduced the endpoint error directly on this Windows host: Node `fs.readdirSync("X:\\")` fails with `ENOENT`, although PowerShell and Python list the same drive root. Node `fs.readdirSync("X:")` succeeds, and `path.join("X:", "media")` produces the usable `X:\media` child path. The web app calls `path.resolve(configData.storage_path)`, converting a configured root `X:\` into the form that fails when enumerated. Fix: retain a Windows drive root as `X:` after resolution; verify the actual mounted-drive tree and existing subfolder endpoints.


### Fix 15 — normalize mounted Windows drive roots for Node enumeration

**Changed:** The web backend now preserves a configured Windows drive root as `X:` instead of returning the normalized `X:\\` form. Node 22 can enumerate `X:` and join child directories, but returned `ENOENT` enumerating the trailing-slash root of this SUBST drive.

**Verification:** `node --check neurafs/web/app.js` passed. Rebuilt and force-installed a wheel from the Z: project after stopping Web to release its package-file lock, then restarted Web (PID 3324). With X: mounted, HTTP checks returned 200 for Web `/health`, `/`, `/api/fs/tree`, and API `/health`. The tree response listed the existing `documents` and `media` folders and returned `used_bytes: 68652244`.

**Limitations:** The active web process found Express, Multer and lzma-native via the user's existing `C:\Users\tonic\node_modules`; provisioning those npm packages on a clean installation remains open. Task Scheduler persistence is still unregistered due to session privileges.

### Final Windows CLI and lifecycle pass — 2026-10-16

**Installed build:** Commands were run from the Python 3.12 Scripts executable installed from the Z: project. The Z: Git checkout remains the only edited project; C: source is untouched. The installed Python package is version 2.0.0. The separate broken Program Files bundle could not be removed without Administrator elevation, so this PC still has the unrelated zero-byte System32 `neurafs` shadowing issue. Use the full Scripts path for accurate CLI checks.

**Additional CLI checks:** Top-level help lists all commands and aliases; command parser help paths were previously checked (25/25). `vfs status`, `storage set X:\\` (same existing value), `storage check`, and API/Web/service/watchdog status commands were exercised. A generated 0.25-second WAV completed the real DAC encode → HCS → decode → inspect workflow with exact 11,025-frame/0.25-second decoded duration. Samba was skipped as requested on Windows. `storage move` and `storage remove` were not run because they relocate or reset user data; benchmark was not run because it writes reports/output artifacts in the current directory. Hidden daemon-internal commands were parser-checked, not invoked directly. Codec set was not changed to avoid modifying user preference.

**Restart failure and recovery:** `neurafs restart` stopped VFS, API, Web, and watcher, remounted X:, restarted Web and watcher, but API health did not come up within the 10-second start window. The CLI then printed “All NeuraFS background services are active & operational” despite reporting `Startup completed with failures: api`. Subsequent API retries while an untracked prior process still held port 8000 spawned duplicate Uvicorn processes which failed with Windows `Errno 10048` (address already in use); this exposed that `_wait_for_api_ready()` can accept a healthy endpoint owned by another process before confirming its own child is alive. After identifying and stopping the orphan API process, a clean `api start --daemon` succeeded (PID 15604), `/health` returned HTTP 200, and both `api status` and global `status` correctly reported it running. This is a reproducible API startup race plus an inaccurate global success message; both need source fixes and regression tests. No source fix for these newly found defects has been applied yet.

**Final service state:** VFS mounted X: read/write from `C:\\Users\\tonic\\.neurafs\\storage`; API PID 15604 healthy on port 8000; Web PID 27908 running on port 3000; watcher active; Samba unavailable by design on Windows. Global status confirms all four supported services running. Boot persistence remains disabled because Task Scheduler registration returns `Access is denied` in this non-elevated session.

**Outstanding command/environment limits:** Windows Task Scheduler autostart and removal of the Program Files bundle require Administrator elevation and remain incomplete. Native Linux/macOS install/runtime validation remains impossible on this Windows host. Clean-host Node dependency provisioning remains unverified; current Web launch depends on preexisting `C:\\Users\\tonic\\node_modules` packages. The newly discovered API startup race and false-success message are next debugging fixes.

### Fix 16 — make `start` report incomplete startup honestly

**Changed:** `handle_start` now checks the result returned by `ServiceOrchestrator.start_all()`. If any service status begins with `FAILED`, the CLI prints the failed service names, exits with status 1, and does not print the all-operational claim.

**Verification:** Focused `test_service_orchestrator.py` passed (2 passed). This directly covers the previously observed case where API startup failed but `neurafs start` still printed “All NeuraFS background services are active & operational.” The fixed source still needs to be installed and exercised through the real CLI before considering the fix complete.

**Fix 16 installed and rechecked:** Reinstalled the package from the Z: checkout after the focused test. A fresh real `neurafs start` returned with VFS mounted, API PID 12336, Web PID 21796, and watcher active. API `/health` returned `{"status":"ok"}` and Web `/health` returned `{"status":"ok","service":"neurafs-web"}`. Global status reports all four supported Windows services running. The earlier API duplicate-start race did not recur on this clean start, but it remains an observed defect to investigate because PID/status mismatches and port collisions were reproducible during the prior restart sequence.

### Fix 17 — recover API listener tracking and prevent duplicate starts

**Changed:** The API manager now checks the process listening on port 8000 when its PID file is missing or stale, verifies that the process command line belongs to NeuraFS before adopting it, and rewrites the PID file for a recognized listener. If the endpoint is healthy but its listener cannot be identified, `start` refuses to launch a duplicate; `status` reports a healthy but unidentified API, and `stop` leaves that process untouched. Startup readiness now briefly rechecks the spawned child after the health probe so a competing listener cannot make a child that failed to bind appear ready.

**Verification:** Focused API-manager and service-orchestrator suites passed (9 passed). Live Windows validation removed the API PID file while the server was running; `api status` recovered and rewrote the correct PID (30404). A repeated daemon start reported that same existing PID instead of spawning another server. `api stop` then stopped it, and `api start --daemon` started a fresh server (PID 16296). API `/health` returned `{"status":"ok"}`; Web `/health` returned `{"status":"ok","service":"neurafs-web"}`. Global service status confirmed VFS mounted, API running, Web running, and watcher active. `git diff --check` passed.

**Limitations:** Listener discovery uses process command-line inspection and can be denied by host process permissions; in that case the CLI reports the healthy API as untracked and avoids terminating it or launching a duplicate. Port discovery currently follows NeuraFS's default API port 8000 for PID recovery.

### Command conflict investigation — blocked on Administrator elevation

**Observed:** `where neurafs` resolves first to `C:\\Windows\\System32\\neurafs`, a zero-byte regular file, before the working `C:\\Users\\tonic\\AppData\\Local\\Programs\\Python\\Python312\\Scripts\\neurafs.exe`. The machine PATH places `C:\\WINDOWS\\system32` before the Python Scripts directory. The zero-byte file ACL grants full control only to SYSTEM and Administrators; Users have read/execute only.

The separate `C:\\Program Files\\NeuraFS\\neurafs.exe` is 142,966,285 bytes, but `C:\\Program Files\\NeuraFS\\_internal\\python312.dll` is missing, matching its previously observed launch failure. No root-level uninstaller file or NeuraFS uninstall registry entry was found. The Program Files directory ACL grants Administrators/SYSTEM full control and Users read/execute. `IsUserAnAdmin()` is false in this Codex session.

**Action taken:** Read-only inspection only. No file in System32 or Program Files was renamed/deleted, and PATH was not modified. This session cannot perform the requested cleanup safely without Administrator elevation. Until then, use the explicit working command `C:\\Users\\tonic\\AppData\\Local\\Programs\\Python\\Python312\\Scripts\\neurafs.exe`.

**Administrator cleanup steps for the user:** Open PowerShell with **Run as administrator**. First rename the exact zero-byte shadow (reversible): `Rename-Item -LiteralPath 'C:\\Windows\\System32\\neurafs' -NewName 'neurafs.disabled'`. Then verify `where.exe neurafs` resolves to the Python 3.12 Scripts executable. If the broken bundle should also be removed, inspect `C:\\Program Files\\NeuraFS` once more and remove that exact directory from the elevated shell; it has no registered uninstaller. Do not remove the `C:\\Users\\tonic\\AppData\\Local\\Programs\\Python\\Python312\\Scripts\\neurafs.exe` working CLI.

### Command conflict cleanup attempt — user authorized, OS elevation required

The user approved keeping the working per-user Python install and removing the conflicting/broken system-wide entries. Rechecked for scheduled task actions, Windows services, and Run-key entries referencing NeuraFS/neurafs; none were found. The Program Files NeuraFS root contains only `neurafs.exe` and `_internal` bundled files (no user storage directory or root uninstaller). The zero-byte `C:\\Windows\\System32\\neurafs` is the first PATH match; the working user Scripts executable is second.

Attempted the reversible rename `C:\\Windows\\System32\\neurafs` → `neurafs.disabled` with the available escalated command execution. Windows returned `Access to the path is denied`. Python `IsUserAnAdmin()` remains false. Thus the requested system-wide cleanup cannot be performed by this session; no System32 or Program Files files were changed. User approval is already established; the remaining blocker is a Windows administrator token.

Once in an elevated PowerShell, rename the zero-byte shadow, confirm `where.exe neurafs` points to the user Python Scripts executable, then remove only `C:\\Program Files\\NeuraFS` after rechecking that exact directory. Finally run `neurafs --help` and `neurafs status`. Until then, the working full-path CLI remains usable.
