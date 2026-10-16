# Nexus Project State & Architecture Record

## Project Information
- **Project Name**: NeuraFS (Virtual Neural Media File System)
- **Repository**: extreme4music-nexus/NeuraFS_v2.0
- **Version**: 2.3.0
- **Last Updated**: 2026-09-30

## Current Milestone Status: Phase 4 (VFS OS Illusion & Cross-Platform RAM Engine) COMPLETED ✅

### 1. Watchdog Reprocessing Immunity
- Intercepts filesystem events and verifies `StateManager.is_processed(abs_path)` and `.hcs` container existence.
- Completely suppresses re-encoding loops when files are converted or accessed inside storage directories.

### 2. OS-Level & Network File Illusion (Windows, Linux, macOS, Samba)
- Intercepts directory enumeration (`readdir` / `ReadDirectory`) and stat queries (`getattr` / `GetFileInfo`).
- Lies to Windows Explorer, Linux Nautilus/Dolphin, macOS Finder, and Samba SMB clients by displaying original filenames (`song.wav`) and exact uncompressed file sizes (`441044` bytes), while hiding `.hcs` extensions.

### 3. Smart RAM Streamer & Drag-and-Drop / Copy-Paste On-the-Fly Decode
- **Playback / Double-Click**: Resynthesizes audio in RAM buffers (`RAMStreamBuffer`) with 0ms latency (chunk 0 priority) and sliding window LRU cache. Automatically purges RAM buffers upon playback completion (0 bytes leaked).
- **Copy-Paste / Drag-and-Drop / Network Transfer**: Intercepts sequential and offset byte read requests (`read_pcm_bytes`), serving exact uncompressed WAV RIFF header and decoded PCM payload on the fly so copied files land as 100% valid original `.wav` files on target drives or network shares.

### 4. Dynamic Mono vs. Stereo Channel Preservation
- Preserves full multi-channel shape across all neural codecs (`dac`, `siren`, `encodec`) without lossy downmixing.

### 5. Smart Container Auto-Codec Binding on Decode
- `.hcs` binary containers enforce strict auto-codec binding during decoding based on stored manifest architecture.

---

## Recent Fixes & Enhancements

- **2026-09-30: VFS Mount, Drive Letter Assignment & Cross-Platform Process Stability**:
  - **Intelligent Drive Selection**: `find_free_windows_drive()` dynamically checks drive letters from `Z:` down to `D:` using Windows `GetLogicalDrives()` API and filesystem path accessibility checks (`os.path.exists`/`os.path.isdir`).
  - **Synchronous Drive Binding**: `VFSServiceManager._mount_windows()` executes `subst` synchronously (0ms delay) so drive letter binding occurs immediately before state verification.
  - **Fixed `proc` Typo**: Resolved `NameError: name 'proc' is not defined` bug in `_mount_windows()`.
  - **Top-Level CLI Shortcuts**: Added direct `neurafs mount` and `neurafs umount` top-level CLI commands alongside `neurafs vfs mount`.
  - **Internal Driver CLI Subcommand**: Registered `_run_winfsp_driver` in `cli.py` to support background driver execution under PyInstaller and standard Python.
  - **Unmounted Drive Fallback**: Updated `StorageManager.get_path()` so if a configured Windows virtual drive letter is disconnected or unmounted, services automatically fall back to physical storage (`~/.neurafs/storage`) instead of crashing with `FileNotFoundError`.
  - **Process Creation & Encoding Protection**: Added `sys.stdout.reconfigure(errors="replace")` in `neurafs/__init__.py` and replaced non-ASCII status indicators with clean `[OK]`, `[OFFLINE]`, `[MOUNTED]` tags to prevent `UnicodeEncodeError` crashes on Windows `cp1252` console.
