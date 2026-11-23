extends SceneTree

# Rows: neutral Normal + flat Roughness; Normal only; full PBR.
# Columns: cold, warm, grazing light. Camera and illumination are shared by rows.
const SIZE := 384
const VARIANTS := ["control", "normal_only", "full_pbr"]
const LIGHTS := ["cold", "warm", "grazing"]
const DISTANCES := ["game", "close"]


func _initialize() -> void:
	_run.call_deferred()


func _import(path: String) -> Dictionary:
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var error := document.append_from_file(path, state)
	if error != OK:
		_fail("GLB import failed for %s: %s" % [path, error_string(error)])
		return {}
	var asset := document.generate_scene(state) as Node3D
	if asset == null:
		_fail("GLB did not produce a 3D scene: %s" % path)
		return {}
	return {"asset": asset, "materials": state.get_materials()}


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 4 or args.size() > 6 or DisplayServer.get_name() == "headless":
		_fail("Expected control GLB, Normal-only GLB, full PBR GLB, output directory, optional Godot GLB and prefab")
		return
	DirAccess.make_dir_recursive_absolute(args[3])
	var imported: Array[Dictionary] = []
	for index in range(3):
		var result := _import(args[index])
		if result.is_empty():
			return
		imported.append(result)
		result.asset.visible = false
		root.add_child(result.asset)

	var metrics := {"triangles": _triangle_count(imported[2].asset), "differences": {}}
	var wall_check := args.size() >= 5
	if metrics.triangles <= 0:
		_fail("Expected a visible PBR mesh")
		return
	if wall_check and metrics.triangles != 12:
		_fail("Expected 12 visible wall triangles, got %s" % metrics.triangles)
		return
	if not _check_pbr_material(imported[2].materials, metrics, wall_check):
		return
	if wall_check:
		var godot_scene := ResourceLoader.load(args[4]) as PackedScene
		if godot_scene == null:
			_fail("Could not load imported Godot GLB: %s" % args[4])
			return
		var godot := godot_scene.instantiate() as Node3D
		if godot == null or not _check_collision(godot, "Godot GLB", metrics):
			_fail("Imported Godot GLB did not produce the expected wall and collision")
			return
		godot.free()
	if args.size() == 6:
		var packed := ResourceLoader.load(args[5]) as PackedScene
		if packed == null:
			_fail("Could not load prefab: %s" % args[5])
			return
		var prefab := packed.instantiate() as Node3D
		if prefab == null or not _check_collision(prefab, "prefab", metrics):
			_fail("Prefab did not produce the expected wall and collision")
			return
		prefab.free()

	var bounds := _visible_bounds(imported[2].asset)
	if bounds.size == Vector3.ZERO:
		_fail("PBR asset has no visible mesh")
		return
	var target := bounds.get_center()
	var diameter := bounds.size.length()
	_add_environment()
	var cold := _add_cold_light(diameter)
	var warm := _add_warm_light(target, diameter)
	var grazing := _add_grazing_light(diameter)
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.position = target + Vector3(0.45, 0.32, 1.0).normalized() * diameter * 2.5
	camera.near = diameter * 0.05
	camera.far = diameter * 6.0
	camera.look_at(target)
	camera.current = true
	root.size = Vector2i(SIZE, SIZE)
	root.content_scale_size = Vector2i(SIZE, SIZE)

	var captures := {}
	for distance in DISTANCES:
		captures[distance] = {}
		camera.size = diameter * (1.12 if distance == "game" else 0.68)
		var sheet := Image.create(SIZE * 3, SIZE * 3, false, Image.FORMAT_RGBA8)
		for row in range(3):
			captures[distance][VARIANTS[row]] = {}
			for other in range(3):
				imported[other].asset.visible = other == row
			for column in range(3):
				cold.visible = column != 2
				warm.visible = column == 1
				grazing.visible = column == 2
				await process_frame
				await RenderingServer.frame_post_draw
				var frame := root.get_texture().get_image()
				if frame.get_size() != Vector2i(SIZE, SIZE):
					frame.resize(SIZE, SIZE, Image.INTERPOLATE_LANCZOS)
				frame.convert(Image.FORMAT_RGBA8)
				captures[distance][VARIANTS[row]][LIGHTS[column]] = frame
				sheet.blit_rect(frame, Rect2i(0, 0, SIZE, SIZE), Vector2i(SIZE * column, SIZE * row))
		var path := args[3].path_join("ab_%s.png" % distance)
		if sheet.save_png(path) != OK:
			_fail("Could not save A/B sheet: %s" % path)
			return
		metrics["ab_%s" % distance] = path
		metrics.differences[distance] = {
			"normal": {}, "roughness": {}
		}
		for light in LIGHTS:
			metrics.differences[distance].normal[light] = _image_difference(
				captures[distance].control[light], captures[distance].normal_only[light]
			)
			metrics.differences[distance].roughness[light] = _image_difference(
				captures[distance].normal_only[light], captures[distance].full_pbr[light]
			)
	var report := FileAccess.open(args[3].path_join("metrics.json"), FileAccess.WRITE)
	if report == null:
		_fail("Could not write Godot metrics")
		return
	report.store_string(JSON.stringify(metrics, "\t") + "\n")
	print("PBR_IMPORT_OK triangles=%s; A/B sheets and metrics saved" % metrics.triangles)
	quit()


func _check_pbr_material(materials: Array[Material], metrics: Dictionary, wall_check: bool) -> bool:
	var pbr_materials: Array[StandardMaterial3D] = []
	for candidate in materials:
		if candidate is StandardMaterial3D:
			var material := candidate as StandardMaterial3D
			if material.normal_enabled and material.normal_texture != null and material.roughness_texture != null:
				pbr_materials.append(material)
	if pbr_materials.is_empty():
		_fail("Godot material is missing Normal or Roughness")
		return false
	if wall_check and (materials.size() != 1 or pbr_materials.size() != 1):
		_fail("Expected one imported wall StandardMaterial3D")
		return false
	var material := pbr_materials[0]
	if wall_check and (material.normal_texture.get_size() != Vector2(512, 512)
			or material.roughness_texture.get_size() != Vector2(512, 512)):
		_fail("Expected 512 x 512 wall Normal and Roughness")
		return false
	metrics.material = {
		"normal_size": str(material.normal_texture.get_size()),
		"roughness_size": str(material.roughness_texture.get_size()),
		"normal_scale": material.normal_scale,
		"roughness": material.roughness,
		"metallic": material.metallic,
		"pbr_materials": pbr_materials.size(),
	}
	return true


func _triangle_count(asset: Node) -> int:
	var triangles := 0
	for node: Node in asset.find_children("*", "MeshInstance3D", true, false):
		triangles += (node as MeshInstance3D).mesh.get_faces().size() / 3
	return triangles


func _check_collision(asset: Node, label: String, metrics: Dictionary) -> bool:
	var bodies := asset.find_children("*", "StaticBody3D", true, false).size()
	var shapes := asset.find_children("*", "CollisionShape3D", true, false).size()
	var triangles := _triangle_count(asset)
	if bodies != 1 or shapes != 1 or triangles != 12:
		_fail("%s: expected 1 body, 1 box shape and 12 visible triangles; got %s/%s/%s" % [label, bodies, shapes, triangles])
		return false
	metrics[label] = {"static_bodies": bodies, "collision_shapes": shapes, "triangles": triangles}
	return true


func _visible_bounds(asset: Node3D) -> AABB:
	var bounds := AABB()
	for node: Node in asset.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		var mesh_bounds: AABB = mesh.global_transform * mesh.get_aabb()
		bounds = mesh_bounds if bounds.size == Vector3.ZERO else bounds.merge(mesh_bounds)
	return bounds


func _add_environment() -> void:
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("#252930")
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("#c3d4f2")
	environment.ambient_light_energy = 0.38
	var world := WorldEnvironment.new()
	world.environment = environment
	root.add_child(world)


func _add_cold_light(diameter: float) -> DirectionalLight3D:
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-37, 28, 0)
	light.light_color = Color("#a9c4ff")
	light.light_energy = 0.72
	light.directional_shadow_max_distance = diameter * 6.0
	light.shadow_enabled = true
	root.add_child(light)
	return light


func _add_warm_light(target: Vector3, diameter: float) -> OmniLight3D:
	var light := OmniLight3D.new()
	light.light_color = Color("#ffc887")
	light.light_energy = 1.3
	light.omni_range = diameter * 2.7
	light.position = target + Vector3(-0.65, 0.60, 0.8) * diameter
	light.shadow_enabled = true
	root.add_child(light)
	return light


func _add_grazing_light(diameter: float) -> DirectionalLight3D:
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-8, 78, 0)
	light.light_color = Color("#ffe0b0")
	light.light_energy = 1.5
	light.directional_shadow_max_distance = diameter * 6.0
	light.shadow_enabled = true
	root.add_child(light)
	return light


func _image_difference(first: Image, second: Image) -> float:
	var a := first.get_data()
	var b := second.get_data()
	var total := 0
	var count := 0
	for index in range(0, a.size(), 16):
		for channel in range(3):
			total += absi(a[index + channel] - b[index + channel])
			count += 1
	return float(total) / maxi(count, 1)


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
