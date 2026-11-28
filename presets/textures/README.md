# Исходники фактуры

Карты Diffuse в JPG, 1024×1024, из Poly Haven. Обе распространяются по [CC0](https://polyhaven.com/license).

| Файл | Источник | Автор |
|---|---|---|
| `fine_grained_wood.jpg` | [Fine Grained Wood](https://polyhaven.com/a/fine_grained_wood) | Rob Tuytel |
| `metal_plate_02.jpg` | [Metal Plate 02](https://polyhaven.com/a/metal_plate_02) | Rob Tuytel |

AssetGen использует яркость исходника как модуляцию основного цвета. Игровой GLB содержит запечённый albedo, исходные JPG нужны для пересборки.

## Пробы по референсу ночного двора

Карты сгенерированы встроенным ImageGen по [референсу](../../docs/references/game_references/night-courtyard.png). Это исходники albedo для пробных запеканий. Обе карты 1254×1254 px. На повторении стоит отдельно проверять стык, особенно поперёк древесных волокон.

- [Дерево](night_courtyard_wood_v1.png). Тёмный коричневый тон, продольные волокна, без нарисованных швов досок.
- [Железо](night_courtyard_iron_v1.png). Нейтральный графитовый тон с мелкими следами ковки.

### Промпты ImageGen

**Дерево**

> Use case: stylized-concept. Generate one square seamless game albedo texture for MoonProject. The attached night courtyard scene is a material style reference, especially the barrel at lower left, crate, and wooden door. Fill the entire square edge to edge with one continuous surface of old dark brown matte wood. This is a flat orthographic scan-like material swatch. Narrow vertical wood grain, fine elongated grooves, modest hand-painted tonal variation, a few worn fibers, soft dry worn surface, subdued warm grey-brown, low-poly dark fantasy art direction with clear texture at a 256 px bake. Details should be quiet but present, concentrated in longitudinal grain, with a few restrained medium-scale grain streaks readable at reduced resolution. Medium-dark but readable diffuse base color. Uniform neutral illumination, no scene lighting, no shadow gradients, no highlights, no AO, no blue or orange lighting. Seamless repeat across both axes especially left/right. No board boundaries, seams, nails, bevels, edges, barrel, crate, object, perspective, labels, layout or frames. Vertical grain only. One continuous material RGB albedo.

**Железо**

> Use case: stylized-concept. Generate one square seamless RGB albedo texture for a low-poly dark fantasy game. The attached night courtyard is a material style reference, especially the dark charcoal forged-iron barrel bands and door hinges. Entire square is filled edge to edge with one continuous old charcoal grey hand-forged iron surface, slightly warm neutral near-black gray, subtle medium scale hammer marks and very small pits, a handful of subdued fine scratches, softly stylized granular weathering, slight tonal variation. Allow readable dark graphite midtones at a 256 px bake. No dense orange rust, no blue coloring, no baked specular highlights, light gradients, cast shadows, AO or directional lighting. Neutral flat orthographic scan-like material swatch repeating seamlessly left/right and top/bottom. No rivets, bands, seams, cracks that dominate, borders, perspective, shapes, object, scene, labels or frames.

## PBR каменной стены

`wall_stone_base_color.png`, `wall_stone_normal.png` и `wall_stone_roughness.png` — согласованные панели 724 × 724 px из предоставленного автором триптиха. Используются в `wall_stone_01` с общим масштабом 2 м; Normal — tangent-space OpenGL/Y+, Roughness — линейная data-карта. Панели нужно заменять одним комплектом через `tools/split_pbr_sheet.py`, не редактируя их поодиночке. Разовая визуальная проба источника описана в [отдельной карточке](../../docs/tasks/2026-11-22-wall-pbr-chat-prototype.md), production-проверки — в [карточке PBR-конвейера](../../docs/tasks/2026-11-22-pbr-texture-pipeline.md).

## Арочная дверь

[door_worn_wood_v1.png](door_worn_wood_v1.png) — карта тёплой обтёртой древесины, созданная встроенным ImageGen для `door_arch_heavy_01` и её отдельных рамы и полотна. В baker используется как модуляция яркости; цвет задаёт палитра `wood_oak`. Промпт, референс и проверки — в [карточке задачи](../../docs/tasks/2026-11-21-door-reference-split.md).
