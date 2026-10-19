
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

### Startup persistence attempt — blocked by Windows Task Scheduler access control

Ran the installed `neurafs service autostart on` command. It detected that this session is not an Administrator and returned without registering the task. To test whether a current-user logon task could be created without elevation, attempted a disposable `NeuraFS_PermissionProbe` task with action `cmd.exe /c exit 0`; `schtasks /create` returned `ERROR: Access is denied` (exit code 1). The task was not created, so no cleanup was needed. This confirms that Task Scheduler creation itself is blocked for this token on this PC; the app's privilege gate is not the sole blocker.

No startup task was registered or modified. NeuraFS services were not stopped or changed by this attempt. Enabling persistence requires running `neurafs service autostart on` in an Administrator terminal (the task's configured action invokes the installed package's `service start` command). Verify with `neurafs service autostart status` and `schtasks /query /tn NeuraFS_Master_Daemon` afterward.

### CLI operations and clean-host / OS validation — 2026-10-16

**Scope and isolation:** Validation ran against the Z: source checkout and a disposable copy at `%TEMP%\neurafs-validation-20261016`; no source code was changed. Storage operations used the disposable copy and temporary profile. The actual user config remained `storage_path: X:\` with `default_codec: dac`. Generated benchmark output and fresh dependency installs stayed under the temporary directory.

**Remaining CLI operations:** `storage set`, `storage check`, `storage move`, and `storage remove` completed on temporary source/destination directories. A marker file moved to the destination; `remove` reset only the temporary profile to the copied package's default storage. `codec list`, `codec set dac`, and `codec get` ran in the temporary profile. The full benchmark command completed successfully: encoding 430.71 KB audio took 22.35 s; decoding completed with chunk-0 latency 4,082 ms and full stream throughput in 11.95 s. The command returned exit code 0 and wrote `benchmark_report.json` only in the temporary benchmark working directory. Peak RAM reported 3,294.7 MB, so avoid treating a full benchmark as lightweight.

**Clean Node dependency check:** The source package's locked Node dependencies installed from the npm cache into an empty `node_modules` in the temporary copy (`npm ci --offline`, 85 packages). Express, lzma-native, and Multer resolved from that copy. Running its Web Manager on isolated port 43127 returned `{"status":"ok","service":"neurafs-web"}`; `web stop` stopped it and the endpoint became unavailable. This confirms the checked-in lockfile can provision the Node side when npm is available, but the Python installer does not itself invoke npm install/ci; clean Python installations still need an explicit Node dependency provisioning step before Web startup.

**Python dependency metadata:** A fresh Python 3.12 virtual environment successfully built package metadata and pip began resolving all declared dependencies, including the Windows-only `winfspy` marker on this host. The resolver began downloading the 124.1 MB PyTorch wheel; the dry run was interrupted before completion to avoid a large unnecessary download. This is partial evidence, not a completed clean Python installation.

**Other operating systems:** WSL Ubuntu is registered, but it cannot start: WSL reports that its `ext4.vhdx` disk path is missing (`ERROR_PATH_NOT_FOUND`). Therefore Linux runtime/install commands could not be executed. No macOS host or runner is available in this environment, so macOS remains untested. `setup.py` explicitly limits its custom PyInstaller install/uninstall flows to Windows and instructs other hosts to use `python -m pip install .`; actual Linux/macOS dependency installation and runtime behavior remain to be validated on working hosts.

**Repository effects:** Only this validation record is added by this round. Temporary validation directory is retained for review and can be removed after approval; no cleanup was done automatically. Existing untracked `build/`, `dist/`, and `neurafs.egg-info/` entries predate this round and were left untouched.

### WSL Linux installation and startup — status recorded 2026-10-19

**Linux environment setup:** Ubuntu 26.04.1 under WSL2 was running as `tonic` with Python 3.14.4. The Z: drive was not automounted. Read-only CIFS access to `//192.168.50.23/NAS` was established at `/mnt/z`; the mounted checkout reported Git HEAD `24e9de7b`. No NAS credentials are stored in this log. WSL packages `python3-pip`, `python3.14-venv`, and `cifs-utils` were installed for testing.

**Isolated Linux package install:** A copy of the package source and packaging metadata was made under `/tmp/neurafs-linux-validation-20261016`, outside the Z: checkout. A Python 3.14 virtual environment was created there. The official PyTorch CPU wheel `torch 2.14.1+cpu` was installed, then `pip install` of the copied NeuraFS source completed successfully, including its declared Python dependencies. The default PyPI PyTorch candidate also resolved CUDA toolkit packages; the CPU wheel was used to avoid installing GPU libraries in this CPU-only WSL test. No NeuraFS CLI start was run from this temporary validation environment.

**User venv startup attempt:** The user then ran `start` from `~/neurafs-venv` with `HOME` preserved under `sudo`. Startup reached the VFS, API, Web, and watcher stages. It reported three failures: VFS did not become visible at `/home/tonic/NeuraFS_Drive` before the readiness timeout; FastAPI exited because `python-multipart` was missing; Node exited because `express` was missing. The watcher reported that it was already running. Startup correctly reported `vfs, api, web` as failures. The configured storage path shown was `/home/tonic/.neurafs/storage`.

**Current status:** On 2026-10-18, the user reported “It's working now.” Record this as user-reported success; it has not been independently rechecked. No credentials or passwords are recorded. macOS remains untested.

**Repository state:** At the time of this log update, `neurafs/core/codecs/dac.py` had an uncommitted change, along with pre-existing untracked build artifacts and `neurafs_uninstall.log`. These were left untouched; only this report entry is included in the commit.

### Fix 18 — resample DAC inputs and restore source audio format details — 2026-10-19

**Changed:** DAC encoding now keeps the source sample rate unchanged in metadata, resamples every source chunk to the model's required rate before preprocessing, and resamples decoded chunks back to the source rate before enforcing their original sample counts. This fixes both the model's sample-rate assertion and duration/speed corruption after decode. The engine now asks the loader to preserve source sample rate and channel count for compressed formats. The FFmpeg fallback returns float WAV at the decoded file's native rate/channel layout instead of forcing 44.1 kHz stereo. Direct integer WAV loading now normalizes signed widths and unsigned 8-bit PCM into the expected [-1, 1] float range. The loader's explicit target-rate option remains available for callers that request it.

**Verification:** On Windows, real DAC → HCS → WAV round trips passed for 22,050 Hz signed 16-bit, 48,000 Hz float32, and 96,000 Hz signed 32-bit WAVs. All decoded files retained the exact source sample rate and 0.25-second sample count; the recorded DAC metadata also retained each source rate. An 8-bit WAV check confirmed expected normalization and source-rate preservation. An MP3 created from a 32 kHz mono WAV loaded through FFmpeg as 32 kHz mono float32 on the engine path; the loader's explicit default target still resampled to 44.1 kHz. Python compilation and `git diff --check` passed. Only upstream TensorFlow oneDNN initialization and PyTorch weight-normalization deprecation notices appeared during real DAC validation.

**Scope:** Windows host only; no WSL commands or runtime were used. This fix addresses source-rate/PCM normalization and the DAC model-rate boundary. Other codec output-level behavior is addressed separately in the following EnCodec fix.

### Fix 19 — preserve EnCodec normalization scales and frame boundaries — 2026-10-19

**Changed:** EnCodec encoding now stores each encoded frame's code length and normalization scale in the HCS chunk metadata. Decoding rebuilds the original `(codes, scale)` frame list instead of concatenating all codes into one frame and passing `None`; this restores the model's amplitude normalization and frame overlap behavior. Legacy containers without these fields remain readable through the prior one-frame decode path. A 48 kHz mono input is now duplicated to the stereo-only 48 kHz model at encode time, then averaged back to mono during decode; the selected model rate is recorded in neural metadata.

**Verification:** Added a deterministic regression test proving that two frame scales and frame boundaries survive codec encode/decode (`1 passed`). Real Windows 48 kHz EnCodec round trips passed for stereo and mono WAVs using cached model weights. The stereo source peak was 0.1800 and decoded peak 0.1917; the mono source peak was 0.1800 and decoded peak 0.2002. The mono result retained 24,000 samples at 48 kHz with one output channel. A real 24 kHz mono round trip passed with 6,000 samples and the expected `None` frame scales. Python compilation and `git diff --check` passed; only PyTorch's upstream `weight_norm` deprecation warning appeared in the real model test.

**Scope:** Validation ran on Windows only, using temporary files and cached EnCodec weights. No WSL activity or user audio files were used.

### RAM-streaming, VFS callback, and installation pass — 2026-10-19

**Changed:** Added virtual WAV sizing and range reads tied to the source duration; added in-memory rendering for compressed audio formats; fixed later-chunk decoding so SIREN chunk sequencing does not silently restart at the wrong time; and exposed matching virtual metadata and bytes through the VFS interface. Added read-only WinFSP callbacks for directory listing, metadata, and file reads, including an explicit cleanup callback. Added regression tests for stereo SIREN output, byte-accurate WAV reads and EOF, chunk sequencing, MP3 rendering, and WinFSP callbacks without mounting a real drive. Runtime dependency checks now include multipart, watchdog, and Node packages; the packaging metadata and compatibility setup installer were aligned to version 2.3.0 and project-root-independent paths. Default storage now resolves under the user's home directory. Installation guidance documents platform behavior and the current macOS VFS limitation.

**Verification:** Focused VFS/streaming tests passed (9 passed). Python compilation, Node syntax checks, and `git diff --check` passed. The installed package reports version 2.3.0; installed CLI help resolves the command set from `C:\Windows\System32`. Read-only API and Web health requests returned HTTP 200. Installed `npm ci --offline` completed with 85 packages and no reported vulnerabilities. The installed global status reports API, Web, and watcher running; the VFS is unmounted. No services were started, stopped, or mounted during this verification.

**Installation recovery:** The first package reinstall attempt encountered a Windows file lock on the installed `neurafs/web` directory and pip left the package partially removed. Recovery used `pip install --ignore-installed --no-deps --no-build-isolation .` from the Z: source checkout, which installed NeuraFS 2.3.0 successfully; Node packages were then installed into the installed package directory. No user configuration or storage data was reset. `pip check` still reports conflicts belonging to other globally installed machine-learning packages and stale pip temporary distribution names; those unrelated packages were not changed.

**Safety and limits:** A previous real WinFSP mount attempt was associated with an Explorer crash/freeze. The callback cleanup defect has a direct regression test now, but this round deliberately did not mount a drive, open the ghost W: drive, or invoke `neurafs init/start`; an actual Explorer-visible filesystem mount remains unverified. Windows was the only runtime host available for these checks. Linux/macOS and clean-host Python dependency resolution remain separate validation work.

### WinFSP CFFI stale file-context crash investigation — 2026-10-20

**User-observed failure:** On a real `neurafs start`, the installed driver process terminated with `Fatal Python error: b_from_handle: ffi.from_handle() detected that the address passed points to garbage`. The failing frame is installed `winfspy/operations.py:401` (`ll_get_file_info`), called from the CFFI WinFSP trampoline. The other active stack is `winfspy/file_system.py:191` during `FileSystem.start()`. The user rebooted afterward; read-only `neurafs status` then reported VFS, API, Web, and watcher offline, with persistence disabled.

**Confirmed code path:** Installed WinFSPy is version 0.8.4. Its `FileSystem.start()` sets the mount point, starts the dispatcher, then immediately calls `os.stat(self.mountpoint)` as a readiness probe. This triggers the first real Windows filesystem callback during startup. WinFSPy `BaseFileSystemOperations.ll_open()` creates a CFFI handle and stores it in `_opened_objs`; `ll_close()` removes it. NeuraFS constructs the operations object with `super().__init__()` and retains both that object and the `FileSystem` instance throughout the driver loop. The Z: source and installed driver files are byte-for-byte equivalent in the inspected sections.

**Non-mount verification:** A no-mount low-level callback exercise using the installed code called `ll_open` with an actual CFFI `wchar_t[]` path, then `ll_get_file_info`, and finally `ll_close`. It returned success, retained one context before close, and removed it at close. This confirms the ordinary WinFSPy handle sequence works outside the real dispatcher.

**Finding and limits:** The exception proves that real `GetFileInfo` received a `FileContext` pointer whose `ffi.new_handle()` object was no longer alive. The crash occurs on the startup readiness-stat path. The normal NeuraFS `operations`/`FileSystem` object references are retained, and the isolated open/info/close sequence passes, so source inspection does not show a simple premature collection in that normal sequence. A callback ordering/lifetime race in the real dispatcher/startup path is the leading hypothesis, but the exact origin of the stale per-file context is not yet proven; confirming it requires recording callback pointer identity and open/close order during a native mount. No new mount was attempted because this failure previously froze or destabilized Explorer.

**No source fix applied in this investigation.** `DEBUG_REPORT.md` records the stack, status, code inspection, test, and unresolved native-dispatcher hypothesis. The next safe code step is to add a non-fatal validity guard and lifecycle diagnostics around `ll_get_file_info` (and cover the callback ordering in tests) before considering another real mount.

### WinFSP GetFileInfo stale-context guard — 2026-10-20

**Changed:** `_NeuraFSWinFSPOperations.ll_get_file_info` now verifies that the incoming CFFI context is still registered in WinFSPy's `_opened_objs` before calling its `ffi.from_handle()`. Unknown pointers are logged and return `STATUS_INVALID_HANDLE`, preventing the specific stale-context callback from terminating Python with a fatal CFFI error. Added no-mount regression tests for both a valid low-level open/info/close sequence and an unregistered native pointer.

**Verification:** Focused VFS/streaming and mount-state tests passed (11 passed). `git diff --check` passed. Reinstalled NeuraFS 2.3.0 from the Z: checkout after post-reboot status confirmed all services offline. A direct callback against the installed module logged a synthetic invalid pointer and returned `0xC0000008` (`STATUS_INVALID_HANDLE`) instead of crashing. A subsequent installed `neurafs status` still reports VFS/API/Web/watcher offline and persistence disabled.

**Limits:** This is a defensive guard and diagnostic, not proof of the native dispatcher race's origin. No `neurafs start` or real mount was run after the change. Python pip continues to warn about pre-existing invalid distribution remnants (`~`, `~eurafs`, `~~urafs`); they were not modified.

### Guarded real-mount retest blocked — 2026-10-20

**Attempt status:** After installing the GetFileInfo guard, a single repeat of the previously requested real `neurafs start` was submitted for verification. Automatic approval review rejected it before process launch because the earlier real WinFSP mount caused a fatal Python CFFI crash and Explorer/system instability, and the latest work was scoped to no-mount debugging. No NeuraFS start command ran and no mount was attempted in this step.

**Current verified state:** The installed NeuraFS `status` command reports VFS, API, Web, and watcher offline; boot persistence is disabled. The guard and its 11 passing no-mount tests remain installed/committed. Real native-dispatcher behavior after the guard is therefore still unverified.
