"""Clone committed HEAD, install dependencies and exercise viewing without Blender/out."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="assetgen-clone-") as directory:
        clone = Path(directory) / "project"
        subprocess.run(["git", "clone", "--no-local", str(ROOT), str(clone)], check=True, capture_output=True)
        assert not (clone / "out").exists()
        assert not (clone / ".workbench").exists()
        assert not (clone / "assetgen.local.json").exists()
        subprocess.run([sys.executable, "-m", "venv", str(clone / ".venv")], check=True)
        python = clone / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt"], cwd=clone, check=True)
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        assert npm, "Install Node.js/npm first"
        subprocess.run([npm, "--prefix", "web", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=clone, check=True)
        subprocess.run([str(python), "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], cwd=clone, check=True)
        subprocess.run([str(python), "tools/check_distribution.py"], cwd=clone, check=True)
        with (clone / "server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([str(python), "-u", "workbench.py", "--port", "0"], cwd=clone,
                                       env={**os.environ, "BLENDER": "missing-on-purpose", "ASSETGEN_OUT": "out"},
                                       stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8")
            try:
                line = process.stdout.readline().strip()
                assert line.startswith("AssetGen Workbench: http://127.0.0.1:"), line
                url = line.split(": ", 1)[1]
                with urllib.request.urlopen(url + "/api/catalog", timeout=15) as response:
                    catalog = json.load(response)
                built = [asset for asset in catalog["assets"] if asset.get("built")]
                manifest = json.loads((clone / "library/manifest.json").read_text(encoding="utf-8"))
                assert len(built) == len(manifest["assets"]) > 0, "Bundled assets are missing from fresh-clone catalog"
                for asset in built:
                    with urllib.request.urlopen(f"{url}/asset/{asset['name']}/{asset['name']}.glb", timeout=15) as response:
                        assert response.read(4) == b"glTF", asset["name"]
                for route in ("/", "/app.js", "/node_modules/three/build/three.module.js"):
                    with urllib.request.urlopen(url + route, timeout=15) as response:
                        assert response.status == 200
                print(f"Fresh clone passed: {len(built)} viewable models, isolated venv/npm ci, no Blender/out/local config", flush=True)
            finally:
                process.terminate()
                process.wait(timeout=10)
                process.stdout.close()


if __name__ == "__main__":
    main()
