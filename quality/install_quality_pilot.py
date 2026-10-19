"""Fail-closed installer for generalized QA45 policy source fidelity changes (stdlib only).

CHECK is read-only. APPLY preserves original files in .timezone_display_backups.
Never overwrites unrecognized customizations or touches databases/.env/policies.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

BUNDLE = Path(__file__).resolve().parent
MANIFEST = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))["files"]
BACKUP_ROOT = ".qa45_source_fidelity_backups"


def _sha(path: Path) -> str | None:
    return sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _put_atomic(src: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.qastage_{uuid4().hex}")
    try:
        shutil.copy2(src, staging)
        os.replace(staging, target)
    finally:
        if staging.exists():
            staging.unlink()


def _verify_paths(project: Path) -> list[str]:
    errors: list[str] = []
    for rel, info in MANIFEST.items():
        actual = _sha(project / rel)
        if actual == info["new_sha256"]:
            continue  # safely idempotent
        if actual == info["old_sha256"]:
            continue
        if actual is None and not info["preexisting"]:
            continue
        errors.append(rel)
    return errors


def _apply(project: Path) -> int:
    invalid = _verify_paths(project)
    if invalid:
        print("STOP: These source files do not match the audited baseline or installed version:")
        for path in invalid:
            print(" -", path)
        print("No files changed. Do not overwrite local customizations; provide the current files for a merge review.")
        return 2
    needs_change = [rel for rel, info in MANIFEST.items() if _sha(project / rel) != info["new_sha256"]]
    if not needs_change:
        print("ALREADY APPLIED; nothing to change.")
        return 0
    root = project / BACKUP_ROOT
    folder = root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:6])
    try:
        folder.mkdir(parents=True, exist_ok=False)
        for rel in needs_change:
            existing = project / rel
            if existing.is_file():
                backup = folder / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(existing, backup)
        (folder / "rollback_manifest.json").write_text(json.dumps({"modified":needs_change},indent=2),encoding="utf-8")
        for rel in needs_change:
            _put_atomic(BUNDLE / "payload" / rel, project / rel)
    except Exception as ex:
        print("Installation error; restoring files that were already changed:",ex)
        for rel in needs_change:
            orig=folder/rel;dest=project/rel
            if orig.exists(): _put_atomic(orig,dest)
            elif dest.is_file() and _sha(dest)==MANIFEST[rel]["new_sha256"]:dest.unlink()
        return 3
    print(f"APPLIED {len(needs_change)} files. Source backup: {folder}")
    print("No database, configuration, policy records, or timezone UI files were modified.")
    return 0


def _rollback(project: Path) -> int:
    root=project/BACKUP_ROOT
    backups=sorted((f for f in root.iterdir() if f.is_dir() and (f/"rollback_manifest.json").exists()),reverse=True) if root.is_dir() else []
    if not backups:
        print("No QA45 source-fidelity patch backups found.");return 2
    folder=backups[0]
    changed=json.loads((folder/"rollback_manifest.json").read_text(encoding="utf-8"))["modified"]
    divergent=[rel for rel in changed if _sha(project/rel)!=MANIFEST[rel]["new_sha256"]]
    if divergent:
        print("STOP: Files changed since installation. Rollback would overwrite later edits:")
        for rel in divergent:print(" -",rel)
        return 2
    for rel in changed:
        orig=folder/rel;target=project/rel
        if orig.exists():_put_atomic(orig,target)
        elif target.is_file():target.unlink()
    (folder/"rollback_manifest.json").rename(folder/"rolled_back.json")
    print(f"ROLLED BACK from {folder}; database unchanged.")
    return 0


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",required=True,help="Current C:\\User_dev\\HR_Assistant folder")
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check",action="store_true",help="Verify only; do not modify anything")
    g.add_argument("--apply",action="store_true",help="Safely install after preflight and backup")
    g.add_argument("--rollback",action="store_true",help="Restore latest patch backup if unchanged")
    a=p.parse_args()
    project=Path(a.project).resolve()
    if not (project/"app.py").is_file() or not (project/"modules/smart_ai/portal_ai.py").is_file():
        print("STOP: Incorrect project root:",project)
        return 2
    if a.rollback:return _rollback(project)
    invalid=_verify_paths(project)
    if a.check:
        if invalid:
            print("NOT SAFE to apply; source mismatch:")
            for rel in invalid:print(" -",rel)
            return 2
        for rel in MANIFEST:
            info=MANIFEST[rel];digest=_sha(project/rel)
            status="already applied" if digest==info["new_sha256"] else "ready"
            print(f"{status:15} {rel}")
        print("CHECK PASSED. No files were changed.")
        return 0
    return _apply(project)


if __name__ == "__main__":
    sys.exit(main())
