"""NeuraFS VFS Virtualization & Presentation Layer (Directory Listing & Attribute Masking)."""

import os
import stat
from pathlib import Path
from typing import Dict, Any, List, Optional
from neurafs.core.modules.state_db import StateManager


class VFSVirtualLayer:
    """Translates physical storage state (.hcs / temporary files) into transparent virtual files."""

    @classmethod
    def resolve_virtual_listing(cls, physical_dir: str) -> List[Dict[str, Any]]:
        """Intercepts directory listing (readdir) to return spoofed virtual files."""
        if not os.path.exists(physical_dir):
            return []

        # Read state DB records to map original metadata
        records = {r["original_path"]: r for r in StateManager.get_all_records()}
        virtual_items = []
        seen_files = set()

        for entry in os.scandir(physical_dir):
            name = entry.name
            abs_path = os.path.abspath(entry.path)

            # 1. Hide internal database, lock, and temporary files
            if name.startswith(".") or name.endswith(".db") or name.endswith("-wal") or name.endswith("-shm"):
                continue

            # 2. Handle Completed .hcs Containers (Masking)
            if name.endswith(".hcs"):
                orig_name = name[:-4]  # Remove '.hcs' -> 'song.wav'
                orig_path = abs_path[:-4]
                rec = records.get(orig_path)

                if orig_name not in seen_files:
                    # Spoof attribute: Tell OS this is a WAV with its ORIGINAL size
                    spoofed_size = rec["file_size"] if rec and rec["file_size"] > 0 else entry.stat().st_size
                    virtual_items.append({
                        "name": orig_name,
                        "is_dir": False,
                        "size": spoofed_size,
                        "physical_path": abs_path,
                        "type": "HCS_VIRTUAL"
                    })
                    seen_files.add(orig_name)
                continue

            # 3. Handle Regular Directories
            if entry.is_dir():
                virtual_items.append({
                    "name": name,
                    "is_dir": True,
                    "size": 0,
                    "physical_path": abs_path,
                    "type": "DIRECTORY"
                })
            # 4. Handle Processing/Unconverted Files
            else:
                if name not in seen_files:
                    virtual_items.append({
                        "name": name,
                        "is_dir": False,
                        "size": entry.stat().st_size,
                        "physical_path": abs_path,
                        "type": "RAW_PHYSICAL"
                    })
                    seen_files.add(name)

        return virtual_items

    @classmethod
    def get_virtual_attributes(cls, physical_root: str, virtual_rel_path: str) -> Optional[Dict[str, Any]]:
        """Intercepts file attribute queries (getattr/stat) to spoof original file metadata."""
        clean_rel = virtual_rel_path.lstrip("/\\")
        if not clean_rel:
            st = os.stat(physical_root)
            return {"size": st.st_size, "is_dir": True, "mtime": st.st_mtime}

        phys_direct = os.path.join(physical_root, clean_rel)
        phys_hcs = f"{phys_direct}.hcs"

        # Scenario A: File is COMPLETED_HCS (.hcs exists physically)
        if os.path.exists(phys_hcs):
            records = {r["original_path"]: r for r in StateManager.get_all_records()}
            rec = records.get(os.path.abspath(phys_direct))
            hcs_st = os.stat(phys_hcs)

            # Return original uncompressed size from state.db
            spoofed_size = rec["file_size"] if rec and rec["file_size"] > 0 else hcs_st.st_size
            return {
                "size": spoofed_size,
                "is_dir": False,
                "mtime": hcs_st.st_mtime,
                "physical_path": phys_hcs,
                "type": "HCS_VIRTUAL"
            }

        # Scenario B: File is in PROCESSING or UNCONVERTED state
        if os.path.exists(phys_direct):
            st = os.stat(phys_direct)
            return {
                "size": st.st_size,
                "is_dir": os.path.isdir(phys_direct),
                "mtime": st.st_mtime,
                "physical_path": phys_direct,
                "type": "DIRECTORY" if os.path.isdir(phys_direct) else "RAW_PHYSICAL"
            }

        return None