"""Numeric checks for the procedural texture pipeline inside Blender."""

import importlib.util
import os
import sys
from tempfile import TemporaryDirectory

import bpy

argv = sys.argv[sys.argv.index("--") + 1 :]
ROOT = os.path.abspath(argv[0])
MODULE_PATH = os.path.join(ROOT, "blender", "bake_texture.py")
spec = importlib.util.spec_from_file_location("assetgen_bake_texture", MODULE_PATH)
texture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(texture)


def assert_close(actual, expected, tolerance, message):
    assert abs(actual - expected) <= tolerance, f"{message}: got {actual}, expected {expected}"


def linear_to_srgb(value):
    return value / 12.92 if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055


assert texture.ramp_positions(4, "constant") == [0.0, 0.25, 0.5, 0.75]
for gradient in ("linear", "ease"):
    positions = texture.ramp_positions(4, gradient)
    assert positions[0] == 0.0 and positions[-1] == 1.0
    assert_close(positions[1], 1 / 3, 1e-8, f"{gradient} second stop")
    assert_close(positions[2], 2 / 3, 1e-8, f"{gradient} third stop")
assert texture.ramp_positions(1, "ease") == [0.0]

original = {"palette": "stone_grey"}
resolved = texture.resolve_material(original)
assert original == {"palette": "stone_grey"}, "resolve_material mutated its input"
assert resolved["gradient"] == "ease" and resolved["contrast_pivot"] == 0.5
assert resolved["ao"] == 0.25 and resolved["preset"] == "noise"

wood = texture.resolve_material(
    {"palette": "wood_dark", "preset": "wood", "scale": 5, "direction": "Z", "distortion": 0.4, "detail": 5}
)
wood_layers = texture.preset_layers(wood)
assert_close(sum(layer["weight"] for layer in wood_layers), 1.0, 1e-8, "wood weights")
assert wood_layers[0]["direction"] == "Z" and wood_layers[0]["distortion"] == 0.4
assert_close(wood_layers[1]["scale"], 2.0, 1e-8, "wood broad scale")
assert_close(wood_layers[2]["scale"], 20.0, 1e-8, "wood fine scale")
assert wood_layers[1]["detail"] == 5

stone = texture.preset_layers(texture.resolve_material({"palette": "stone_grey", "preset": "stone", "scale": 8}))
assert_close(sum(layer["weight"] for layer in stone), 1.0, 1e-8, "stone weights")
assert_close(stone[0]["scale"], 2.8, 1e-8, "stone broad scale")
assert stone[1]["type"] == "voronoi" and stone[1]["weight"] == 0.25
assert_close(stone[2]["scale"], 24.0, 1e-8, "stone fine scale")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_plane_add(size=2)
obj = bpy.context.object
obj.name = "texture_test_plane"
material = bpy.data.materials.new("texture_test")
obj.data.materials.append(material)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 1
scene.cycles.seed = 1
scene.cycles.use_animated_seed = False
scene.render.bake.target = "IMAGE_TEXTURES"
scene.render.bake.use_selected_to_active = False
scene.render.bake.use_clear = True
scene.render.bake.margin = 0
scene.render.bake.margin_type = "EXTEND"
scene.view_settings.view_transform = "Standard"


def bake_color(config):
    image = bpy.data.images.new("numeric_test", 16, 16, alpha=False)
    image.colorspace_settings.name = "sRGB"
    texture.build_bake_material(material, config, image, seed=1)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.bake(type="EMIT")
    pixel = list(image.pixels[0:4])
    bpy.data.images.remove(image)
    return pixel


def assert_baked_factor(config, expected_factor, message):
    color = bake_color(config)
    expected = linear_to_srgb(expected_factor)
    for channel in color[:3]:
        assert_close(channel, expected, 0.025, message)


base = {"gradient": "linear", "palette": ["#000000", "#ffffff"], "ao": 0, "edge": 0}
weighted = {
    **base,
    "layers": [
        {"type": "constant", "value": 0, "weight": 1},
        {"type": "constant", "value": 1, "weight": 3},
    ],
}
assert_baked_factor(weighted, 0.75, "weighted constant layers")

with TemporaryDirectory() as source_dir:
    source = bpy.data.images.new("source_black", 1, 1)
    source.pixels[:] = (0.0, 0.0, 0.0, 1.0)
    source.filepath_raw = os.path.join(source_dir, "black.png")
    source.file_format = "PNG"
    source.save()
    bpy.data.images.remove(source)
    original_source_dir = texture.SOURCE_TEXTURES
    texture.SOURCE_TEXTURES = source_dir
    with_image = {
        **base,
        "contrast": 0,
        "source_detail": {"image": "black.png", "tile_size": 0.6, "strength": 0.5},
    }
    assert_baked_factor(with_image, 0.25, "source detail modulates linear albedo")
    assert_baked_factor({**with_image, "source_mode": "procedural"}, 0.5, "procedural ignores image")
    source = bpy.data.images.new("source_rgb", 1, 1)
    source.colorspace_settings.name = "sRGB"
    source.pixels[:] = (0.8, 0.4, 0.2, 1.0)
    source.filepath_raw = os.path.join(source_dir, "rgb.png")
    source.file_format = "PNG"
    source.save()
    bpy.data.images.remove(source)
    image_config = {**base, "source_mode": "image", "palette": ["#00ff00"],
                    "source_detail": {"image": "rgb.png", "tile_size": 1, "strength": 0}}
    # The saved image is reloaded as sRGB and converted to linear by Blender.
    rgb = bake_color(image_config)
    for channel, expected in zip(rgb[:3], (0.8, 0.4, 0.2)):
        assert_close(channel, expected, 0.025, "image preserves RGB, ignores palette and detail strength")
    grey = bake_color({**image_config, "contrast": 0, "brightness": 0.1})
    for channel in grey[:3]:
        assert_close(channel, linear_to_srgb(0.6), 0.025, "image brightness and contrast")
    # Loading this same file as detail must not change the RGB datablock's space.
    bake_color({**image_config, "source_mode": "mixed"})
    again = bake_color(image_config)
    for channel, expected in zip(again[:3], rgb[:3]):
        assert_close(channel, expected, 0.025, "shared file colorspace isolation")
    texture.SOURCE_TEXTURES = original_source_dir

zero_contrast = {**base, "layers": [{"type": "constant", "value": 0.25}], "contrast": 0}
assert_baked_factor(zero_contrast, 0.5, "zero contrast pivot")

pivot = {**base, "layers": [{"type": "constant", "value": 0.5}], "contrast": 3.5}
assert_baked_factor(pivot, 0.5, "contrast preserves pivot")

clamped = {**base, "layers": [{"type": "constant", "value": 0.8}], "contrast": 4}
assert_baked_factor(clamped, 1.0, "factor upper clamp")

inverted = {**base, "layers": [{"type": "constant", "value": 0.25, "invert": True}]}
assert_baked_factor(inverted, 0.75, "inverted constant layer")

grey = bake_color({"palette": ["#808080"], "layers": [{"type": "constant", "value": 0.6}], "ao": 0, "edge": 0})
for channel in grey[:3]:
    assert_close(channel, 128 / 255, 0.02, "sRGB round-trip")
assert_close(grey[3], 1.0, 1e-6, "opaque alpha")

filter_image = bpy.data.images.new("filter_test", 1, 1, alpha=False)
for pixel, expected_interpolation in ((True, "Closest"), (False, "Linear")):
    texture.finalize_material(material, {"roughness": 0.9, "metallic": 0}, filter_image, pixel)
    image_node = next(node for node in material.node_tree.nodes if node.type == "TEX_IMAGE")
    assert image_node.interpolation == expected_interpolation
for opacity in (None, 0, 0.35, 1):
    raw_config = {"palette": "stone_grey"}
    if opacity is not None:
        raw_config["opacity"] = opacity
    expected_alpha = 1.0 if opacity is None else opacity
    config = texture.resolve_material(raw_config)
    material.use_backface_culling = True
    texture.finalize_material(material, config, filter_image, False)
    principled = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    assert_close(principled.inputs["Alpha"].default_value, expected_alpha, 1e-6, "material alpha")
    assert config["opacity"] == expected_alpha
    assert material.use_backface_culling == (expected_alpha == 1)
bpy.data.images.remove(filter_image)

quantized_image = bpy.data.images.new("quantize_test", 2, 2, alpha=False)
quantized_image.colorspace_settings.name = "sRGB"
quantized_image.pixels.foreach_set(
    [0.1, 0.1, 0.1, 1, 0.9, 0.9, 0.9, 1, 0.2, 0.2, 0.2, 1, 0.8, 0.8, 0.8, 1]
)
texture.quantize(quantized_image, ["#000000", "#ffffff"])
quantized_pixels = list(quantized_image.pixels[:])
for index in range(0, len(quantized_pixels), 4):
    assert all(channel in (0.0, 1.0) for channel in quantized_pixels[index : index + 3])
bpy.data.images.remove(quantized_image)

print("Verified ramps, recipes, layers, contrast, sRGB, quantization and texture filtering")
