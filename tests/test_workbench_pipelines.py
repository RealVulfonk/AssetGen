"""Real CLI intake, restart recovery and safe whole-set publication."""
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import workbench as wb
from workbench_pipelines import PipelineRuns, inspect_upload, publication_guard
from workbench_surfaces import surface_catalog


def sheet_bytes():
    sheet = Image.new("RGB", (48, 16))
    sheet.paste((85, 55, 32), (0, 0, 16, 16))
    sheet.paste((128, 128, 255), (16, 0, 32, 16))
    sheet.paste((160, 160, 160), (32, 0, 48, 16))
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG")
    return buffer.getvalue()


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "tools").mkdir()
        (self.root / "presets/textures").mkdir(parents=True)
        for name in ("split_pbr_sheet.py", "process_pbr_seams.py"):
            shutil.copy2(wb.ROOT / "tools" / name, self.root / "tools" / name)
        self.state = self.root / ".workbench"
        self.runs = PipelineRuns(self.root, self.state)

    def intake(self, band=2):
        run_id = self.runs.create("test_wall", band, sheet_bytes(), "my source.png")
        self.runs.pending.join()
        return self.runs.get(run_id)

    def test_real_intake_variant_and_restart_preserve_sources_and_outputs(self):
        data = sheet_bytes()
        run = self.intake()
        self.assertEqual(run["status"], "needs_review")
        self.assertEqual(self.runs.file(run["id"], "input", "source").read_bytes(), data)
        split = self.runs.file(run["id"], "split", "test_wall_base_color.png").read_bytes()
        variant = self.runs.variant(run["id"], 4)
        self.runs.pending.join()
        other = self.runs.get(variant)
        self.assertEqual(other["status"], "needs_review")
        self.assertEqual(other["source_run"], run["id"])
        self.assertEqual(self.runs.file(variant, "split", "test_wall_base_color.png").read_bytes(), split)
        reloaded = PipelineRuns(self.root, self.state)
        self.assertEqual(len(reloaded.snapshot()), 2)
        self.assertEqual(reloaded.get(variant)["status"], "needs_review")
        self.assertTrue(reloaded.file(variant, "candidate", "report.json").is_file())

    def test_failed_second_stage_keeps_split_and_allows_corrected_variant(self):
        run = self.intake(12)
        self.assertEqual(run["status"], "error")
        self.assertEqual(run["stage"], "seam")
        self.assertTrue(run["split_ready"])
        self.assertIn("band must fit", run["error"])
        self.assertTrue(self.runs.file(run["id"], "split", "test_wall_normal.png").is_file())
        corrected = self.runs.variant(run["id"], 3)
        self.runs.pending.join()
        self.assertEqual(self.runs.get(corrected)["status"], "needs_review")
        self.assertEqual(run["status"], "error")
        # The failed candidate can never be published, but its split is useful.
        with self.assertRaises(ValueError):
            self.runs.publish(run["id"], "candidate", "failed_wall")
        receipt = self.runs.publish(run["id"], "split", "original_wall")
        self.assertEqual(receipt["status"], "published")

    def test_publication_copies_selected_set_and_rejects_every_conflict(self):
        run = self.intake()
        before = {p.name: p.read_bytes() for p in self.runs.result_folder(run, "candidate").glob("*.png")}
        receipt = self.runs.publish(run["id"], "candidate", "published_wall")
        output = self.root / "presets/textures"
        self.assertEqual(len(receipt["files"]), 3)
        for role in ("base_color", "normal", "roughness"):
            self.assertEqual((output / f"published_wall_{role}.png").read_bytes(), before[f"test_wall_{role}.png"])
        with self.assertRaises(ValueError):
            self.runs.publish(run["id"], "split", "published_wall")
        (output / "single_wall.jpg").write_bytes(b"existing")
        with self.assertRaises(ValueError):
            self.runs.publish(run["id"], "candidate", "single_wall")
        self.assertEqual((output / "single_wall.jpg").read_bytes(), b"existing")
        self.assertEqual(surface_catalog(output)[0]["kind"], "pbr")

    def test_mid_publication_failure_removes_own_links_and_keeps_foreign_file(self):
        run = self.intake()
        output = self.root / "presets/textures"
        real_link = os.link
        count = 0
        def failing_link(source, target):
            nonlocal count
            count += 1
            if count == 2:
                target.write_bytes(b"arrived concurrently")
                raise FileExistsError("concurrent file")
            real_link(source, target)
        with patch("workbench_pipelines.os.link", side_effect=failing_link), self.assertRaises(FileExistsError):
            self.runs.publish(run["id"], "candidate", "collision_wall")
        self.assertFalse((output / "collision_wall_base_color.png").exists())
        self.assertEqual((output / "collision_wall_normal.png").read_bytes(), b"arrived concurrently")
        self.assertEqual(run["publications"][-1]["status"], "rolled_back")

    def test_restart_rolls_back_interrupted_publication_by_file_identity(self):
        run = self.intake()
        output = self.root / "presets/textures"
        staging = output / (".workbench-publish-" + "a" * 32)
        staging.mkdir()
        files = [f"crash_wall_{role}.png" for role in ("base_color", "normal", "roughness")]
        for filename in files:
            (staging / filename).write_bytes(b"staged")
        os.link(staging / files[0], output / files[0])
        # Someone replaced the second target after the interrupted publisher.
        (output / files[1]).write_bytes(b"foreign replacement")
        run["publications"].append({"name": "crash_wall", "selection": "candidate", "status": "publishing",
                                    "staging": staging.name, "files": files})
        self.runs.save(run)
        restarted = PipelineRuns(self.root, self.state)
        self.assertFalse((output / files[0]).exists())
        self.assertEqual((output / files[1]).read_bytes(), b"foreign replacement")
        self.assertEqual(restarted.get(run["id"])["publications"][-1]["status"], "rolled_back")
        self.assertFalse(staging.exists())

    def test_restart_marks_unfinished_runs_and_retries_saved_upload(self):
        run = self.intake()
        # Represent a process stopped before split. Its saved source is sufficient.
        run.update(status="running", split_ready=False)
        self.runs.save(run)
        restarted = PipelineRuns(self.root, self.state)
        self.assertEqual(restarted.get(run["id"])["status"], "interrupted")
        variant = restarted.variant(run["id"], 2)
        restarted.pending.join()
        self.assertEqual(restarted.get(variant)["status"], "needs_review")
        self.assertNotIn("source_run", restarted.get(variant))

    def test_invalid_upload_and_parameters_do_not_create_runs(self):
        for data in (b"", b"this is not a picture"):
            with self.assertRaises(ValueError):
                self.runs.create("test_wall", 2, data)
        image = Image.new("RGB", (47, 16)); stream = io.BytesIO(); image.save(stream, format="PNG")
        with self.assertRaises(ValueError):
            inspect_upload(stream.getvalue())
        for name, band in (("../wall", 2), ("wall", True), ("wall", 0), ("wall", "24")):
            with self.assertRaises(ValueError):
                self.runs.create(name, band, sheet_bytes())
        self.assertEqual(self.runs.snapshot(), [])

    def test_result_paths_and_os_lock_reject_unsafe_access(self):
        run = self.intake()
        with self.assertRaises(ValueError):
            self.runs.file(run["id"], "split", "../source")
        with self.assertRaises(ValueError):
            self.runs.file("../outside", "input", "source")
        with publication_guard(self.state):
            with self.assertRaises(ValueError):
                self.runs.publish(run["id"], "split", "locked_wall")
        self.assertEqual(self.runs.publish(run["id"], "split", "unlocked_wall")["status"], "published")

    def test_http_upload_saved_input_history_variant_and_publication(self):
        server = wb.ThreadingHTTPServer(("127.0.0.1", 0), wb.Handler)
        server.pipelines = self.runs
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        def post(path, data):
            request = urllib.request.Request(base + path, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request) as response:
                return json.load(response)
        try:
            request = urllib.request.Request(base + "/api/pipelines/pbr_intake?name=test_wall&band=2&filename=uploaded.png",
                                             data=sheet_bytes(), headers={"Content-Type": "application/octet-stream"})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 202)
                run_id = json.load(response)["id"]
            self.runs.pending.join()
            with urllib.request.urlopen(base + "/api/runs") as response:
                history = json.load(response)
                self.assertEqual(history[0]["id"], run_id)
                self.assertEqual(history[0]["status"], "needs_review")
            with urllib.request.urlopen(base + f"/run-file/{run_id}/input/source") as response:
                self.assertEqual(response.read(), sheet_bytes())
            with urllib.request.urlopen(base + f"/run-file/{run_id}/candidate/report.json") as response:
                self.assertEqual(json.load(response)["band_px"], 2)
            variant = post("/api/runs/variant", {"id": run_id, "band": 4})["id"]
            self.runs.pending.join()
            self.assertEqual(self.runs.get(variant)["source_run"], run_id)
            receipt = post("/api/runs/publish", {"id": variant, "selection": "candidate", "name": "http_wall"})
            self.assertEqual(receipt["status"], "published")
            with self.assertRaises(urllib.error.HTTPError) as error:
                post("/api/runs/publish", {"id": variant, "selection": "candidate", "name": "http_wall"})
            self.assertEqual(error.exception.code, 400)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(base + "/api/pipelines/pbr_intake?name=test_wall", data=b"invalid", headers={"Content-Type": "application/octet-stream", "Origin": "https://example.com"}))
            self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class SurfaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.folder = self.root / "presets/textures"
        self.folder.mkdir(parents=True)
        for prefix in ("wall", "wall_02"):
            for role in ("base_color", "normal", "roughness"):
                Image.new("RGB", (4, 4)).save(self.folder / f"{prefix}_{role}.png")
        for name in ("single.jpg", "partial_base_color.png", "orphan_normal.png", "bad_base_color.png", "bad_normal.jpg", "bad_roughness.png"):
            Image.new("RGB", (4, 4)).save(self.folder / name)
        self.spec = {"materials": {"a": {"source_mode": "image", "source_detail": {"image": "wall_base_color.png", "tile_size": 0.3}, "pbr_detail": {"normal": "wall_normal.png", "roughness": "wall_roughness.png"}},
                                   "b": {"source_mode": "image", "source_detail": {"image": "wall_base_color.png", "tile_size": 2.5}, "pbr_detail": {"normal": "custom.png", "roughness": "custom_r.png"}}}}

    def test_grouping_exact_prefixes_incomplete_orphans_and_non_png_data(self):
        groups = {surface["id"]: surface for surface in surface_catalog(self.folder)}
        self.assertEqual(groups["wall"]["kind"], "pbr")
        self.assertEqual(groups["wall_02"]["kind"], "pbr")
        self.assertEqual(groups["partial"]["missing"], ["normal", "roughness"])
        self.assertIsNone(groups["orphan"]["image"])
        self.assertEqual(groups["bad"]["missing"], ["normal"])
        self.assertNotIn("bad_normal.jpg", groups)
        self.assertEqual(groups["single.jpg"]["kind"], "image")

    def test_surface_change_replaces_all_channels_and_preserves_each_scale(self):
        self.spec["materials"]["b"]["pbr_detail"]["normal_strength"] = 0.4
        with patch.object(wb, "ROOT", self.root), patch.object(wb, "STATE", self.root / ".workbench"):
            result = self.spec
            for tag in ("a", "b"):
                result = wb.patched_spec(result, tag, {"surface": "wall_02", "source_mode": "image"})
                expected = {**self.spec["materials"][tag]["pbr_detail"], "normal": "wall_02_normal.png", "roughness": "wall_02_roughness.png"}
                self.assertEqual(result["materials"][tag]["pbr_detail"], expected)
                self.assertEqual(result["materials"][tag]["source_detail"]["tile_size"], self.spec["materials"][tag]["source_detail"]["tile_size"])
            result = wb.patched_spec(result, "a", {"surface": "single.jpg"})
            self.assertNotIn("pbr_detail", result["materials"]["a"])
            self.assertEqual(result["materials"]["a"]["source_detail"]["tile_size"], 0.3)
            result = wb.patched_spec(result, "b", {"surface": "partial"})
            self.assertNotIn("pbr_detail", result["materials"]["b"])

    def test_legacy_explicit_channels_and_brightness_preserve_actual_maps(self):
        with patch.object(wb, "ROOT", self.root), patch.object(wb, "STATE", self.root / ".workbench"):
            for patch_data in ({"brightness": 0.2}, {"source_detail": {"tile_size": 5}}):
                result = wb.patched_spec(self.spec, "b", patch_data)
                self.assertEqual(result["materials"]["b"]["pbr_detail"], self.spec["materials"]["b"]["pbr_detail"])
            custom = {"normal": "custom_normal.png", "roughness": "custom_roughness.png"}
            result = wb.patched_spec(self.spec, "b", {"source_detail": {"image": "single.jpg"}, "pbr_detail": custom})
            self.assertEqual(result["materials"]["b"]["pbr_detail"], custom)
            changed = wb.patched_spec(self.spec, "a", {"source_detail": {"image": "wall_02_base_color.png"}})
            self.assertEqual(changed["materials"]["a"]["pbr_detail"]["normal"], "wall_02_normal.png")
            cleared = wb.patched_spec(self.spec, "a", {"source_detail": None})
            self.assertNotIn("source_detail", cleared["materials"]["a"])
            self.assertNotIn("pbr_detail", cleared["materials"]["a"])

    def test_mixed_selection_is_color_only_and_clear_then_selection_retains_scale(self):
        with patch.object(wb, "ROOT", self.root), patch.object(wb, "STATE", self.root / ".workbench"):
            mixed = wb.patched_spec(self.spec, "a", {"source_mode": "mixed", "surface": "wall_02"})
            self.assertNotIn("pbr_detail", mixed["materials"]["a"])
            restored = wb.patched_spec(self.spec, "a", {"surface": "wall_02", "source_detail": None})
            self.assertEqual(restored["materials"]["a"]["source_detail"]["tile_size"], 0.3)
            with self.assertRaises(ValueError):
                wb.patched_spec(self.spec, "a", {"surface": "orphan"})


if __name__ == "__main__":
    unittest.main()
