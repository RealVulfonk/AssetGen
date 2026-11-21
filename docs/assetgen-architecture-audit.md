# Аудит архитектуры и кода AssetGen

Аудит начат 21 ноября 2026 года, актуализирован по текущему дереву 22 ноября. Рабочее дерево менялось параллельными задачами; выводы ниже относятся к состоянию финальных проверок, а не к первоначальному snapshot.

Связанные результаты: [дорожная карта моделирования](assetgen-roadmap.md), [реестр из 14 задач техдолга](tech-debt/README.md), [предлагаемый процесс разработки](agent-development-process.md).

## Резюме

AssetGen уже имеет рабочую архитектуру небольшого офлайн-конвейера: строгие JSON Schema, единый CLI, изолированные Blender-стадии, staged publication, блокировки, отчёты, GLB contract checks, чистые reference-сборки и переносимую библиотеку. Веб-мастерская использует те же стадии и добавляет очередь, backup и HTTP boundary tests.

**Большой rewrite не нужен.** Основной риск находится не в количестве строк и не в отсутствии ещё одного слоя абстракции, а в неполном доказательстве результата: общие verifiers пропускают несобранные ассеты, digest покрывает только модель, существующий CI не запускает Blender/Godot. Пока эти проблемы не закрыты, расширение DSL будет увеличивать число возможных результатов быстрее, чем способность их проверять.

Для качества моделей главное архитектурное ограничение другое: join стирает идентичность и независимость частей, а процедурные координаты привязаны к итоговому объекту. Это не «баг текущего static prop», но блокирует ближайшие игровые задачи — открываемые двери/сундуки, согласованные обломки и предсказуемое направление дерева на каждой доске. План развития предлагает opt-in assemblies и локальные координаты без изменения default для старых моделей.

## Текущая архитектура

| Область | Текущая граница | Оценка |
|---|---|---|
| Входы | `specs/models` + `specs/textures`, JSON Schema, palettes/source images | Строгая синтаксическая проверка; семантика геометрии и полнота defaults ещё не закрыты |
| CLI | `assetgen.py`: validate/new/model/texture, lock, staging, digest модели, Godot preview/copy | Хорошая оркестрация; provenance и report contract неполны |
| Геометрия | `build_model.py` + `cutouts.py` + `uv_layout.py`; BMesh, join, pivot, UV, collision | Разделение уже полезное; нужны точные mirror-семантика и базовые geometry invariants |
| Текстуры | `bake_texture.py`: resolve, node graph, bake, quantize, finalize, export, report | Чистые resolve-функции тестируемы, но размещены внутри bpy-модуля и дублируют схему/workbench |
| Workbench | `workbench.py`: local HTTP, catalog, patch, persistent queue, backup/publish | Использует CLI stages и имеет тесты границ; повторяет текстурный контракт |
| Результаты | Игнорируемый `out/`, версионируемая `library/` с SHA256 manifest | Разделение правильное; freshness snapshot не доказана |
| Проверки | System unittest, Blender scripts, GLB parser, reference builds, Godot glass | Хороший набор отдельных проверок; нет обязательного полного маршрута и единой strict-семантики |
| CI | `.github/workflows/check.yml`: Python/JS/distribution на Ubuntu и Windows | Полезный fast gate, но основные Blender/Godot стадии вне CI |

На 22 ноября каталог содержит **124 model specs, 112 texture specs и 5999 исходных частей**. Самые крупные generated-спеки достигают 297 частей. Это подтверждает потребность в генераторах семейств и отдельном review generated diff, но само по себе не требует немедленного изменения формата хранения.

## Что уже сделано хорошо

- **Воспроизводимый вход.** Имена/типы/диапазоны и неизвестные поля в основном ограничены схемами; `tools/check_distribution.py` валидирует все production model/texture specs.
- **Безопасная стадия.** CLI строит во временной папке внутри asset output, публикует report последним, сериализует доступ через lock и отклоняет bake устаревшей модели.
- **Проверка реальных форматов.** Тесты разбирают GLB, samplers, embedded textures, alpha и collision nodes, а не только читают собственный отчёт.
- **Контрольные полости и UV.** Чистый runner проверяет глубину глазниц, глухой/сквозной cutout, UV margins и крышки бочки.
- **Совместимость.** Для textures есть старые presets, custom layers, explicit source modes и soft/retro независимые настройки.
- **Workbench boundary.** Есть проверки Host/Origin, path containment, размера request, backup перед publish, failed build без перезаписи исходной спеки.
- **Переносимость.** `.gitattributes` фиксирует line endings, локальные config/output/cache исключены, library manifest проверяет размеры и SHA256.

Эти сильные места нужно сохранить через regression tests, а не переписывать ради более «модульной» структуры.

## Основные выводы

### P0 — сначала честность результата

1. [TD-001](tech-debt/TD-001-strict-output-verification.md): общий `verify_outputs.py` успешно завершился на 48 моделях/42 textured GLB, пропустив 76 specs. Discovery полезен, но не должен быть release gate.
2. [TD-002](tech-debt/TD-002-artifact-provenance.md): freshness модели проверяется только в одном месте CLI; verifier её не проверяет, а texture spec/source images не имеют digest. Инструменты и реализация стадии не записаны в provenance.
3. [TD-003](tech-debt/TD-003-ci-blender-godot.md): существующий CI подтверждает источники и библиотеку, но не выполняет основной generator pipeline на чистом checkout.

### P1 — архитектурные границы и игровые контракты

- [TD-004](tech-debt/TD-004-artifact-report-paths.md): три варианта записи/remap путей, абсолютные report paths и их устаревание после переноса.
- [TD-005](tech-debt/TD-005-output-root-consistency.md): `ASSETGEN_OUT` поддержан не всеми tools/verifiers, поэтому один агент может проверять другой output root.
- [TD-008](tech-debt/TD-008-clean-build-determinism.md): determinism тест повторяет только bake из одного `.blend`, а не две независимые чистые сборки.
- [TD-009](tech-debt/TD-009-godot-semantic-contracts.md): collision и общий Godot import не имеют semantic tests для существующих режимов.
- [TD-010](tech-debt/TD-010-texture-contract-single-source.md): defaults, source validation и preset-only controls размножены между schema/CLI/workbench/baker.

### P1 — воспроизведённые или кодом подтверждённые дефекты

- [TD-006](tech-debt/TD-006-flora-dry-run.md): `gen_flora.py --all --dry-run` падает с `KeyError` на `rock`.
- [TD-007](tech-debt/TD-007-flora-batch-exit-code.md): batch flora может вернуть 0 после failures и копирует в Godot без явного opt-in.
- [TD-011](tech-debt/TD-011-mirror-jitter.md): mirror строится с новым jitter и не является точной копией источника.
- [TD-012](tech-debt/TD-012-opaque-backface-culling.md): opaque wood/metal/frame фактически имеют `doubleSided=true` в GLB.
- [TD-013](tech-debt/TD-013-semantic-mesh-validation.md): схема принимает self-intersecting extrude и zero scale; базовые geometry invariants не проверяются.
- [TD-014](tech-debt/TD-014-new-invalid-name.md) (P2): ошибка имени в `new` возникает после записи невалидного файла.

## Рекомендуемая целевая граница без rewrite

1. Оставить `assetgen.py` оркестратором процессов и публикации, а `workbench.py` — local UI/queue adapter.
2. Вынести только общий чистый контракт: output resolver, texture resolve/semantic validation, input fingerprints и report serialization. Эти функции должны работать в системном Python без `bpy`.
3. Оставить Blender primitives/node graph в адаптерах. Не вводить DI-фреймворк, event bus или универсальный plugin API.
4. Сохранить join как default для статичных ассетов. Для assemblies добавить отдельный opt-in контракт после numeric/GLB/Godot fixtures, а не менять все модели одновременно.
5. Все новые возможности связывать с [этапами дорожной карты](assetgen-roadmap.md) и одним контрольным ассетом.

## Фактические проверки аудита

| Проверка | Фактический результат |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py" -v` | **26/26 прошли** на финальном дереве |
| `python tools/check_distribution.py` | **124 model specs, 112 texture specs, 48 bundled assets** прошли |
| `node --check web/app.js && node --check web/viewer.js` | Прошли без ошибок |
| `python tests/verify_reference_builds.py` | 7 моделей/6 textured GLB собраны с нуля; UV, cutouts, lock, failure recovery, stale model guard и rebake invalidation прошли |
| Blender `verify_texture_pipeline.py` | Пройден на Blender 5.2.3 LTS |
| Blender `verify_texture_colors.py` | Пройден для найденных PNG, но режим содержит skips; это не полная проверка каталога |
| `python tests/verify_outputs.py` | Exit 0; 48 models/42 textured GLB, **76 skipped** |
| `python -B tools/gen_flora.py --all --dry-run` | **Воспроизведён сбой** `KeyError: expected_size` на rock |
| Схема model fixtures | Self-intersecting extrude и zero scale приняты как valid |
| Разбор `barrel_01.glb`/`window_glass_01.glb` | Opaque материалы имеют `doubleSided=true`; прозрачное стекло — ожидаемо true |

## Ограничения аудита

- Полная чистая пересборка всех 124 моделей не выполнялась; именно поэтому TD-001/TD-003 требуют scheduled/full gate, а не утверждают её результат.
- В этом аудите Godot не запускался; зафиксированные ранее результаты стекла учтены как история, но не выдаются за новый прогон.
- Не проводился исчерпывающий художественный review каждого ассета или браузерный UI test всех сценариев. Дорожная карта основана на коде, очереди MoonProject и выборочных текущих превью.
- Найденные проблемы зарегистрированы, но не исправлены: задача ограничена аудитом и документацией.

## Порядок внедрения

1. Ввести strict/freshness и обязательный clean Blender CI (TD-001–TD-003).
2. Устранить общие контрактные разветвления (TD-004/TD-005/TD-010) маленькими PR.
3. Добавить независимый determinism и Godot semantics (TD-008/TD-009).
4. Локальные дефекты исправлять отдельно с исходным сценарием; не смешивать их с общей архитектурной работой.
5. Только затем начинать крупный этап assemblies/local material coordinates из дорожной карты.
