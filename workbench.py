#!/usr/bin/env python3
"""Local AssetGen workbench. Run: python workbench.py [--port 5173] [--open]."""

import argparse
import copy
import hashlib
import json
import mimetypes
import queue
import re
import shutil
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import assetgen as ag

ROOT = ag.ROOT
WEB = ROOT / "web"
STATE = ROOT / ".workbench"
NAME = re.compile(r"^[a-z0-9_]+$")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def asset_paths(name):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError("Invalid asset name")
    model = ROOT / "specs/models" / f"{name}.json"
    data = read_json(model)
    return model, ROOT / "specs/textures" / f"{name}.json", ag.output_dir(ag.OUT, name, data.get("category"))


def display_dir(name):
    """Local builds take precedence; a fresh clone can view the shared library."""
    model, _, output = asset_paths(name)
    if (output / f"{name}.glb").is_file():
        return output
    category = read_json(model).get("category")
    return ag.output_dir(ROOT / "library", name, category)


def catalog():
    assets = []
    for path in sorted((ROOT / "specs/models").glob("*.json")):
        try:
            model, texture, output = asset_paths(path.stem)
            output = display_dir(path.stem)
            spec = read_json(model)
            report = read_json(output / "report.json") if (output / "report.json").is_file() else {}
            tex = read_json(texture) if texture.is_file() else None
            glb = output / f"{path.stem}.glb"
            digest = hashlib.sha256(model.read_bytes()).hexdigest()
            assets.append({
                "name": path.stem, "category": spec.get("category", "uncategorized"),
                "tags": sorted({p.get("material", "default") for p in spec["parts"]}),
                "texture": tex, "built": glb.is_file(),
                "textured": (output / "report_texture.json").is_file(),
                "stale": report.get("model_digest") != digest,
                "tris": report.get("tris"), "dimensions": report.get("dimensions"),
                "version": glb.stat().st_mtime_ns if glb.is_file() else 0,
                "preview": (output / "preview_iso.png").is_file(),
            })
        except (OSError, ValueError, KeyError) as error:
            assets.append({"name": path.stem, "error": str(error), "tags": [], "category": "error"})
    return assets


def patched_spec(original, tag, patch):
    """Patch explicit fields only; never infer another asset's entire recipe."""
    result = copy.deepcopy(original)
    if tag not in result["materials"]:
        raise ValueError(f"Material {tag!r} has no explicit recipe")
    material = result["materials"][tag]
    if "source_detail" in patch:
        detail = patch["source_detail"]
        if detail is None:
            material.pop("source_detail", None)
        elif isinstance(detail, dict):
            material["source_detail"] = {"tile_size": 1, "strength": 0.6,
                                         **material.get("source_detail", {}), **detail}
        else:
            raise ValueError("source_detail must be an object or null")
    if "preset" in patch:
        # These controls belong to the old generator, not the shared appearance.
        for key in ("layers", "scale", "direction", "detail", "distortion", "value",
                    "staves", "seam_width", "lid_board_width", "grain_strength"):
            material.pop(key, None)
    material.update({key: value for key, value in patch.items() if key != "source_detail"})
    if material.get("source_mode") == "image":
        result["quantize"] = False
    return result


def validate_candidate(path, name):
    data = ag.validate(path, "texture.schema.json")
    if data["asset"] != name:
        raise ValueError("Texture asset name does not match model")
    palettes = read_json(ROOT / "presets/palettes.json")
    for material in data["materials"].values():
        palette = material["palette"]
        if isinstance(palette, str) and palette not in palettes:
            raise ValueError(f"Unknown palette: {palette}")
        detail = material.get("source_detail")
        if detail and not (ROOT / "presets/textures" / detail["image"]).is_file():
            raise ValueError(f"Missing source image: {detail['image']}")


def publish(staging, output, texture_path, candidate, backup):
    """Publish complete files, reports last; retain previous files for recovery."""
    output.mkdir(parents=True, exist_ok=True)
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(texture_path, backup / "texture_spec.json")
    files = sorted(staging.iterdir(), key=lambda p: p.name.startswith("report"))
    files = [p for p in files if p.is_file() and not p.name.endswith(".blend1")]
    texture_report = read_json(staging / "report_texture.json")
    obsolete = ["preview_lighting.png"]
    if not texture_report.get("godot_glb"):
        obsolete.append(f"{candidate['asset']}_godot.glb")
    touched = list(dict.fromkeys([p.name for p in files] + obsolete))
    previous = []
    for filename in touched:
        destination = output / filename
        if destination.is_file():
            shutil.copy2(destination, backup / filename)
            previous.append(filename)
    write_json(backup / "manifest.json", {"output": str(output), "texture_spec": str(texture_path),
                                           "files": touched, "previous": previous})
    try:
        for filename in obsolete:
            (output / filename).unlink(missing_ok=True)
        for source in files:
            destination = output / source.name
            if source.name.startswith("report") and source.suffix == ".json":
                report = read_json(source)
                for key in ("blend", "glb", "godot_glb", "texture", "lighting_preview"):
                    if report.get(key):
                        report[key] = str(output / Path(report[key]).name)
                report["previews"] = [str(output / Path(p).name) for p in report.get("previews", [])]
                write_json(destination, report)
            else:
                temporary = destination.with_name(destination.name + ".workbench-tmp")
                shutil.copy2(source, temporary)
                temporary.replace(destination)
        if read_json(texture_path) != candidate:
            write_json(texture_path, candidate)
    except Exception:
        for filename in touched:
            destination = output / filename
            if filename in previous:
                shutil.copy2(backup / filename, destination)
            else:
                destination.unlink(missing_ok=True)
        shutil.copy2(backup / "texture_spec.json", texture_path)
        raise


class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.pending = queue.Queue()
        self.jobs = []
        for path in sorted((STATE / "jobs").glob("*/job.json")):
            try:
                job = read_json(path)
            except (OSError, ValueError) as error:
                print(f"Skipping unreadable job {path}: {error}", flush=True)
                continue
            if job["status"] in ("queued", "running"):
                job["status"] = "interrupted"
                for item in job["items"]:
                    if item["status"] in ("queued", "running"):
                        item.update(status="error", error="Server stopped; submit the task again")
                write_json(path, job)
            self.jobs.append(job)
        threading.Thread(target=self.worker, daemon=True).start()

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.jobs[-30:][::-1])

    def save(self, job):
        write_json(STATE / "jobs" / job["id"] / "job.json", job)

    def submit(self, payload):
        names, patch = payload.get("assets"), payload.get("patch", {})
        tags = payload.get("tags", [payload.get("tag")])
        if not isinstance(names, list) or not names or len(names) > 500:
            raise ValueError("Select 1–500 assets")
        if (not isinstance(tags, list) or not tags or len(tags) > 128
                or any(not isinstance(tag, str) or not tag.strip() for tag in tags)
                or not isinstance(patch, dict)):
            raise ValueError("Select 1–128 material tags and provide a patch")
        tags = list(dict.fromkeys(tags))
        job = {"id": f"{time.time_ns()}-{uuid.uuid4().hex[:6]}", "status": "queued",
               "tags": tags, "tag": ", ".join(tags), "created": time.time(), "items": []}
        folder = STATE / "jobs" / job["id"]
        for name in dict.fromkeys(names):
            model, texture, _ = asset_paths(name)
            item = {"name": name, "status": "queued"}
            original = read_json(texture) if texture.is_file() else None
            matching = [tag for tag in tags if original and tag in original["materials"]]
            item["tags"] = matching
            if not matching:
                item.update(status="skipped", error=f"No explicit materials: {', '.join(tags)}")
            else:
                candidate = original
                for tag in matching:
                    candidate = patched_spec(candidate, tag, patch)
                path = folder / name / "candidate.json"
                write_json(path, candidate)
                validate_candidate(path, name)
                item["texture_digest"] = hashlib.sha256(texture.read_bytes()).hexdigest()
                item["model_digest"] = hashlib.sha256(model.read_bytes()).hexdigest()
            job["items"].append(item)
        with self.lock:
            self.jobs.append(job)
            self.save(job)
        self.pending.put(job)
        return job["id"]

    def update(self, job, record, **fields):
        with self.lock:
            record.update(fields)
            self.save(job)

    def worker(self):
        while True:
            job = self.pending.get()
            self.update(job, job, status="running")
            for item in job["items"]:
                if item["status"] == "skipped":
                    continue
                self.update(job, item, status="running")
                try:
                    self.build(job, item)
                    self.update(job, item, status="done")
                except Exception as error:
                    self.update(job, item, status="error", error=str(error))
            status = "error" if any(i["status"] == "error" for i in job["items"]) else "done"
            self.update(job, job, status=status)
            self.pending.task_done()

    def build(self, job, item):
        name = item["name"]
        model, texture, output = asset_paths(name)
        folder = STATE / "jobs" / job["id"] / name
        candidate_path = folder / "candidate.json"
        staging = folder / "output"
        staging.mkdir(exist_ok=True)
        candidate = read_json(candidate_path)
        with ag.asset_lock(output):
            def check_inputs():
                for key, path in (("texture_digest", texture), ("model_digest", model)):
                    if hashlib.sha256(path.read_bytes()).hexdigest() != item[key]:
                        raise ValueError(f"{path.name} changed after enqueue; submit again")
            check_inputs()
            validate_candidate(candidate_path, name)
            snapshot = folder / "model.json"
            snapshot.write_bytes(model.read_bytes())
            ag.validate(snapshot, "model.schema.json")
            report_path = output / "report.json"
            report = read_json(report_path) if report_path.is_file() else {}
            blend = output / f"{name}.blend"
            if not blend.is_file() or report.get("model_digest") != item["model_digest"]:
                report = ag.build_stage("model", snapshot, staging)
                blend = Path(report["blend"])
            ag.build_stage("texture", candidate_path, staging, blend=blend, model_digest=item["model_digest"])
            check_inputs()
            publish(staging, output, texture, candidate, folder / "backup")


class Handler(BaseHTTPRequestHandler):
    def json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def trusted(self):
        expected = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != expected:
            raise ValueError("Open the workbench at http://" + expected)
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + expected:
            raise ValueError("Cross-origin requests are not allowed")

    def do_GET(self):
        try:
            self.trusted()
            path = unquote(urlsplit(self.path).path)
            if path == "/api/catalog":
                return self.json({"assets": catalog(), "palettes": read_json(ROOT / "presets/palettes.json"),
                                  "images": sorted(p.name for p in (ROOT / "presets/textures").iterdir()
                                                   if p.suffix.lower() in (".png", ".jpg", ".jpeg")
                                                   and re.fullmatch(r"[a-z0-9_]+\.(png|jpe?g)", p.name)),
                                  "schema": read_json(ROOT / "schemas/texture.schema.json")})
            if path == "/api/jobs":
                return self.json(self.server.jobs.snapshot())
            if path.startswith("/asset/"):
                _, _, name, filename = path.split("/")
                folder = display_dir(name)
                if filename not in (f"{name}.glb", "preview_iso.png"):
                    raise ValueError("Unsupported asset file")
            elif path.startswith("/textures/"):
                folder, filename = ROOT / "presets/textures", path.removeprefix("/textures/")
                if not re.fullmatch(r"[a-z0-9_]+\.(png|jpe?g)", filename):
                    raise ValueError("Unsupported texture file")
            else:
                folder, filename = WEB, path.lstrip("/") or "index.html"
                if filename.startswith("node_modules/") and not filename.startswith("node_modules/three/"):
                    raise ValueError("Unsupported dependency")
            target = (folder / filename).resolve()
            if not target.is_relative_to(folder.resolve()) or not target.is_file():
                raise FileNotFoundError("File not found")
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript" if target.suffix == ".js" else
                             mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (ValueError, OSError, KeyError) as error:
            self.json({"error": str(error)}, 404)

    def do_POST(self):
        try:
            self.trusted()
            if self.path != "/api/jobs":
                raise ValueError("Unknown endpoint")
            if self.headers.get("Content-Type") != "application/json":
                raise ValueError("Expected application/json")
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 1_000_000:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Expected JSON object")
            return self.json({"id": self.server.jobs.submit(payload)}, 202)
        except (ValueError, OSError, KeyError, TypeError, ag.AssetGenError) as error:
            self.json({"error": str(error)}, 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    if not (WEB / "node_modules/three/build/three.module.js").is_file():
        parser.error("Install browser dependencies first: npm --prefix web ci")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.jobs = Jobs()
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"AssetGen Workbench: {url}", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping workbench; queued/running jobs will be marked interrupted on restart.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
