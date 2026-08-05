NeuraFS Complete Installation & Setup Guide
This guide details the setup procedures for installing the NeuraFS core engine, Python SDK, Express Web Explorer, native OS virtual drivers (Linux FUSE / Windows WinFSP), and Samba network sharing.

1. System Requirements
Python: Python 3.8 or higher

Node.js: Node.js v16 or higher (for Web UI)

C Compiler: GCC / Clang (Linux/Samba) or MSVC (Windows build tools)

Dependencies: PyTorch, NumPy, SciPy, FastAPI, Uvicorn, Multer, Express

2. Python Package Setup (Core Engine & CLI)
Clone the repository and navigate to the project root:

Bash
git clone https://github.com/your-org/NeuraFS.git
cd NeuraFS
Create and activate a virtual environment (recommended):

Bash
# Windows PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
Install NeuraFS in editable mode:

Bash
pip install -e . --no-build-isolation
Verify installation:

Bash
neurafs --help
3. Web Explorer UI Setup
Navigate to the web directory:

Bash
cd web
Install Node.js dependencies:

Bash
npm install
Start the Express Web Explorer server:

Bash
npm start
Open http://localhost:3000 in your web browser.

4. Native OS Drivers Setup
Linux FUSE Mounting
Ensure fuse3 libraries are installed:

Bash
sudo apt-get install libfuse3-dev fuse3
python -m neurafs.drivers.linux_fuse /path/to/storage /mnt/neurafs
Windows WinFSP Mounting
Download and install WinFSP.

Run the WinFSP driver launcher:

PowerShell
python -m neurafs.drivers.windows_winfsp C:\Users\tonic\Documents\NeuraFS\storage Z:
5. Samba VFS Network Sharing
To expose .hcs containers as uncompressed .wav files across a local network share:

Compile the C VFS module (neurafs_samba_vfs.c):

Bash
gcc -shared -fPIC -O2 neurafs/drivers/samba_vfs.c -o /usr/lib/x86_64-linux-gnu/samba/vfs/neurafs.so
Add the following share block to /etc/samba/smb.conf:

Ini, TOML
[NeuraFS-Share]
   comment = NeuraFS Virtual Neural Media Network Share
   path = /var/neurafs/storage
   vfs objects = neurafs
   read only = yes
   guest ok = yes
   browseable = yes
Restart Samba service:

Bash
sudo systemctl restart smbd