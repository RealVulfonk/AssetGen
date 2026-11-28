"""Persistent, local named pipelines. No arbitrary commands or caller paths."""
import copy
import hashlib
import io
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, UnidentifiedImageError

PANELS = ("base_color", "normal", "roughness")
SAFE_NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
SAFE_ID = re.compile(r"[0-9]+-[a-f0-9]{8}$")
MAX_UPLOAD = 40 * 1024 * 1024
PIPELINES = [{"id": "pbr_intake", "title": "Подготовить PBR",
              "description": "Разрезать лист Base Color / Normal / Roughness и создать кандидат обработки стыков. Исходник сохраняется; публикация выполняется отдельно.",
              "parameters": {"band": {"default": 24, "minimum": 1}, "name": "snake_case"}}]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


@contextmanager
def publication_guard(state):
    """OS-owned lock releases even when the process is killed."""
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    with (state / ".publication.lock").open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("Library publication is active; retry shortly") from error
        yield


def validate_name(name):
    if not isinstance(name, str) or len(name) > 80 or not SAFE_NAME.fullmatch(name):
        raise ValueError("Use snake_case, starting with a letter (up to 80 characters)")


def validate_band(band):
    if type(band) is not int or not 1 <= band <= 4096:
        raise ValueError("Band must be an integer from 1 to 4096 px")


def inspect_upload(data):
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError("Upload must contain an image up to 40 MiB")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ("PNG", "JPEG", "WEBP"):
                raise ValueError("Use a PNG, JPEG or WebP image")
            width, height = image.size
            if width % 3 or width < 3 or height < 1:
                raise ValueError(f"Sheet width must be divisible by 3, got {width}×{height}")
            # Bound memory and CPU for the Python seam processor/repeat previews.
            if width // 3 > 4096 or height > 4096:
                raise ValueError("Each panel must be at most 4096×4096 px")
            image.verify()
            return [width, height]
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ValueError(f"Cannot read uploaded image: {error}") from error


class PipelineRuns:
    def __init__(self, root, state):
        self.root, self.state, self.folder = Path(root), Path(state), Path(state) / "runs"
        self.lock = threading.RLock()
        self.pending = queue.Queue()
        self.runs = {}
        self.folder.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.folder.glob("*/run.json")):
            try:
                run = read_json(path)
                if run["status"] in ("queued", "running"):
                    run.update(status="interrupted", error="Server stopped. Repeat this saved input to continue.")
                    write_json(path, run)
                self.runs[run["id"]] = run
            except (OSError, ValueError, KeyError) as error:
                print(f"Skipping unreadable pipeline run {path}: {error}", flush=True)
        with publication_guard(self.state):
            self.recover_publications()
        threading.Thread(target=self.worker, daemon=True).start()

    def recover_publications(self):
        """Only remove links still owned by an unfinished transaction.

        Keeping the staged inode until commit lets recovery distinguish our file
        from any unrelated file created or replaced after a crash.
        """
        output = self.root / "presets/textures"
        for run in self.runs.values():
            for receipt in run.get("publications", []):
                if receipt["status"] != "publishing":
                    continue
                stage_name = receipt.get("staging", "")
                if not re.fullmatch(r"\.workbench-publish-[a-f0-9]{32}", stage_name):
                    receipt.update(status="recovery_error", error="Unknown staging directory; files preserved")
                    self.save(run)
                    continue
                staging = output / stage_name
                if not staging.is_dir() or staging.resolve().parent != output.resolve():
                    receipt.update(status="recovery_error", error="Staged files are missing or outside the library; target files preserved")
                    self.save(run)
                    continue
                for filename in receipt["files"]:
                    target, staged = output / filename, staging / filename
                    if not re.fullmatch(r"[a-z0-9_]+\.png", filename):
                        continue
                    if target.is_file() and staged.is_file() and os.path.samefile(staged, target):
                        target.unlink()
                receipt["status"] = "rolled_back"
                self.save(run)
                if staging.is_dir() and staging.resolve().parent == output.resolve():
                    shutil.rmtree(staging)

    def get(self, run_id):
        if not isinstance(run_id, str) or not SAFE_ID.fullmatch(run_id) or run_id not in self.runs:
            raise ValueError("Unknown pipeline run")
        return self.runs[run_id]

    def save(self, run):
        write_json(self.folder / run["id"] / "run.json", run)

    def update(self, run, **fields):
        with self.lock:
            run.update(fields)
            self.save(run)

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(sorted(self.runs.values(), key=lambda run: run["created"], reverse=True))

    def create(self, name, band, data=None, filename="", previous=None):
        validate_name(name)
        validate_band(band)
        source = None
        if previous:
            with self.lock:
                parent = self.get(previous)
                source = self.get(parent.get("source_run") or parent["id"])
                # A new run references a completed immutable split. If splitting
                # was interrupted, retry from a copy of the original upload.
                if not source.get("split_ready"):
                    data = (self.folder / source["id"] / "source").read_bytes()
                    filename = source["filename"]
                    source = None
        size = source["size"] if source else inspect_upload(data)
        run = {"id": f"{time.time_ns()}-{uuid.uuid4().hex[:8]}", "pipeline": "pbr_intake",
               "name": name, "band": band, "created": time.time(), "status": "queued", "stage": "queued",
               "size": size, "filename": Path(filename.replace("\\", "/")).name[:200],
               "events": [], "publications": [], "split_ready": False}
        if previous:
            run["previous"] = previous
        folder = self.folder / run["id"]
        folder.mkdir()
        if source:
            run.update(source_run=source["id"], name=source["name"], filename=source["filename"],
                       source_sha256=source["source_sha256"], split_ready=True)
        else:
            (folder / "source").write_bytes(data)
            run["source_sha256"] = hashlib.sha256(data).hexdigest()
        with self.lock:
            self.save(run)
            self.runs[run["id"]] = run
        self.pending.put(run)
        return run["id"]

    def variant(self, run_id, band):
        with self.lock:
            run = self.get(run_id)
            if run["status"] in ("queued", "running"):
                raise ValueError("Wait until this run finishes")
            return self.create(run["name"], band, previous=run_id)

    def event(self, run, stage, message):
        with self.lock:
            run["stage"] = stage
            run["events"].append({"time": time.time(), "stage": stage, "message": message})
            self.save(run)

    def command(self, run, stage, arguments):
        self.event(run, stage, "Started " + stage)
        result = subprocess.run([sys.executable, *map(str, arguments)], cwd=self.root,
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=1800, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.event(run, stage, (result.stdout + result.stderr)[-24000:])
        if result.returncode:
            raise ValueError(f"{stage} failed (exit {result.returncode}). {result.stderr[-4000:] or result.stdout[-4000:]}")

    def worker(self):
        while True:
            run = self.pending.get()
            try:
                self.update(run, status="running")
                folder = self.folder / run["id"]
                if not run.get("source_run"):
                    split = folder / "split"
                    split.mkdir()
                    self.command(run, "split", [self.root / "tools/split_pbr_sheet.py", folder / "source",
                                                "--out", split, "--name", run["name"]])
                    self.validate_maps(split, run["name"])
                    self.update(run, split_ready=True)
                source = self.get(run.get("source_run") or run["id"])
                split = self.folder / source["id"] / "split"
                self.validate_maps(split, run["name"])
                candidate = folder / "seam"
                candidate.mkdir()
                self.command(run, "seam", [self.root / "tools/process_pbr_seams.py", "--source", split,
                                           "--out", candidate, "--name", run["name"], "--band", run["band"]])
                self.validate_maps(candidate / (run["name"] + "_seam_candidate"), run["name"])
                self.event(run, "review", "Candidate requires visual review. Publication is an explicit separate action.")
                self.update(run, status="needs_review")
            except Exception as error:
                self.event(run, run["stage"], str(error))
                self.update(run, status="error", error=str(error))
            finally:
                self.pending.task_done()

    @staticmethod
    def validate_maps(folder, name):
        sizes = []
        for role in PANELS:
            with Image.open(folder / f"{name}_{role}.png") as image:
                image.load()
                sizes.append(image.size)
        if len(set(sizes)) != 1:
            raise ValueError("Map dimensions differ")

    def result_folder(self, run, selection):
        if selection == "split":
            source = self.get(run.get("source_run") or run["id"])
            if not source.get("split_ready"):
                raise ValueError("Split is not ready")
            return self.folder / source["id"] / "split"
        if selection == "candidate" and run["status"] == "needs_review":
            return self.folder / run["id"] / "seam" / (run["name"] + "_seam_candidate")
        raise ValueError("Select a completed split or candidate")

    def file(self, run_id, selection, filename):
        with self.lock:
            run = self.get(run_id)
            if selection == "input" and filename == "source":
                source = self.get(run.get("source_run") or run["id"])
                return self.folder / source["id"] / "source"
            allowed = {f"{run['name']}_{role}.png" for role in PANELS}
            if selection == "candidate":
                allowed |= {f"{role}_{when}_repeat.png" for role in PANELS for when in ("before", "after")}
                allowed.add("report.json")
            if filename not in allowed:
                raise ValueError("Unsupported result file")
            return self.result_folder(run, selection) / filename

    def publish(self, run_id, selection, name):
        """Serialize publishers, stage all files and roll back a partial copy.

        Pending receipt makes a process interruption recoverable; catalog only
        exposes fully committed sets after this short publication lock is held.
        """
        validate_name(name)
        with self.lock, publication_guard(self.state):
            run = self.get(run_id)
            source = self.result_folder(run, selection)
            self.validate_maps(source, run["name"])
            output = self.root / "presets/textures"
            output.mkdir(parents=True, exist_ok=True)
            staging = output / (".workbench-publish-" + uuid.uuid4().hex)
            try:
                conflicts = [p for p in output.iterdir() if p.is_file() and p.stem in
                             {name, *(f"{name}_{role}" for role in PANELS)}]
                if conflicts:
                    raise ValueError("Name is occupied. Choose another name: " + name)
                staging.mkdir()
                for role in PANELS:
                    shutil.copy2(source / f"{run['name']}_{role}.png", staging / f"{name}_{role}.png")
                receipt = {"name": name, "selection": selection, "created": time.time(), "status": "publishing",
                           "staging": staging.name, "files": [f"{name}_{role}.png" for role in PANELS]}
                run["publications"].append(receipt)
                self.save(run)
                try:
                    for filename in receipt["files"]:
                        # Atomic exclusive hard link: no partial file is exposed,
                        # no existing file can be replaced, identity survives a crash.
                        os.link(staging / filename, output / filename)
                    receipt["status"] = "published"
                    self.save(run)
                except Exception:
                    for filename in receipt["files"]:
                        staged, target = staging / filename, output / filename
                        if target.is_file() and os.path.samefile(staged, target):
                            target.unlink()
                    receipt["status"] = "rolled_back"
                    self.save(run)
                    raise
            finally:
                if staging.is_dir() and staging.resolve().parent == output.resolve():
                    shutil.rmtree(staging)
            return copy.deepcopy(receipt)
