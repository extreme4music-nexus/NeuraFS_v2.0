# NeuraFS Cross-Platform Readiness Roadmap

**Authoritative checkout:** `Z:\Documents\NeuraFS`. The C: copy is frozen and is not a work target.

## Goal
Make NeuraFS installable and dependable on Windows, Linux, and macOS, with platform-specific capabilities detected and explained honestly. Core operations should work after installation without depending on the caller's current directory. OS-level mounting and startup integration must be validated separately for each supported platform.

## Phases
1. **Packaging and platform boundaries:** make package metadata and installer imports host-safe; declare OS-specific dependencies only on their supported hosts; establish an explicit support/capability matrix.
2. **First-run setup:** make `init` detect prerequisites, guide installation per OS, configure paths, and finish without requiring hidden manual service startup steps.
3. **Core behavior:** verify storage, codecs, API, web UI, CLI and SDK on clean Windows/Linux/macOS environments, including model-cache/network assumptions.
4. **Native VFS and services:** validate the selected mount implementation, permissions, service lifecycle and boot persistence on each OS. Select and implement a macOS mount path before claiming macOS VFS support.
5. **Clean-install and lifecycle verification:** test install, init, start, status, core workflows, stop, upgrade and uninstall on clean host images; document anything that needs elevated privileges or network access.
6. **Release evidence:** maintain a Windows/Linux/macOS test matrix and mark each capability supported only when its host-level checks have passed.

## Evidence and change logging
Every implementation change must have a corresponding entry in `DEBUG_REPORT.md` describing the change, verification command/environment and result, plus limitations. Keep unverified host-specific behavior explicitly marked as unverified. Do not modify the frozen C: copy.

## Work started
First target: remove the packaging-time Windows-only import/dependency assumptions so Linux and macOS can build/install the Python package. This does not claim that their native VFS or complete first-run flow is already supported.
