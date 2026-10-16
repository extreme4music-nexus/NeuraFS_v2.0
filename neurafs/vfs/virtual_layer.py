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

        from neurafs.core.container import HCSContainer

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
                # E.g. 'song.wav.hcs' -> 'song.wav', or 'song.hcs' -> original name from manifest
                rec = records.get(abs_path[:-4])
                manifest = None
                orig_name = None
                orig_size = 0
                codec_id = "dac"

                try:
                    with open(abs_path, "rb") as f:
                        manifest, _ = HCSContainer.unpack(f.read())
                    orig_info = manifest.get("original", {})
                    neural_info = manifest.get("neural", {})
                    orig_name = orig_info.get("name")
                    orig_size = orig_info.get("size", 0)
                    codec_id = neural_info.get("codec") or neural_info.get("architecture") or "dac"
                except Exception:
                    pass

                if not orig_name:
                    orig_name = name[:-4]

                if not orig_size and rec:
                    orig_size = rec.get("file_size", 0)
                if not orig_size:
                    orig_size = entry.stat().st_size

                if orig_name not in seen_files:
                    virtual_items.append({
                        "name": orig_name,
                        "is_dir": False,
                        "size": orig_size,
                        "physical_path": abs_path,
                        "type": "HCS_VIRTUAL",
                        "codec": codec_id,
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
        from neurafs.core.container import HCSContainer

        clean_rel = virtual_rel_path.lstrip("/\\")
        if not clean_rel:
            st = os.stat(physical_root)
            return {"size": st.st_size, "is_dir": True, "mtime": st.st_mtime}

        phys_direct = os.path.join(physical_root, clean_rel)
        phys_hcs = f"{phys_direct}.hcs"

        # Check direct .hcs path or append .hcs
        target_hcs = None
        if os.path.exists(phys_hcs):
            target_hcs = phys_hcs
        elif phys_direct.endswith(".hcs") and os.path.exists(phys_direct):
            target_hcs = phys_direct

        # Scenario A: File is COMPLETED_HCS (.hcs exists physically)
        if target_hcs:
            records = {r["original_path"]: r for r in StateManager.get_all_records()}
            rec = records.get(os.path.abspath(phys_direct))
            hcs_st = os.stat(target_hcs)
            orig_size = 0
            codec_id = "dac"

            try:
                with open(target_hcs, "rb") as f:
                    manifest, _ = HCSContainer.unpack(f.read())
                orig_size = manifest.get("original", {}).get("size", 0)
                neural_info = manifest.get("neural", {})
                codec_id = neural_info.get("codec") or neural_info.get("architecture") or "dac"
            except Exception:
                pass

            if not orig_size and rec:
                orig_size = rec.get("file_size", 0)
            if not orig_size:
                orig_size = hcs_st.st_size

            return {
                "size": orig_size,
                "is_dir": False,
                "mtime": hcs_st.st_mtime,
                "physical_path": target_hcs,
                "type": "HCS_VIRTUAL",
                "codec": codec_id,
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