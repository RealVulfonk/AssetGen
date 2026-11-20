"""Bake a procedural albedo onto a generated model.

blender -b out/x/x.blend --python-exit-code 1 -P blender/bake_texture.py -- tex_spec.json out_dir
"""

import json
import math
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
from common import export_glb, hex2lin, hex2rgb, render_previews

SOURCE_TEXTURES = os.path.join(HERE, "..", "presets", "textures")
from uv_layout import pack_uv_islands

with open(os.path.join(HERE, "..", "presets", "palettes.json"), encoding="utf-8") as handle:
    PALETTES = json.load(handle)


def palette(config):
    value = config["palette"]
    return PALETTES[value] if isinstance(value, str) else value


def resolve_layer(layer):
    kind = layer["type"]
    resolved = {"type": kind, "weight": 1.0, "invert": False}
    if kind in ("noise", "wave", "voronoi"):
        resolved["scale"] = 5.0
    if kind == "noise":
        resolved["detail"] = 2.0
    elif kind == "wave":
        resolved.update(direction="X", distortion=4.0)
    elif kind == "constant":
        resolved["value"] = 0.6
    resolved.update(layer)
    return resolved


def resolve_material(config):
    resolved = {
        "gradient": "ease",
        "contrast": 1.0,
        "contrast_pivot": 0.5,
        "brightness": 0.0,
        "ao": 0.25,
        "ao_distance": 0.15,
        "edge": 0.0,
        "metallic": 0.0,
        "opacity": 1.0,
        "roughness": 0.9,
    }
    if config.get("preset") == "coopered_wood":
        resolved.update(staves=10, seam_width=0.06, lid_board_width=0.12, grain_strength=0.55)
    elif "layers" not in config:
        resolved.update(
            preset="noise",
            scale=5.0,
            direction="X",
            distortion=4.0,
            detail=2.0,
            value=0.6,
        )
    resolved.update(config)
    if "layers" in resolved:
        resolved["layers"] = [resolve_layer(layer) for layer in resolved["layers"]]
    return resolved


def preset_layers(config):
    preset = config.get("preset", "noise")
    scale = config.get("scale", 5.0)
    detail = config.get("detail", 2.0)
    if preset == "wood":
        layers = [
            {
                "type": "wave",
                "scale": scale,
                "direction": config.get("direction", "X"),
                "distortion": config.get("distortion", 4.0),
                "weight": 0.60,
            },
            {"type": "noise", "scale": scale * 0.4, "detail": detail, "weight": 0.25},
            {"type": "noise", "scale": scale * 4.0, "detail": 2.0, "weight": 0.15},
        ]
    elif preset == "stone":
        layers = [
            {"type": "noise", "scale": scale * 0.35, "detail": detail, "weight": 0.55},
            {"type": "voronoi", "scale": scale, "weight": 0.25},
            {"type": "noise", "scale": scale * 3.0, "detail": 2.0, "weight": 0.20},
        ]
    elif preset == "flat":
        layers = [{"type": "constant", "value": config.get("value", 0.6), "weight": 1.0}]
    else:
        layers = [{"type": "noise", "scale": scale, "detail": detail, "weight": 1.0}]
    return [resolve_layer(layer) for layer in layers]


def ramp_positions(count, gradient):
    if count < 1:
        raise ValueError("A palette needs at least one color")
    if count == 1:
        return [0.0]
    if gradient == "constant":
        return [index / count for index in range(count)]
    return [index / (count - 1) for index in range(count)]


def math_node(nodes, links, operation, first, second, clamp=False):
    node = nodes.new("ShaderNodeMath")
    node.operation = operation
    node.use_clamp = clamp
    for index, value in enumerate((first, second)):
        if isinstance(value, (int, float)):
            node.inputs[index].default_value = value
        else:
            links.new(value, node.inputs[index])
    return node.outputs[0]


def multiply_color(nodes, links, color, gain):
    node = nodes.new("ShaderNodeMixRGB")
    node.blend_type = "MULTIPLY"
    node.inputs[0].default_value = 1.0
    links.new(color, node.inputs[1])
    if isinstance(gain, (int, float)):
        node.inputs[2].default_value = (gain, gain, gain, 1.0)
    else:
        links.new(gain, node.inputs[2])
    return node.outputs[0]


def apply_source_detail(nodes, links, color, vector, config):
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(os.path.join(SOURCE_TEXTURES, config["image"]), check_existing=True)
    texture.image.colorspace_settings.name = "Non-Color"
    texture.projection = "BOX"
    texture.projection_blend = 0.25
    texture.interpolation = "Linear"
    mapping = nodes.new("ShaderNodeVectorMath")
    mapping.operation = "SCALE"
    mapping.inputs["Scale"].default_value = 1 / config["tile_size"]
    links.new(vector, mapping.inputs[0])
    links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
    grey = nodes.new("ShaderNodeRGBToBW")
    links.new(texture.outputs["Color"], grey.inputs["Color"])
    # Treat the photograph as a tonal detail map, leaving the palette in charge of hue.
    strength = config["strength"]
    gain = math_node(nodes, links, "MULTIPLY", grey.outputs["Val"], 2 * strength)
    gain = math_node(nodes, links, "ADD", gain, 1 - strength)
    return multiply_color(nodes, links, color, gain)


def layer_socket(nodes, links, layer, vector, layer_index, seed):
    layer = resolve_layer(layer)
    mapping = nodes.new("ShaderNodeMapping")
    links.new(vector, mapping.inputs["Vector"])
    mapping.inputs["Location"].default_value = (
        seed * 1.37 + layer_index * 3.17,
        seed * 2.11 + layer_index * 5.03,
        seed * 0.73 + layer_index * 7.19,
    )
    mapped = mapping.outputs["Vector"]
    kind = layer["type"]
    scale = layer.get("scale", 5.0)

    if kind == "wave":
        node = nodes.new("ShaderNodeTexWave")
        node.wave_type = "BANDS"
        node.bands_direction = layer.get("direction", "X")
        node.inputs["Scale"].default_value = scale
        node.inputs["Distortion"].default_value = layer.get("distortion", 4.0)
        links.new(mapped, node.inputs["Vector"])
        value = node.outputs["Fac"]
    elif kind == "voronoi":
        node = nodes.new("ShaderNodeTexVoronoi")
        node.feature = "F1"
        node.inputs["Scale"].default_value = scale
        links.new(mapped, node.inputs["Vector"])
        value = node.outputs["Distance"]
    elif kind == "constant":
        node = nodes.new("ShaderNodeValue")
        node.outputs[0].default_value = layer.get("value", 0.6)
        value = node.outputs[0]
    else:
        node = nodes.new("ShaderNodeTexNoise")
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = layer.get("detail", 2.0)
        links.new(mapped, node.inputs["Vector"])
        value = node.outputs["Fac"]

    value = math_node(nodes, links, "ADD", value, 0.0, clamp=True)
    if layer.get("invert", False):
        value = math_node(nodes, links, "SUBTRACT", 1.0, value)
    return value


def pattern(nodes, links, config, vector, seed):
    layers = config.get("layers") or preset_layers(config)
    total_weight = sum(layer["weight"] for layer in layers)
    combined = None
    for index, layer in enumerate(layers):
        value = layer_socket(nodes, links, layer, vector, index, seed)
        weighted = math_node(nodes, links, "MULTIPLY", value, layer["weight"])
        combined = weighted if combined is None else math_node(nodes, links, "ADD", combined, weighted)
    return math_node(nodes, links, "DIVIDE", combined, total_weight, clamp=True)


def wood_board_factor(nodes, links, phase, vector, stretch, config, seed):
    def calc(operation, a, b):
        return math_node(nodes, links, operation, a, b)

    board_id = calc("FLOOR", phase, 0)
    variation = nodes.new("ShaderNodeTexWhiteNoise")
    variation.noise_dimensions = "1D"
    links.new(calc("ADD", board_id, seed), variation.inputs["W"])

    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = stretch
    mapping.inputs["Location"].default_value = (0, seed * 0.17, seed * 0.31)
    links.new(vector, mapping.inputs["Vector"])
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1
    noise.inputs["Detail"].default_value = 2
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])

    fraction = calc("FRACT", phase, 0)
    distance = calc("MINIMUM", fraction, calc("SUBTRACT", 1, fraction))
    seam = math_node(nodes, links, "DIVIDE", distance, config["seam_width"] / 2, clamp=True)
    grain = calc("MULTIPLY", calc("SUBTRACT", noise.outputs["Fac"], 0.5), config["grain_strength"])
    tone = calc("ADD", 0.55, calc("MULTIPLY", variation.outputs["Value"], 0.28))
    return calc("MULTIPLY", calc("ADD", tone, grain), seam)


def coopered_wood_pattern(nodes, links, config, vector, seed):
    coordinates = nodes.new("ShaderNodeSeparateXYZ")
    links.new(vector, coordinates.inputs["Vector"])
    angle = math_node(nodes, links, "ARCTAN2", coordinates.outputs["Y"], coordinates.outputs["X"])
    phase = math_node(nodes, links, "MULTIPLY", angle, config["staves"] / math.tau)
    phase = math_node(nodes, links, "MODULO", phase, config["staves"])
    positive = math_node(nodes, links, "ADD", phase, config["staves"])
    phase = math_node(nodes, links, "MODULO", positive, config["staves"])
    side = wood_board_factor(nodes, links, phase, vector, (48, 48, 6), config, seed)

    lid_phase = math_node(nodes, links, "DIVIDE", coordinates.outputs["X"], config["lid_board_width"])
    lid = wood_board_factor(nodes, links, lid_phase, vector, (48, 6, 1), config, seed)
    geometry = nodes.new("ShaderNodeNewGeometry")
    normal = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geometry.outputs["True Normal"], normal.inputs["Vector"])
    abs_z = math_node(nodes, links, "ABSOLUTE", normal.outputs["Z"], 0)
    top_or_bottom = math_node(nodes, links, "GREATER_THAN", abs_z, 0.95)
    difference = math_node(nodes, links, "SUBTRACT", lid, side)
    return math_node(nodes, links, "ADD", side, math_node(nodes, links, "MULTIPLY", difference, top_or_bottom))


def build_factor(nodes, links, pattern_socket, config):
    pivot = config.get("contrast_pivot", 0.5)
    factor = math_node(nodes, links, "SUBTRACT", pattern_socket, pivot)
    factor = math_node(nodes, links, "MULTIPLY", factor, config.get("contrast", 1.0))
    factor = math_node(nodes, links, "ADD", factor, pivot)
    factor = math_node(nodes, links, "ADD", factor, config.get("brightness", 0.0))
    return math_node(nodes, links, "ADD", factor, 0.0, clamp=True)


def build_bake_material(material, config, image, seed):
    config = resolve_material(config)
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    coordinates = nodes.new("ShaderNodeTexCoord")
    vector = coordinates.outputs["Object"]
    if config.get("preset") == "coopered_wood":
        factor = coopered_wood_pattern(nodes, links, config, vector, seed)
    else:
        factor = pattern(nodes, links, config, vector, seed)
    factor = build_factor(nodes, links, factor, config)

    colors = palette(config)
    gradient = config["gradient"]
    positions = ramp_positions(len(colors), gradient)
    ramp = nodes.new("ShaderNodeValToRGB")
    color_ramp = ramp.color_ramp
    color_ramp.interpolation = gradient.upper()
    color_ramp.elements[0].position = positions[0]
    color_ramp.elements[0].color = (*hex2lin(colors[0]), 1.0)
    if len(colors) == 1:
        color_ramp.elements[1].position = 1.0
        color_ramp.elements[1].color = (*hex2lin(colors[0]), 1.0)
    else:
        color_ramp.elements.remove(color_ramp.elements[1])
        for color, position in zip(colors[1:], positions[1:]):
            element = color_ramp.elements.new(position)
            element.color = (*hex2lin(color), 1.0)
    links.new(factor, ramp.inputs["Fac"])
    color = ramp.outputs["Color"]
    if config.get("source_detail", {}).get("strength", 0) > 0:
        color = apply_source_detail(nodes, links, color, vector, config["source_detail"])

    if config["ao"] > 0:
        ao = nodes.new("ShaderNodeAmbientOcclusion")
        ao.inputs["Distance"].default_value = config["ao_distance"]
        darkening = math_node(
            nodes,
            links,
            "MULTIPLY",
            math_node(nodes, links, "SUBTRACT", 1.0, ao.outputs["AO"]),
            config["ao"],
        )
        ao_gain = math_node(nodes, links, "SUBTRACT", 1.0, darkening)
        color = multiply_color(nodes, links, color, ao_gain)

    if config["edge"] > 0:
        geometry = nodes.new("ShaderNodeNewGeometry")
        edge = math_node(nodes, links, "SUBTRACT", geometry.outputs["Pointiness"], 0.5)
        edge_gain = math_node(
            nodes,
            links,
            "ADD",
            math_node(nodes, links, "MULTIPLY", edge, config["edge"] * 0.5),
            1.0,
        )
        color = multiply_color(nodes, links, color, edge_gain)

    links.new(color, emission.inputs["Color"])
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    nodes.active = texture
    texture.select = True


def finalize_material(material, config, image, pixel):
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    texture.interpolation = "Closest" if pixel else "Linear"
    links.new(texture.outputs["Color"], principled.inputs["Base Color"])
    principled.inputs["Roughness"].default_value = config.get("roughness", 0.9)
    principled.inputs["Metallic"].default_value = config.get("metallic", 0.0)
    opacity = config.get("opacity", 1.0)
    principled.inputs["Alpha"].default_value = opacity
    if opacity < 1.0:
        material.use_backface_culling = False
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    nodes.active = texture
    texture.select = True


def quantize(image, hex_colors):
    colors = np.array([hex2rgb(value) for value in sorted(set(hex_colors))], dtype=np.float32)
    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    pixels = pixels.reshape(-1, 4)
    indices = ((pixels[:, None, :3] - colors[None]) ** 2).sum(-1).argmin(1)
    pixels[:, :3] = colors[indices]
    pixels[:, 3] = 1.0
    image.pixels.foreach_set(pixels.ravel())
    image.update()


def unique_color_count(image):
    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    rgb = np.round(np.clip(pixels.reshape(-1, 4)[:, :3], 0.0, 1.0) * 255).astype(np.uint8)
    return int(len(np.unique(rgb, axis=0)))


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :]
    with open(argv[0], encoding="utf-8") as handle:
        spec = json.load(handle)
    out = os.path.abspath(argv[1])
    os.makedirs(out, exist_ok=True)

    obj = bpy.data.objects.get(spec["asset"])
    if obj is None or obj.type != "MESH":
        raise RuntimeError(f"Mesh object {spec['asset']!r} was not found in the loaded .blend file")
    size = spec.get("size", 128)
    seed = spec.get("seed", 1)
    samples = spec.get("samples", 64)
    pack_uv = spec.get("pack_uv", False)
    margin = spec.get("margin", min(4, size // 64) if pack_uv else 4)
    should_quantize = spec.get("quantize", False)
    pixel = spec.get("pixel", False)

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.seed = seed
    scene.cycles.use_animated_seed = False
    scene.render.bake.margin = margin
    scene.render.bake.margin_type = "EXTEND"
    scene.render.bake.target = "IMAGE_TEXTURES"
    scene.render.bake.use_selected_to_active = False
    scene.render.bake.use_clear = True
    scene.view_settings.view_transform = "Standard"

    image = bpy.data.images.new(spec["asset"] + "_albedo", size, size, alpha=False)
    image.colorspace_settings.name = "sRGB"
    all_colors, configs, defaulted_materials = [], {}, []
    for slot in obj.material_slots:
        material = slot.material
        if material.name in spec["materials"]:
            raw_config = spec["materials"][material.name]
        else:
            raw_config = spec["materials"]["default"]
            defaulted_materials.append(material.name)
        config = resolve_material(raw_config)
        configs[material.name] = config
        build_bake_material(material, config, image, seed)
        all_colors += palette(config)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if pack_uv:
        # Reserve an extra half texel per island for raster sampling at its boundary.
        fraction = (margin + 0.5) / size
        if fraction >= 0.5:
            raise ValueError("margin leaves no usable atlas with pack_uv enabled")
        bpy.ops.object.mode_set(mode="EDIT")
        pack_uv_islands(fraction)
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.bake(type="EMIT")

    if should_quantize:
        quantize(image, all_colors)
    png_path = os.path.join(out, image.name + ".png")
    image.filepath_raw = png_path
    image.file_format = "PNG"
    image.save()
    image.pack()
    image.filepath_raw = "//" + os.path.basename(png_path)

    for slot in obj.material_slots:
        finalize_material(slot.material, configs[slot.material.name], image, pixel)

    blend_path = os.path.join(out, spec["asset"] + "_tex.blend")
    glb_path = os.path.join(out, spec["asset"] + ".glb")
    godot_path = None
    bpy.ops.wm.save_as_mainfile(filepath=blend_path, check_existing=False, relative_remap=False)
    mesh_objects = [scene_obj for scene_obj in bpy.data.objects if scene_obj.type == "MESH"]
    export_glb(glb_path, [obj], obj)
    if len(mesh_objects) > 1:
        godot_path = os.path.join(out, spec["asset"] + "_godot.glb")
        export_glb(godot_path, mesh_objects, obj)
    preview_paths = render_previews(obj, out, "TEXTURE")

    material_settings = {}
    for name, config in configs.items():
        settings = {key: value for key, value in config.items() if key not in ("palette", "layers")}
        settings["palette"] = palette(config)
        if "layers" in config:
            settings["layers"] = config["layers"]
        if config.get("preset") != "coopered_wood":
            settings["resolved_layers"] = config.get("layers") or preset_layers(config)
        material_settings[name] = settings

    report = {
        "name": spec["asset"],
        "stage": "texture",
        "size": size,
        "seed": seed,
        "pixel": pixel,
        "quantize": should_quantize,
        "samples": samples,
        "margin": margin,
        "margin_type": "EXTEND",
        "pack_uv": pack_uv,
        "unique_colors": unique_color_count(image),
        "materials": sorted(configs),
        "defaulted_materials": sorted(defaulted_materials),
        "material_settings": material_settings,
        "texture": png_path,
        "blend": blend_path,
        "glb": glb_path,
        "godot_glb": godot_path,
        "previews": preview_paths,
        "status": "OK",
        "warnings": [],
    }
    with open(os.path.join(out, "report_texture.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
