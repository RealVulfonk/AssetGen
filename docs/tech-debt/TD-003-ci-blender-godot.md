# TD-003 · Обязательный Blender/Godot gate на чистом checkout

Приоритет — P0. Тип — tests/architecture. Объём — L.
Статус — предложено. Доказательство — подтверждено конфигурацией.

## Проблема и доказательство

[`.github/workflows/check.yml:4-25`](../../.github/workflows/check.yml#L4-L25) запускает только системные тесты, JS syntax и distribution check. Он не устанавливает Blender/Godot и не вызывает `verify_reference_builds.py`, `verify_texture_pipeline.py` или Godot semantic checks.

При этом основной риск проекта находится именно в Blender-геометрии, bake и GLB. Локально чистый reference-набор проходит, но это не обязательный результат для push/PR.

## Сценарий влияния

PR меняет transform, UV или экспорт. Системные тесты и валидность JSON зелёные, а сборка на чистом checkout падает либо GLB теряет материал/коллизию. Дополнительный риск — импорт модуля, который существует только в рабочем дереве автора и не попал в коммит.

## Границы

Сохранить существующий быстрый matrix job. Не запускать весь каталог и графические golden images в каждом PR. Сначала один закреплённый Blender reference job; Godot подключается вместе с TD-009.

## Минимальный план

1. Добавить кэшированную, закреплённую установку эталонного Blender (текущий проверенный baseline — 5.2.3 LTS).
2. Запускать `python tests/verify_reference_builds.py` и численные texture pipeline checks на чистом checkout.
3. После TD-009 добавить headless Godot smoke на закреплённой версии.
4. Сделать job обязательным для generator/schema/export PR; сохранять отчёты и превью как временные artifacts при сбое.

## Приёмка

- Намеренный сбой тестового builder в PR делает required check красным.
- Чистый checkout без локального config/out проходит штатно.
- Отсутствие обязательного ассета или пропущенный этап считается failure после TD-001.
- Версии Blender/Godot видны в журнале; generated output не попадает в Git.

## Связи

[TD-001](TD-001-strict-output-verification.md), [TD-009](TD-009-godot-semantic-contracts.md); [предлагаемый процесс](../agent-development-process.md).
