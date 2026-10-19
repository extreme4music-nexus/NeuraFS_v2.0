# NeuraFS installation and setup

NeuraFS installs as a Python package. Its code and executables are installed into the active Python environment; storage and user settings live separately under the user's home directory.

## Requirements

- Python 3.8 or newer
- Node.js 16 or newer with npm, for the Web Dashboard
- FFmpeg, for audio conversion and non-WAV virtual audio formats
- Windows: WinFSP, for the virtual drive
- Linux: FUSE 3 and the `fusepy` Python binding, for the virtual mount
- macOS: Python package installation is available; the native NeuraFS VFS driver is not implemented yet

DAC and EnCodec are provided as install extras. Install the `codecs` extra to enable both.

## Install from the project directory

Create and activate a virtual environment first if you want an isolated installation.

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install ".[codecs]"
```

```bash
# Linux or macOS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install '.[codecs]'
```

The Python package includes the CLI entry point and declares its runtime Python dependencies. `neurafs init` checks for platform tools, codecs, and the locked Node packages, and offers to install missing components.

## Install from a different working directory

`setup.py` resolves the project root from its own location, so the legacy install form does not depend on the caller's current directory:

```powershell
python "Z:\path\to\NeuraFS\setup.py" install
```

The equivalent works on Linux and macOS with the appropriate project path. The recommended command remains `python -m pip install <project-path>[codecs]`.

To uninstall from that same Python environment:

```powershell
python "Z:\path\to\NeuraFS\setup.py" uninstall
```

Uninstall removes the Python package and its CLI entry point. It preserves `~/.neurafs/config.json` and `~/.neurafs/storage`.

## Initialize and start

```text
neurafs --help
neurafs init
neurafs start
neurafs status
```

Run `neurafs stop` to stop services and unmount the VFS. Do not start the WinFSP driver module directly; `neurafs start` manages its process and mount lifecycle.

## Configuration and data locations

- User configuration: `~/.neurafs/config.json`
- Default storage: `~/.neurafs/storage`
- Runtime state and PID files: `~/.neurafs/run`

An existing configured `storage_path` is retained by package upgrades and reinstallations. The defaults do not depend on the source checkout or Python installation directory.

## Manual Web dependency provisioning

If `neurafs init` cannot install Node dependencies automatically, run `npm ci` in the installed NeuraFS package directory. The package directory can be printed with:

```powershell
python -c "import pathlib, neurafs; print(pathlib.Path(neurafs.__file__).parent)"
```

Then use the printed path as the `--prefix` value:

```powershell
npm ci --prefix "<printed-package-directory>"
```
