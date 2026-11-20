extends SceneTree

const SIZE := 512


func _initialize() -> void:
	_render.call_deferred()


func _render() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 2 or DisplayServer.get_name() == "headless":
		_fail("Expected a GLB and an output PNG with a rendering display")
		return

	var document := GLTFDocument.new()
	var state := GLTFState.new()
	var error := document.append_from_file(args[0], state)
	if error != OK:
		_fail("GLB import failed: %s" % error_string(error))
		return
	var asset := document.generate_scene(state) as Node3D
	if asset == null:
		_fail("The GLB did not produce a 3D scene")
		return
	root.add_child(asset)
	var bounds := AABB()
	for node: Node in asset.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		var mesh_bounds: AABB = mesh.global_transform * mesh.get_aabb()
		if bounds.size == Vector3.ZERO:
			bounds = mesh_bounds
		else:
			bounds = bounds.merge(mesh_bounds)
	if bounds.size == Vector3.ZERO:
		_fail("The GLB has no visible mesh")
		return

	var target := bounds.get_center()
	var diameter := bounds.size.length()
	_add_environment()
	var warm := _add_lights(target, diameter)
	var camera := Camera3D.new()
	root.add_child(camera)
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = diameter * 1.12
	camera.position = target + Vector3(0.65, 0.47, 1.0).normalized() * diameter * 2.5
	camera.near = diameter * 0.05
	camera.far = diameter * 6.0
	camera.look_at(target)
	camera.current = true
	root.size = Vector2i(SIZE, SIZE)
	root.content_scale_size = Vector2i(SIZE, SIZE)

	var sheet := Image.create(SIZE * 2, SIZE, false, Image.FORMAT_RGBA8)
	for column: int in range(2):
		warm.visible = column == 1
		await process_frame
		await RenderingServer.frame_post_draw
		var frame := root.get_texture().get_image()
		if frame.get_size() != Vector2i(SIZE, SIZE):
			frame.resize(SIZE, SIZE, Image.INTERPOLATE_LANCZOS)
		frame.convert(Image.FORMAT_RGBA8)
		sheet.blit_rect(frame, Rect2i(0, 0, SIZE, SIZE), Vector2i(SIZE * column, 0))

	error = sheet.save_png(args[1])
	if error != OK:
		_fail("Could not save lighting preview: %s" % error_string(error))
		return
	quit()


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


func _add_lights(target: Vector3, diameter: float) -> OmniLight3D:
	var cold := DirectionalLight3D.new()
	cold.rotation_degrees = Vector3(-37, 28, 0)
	cold.light_color = Color("#a9c4ff")
	cold.light_energy = 0.72
	cold.directional_shadow_max_distance = diameter * 6.0
	cold.shadow_enabled = true
	root.add_child(cold)

	var warm := OmniLight3D.new()
	warm.light_color = Color("#ffc887")
	warm.light_energy = 1.3
	warm.omni_range = diameter * 2.7
	warm.position = target + Vector3(-0.65, 0.60, 0.8) * diameter
	warm.shadow_enabled = true
	root.add_child(warm)
	return warm


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
