"""Bake a palette-quantized procedural albedo onto a generated model.

blender -b out/x/x.blend --python-exit-code 1 -P blender/bake_texture.py -- tex_spec.json out_dir
"""

import json
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
from common import export_glb, hex2lin, hex2rgb, render_previews

argv = sys.argv[sys.argv.index("--") + 1 :]
with open(argv[0], encoding="utf-8") as handle:
    spec = json.load(handle)
OUT = os.path.abspath(argv[1])
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(HERE, "..", "presets", "palettes.json"), encoding="utf-8") as handle:
    PALETTES = json.load(handle)

obj = bpy.data.objects.get(spec["asset"])
if obj is None or obj.type != "MESH":
    raise RuntimeError(f"Mesh object {spec['asset']!r} was not found in the loaded .blend file")
size = spec.get("size", 128)
seed = spec.get("seed", 1)


def palette(config):
    value = config["palette"]
    return PALETTES[value] if isinstance(value, str) else value


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


def pattern(nodes, links, config, vector):
    kind = config.get("preset", "noise")
    scale = config.get("scale", 5.0)
    mapping = nodes.new("ShaderNodeMapping")
    links.new(vector, mapping.inputs["Vector"])
    mapping.inputs["Location"].default_value = (seed * 1.37, seed * 2.11, seed * 0.73)
    mapped = mapping.outputs["Vector"]

    if kind == "wood":
        node = nodes.new("ShaderNodeTexWave")
        node.wave_type = "BANDS"
        node.bands_direction = config.get("direction", "X")
        node.inputs["Scale"].default_value = scale
        node.inputs["Distortion"].default_value = config.get("distortion", 4.0)
        links.new(mapped, node.inputs["Vector"])
        return node.outputs["Fac"]
    if kind == "stone":
        node = nodes.new("ShaderNodeTexVoronoi")
        node.feature = "F1"
        node.inputs["Scale"].default_value = scale
        links.new(mapped, node.inputs["Vector"])
        return node.outputs["Distance"]
    if kind == "flat":
        node = nodes.new("ShaderNodeValue")
        node.outputs[0].default_value = config.get("value", 0.6)
        return node.outputs[0]

    node = nodes.new("ShaderNodeTexNoise")
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = config.get("detail", 2.0)
    links.new(mapped, node.inputs["Vector"])
    return node.outputs["Fac"]


def build_bake_material(material, config, image):
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    coordinates = nodes.new("ShaderNodeTexCoord")
    factor = pattern(nodes, links, config, coordinates.outputs["Object"])
    factor = math_node(nodes, links, "MULTIPLY", factor, config.get("contrast", 1.0))
    factor = math_node(nodes, links, "ADD", factor, config.get("brightness", 0.0))

    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = config.get("ao_distance", 0.15)
    darkening = math_node(
        nodes,
        links,
        "MULTIPLY",
        math_node(nodes, links, "SUBTRACT", 1.0, ao.outputs["AO"]),
        config.get("ao", 0.5),
    )
    factor = math_node(nodes, links, "SUBTRACT", factor, darkening)

    if config.get("edge", 0) > 0:
        geometry = nodes.new("ShaderNodeNewGeometry")
        edge = math_node(nodes, links, "SUBTRACT", geometry.outputs["Pointiness"], 0.5)
        factor = math_node(
            nodes,
            links,
            "ADD",
            factor,
            math_node(nodes, links, "MULTIPLY", edge, config["edge"] * 2),
        )
    factor = math_node(nodes, links, "ADD", factor, 0.0, clamp=True)

    colors = palette(config)
    ramp = nodes.new("ShaderNodeValToRGB")
    color_ramp = ramp.color_ramp
    color_ramp.interpolation = "CONSTANT"
    color_ramp.elements[0].position = 0.0
    color_ramp.elements[0].color = (*hex2lin(colors[0]), 1.0)
    if len(colors) == 1:
        color_ramp.elements[1].position = 1.0
        color_ramp.elements[1].color = (*hex2lin(colors[0]), 1.0)
    else:
        color_ramp.elements.remove(color_ramp.elements[1])
        for index in range(1, len(colors)):
            element = color_ramp.elements.new(index / len(colors))
            element.color = (*hex2lin(colors[index]), 1.0)
    links.new(factor, ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], emission.inputs["Color"])

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


scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = spec.get("samples", 32)
scene.render.bake.margin = spec.get("margin", 2)
scene.render.bake.target = "IMAGE_TEXTURES"
scene.render.bake.use_selected_to_active = False
scene.render.bake.use_clear = True
scene.view_settings.view_transform = "Standard"

image = bpy.data.images.new(spec["asset"] + "_albedo", size, size, alpha=False)
image.colorspace_settings.name = "sRGB"
all_colors, configs = [], {}
for slot in obj.material_slots:
    material = slot.material
    config = spec["materials"].get(material.name) or spec["materials"]["default"]
    configs[material.name] = config
    build_bake_material(material, config, image)
    all_colors += palette(config)

bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.bake(type="EMIT")

if spec.get("quantize", True):
    quantize(image, all_colors)
png_path = os.path.join(OUT, image.name + ".png")
image.filepath_raw = png_path
image.file_format = "PNG"
image.save()
image.pack()

pixel = spec.get("pixel", True)
for slot in obj.material_slots:
    finalize_material(slot.material, configs[slot.material.name], image, pixel)

blend_path = os.path.join(OUT, spec["asset"] + "_tex.blend")
glb_path = os.path.join(OUT, spec["asset"] + ".glb")
godot_path = None
bpy.ops.wm.save_as_mainfile(filepath=blend_path, check_existing=False)
mesh_objects = [scene_obj for scene_obj in bpy.data.objects if scene_obj.type == "MESH"]
export_glb(glb_path, [obj], obj)
if len(mesh_objects) > 1:
    godot_path = os.path.join(OUT, spec["asset"] + "_godot.glb")
    export_glb(godot_path, mesh_objects, obj)
preview_paths = render_previews(obj, OUT, "TEXTURE")
report = {
    "name": spec["asset"],
    "stage": "texture",
    "size": size,
    "materials": sorted(configs),
    "texture": png_path,
    "blend": blend_path,
    "glb": glb_path,
    "godot_glb": godot_path,
    "previews": preview_paths,
    "status": "OK",
    "warnings": [],
}
with open(os.path.join(OUT, "report_texture.json"), "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2, ensure_ascii=False)
