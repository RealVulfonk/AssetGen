# TD-010 · Единый контракт текстуры для schema, CLI, workbench и baker

Приоритет — P1. Тип — architecture/code. Объём — M.
Статус — предложено. Доказательство — подтверждено дублированием.

## Проблема и доказательство

- Defaults находятся в [`texture.schema.json`](../../schemas/texture.schema.json) и повторяются в [`bake_texture.py:30-73`](../../blender/bake_texture.py#L30-L73) и [`bake_texture.py:432-438`](../../blender/bake_texture.py#L432-L438). Тест [`test_texture_schema.py:51-61`](../../tests/test_texture_schema.py#L51-L61) проверяет лишь несколько значений, а не полное соответствие runtime.
- Палитра и наличие source image проверяются в [`assetgen.py:60-73`](../../assetgen.py#L60-L73), затем повторяются в [`workbench.py:108-120`](../../workbench.py#L108-L120).
- Preset-only поля перечислены в схеме и вручную повторены при смене рецепта в [`workbench.py:97-102`](../../workbench.py#L97-L102).

## Сценарий влияния

Новое поле или changed default проходит JSON validation, но baker/workbench использует другое значение. При смене preset в UI остаётся несовместимое старое поле, а CLI и workbench по-разному проверяют один вход.

## Границы

Не строить универсальный шейдерный редактор и не генерировать весь UI из Schema. Вынести только чистый контракт, общий всем текущим потребителям; Blender-граф остаётся в baker.

## Минимальный план

1. Вынести resolve/semantic validation в модуль системного Python без `bpy`; CLI, workbench и baker вызывают его.
2. Выбрать один источник defaults либо исчерпывающий тест соответствия всех schema defaults фактически resolved значениям, включая layers и `coopered_wood`.
3. Централизовать набор preset-only controls для patch-операции; ошибки содержат путь до поля.
4. Сохранить старые JSON и legacy inference `source_mode` без миграции.

## Приёмка

- Одна и та же candidate/spec получает одинаковые resolved settings и ошибки в CLI и workbench.
- Тест покрывает каждый documented default и взаимоисключения; изменение одного источника без синхронизации падает.
- Неизвестная палитра/отсутствующий source image одинаково отклоняются до Blender.
- Контрольный bake сохраняет прежние defaults и пиксели либо имеет объяснённый approved diff.

## Связи

[TD-003](TD-003-ci-blender-godot.md); [этап материалов](../assetgen-roadmap.md).
