"""Preserve working sources, generated assets and history outside the repository."""
import argparse
import hashlib
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", "node_modules", "__pycache__", ".venv", "venv"}


def digest(path):
    with path.open("rb") as stream:
        value = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
        return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, help="new directory outside the repository")
    args = parser.parse_args()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    destination = (args.destination or ROOT.parent / f"{ROOT.name}-backups" / timestamp).resolve()
    if destination.is_relative_to(ROOT):
        parser.error("Backup destination must be outside the repository")
    destination.mkdir(parents=True, exist_ok=False)
    bundle = destination / "repository.bundle"
    subprocess.run(["git", "bundle", "create", str(bundle), "--all"], cwd=ROOT, check=True)
    subprocess.run(["git", "bundle", "verify", str(bundle)], cwd=ROOT, check=True, capture_output=True)
    temporary = destination / "workspace.zip.partial"
    entries = []
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or any(part in EXCLUDED for part in relative.parts):
                continue
            before = path.stat()
            data = path.read_bytes()
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError(f"File changed during snapshot: {relative}; run backup again when builds are idle")
            archive.writestr(relative.as_posix(), data)
            entries.append({"path": relative.as_posix(), "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        manifest = {"created_utc": timestamp, "excluded_reproducible_directories": sorted(EXCLUDED), "files": entries}
        archive.writestr("BACKUP-MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(temporary) as archive:
        assert archive.testzip() is None, "Archive CRC verification failed"
        for entry in entries:
            if hashlib.sha256(archive.read(entry["path"])).hexdigest() != entry["sha256"]:
                raise RuntimeError(f"Archive SHA256 verification failed: {entry['path']}")
    archive_path = destination / "workspace.zip"
    temporary.replace(archive_path)
    (destination / "SHA256SUMS").write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in (bundle, archive_path)), encoding="utf-8")
    print(json.dumps({"backup": str(destination), "files": len(entries), "archive_bytes": archive_path.stat().st_size}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
