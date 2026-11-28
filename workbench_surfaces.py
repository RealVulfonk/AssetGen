"""Exact-name surface catalog and atomic material selection for the workbench."""
import re

IMAGE = re.compile(r"[a-z0-9_]+\.(?:png|jpe?g)$")
CHANNELS = ("base_color", "normal", "roughness")


def surface_catalog(folder):
    groups, singles = {}, []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or not IMAGE.fullmatch(path.name):
            continue
        role = next((role for role in CHANNELS if path.stem.endswith("_" + role)), None)
        if role and role != "base_color" and path.suffix != ".png":
            continue  # Data maps accepted by the texture schema are PNG only.
        if role:
            stem = path.stem[:-(len(role) + 1)]
            groups.setdefault(stem, {}).setdefault(role, path.name)
        else:
            singles.append({"id": path.name, "name": path.stem, "image": path.name,
                            "maps": {"base_color": path.name}, "missing": [], "kind": "image"})
    surfaces = []
    for name, maps in groups.items():
        # Data-only fragments are visible as diagnostics, never offered as colors.
        missing = [role for role in CHANNELS if role not in maps]
        surfaces.append({"id": name, "name": name, "image": maps.get("base_color"),
                         "maps": maps, "missing": missing,
                         "kind": "pbr" if not missing else "incomplete"})
    return sorted(surfaces + singles, key=lambda item: (item["name"], item["id"]))


def select_surface(material, selection, surfaces):
    surface = next((item for item in surfaces if item["id"] == selection), None)
    if not surface or not surface["image"]:
        raise ValueError("Select a surface with a Base Color image")
    # Preserve each target's own projection/strength; a choice never copies the
    # active tag's tile size into the rest of a batch.
    material["source_detail"] = {"tile_size": 1, "strength": 0.6,
                                 **material.get("source_detail", {}), "image": surface["image"]}
    previous = material.pop("pbr_detail", None) or {}
    if material.get("source_mode") == "image" and surface["kind"] == "pbr":
        material["pbr_detail"] = {key: surface["maps"][key] for key in ("normal", "roughness")}
        if "normal_strength" in previous:
            material["pbr_detail"]["normal_strength"] = previous["normal_strength"]
