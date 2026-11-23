"""Workbench boundary tests: heterogeneous recipes, failed builds and publication."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import workbench as wb


class WorkbenchTests(unittest.TestCase):
    def test_multiple_tags_form_one_candidate_per_asset_and_preserve_other_settings(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(wb, "STATE", Path(directory)):
            built = []
            def inspect(job, item):
                candidate = wb.read_json(Path(directory) / "jobs" / job["id"] / item["name"] / "candidate.json")
                original = wb.read_json(wb.ROOT / f"specs/textures/{item['name']}.json")
                self.assertEqual(item["tags"], ["wood", "metal"])
                for tag in ("wood", "metal"):
                    expected = {**original["materials"][tag], "brightness": 0.17}
                    self.assertEqual(candidate["materials"][tag], expected)
                self.assertEqual(candidate["materials"]["default"], original["materials"]["default"])
                built.append(item["name"])
            jobs = wb.Jobs()
            with patch.object(jobs, "build", side_effect=inspect):
                jobs.submit({"assets": ["barrel_01", "door_arch_heavy_01", "window_glass_01"],
                             "tags": ["wood", "metal", "wood", "missing"], "patch": {"brightness": 0.17}})
                jobs.pending.join()
            self.assertEqual(built, ["barrel_01", "door_arch_heavy_01"])
            result = jobs.snapshot()[0]
            self.assertEqual(result["status"], "done")
            self.assertEqual(result["items"][-1]["status"], "skipped")
            self.assertEqual(result["tags"], ["wood", "metal", "missing"])

    def test_invalid_tag_lists_do_not_enqueue(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(wb, "STATE", Path(directory)):
            jobs = wb.Jobs()
            for tags in ([], "wood", [None], [""], ["wood"] * 129):
                with self.subTest(tags=tags), self.assertRaises(ValueError):
                    jobs.submit({"assets": ["barrel_01"], "tags": tags})
            self.assertEqual(jobs.snapshot(), [])

    def test_source_switch_preserves_recipe_and_individual_image_scale(self):
        original = wb.read_json(wb.ROOT / "specs/textures/barrel_01.json")
        original["quantize"] = True
        image = wb.patched_spec(original, "wood", {"source_mode": "image", "source_detail": {"image": "door_worn_wood_v1.png"}})
        self.assertFalse(image["quantize"])
        for field in ("staves", "preset", "palette"):
            self.assertEqual(image["materials"]["wood"][field], original["materials"]["wood"][field])
        self.assertEqual(image["materials"]["wood"]["source_detail"]["tile_size"], 1.1)
        procedural = wb.patched_spec(image, "wood", {"source_mode": "procedural"})
        self.assertEqual(procedural["materials"]["wood"]["source_detail"], image["materials"]["wood"]["source_detail"])
        with tempfile.TemporaryDirectory() as directory:
            for candidate in (image, procedural):
                path = Path(directory) / "candidate.json"
                wb.write_json(path, candidate)
                wb.validate_candidate(path, "barrel_01")

    def test_switching_pbr_material_away_from_image_drops_pbr_detail(self):
        original = wb.read_json(wb.ROOT / "specs/textures/wall_stone_01.json")
        self.assertIn("pbr_detail", original["materials"]["stone"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            for mode in ("procedural", "mixed"):
                with self.subTest(mode=mode):
                    candidate = wb.patched_spec(original, "stone", {"source_mode": mode})
                    self.assertNotIn("pbr_detail", candidate["materials"]["stone"])
                    wb.write_json(path, candidate)
                    wb.validate_candidate(path, "wall_stone_01")

    def test_local_http_boundary_and_static_entrypoint(self):
        server = wb.ThreadingHTTPServer(("127.0.0.1", 0), wb.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(base) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"/app.js", response.read())
            requests = [
                (urllib.request.Request(base + "/api/jobs", data=b"{}", headers={
                    "Content-Type": "application/json", "Origin": "https://example.com"}), 400),
                (urllib.request.Request(base + "/%2e%2e/assetgen.py"), 404),
                (urllib.request.Request(base, headers={"Host": "example.com"}), 404),
            ]
            for request, status in requests:
                with self.subTest(url=request.full_url), self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code, status)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_appearance_patch_preserves_specialized_recipes(self):
        for name in ("barrel_01", "door_arch_heavy_01"):
            original = wb.read_json(wb.ROOT / f"specs/textures/{name}.json")
            updated = wb.patched_spec(original, "wood", {"brightness": 0.1, "source_detail": {"strength": 0.3}})
            expected = json.loads(json.dumps(original))
            expected["materials"]["wood"]["brightness"] = 0.1
            expected["materials"]["wood"]["source_detail"]["strength"] = 0.3
            self.assertEqual(updated, expected)
            self.assertNotEqual(original["materials"]["wood"]["source_detail"]["strength"], 0.3)

    def test_explicit_preset_change_clears_old_controls(self):
        original = wb.read_json(wb.ROOT / "specs/textures/barrel_01.json")
        updated = wb.patched_spec(original, "wood", {"preset": "wood", "scale": 7, "source_detail": None})
        material = updated["materials"]["wood"]
        self.assertNotIn("staves", material)
        self.assertNotIn("source_detail", material)
        self.assertEqual(material["scale"], 7)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            wb.write_json(path, updated)
            wb.validate_candidate(path, "barrel_01")

    def test_failed_bake_keeps_recipe_and_outputs_and_queue_continues(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(wb, "STATE", Path(directory)):
            _, recipe, output = wb.asset_paths("barrel_01")
            recipe_bytes = recipe.read_bytes()
            glb = output / "barrel_01.glb"
            glb_bytes = glb.read_bytes() if glb.is_file() else None
            with patch.object(wb.ag, "build_stage", side_effect=RuntimeError("Blender unavailable")):
                jobs = wb.Jobs()
                jobs.submit({"assets": ["barrel_01", "door_arch_heavy_01"], "tag": "wood", "patch": {"brightness": 0.2}})
                jobs.pending.join()
            snapshot = jobs.snapshot()[0]
            self.assertEqual([item["status"] for item in snapshot["items"]], ["error", "error"])
            self.assertIn("Blender unavailable", snapshot["items"][1]["error"])
            self.assertEqual(recipe.read_bytes(), recipe_bytes)
            if glb_bytes is not None:
                self.assertEqual(glb.read_bytes(), glb_bytes)

    def test_publication_backs_up_files_remaps_reports_and_removes_stale_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staging, output, backup = [root / name for name in ("staging", "output", "backup")]
            staging.mkdir(); output.mkdir()
            texture = root / "texture.json"
            wb.write_json(texture, {"old": True})
            (output / "a.glb").write_bytes(b"old")
            (output / "a_godot.glb").write_bytes(b"old collision")
            (output / "a_normal.png").write_bytes(b"stale normal")
            (output / "a_orm.png").write_bytes(b"stale orm")
            (output / "preview_lighting.png").write_bytes(b"stale")
            (staging / "a.glb").write_bytes(b"new")
            wb.write_json(staging / "report_texture.json", {"glb": str(staging / "a.glb"), "previews": []})
            wb.publish(staging, output, texture, {"asset": "a"}, backup)
            self.assertEqual((backup / "a.glb").read_bytes(), b"old")
            self.assertEqual(wb.read_json(backup / "texture_spec.json"), {"old": True})
            self.assertEqual(wb.read_json(output / "report_texture.json")["glb"], str(output / "a.glb"))
            self.assertFalse((output / "a_godot.glb").exists())
            self.assertFalse((output / "a_normal.png").exists())
            self.assertFalse((output / "a_orm.png").exists())
            self.assertFalse((output / "preview_lighting.png").exists())

    def test_rejects_bad_batch_before_enqueuing_any_work(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(wb, "STATE", Path(directory)):
            jobs = wb.Jobs()
            with self.assertRaises(wb.ag.AssetGenError):
                jobs.submit({"assets": ["barrel_01", "door_arch_heavy_01"], "tag": "wood", "patch": {"staves": 10}})
            self.assertEqual(jobs.snapshot(), [])
            self.assertTrue(jobs.pending.empty())
            with self.assertRaises(ValueError):
                jobs.submit({"assets": ["../assetgen"], "tag": "wood"})


if __name__ == "__main__":
    unittest.main()
