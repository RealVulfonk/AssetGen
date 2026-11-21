# TD-012 · Непрозрачные материалы экспортируются двусторонними

Приоритет — P1. Тип — code/export. Объём — S.
Статус — предложено. Доказательство — воспроизведено на GLB.

## Проблема и доказательство

`get_material` в [`build_model.py:163-173`](../../blender/build_model.py#L163-L173) не включает backface culling. `finalize_material` в [`bake_texture.py:381-396`](../../blender/bake_texture.py#L381-L396) только выключает culling для `opacity < 1`, но не включает его обратно для непрозрачного материала.

Фактический разбор текущих GLB показал:

- `barrel_01`: `wood.doubleSided = true`, `metal.doubleSided = true`, оба opaque;
- `window_glass_01`: `frame.doubleSided = true`, хотя рама opaque; `glass = true`, как и задумано.

Это расходится с README, где двусторонность указана как следствие прозрачности.

## Сценарий влияния

Закрытые меши выполняют лишнюю работу по рендерингу обратных граней. При ошибке нормалей дефект может быть скрыт; при последующем изменении прозрачности поведение зависит от прежнего состояния material datablock.

## Границы

Не добавлять общий UI/DSL для двусторонности без потребителя. Прозрачные плоскости остаются двусторонними; отдельная opaque plane с неопределённой ориентацией требует fixture, а не молчаливого глобального исключения.

## Минимальный план

1. Задать явный default culling для материалов модели и явно устанавливать `use_backface_culling = opacity >= 1` при finalize.
2. Расширить GLB contract checks: opaque closed mesh односторонний, transparent — двусторонний.
3. Проверить model-only и textured GLB, front/back в Godot и существующие окна.

## Приёмка

- У бочки и рамы `doubleSided` отсутствует/равен false в обоих вариантах GLB; у стекла true.
- Alpha и filtering не меняются; reference builds и glass import проходят.
- Не наблюдается исчезновения корректно ориентированных наружных граней; неправильная winding диагностируется, а не маскируется.

## Связи

[TD-009](TD-009-godot-semantic-contracts.md), [TD-013](TD-013-semantic-mesh-validation.md).
