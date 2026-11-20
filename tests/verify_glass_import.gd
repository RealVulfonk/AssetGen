extends SceneTree

const SIZE := 400


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty() or args.size() > 2:
		_fail("Expected the window GLB and an optional output PNG path")
		return

	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var error := document.append_from_file(args[0], state)
	if error != OK:
		_fail("GLB import failed: %s" % error_string(error))
		return
	var window := document.generate_scene(state) as Node3D
	if window == null:
		_fail("GLB did not produce a 3D scene")
		return
	root.add_child(window)
	if not _check_materials(state.get_materials()):
		return

	if args.size() == 2:
		if DisplayServer.get_name() == "headless":
			_fail("Capturing the transparency preview requires a rendering display")
			return
		error = await _capture(args[1])
		if error != OK:
			_fail("Could not save transparency preview: %s" % error_string(error))
			return
	quit()


func _check_materials(materials: Array[Material]) -> bool:
	var by_name: Dictionary[String, StandardMaterial3D] = {}
	for material: Material in materials:
		if material is StandardMaterial3D:
			by_name[material.resource_name] = material as StandardMaterial3D
	if materials.size() != 2 or not by_name.has("glass") or not by_name.has("frame"):
		_fail("Expected exactly two materials named glass and frame")
		return false
	var glass := by_name["glass"]
	if (
		glass.transparency == BaseMaterial3D.TRANSPARENCY_DISABLED
		or not is_equal_approx(glass.albedo_color.a, 0.35)
		or glass.cull_mode != BaseMaterial3D.CULL_DISABLED
		or not is_equal_approx(glass.roughness, 0.24)
	):
		_fail(
			"Unexpected glass material (transparency %s, alpha %s, roughness %s, culling %s)"
			% [glass.transparency, glass.albedo_color.a, glass.roughness, glass.cull_mode]
		)
		return false
	var frame := by_name["frame"]
	if frame.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED or frame.albedo_color.a != 1.0:
		_fail("Frame must import as opaque")
		return false
	print("Verified glass alpha 0.35, roughness 0.24, two-sided rendering and opaque frame")
	return true


func _capture(path: String) -> Error:
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("#303641")
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color.WHITE
	environment.ambient_light_energy = 0.65
	var world := WorldEnvironment.new()
	world.environment = environment
	root.add_child(world)

	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-40, 25, 0)
	root.add_child(light)
	var target := Vector3(0.0, 0.53, 0.0)
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 1.22
	root.add_child(camera)
	camera.make_current()

	var block := BoxMesh.new()
	block.size = Vector3(0.22, 0.56, 0.14)
	var marker_material := StandardMaterial3D.new()
	marker_material.albedo_color = Color("#ffad37")
	marker_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var marker := MeshInstance3D.new()
	marker.mesh = block
	marker.material_override = marker_material
	marker.rotation_degrees.z = -17.0
	root.add_child(marker)

	root.size = Vector2i(SIZE, SIZE)
	root.content_scale_size = Vector2i(SIZE, SIZE)
	var sheet := Image.create(SIZE * 3, SIZE, false, Image.FORMAT_RGBA8)
	var views: Array[Vector3] = [Vector3.BACK, Vector3.FORWARD, Vector3(0.68, 0.2, 1.0)]
	for index: int in range(views.size()):
		var view := views[index]
		camera.position = target + view.normalized() * 2.5
		camera.look_at(target)
		marker.position = Vector3(0.16, target.y, -0.33 * signf(view.z))
		await process_frame
		await RenderingServer.frame_post_draw
		var frame := root.get_texture().get_image()
		if frame.get_size() != Vector2i(SIZE, SIZE):
			frame.resize(SIZE, SIZE, Image.INTERPOLATE_LANCZOS)
		frame.convert(Image.FORMAT_RGBA8)
		sheet.blit_rect(frame, Rect2i(0, 0, SIZE, SIZE), Vector2i(SIZE * index, 0))
	return sheet.save_png(path)


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
