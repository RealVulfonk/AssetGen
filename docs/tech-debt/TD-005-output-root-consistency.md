# TD-005 · Единый output root для CLI, tools и тестов

Приоритет — P1. Тип — architecture/reliability. Объём — M.
Статус — предложено. Доказательство — подтверждено кодом.

## Проблема и доказательство

CLI учитывает `ASSETGEN_OUT` в [`assetgen.py:25-28`](../../assetgen.py#L25-L28), а `regroup_out` повторяет эту логику. [`outdir.py:18-23`](../../tools/outdir.py#L18-L23) читает только config. [`render_sheet.py:44-65`](../../tools/render_sheet.py#L44-L65), [`verify_texture_colors.py:40-55`](../../tests/verify_texture_colors.py#L40-L55) и [`verify_determinism.py:18-33`](../../tests/verify_determinism.py#L18-L33) жёстко используют `ROOT/out`.

## Сценарий влияния

Агент собирает свежий ассет во временный `ASSETGEN_OUT`, затем `outdir` указывает на старый стандартный каталог, а colors/determinism проверяют другой результат. Это особенно опасно при параллельных worktree и автоматических прогонах.

## Границы

Сохранить относительный `out` как default. Не вводить второй механизм конфигурации и не менять mapping категории — он уже централизован в `assetgen_paths.py`.

## Минимальный план

1. Добавить в `assetgen_config.py` общий resolver: явный `--out` → `ASSETGEN_OUT` → config; относительные пути считать от ROOT.
2. Использовать его в CLI, outdir, render/regroup и соответствующих verifiers.
3. Добавить тесты на absolute/relative path и приоритет env; команды не должны смешивать два корня.

## Приёмка

- Все перечисленные инструменты при одном env видят один временный каталог.
- Явный `--out` verifier имеет приоритет над env и печатает фактический root.
- Без env поведение текущего пользователя не меняется.
- Тест не создаёт и не изменяет стандартный `out/`.

## Связи

[TD-001](TD-001-strict-output-verification.md), [TD-004](TD-004-artifact-report-paths.md), [TD-008](TD-008-clean-build-determinism.md).
