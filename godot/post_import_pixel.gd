# Legacy/retro-only: new GLBs already contain nearest or linear samplers.
# Do not attach this script to soft assets; it overrides their filtering to nearest.
@tool
extends EditorScenePostImport

func _post_import(scene: Node) -> Object:
	_walk(scene)
	return scene

func _walk(node: Node) -> void:
	if node is MeshInstance3D and node.mesh:
		for index in node.mesh.get_surface_count():
			var material := node.mesh.surface_get_material(index)
			if material is BaseMaterial3D:
				material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST_WITH_MIPMAPS
	for child in node.get_children():
		_walk(child)
