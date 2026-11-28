# AssetGen для Godot

JSON-driven генератор low-poly ассетов в стиле Neverlooted Dungeon. Агент описывает модель и текстуру в JSON; Blender-скрипты строят геометрию, UV и коллизию, запекают albedo и согласованные PBR-карты и экспортируют GLB.

## Запуск после клонирования

Для просмотра готовых моделей нужны Python 3.10+, Node.js 22+ / npm и браузер с WebGL 2. Blender нужен только для сборки и изменения текстур.

```powershell
python -m venv .venv
# Windows PowerShell:
.venv/Scripts/python -m pip install -r requirements.txt
npm --prefix web ci
.venv/Scripts/python workbench.py --open
```

На Linux/macOS используй `.venv/bin/python` вместо `.venv/Scripts/python`. В мастерской сразу доступны модели из [library](library/README.md), даже если `out/` пуст. Если порт занят: `python workbench.py --port 5174 --open` (или соответствующий Python виртуального окружения).

Для генерации установи Blender; текущие сборки проверены на 5.2.3 LTS. Он находится через `BLENDER`, затем конфигурацию/`PATH`; на Windows дополнительно проверяется стандартная папка Blender Foundation. Можно скопировать `assetgen.local.example.json` в `assetgen.local.json` и указать свой путь к Blender и папку Godot. Локальный файл не входит в Git. Параметры по умолчанию находятся в `assetgen.config.json`.

[Подготовка к GitHub, резервное копирование и восстановление](docs/sharing.md). [Происхождение внешних файлов и зависимостей](THIRD_PARTY.md).

Перед началом задачи открой [правила работы агентов](AGENTS.md). В [карточках задач](docs/tasks/) хранятся запросы, сообщения о багах, основания решений и результаты проверок.

Для ночной партии достаточно написать агенту: «Сгенерируй модели по референсам из `D:\Refs\Props`». Агент осмотрит изображения, подготовит спеки и соберёт ассеты через CLI. В одной карточке останутся результаты по всей папке, ссылки на GLB и превью и вопросы к утреннему просмотру. [Порядок пакетной работы](AGENTS.md#папка-референсов-на-ночь)

[Аудит и план развития AssetGen](docs/assetgen-improvement-plan.md) содержит исходные замеры и результаты последующих итераций по текстурам, углублениям и сборке.
Визуальный ориентир для материалов и освещения — [ночной двор](docs/assetgen-improvement-plan.md#визуальный-ориентир).

[Список ассетов для MoonProject](docs/moonproject-asset-list.md) связывает каталог AssetGen с потребностями первой миссии.

## Быстрый старт

Требования: Python 3.10+, Blender 4.x/5.x, пакеты `jsonschema` и `Pillow`. NumPy уже входит в Blender. Для первой сборки используй готовую пару спек `barrel_01` из репозитория.

```powershell
python -m pip install -r requirements.txt
python assetgen.py validate barrel_01
python assetgen.py validate-texture barrel_01
python assetgen.py model barrel_01 --no-copy
python assetgen.py texture barrel_01 --no-copy
python tests/verify_outputs.py barrel_01
```

Путь к Blender можно задать в `assetgen.local.json`; переменная окружения `BLENDER` имеет приоритет. Результаты появляются в `out/<group>/<asset>/`, где группа выводится из `category` спеки:

| Группа | Категории | Что внутри |
|---|---|---|
| `out/interiors/` | `architecture`, `doors`, `furniture`, `props`, `remains` | утварь, архитектура, двери, кости, гроб |
| `out/exteriors/` | `flora/trees`, `crypt`, `structure` | деревья и сухостой, могилы, мост |
| `out/environment/` | `flora/understory` | подлесок: камни, пни, брёвна, трава, папоротники, грибы, цветы, ягоды, кусты, камыш |

Соответствие задано в `assetgen_paths.py` (`asset_group`), поэтому и CLI, и тесты, и `tools/` находят файлы одинаково. Узнать путь конкретного ассета:

```powershell
python tools/outdir.py conifer_01     # -> out/exteriors/conifer_01
```

Уже собранные ассеты из плоского `out/<asset>` переносятся в группы командой:

```powershell
python tools/regroup_out.py --dry-run
python tools/regroup_out.py
```

Категория неизвестного ассета попадает в `interiors`; папки без спеки (`out/verification`) команда не трогает.

Внутри папки ассета:

- `<asset>.blend` — модель с цветовыми материалами;
- `<asset>.glb` — видимая модель без collision-меша;
- `<asset>_godot.glb` — вариант с `-colonly` для Godot, если включена коллизия;
- `<asset>_tex.blend` и `<asset>_albedo.png` — после запекания;
- `<asset>_normal.png` и `<asset>_orm.png` — после запекания материала с `pbr_detail`;
- `preview_front.png`, `preview_side.png`, `preview_iso.png`, `preview_top.png`;
- `preview_lighting.png` при сборке с `--lighting-preview`;
- `report.json` и `report_texture.json`.

Для изолированной сборки можно переопределить папку через `ASSETGEN_OUT` и добавить `--no-copy` к команде сборки. CLI публикует файлы после завершения Blender. Повторный `model` сбрасывает результаты старого запекания. Если базовая сборка сделана до появления `model_digest` или JSON модели изменился, перед `texture` один раз запусти `model`.

## Скрипты

### Локальная веб-мастерская

[Бэклог мастерской](docs/workbench-backlog.md): удаление результатов, удаление моделей с метаданными и быстрая примерка текстур без bake (пока не реализованы).

Для первого запуска установи браузерную зависимость (Node.js/npm):

```powershell
npm --prefix web ci
python workbench.py --open
```

Дальше достаточно `python workbench.py --open`. Откроется `http://127.0.0.1:5173`; другой порт задаётся через `--port 5174`. Интернет после установки зависимости не нужен. Python использует те же `requirements.txt`, конфигурацию Blender и `ASSETGEN_OUT`, что и CLI.

- Слева — каталог моделей с собранным GLB, поиск, категории и независимые галочки пакетного выбора. Несобранные спеки скрыты, файлы при этом не удаляются. Клик по строке открывает объект, не меняя выбор партии.
- В центре — два синхронных 3D-вида: текущий GLB с материалами и та же геометрия серым материалом. Несобранные модели помечены отдельно.
- Справа — галочки «Теги для изменения» (можно выбрать несколько), список «Образец настроек», процедурный рецепт, палитра, изображения из `presets/textures/` и параметры из схемы. Теги собраны по активной и выбранным моделям; образец определяет только отображаемые значения активного объекта. На отмеченные теги всей партии переносятся только изменённые поля; отсутствующие явные рецепты пропускаются. Все изменения тегов одной модели запекаются вместе за один проход. Смена процедурного рецепта сбрасывает его специфические параметры; смена картинки сохраняет масштаб и силу фактуры у каждого материала.
- «Перегенерировать текстуры» запускает последовательную очередь. При необходимости сначала собирается актуальная геометрия. Настройки и результат публикуются после успешной сборки; ошибка отдельного объекта не останавливает следующие. Сборка использует штатные `build_stage` и блокировку CLI, всегда без копирования в Godot.

Текстуры появляются после запекания Blender; браузер не имитирует шейдер. «Источник поверхности» разделяет два основных способа: «Из изображения» переносит RGB карты и скрывает процедурный рецепт/палитру; «Процедурный» показывает рецепт/палитру и не использует изображение. В «Дополнительном способе» доступен смешанный режим: изображение модулирует яркость процедурного цвета. Старые рецепты с картой открываются как смешанные. Смена режима сохраняет неактивный рецепт и карту для переключения обратно. В режиме изображения яркость/контраст при переключении сбрасываются к нейтральным, а quantize выключается для всего атласа. Параметры материала свёрнуты по умолчанию. Произвольные `layers` сохраняются; их состав пока редактируется в JSON, а общие параметры доступны в UI. Для моделей без текстурной спеки её нужно сначала добавить в `specs/textures/`.

История очереди, промежуточные результаты и резервные копии лежат в игнорируемой папке `.workbench/jobs/<id>/<asset>/`. При сбое Blender исходные результаты не меняются. Успешная замена сохраняет прежний JSON в `backup/texture_spec.json`, заменяемые файлы — рядом, а список файлов и исходные пути — в `backup/manifest.json`. Восстановление пока ручное, при остановленной очереди: вернуть прежние файлы и JSON по манифесту, удалить выходы из `files`, которых нет в `previous`. Кнопки отката в MVP нет. После перезапуска сервера незавершённые задания помечаются прерванными; их можно отправить заново. Папка истории автоматически не очищается.

Верхняя навигация объединяет **Редактор**, **Пайплайны** и **Запуски**. В редакторе PBR-комплект выбирается одной поверхностью: `*_base_color.png`, `*_normal.png`, `*_roughness.png` группируются по точному имени. Неполные наборы отмечены; отдельные data-карты не предлагаются как цвет. Выбор PBR заменяет все каналы, выбор одиночного изображения удаляет прежние PBR-карты, а смешанный режим использует только цвет. Масштаб каждого отмеченного материала сохраняется, пока автор явно не изменит размер повтора. Сохранённые нестандартные пути видны в составе каналов.

В «Пайплайнах» действие «Подготовить PBR» загружает настоящий локальный PNG/JPEG/WebP до 40 МиБ (ширина делится на 3, каждая панель до 4096 × 4096), запускает существующие split и seam и сохраняет исходные байты, параметры, журнал этапов и карты в `.workbench/runs/<id>/`. Успешный кандидат получает `needs_review`. В «Запусках» доступны три канала, повторы 2 × 2 с общим масштабом, синхронной прокруткой, границами и кнопкой «Показать стык». Слева можно выбрать исходный split или прежний готовый вариант того же входа. «Сравнить другую ширину» сохраняет новый запуск и использует тот же split; ошибка seam не уничтожает исходные карты. После перезапуска доступны история и повтор сохранённого входа, прерванные запуски помечаются отдельно.

Публикация выполняется отдельной кнопкой: выбери **исходный split** или **кандидат** и свободное имя. Все три PNG сохраняются в `presets/textures/` целым комплектом, существующие имена не перезаписываются. Неоконченная публикация восстанавливается при старте: убираются только принадлежащие ей файлы, чужие замены сохраняются. Файловая система должна поддерживать hard links (обычный NTFS/ext4). После публикации «Применить в редакторе» выбирает поверхность, затем автор отмечает модели и теги и запускает обычную очередь bake. Публикация и успешная обработка не заменяют художественную и Godot-проверку; автоматического переноса в игру нет.

Карта репозитория: что за файл и зачем он нужен.

### Точки входа

| Скрипт | Запуск | Отвечает за |
|---|---|---|
| `assetgen.py` | `python assetgen.py <cmd> <name>` | Единственный CLI. Команды: `new` (создать спеку из шаблона), `validate`, `validate-texture`, `model` (собрать геометрию), `texture` (запечь albedo и опциональные PBR-карты). Проверяет спеку по схеме, запускает Blender, печатает отчёт, копирует результат в Godot. |
| `tools/gen_flora.py` | `python tools/gen_flora.py --all --seed N` | Процедурный генератор **спеков** флоры: пишет пары `specs/models/<name>.json` + `specs/textures/<name>.json`. Меши не строит — это делает `assetgen.py model`. |

### Общие модули

| Файл | Отвечает за |
|---|---|
| `assetgen_paths.py` | Соответствие `category` спеки → папке вывода (`interiors` / `exteriors` / `environment`). Импортируется и из CLI, и из Blender-скриптов, и из тестов, поэтому раскладка `out/` задана в одном месте. |
| `blender/common.py` | Хелперы для скриптов внутри Blender: `hex2rgb`/`hex2lin`, экспорт GLB, рендер четырёх превью. |
| `blender/build_model.py` | Строит меш из JSON-спеки: примитивы, операции, join, pivot, flat shading, smart UV, collision-меш, экспорт `.glb` и превью. |
| `blender/bake_texture.py` | Запекает albedo и опциональные Normal/Roughness: собирает шейдерный граф из пресета, слоёв или изображений, считает контраст, AO и edge, сохраняет общий касательный базис PBR, экспортирует текстурированный GLB. |

### Утилиты `tools/`

| Скрипт | Отвечает за |
|---|---|
| `tools/build_flora.ps1` | Пакетная сборка: прогоняет `model` + `texture` по всем ассетам, подходящим под `-Pattern` (regex-альтернатива префиксов, не glob), и печатает сводку с трисами и цветами. |
| `tools/render_sheet.py` | Один ортографический рендер ассета в `out/sheet_<name>.png` — быстрый визуальный контроль без открытия Blender. |
| `tools/split_pbr_sheet.py` | Разрезает горизонтальный триптих Base Color / Normal / Roughness на три PNG без ресемплирования; требует Pillow. |
| `tools/process_pbr_seams.py` | Создаёт отдельный кандидат обработки краёв, repeat-preview и отчёт `needs_review`; качество стыка требует визуальной проверки. |
| `tools/outdir.py` | Печатает папку вывода для ассета (`python tools/outdir.py conifer_01`). Нужен shell-скриптам, чтобы не дублировать маппинг из `assetgen_paths.py`. |
| `tools/inspect_uv.py` | Измеряет острова, швы, покрытие, перекрытия, плотность и зазоры активной UV-карты внутри Blender. |
| `tools/regroup_out.py` | Переносит уже собранные ассеты из плоского `out/<asset>` в `out/<group>/<asset>`. Идемпотентен, есть `--dry-run`, папки без спеки не трогает. |

### Тесты `tests/`

| Скрипт | Отвечает за |
|---|---|
| `test_texture_schema.py` | Юнит-тесты: схема текстур, палитры, custom layers, PBR-поля и defaults. Системный Python. |
| `test_split_pbr_sheet.py` | Пиксельная идентичность панелей, ошибки входа и `--force` у splitter. Системный Python с Pillow. |
| `verify_outputs.py` | Разбирает GLB, отчёты, превью, коллизии, embedded textures, PBR-связи, tangents и samplers. Системный Python. |
| `verify_pbr_import.gd` | Проверяет PBR-материал и префаб в Godot, снимает A/B Normal/Roughness при трёх световых условиях и двух дистанциях. |
| `verify_texture_pipeline.py` | Рецепты, математика слоёв, contrast, цветовое пространство, quantization, filtering. Внутри Blender. |
| `verify_texture_colors.py` | Сверяет albedo с палитрами: quantized — по цветам палитры, soft — по валидности и промежуточным цветам. Внутри Blender. |
| `verify_determinism.py` | Запекает ассет дважды из одного `.blend` и сравнивает пиксели и настройки. Внутри Blender. |

## Godot

Для проверки материала в двух вариантах освещения используй `python assetgen.py texture barrel_01 --lighting-preview`. Флаг работает и с `model` для моделей без запекания. Godot берётся из `GODOT_BIN` или `PATH`, рендеру нужна графическая сессия. В PNG слева холодный общий свет, справа к нему добавлен тёплый фонарь. Оба кадра используют один GLB, камеру и фон. Для пакетной сборки флоры флаг доступен как `-LightingPreview`.

Чтобы автоматически копировать GLB и запечённые карты (без превью), укажи в `assetgen.config.json` относительный или абсолютный путь:

```json
"godot_assets": "../my_game/assets/props"
```

Пустая строка отключает копирование. Категория из спеки становится подпапкой.

Фильтрация уже записана в GLB samplers: `pixel: false` экспортирует linear filtering, `pixel: true` — nearest with mipmaps. Post-import для выбора фильтрации не нужен. `godot/post_import_pixel.gd` оставлен только как legacy/retro-only override: он принудительно делает все материалы nearest, поэтому не назначай его мягким ассетам. Если старый import preset уже назначен, сними его и переимпортируй GLB. Замена внешнего PNG не обновляет текстуру, встроенную в GLB, — пересобери и переимпортируй ассет.

В `<asset>_godot.glb` тип `collision` определяет коллайдер: `mesh` копирует видимые треугольники через `-colonly`, `convex` создаёт выпуклую оболочку через `-convcolonly`, `box` использует ограничивающий куб, `none` отключает коллизию. Используй в игре Godot-вариант: обычные просмотрщики не знают эти суффиксы и отображают collision-меши как геометрию.

## DSL модели

Примитивы: `box`, `cylinder`, `sphere`, `lathe`, `extrude`, `plane`. Общие операции: `scale`, `rotation`, `location`, `bevel`, `jitter`, `array`, `mirror_x`. Полная строгая схема — `schemas/model.schema.json`.

Опциональный массив `cutouts` вычитает закрытые `box` и `cylinder` из одной замкнутой детали. Применяется после `scale`, `bevel` и `jitter`, в метрах относительно детали до её поворота, смещения и отражения. Резец должен пересечь поверхность. Если один конец остаётся внутри детали, получается глухая полость. Если резец пересекает всю её толщину, получается сквозное отверстие. Внутренние грани получают материал своей детали. Пример — [глазницы skull_01](specs/models/skull_01.json). `mesh` повторяет вырез в коллизии, `convex` охватывает его выпуклой оболочкой.

`uv_projection: "cylindrical"` применяет к детали `lathe` боковую полосу и две плоские крышки. Профиль идёт снизу вверх, начинается и заканчивается на оси и имеет плоские торцы, как у корпуса `barrel_01`. Smart UV разворачивает остальные детали, затем сборщик пакует все острова в общий атлас.

Шаблоны: `barrel`, `door`, `coffin`, `bone`, `chest`, `skull`, `candle`, `torch`, `pillar`, `urn`, `table`, `cell_bars`.

Новый проп начни командой `python assetgen.py new <template> <свободное_имя>`. Она создаёт спеку модели. Для запекания добавь одноимённую спеку текстуры. Существующий проп правь в его JSON. Рекомендации по размерам и материалам собраны в [навыке AssetGen](.claude/skills/assetgen/SKILL.md).

## Текстуры

Полная схема — `schemas/texture.schema.json`. Проверка спеки не требует модели или Blender:

```powershell
python assetgen.py validate-texture pillar
```

### Стекло

В текстурной спеке `opacity` задаёт непрозрачность всего материала от `0` до `1` (по умолчанию `1`). Поле работает и с пресетами, и с `layers`. `roughness` управляет шероховатостью от `0` до `1` (по умолчанию `0.9`). Цвет обоих материалов запекается в общий RGB-атлас, а коэффициент альфы записывается отдельно в GLB на этапе `texture`.

Назначь раме и стеклу разные теги. Для остекления используй одну деталь `plane` с простым контуром `points` в локальной плоскости XY и поверни её в плоскость рамы. При `opacity < 1` материал экспортируется двусторонним, поэтому одной поверхности достаточно для обзора с обеих сторон.

```json
"materials": {
  "frame": {"preset": "wood", "palette": "wood_dark_soft"},
  "glass": {"preset": "flat", "palette": "glass_blue", "value": 0.6, "opacity": 0.35, "roughness": 0.24}
}
```

```powershell
python assetgen.py model window_glass_01 --no-copy
python assetgen.py texture window_glass_01 --no-copy --lighting-preview
python tests/verify_outputs.py window_glass_01
$window = Join-Path (Get-Location) "out/interiors/window_glass_01"
& $env:GODOT_BIN --path godot/lighting_preview --script (Resolve-Path tests/verify_glass_import.gd).Path -- "$window/window_glass_01.glb" "$window/preview_through_glass.png"
```

Конвейер пропов MoonProject сохраняет первые два слота, поэтому с дополнительными тегами проверь, что стекло сохранило свой материал после обработки. Перекрывающиеся прозрачные поверхности, например внутренняя и внешняя стенки бутылки, требуют отдельной визуальной проверки сортировки в Godot. [Ограничения прозрачности Godot](https://docs.godotengine.org/en/stable/tutorials/3d/3d_rendering_limitations.html#transparency-sorting)

### Мягкий стиль по умолчанию

Если параметры не указаны, применяются:

| Параметр | Default | Назначение |
|---|---:|---|
| `size` | `128` | Размер albedo |
| `pixel` | `false` | Linear filtering вместо nearest |
| `quantize` | `false` | Промежуточные цвета сохраняются |
| `gradient` | `ease` | Плавная интерполяция палитры |
| `contrast` / `contrast_pivot` | `1` / `0.5` | Контраст вокруг средней точки |
| `ao` | `0.25` | Мягкое умножение цвета на AO |
| `edge` | `0` | Дополнительная Pointiness-коррекция |
| `samples` / `margin` | `64` / `4` | Качество bake и EXTEND gutters |
| `pack_uv` | `false` | Повторная упаковка островов под разрешение albedo и поле bake |

С `pack_uv: true` значение `margin` по умолчанию составляет 1, 2 и 4 px для карт 64, 128 и 256 px соответственно. При 512 px применяется 4 px. Явный `margin` переопределяет это значение. Упаковка выделяет с каждой стороны острова запас `margin + 0.5` px. Поле заполняется методом `EXTEND`, обновлённые UV сохраняются в текстурированных `.blend` и GLB.

Пример обычной спеки:

```json
{
  "asset": "pillar",
  "size": 256,
  "seed": 7,
  "materials": {
    "stone": {
      "preset": "stone",
      "palette": "stone_grey_soft",
      "scale": 7,
      "contrast": 0.85,
      "ao": 0.3,
      "edge": 0.12
    },
    "default": {"preset": "flat", "palette": "stone_grey_soft"}
  }
}
```

`pixel` управляет только sampling текстуры, `gradient` — переходами между цветами палитры, `quantize` — привязкой финального PNG к цветам палитры. Это независимые настройки.

Контраст вычисляется без смещения средней яркости:

```text
factor = clamp((pattern - contrast_pivot) * contrast + contrast_pivot + brightness, 0, 1)
```

Сначала формируется базовый цвет, затем применяются AO и edge. Они больше не переключают резкие полосы палитры. Квантование, если включено, выполняется последним. При общем atlas квантование использует объединение палитр материалов.

### Пресеты и слои

`wood` смешивает направленные Wave-волокна с широким и мелким Noise. `stone` использует широкий Noise как основу, Voronoi как вторичные включения и мелкий Noise как зерно. `metal`, `bone`, `cloth` пока используют Noise; `flat` — Constant.

`coopered_wood` — рецепт для формы с осью Z в центре объекта, например [barrel_01](specs/textures/barrel_01.json). Клёпки идут вокруг оси, доски горизонтальных крышек — вдоль Y. `staves` задаёт количество клёпок, `seam_width` — ширину стыка как долю ширины доски, `lid_board_width` — ширину доски крышки в метрах, `grain_strength` — выраженность волокон.

В любой материал можно добавить `source_detail`, как в [спеке бочки](specs/textures/barrel_01.json). `image` выбирает JPG или PNG из [presets/textures](presets/textures/), `tile_size` задаёт размер повтора в метрах, `strength` управляет влиянием фактуры от 0 до 1. Используется проекция по трём осям объекта. Фактура меняет яркость цвета из палитры, а итог по-прежнему запекается в общий albedo заданного размера.

Поле материала `source_mode` явно выбирает способ:

| Значение | Поведение |
|---|---|
| `procedural` | Только рецепт и палитра; сохранённая `source_detail` не используется. |
| `image` | RGB изображения `source_detail.image` в sRGB, box-проекция с `tile_size`. Палитра, рисунок рецепта, `gradient` и `strength` не влияют на цвет. |
| `mixed` | Прежний процедурный цвет с модуляцией яркости от изображения. |

Без `source_mode` материал с `source_detail` работает как mixed, без неё — как procedural. Для image/mixed карта обязательна. Во всех режимах доступны AO, edge и свойства поверхности (opacity, roughness, metallic). В image `brightness` и `contrast` применяются к линейным RGB относительно `contrast_pivot`. `palette` и процедурные параметры остаются в JSON для обратного переключения, но не используются в image. `quantize: true` с image отклоняется схемой: привязка к процедурной палитре уничтожила бы RGB карты. Мастерская при выборе image явно выключает quantize всего атласа.

Пример RGB-карты:

```json
"wood": {
  "source_mode": "image",
  "preset": "wood",
  "palette": "wood_oak",
  "brightness": 0,
  "contrast": 1,
  "source_detail": {"image": "fine_grained_wood.jpg", "tile_size": 1, "strength": 0.6}
}
```

### Base Color + Normal + Roughness

Для согласованного комплекта используй один горизонтальный лист строго из трёх равных вертикальных панелей в порядке Base Color, Normal, Roughness. Разрезание работает в системном Python и не требует Blender:

```powershell
python tools/split_pbr_sheet.py wall_sheet.png --out presets/textures --name wall_stone
```

Получатся `wall_stone_base_color.png`, `wall_stone_normal.png`, `wall_stone_roughness.png`. Ширина листа должна делиться на три; выходная папка должна существовать. Панели сохраняют RGB-пиксели и размер без ресемплирования. Существующие файлы заменяются только вместе при явном `--force`; ошибка входа не создаёт неполный комплект. [Промпт для генерации листа](docs/prompts/chatgpt-pbr-texture-sheet.md) задаёт совпадение деталей, но не заменяет визуальную проверку.

Подключи обе data-карты через `pbr_detail` материала в режиме `image`:

```json
"stone": {
  "preset": "stone",
  "palette": "stone_grey_soft",
  "source_mode": "image",
  "source_detail": {
    "image": "wall_stone_base_color.png",
    "tile_size": 2.0,
    "strength": 1.0
  },
  "pbr_detail": {
    "normal": "wall_stone_normal.png",
    "roughness": "wall_stone_roughness.png",
    "normal_strength": 1.0
  },
  "roughness": 1.0
}
```

- `normal` и `roughness` обязательны внутри `pbr_detail`; это локальные PNG из `presets/textures/`. `normal_strength` от 0 до 2 по умолчанию равен 1. Поле недопустимо в procedural/mixed.
- Все три карты используют общий `source_detail.tile_size`. Base Color читается как sRGB, Normal и Roughness — как Non-Color. Normal должна быть tangent-space OpenGL/Y+, а не bump из яркости. Палитра, contrast, brightness и quantize не применяются к data-картам.
- Для PBR используется общая dominant-axis UV-проекция по локальной нормали каждой грани со сдвигом на полтайла. Она сохраняет касательный базис источника и уводит границу повтора с центра плоской грани. На сглаженных и сильно изогнутых поверхностях возможны проекционные швы; первый контракт рассчитан на плоские low-poly элементы. Старые материалы без `pbr_detail` сохраняют прежнюю BOX-проекцию с blend 0.25.
- Bake создаёт `<asset>_normal.png` и `<asset>_orm.png` в том же атласе и с тем же размером, что albedo. В ORM канал R=1, Roughness находится в G, B=1. Скаляр `roughness` остаётся множителем glTF, поэтому для исходной карты обычно задают 1.0. `metallic` остаётся независимым скаляром.
- Обычный и `_godot.glb` содержат embedded Base Color, `normalTexture`, `metallicRoughnessTexture`, один UV set и tangent basis. Старые спеки без `pbr_detail` экспортируются по-прежнему только с albedo и скалярными коэффициентами.

```powershell
python assetgen.py validate-texture wall_stone_01
python assetgen.py model wall_stone_01 --no-copy
python assetgen.py texture wall_stone_01 --no-copy --lighting-preview
python tests/verify_outputs.py wall_stone_01
```

Повторный `model` удаляет albedo, Normal, ORM и старый текстурный отчёт. Публикация новых карт происходит вместе с успешной стадией; при отключении `pbr_detail` устаревшие файлы удаляются. Перед распространением PBR на другие материалы проведи A/B с одинаковыми Base Color, камерой и светом через `tests/verify_pbr_import.gd`: передай control GLB, Normal-only GLB, полный PBR GLB и папку отчёта. Скрипт принимает любое число треугольников и подходящие размеры карт. Дополнительные пятый и шестой аргументы — импортированный Godot GLB и префаб `wall_stone_01` — включают стеновые проверки 12 треугольников, карт 512 × 512 и одной box-коллизии. Пример и измерения — в [карточке конвейера](docs/tasks/2026-11-22-pbr-texture-pipeline.md).

Для расширенной настройки вместо `preset` можно задать от 1 до 4 слоёв:

```json
"stone": {
  "palette": "stone_grey_soft",
  "layers": [
    {"type": "noise", "scale": 2.5, "detail": 3, "weight": 0.7},
    {"type": "voronoi", "scale": 8, "weight": 0.2},
    {"type": "noise", "scale": 30, "detail": 2, "weight": 0.1}
  ]
}
```

Доступны `noise`, `wave`, `voronoi`, `constant`. Каждый слой нормализуется, поддерживает положительный `weight` и `invert`; итог — средневзвешенное значение. Не сочетай `layers` с `preset`, material-level `scale`, `direction`, `distortion`, `detail` или `value`: масштабы задаются внутри слоёв.

### Ретро-режим

Для резкой палитры и пиксельной фильтрации задай все три параметра явно:

```json
{
  "pixel": true,
  "quantize": true,
  "materials": {
    "stone": {
      "preset": "stone",
      "palette": "stone_grey",
      "gradient": "constant"
    },
    "default": {"preset": "flat", "palette": "stone_grey", "gradient": "constant"}
  }
}
```

Исходные палитры сохранены. `_soft`-варианты содержат близкие оттенки и предназначены для плавных рамп. Ретро-режим не гарантирует побайтовую идентичность результатам старого baker.

`report_texture.json` дополнительно записывает эффективные defaults, уникальные цвета и resolved settings/layers каждого материала.

## Процедурная флора

`tools/gen_flora.py` порождает спеки моделей и текстур для леса: деревья, сухостой,
кусты и подлесок. Это генератор *спеков*, а не мешей — результат обычные JSON,
которые дальше идут через тот же `assetgen.py model` / `texture`.

```powershell
python tools/gen_flora.py --list                       # семейства и счётчики
python tools/gen_flora.py --family conifer --count 24 --seed 42
python tools/gen_flora.py --all --seed 20261116        # весь набор
python tools/gen_flora.py --all --seed 7 --force       # перезаписать существующие
python tools/gen_flora.py --all --dry-run              # только имена и габариты
```

Семейства: `conifer`, `snag`, `broadleaf`, `shrub`, `stump`, `log`, `fern`,
`grass`, `reed`, `mushroom`, `flower`, `berry`, `rock`.

Деревья строятся по-разному: хвойные — ярусами «лап» вокруг ствола, сухостой —
обломанный ствол с голыми сучьями, лиственные — купол из ветвей со спиралью
Фибоначчи плюс листва из двух слоёв: гранёные комки дают массу, торчащие листья —
рваный силуэт. Только комки читаются как «брокколи», только листья оставляют
крону дырявой.

Почему генератор, а не Godot-скрипт: ассетам нужны запечённый albedo, `-colonly`
коллизии, детерминизм и ревью спеков в git. Рантайм-генерация в Godot всего этого
лишает. Почему не руками: одно дерево — это 30–110 партов, а радиальный массив
в DSL отсутствует (`array` умеет только сдвиг, `mirror_x` — отражение), поэтому
скрипт сам считает тригонометрию и выписывает каждый лепесток явным `rotation`.

Один и тот же `--seed` даёт те же спеки. `expected_size` считается по реальному
bbox с учётом поворотов, поэтому расхождение с Blender только на уровне jitter.

Сборка всего набора:

```powershell
powershell -File tools/build_flora.ps1                 # все семейства
powershell -File tools/build_flora.ps1 -Pattern conifer
```

`-Pattern` — это regex-альтернатива префиксов, не glob.

Посмотреть отдельный ассет одним ортографическим рендером в `out/sheet_<name>.png`:

```powershell
& $env:BLENDER -b --factory-startup -P tools/render_sheet.py -- $PWD broadleaf_01
```

## Проверка собранных ассетов

Что делает каждый тест — в таблице `tests/` выше.

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/verify_reference_builds.py
python tests/verify_outputs.py
& $env:BLENDER -b --factory-startup --python-exit-code 1 -P tests/verify_texture_pipeline.py -- $PWD
& $env:BLENDER -b --factory-startup --python-exit-code 1 -P tests/verify_texture_colors.py -- $PWD
& $env:BLENDER -b out/interiors/pillar/pillar.blend --python-exit-code 1 -P tests/verify_determinism.py -- $PWD pillar
```

Если `BLENDER` не задана, укажи полный путь к `blender.exe`.

`verify_reference_builds.py` запускает обычный CLI в пустой временной папке, требует все ожидаемые артефакты и проверяет геометрию глухого и сквозного вырезов и глубину глазниц.

Для отдельного замера UV передай проверяемый `.blend`, имя ассета, путь JSON-отчёта и поле в пикселях из `report_texture.json`:

```powershell
$assetDir = python tools/outdir.py barrel_01
& $env:BLENDER -b "$assetDir/barrel_01_tex.blend" --python-exit-code 1 -P tools/inspect_uv.py -- barrel_01 "$assetDir/uv.json" 4
```

Зазор и плотность пересчитываются в пиксели для каждой указанной в отчёте шкалы на загруженной развёртке. Чтобы проверить фактическую упаковку для другого разрешения, сначала запеки карту в этом разрешении. Перекрытие и покрытие оцениваются по сетке 1024×1024.

Дополнительно смотри albedo и все превью: автоматические тесты не обнаруживают нежелательный художественный стиль, локальные UV-швы и слабый island bleed.

## Отладка

CLI запускает Blender с `--python-exit-code 1` и дополнительно считает наличие `Traceback` ошибкой. При сбое выводятся последние 40 строк журнала. Не убирай эти проверки: Blender иначе может вернуть код 0 после исключения Python.

Для живой отладки в открытом Blender можно выполнить:

```python
import sys
sys.argv = ["blender", "--", "C:/absolute/path/specs/models/barrel_01.json", "C:/absolute/path/out/interiors/barrel_01"]
exec(open("C:/absolute/path/blender/build_model.py", encoding="utf-8").read())
```

`build_model.py` начинает с `read_factory_settings(use_empty=True)` и очищает открытую сцену. Обычная сборка всегда идёт через CLI для воспроизводимости. После повторной сборки модели текстуру нужно запечь заново: `model` перезаписывает обычный GLB без текстуры.

Команда обработки стыков после split:

```powershell
python tools/process_pbr_seams.py --source presets/textures --out out/verification --name wall_stone --band 24
```

Она сохраняет отдельную папку `<имя>_seam_candidate` с картами, 2 × 2 повторами и JSON-отчётом `needs_review`, не заменяя исходные карты. Смешивание может разрушить детали; визуальная проверка и Godot A/B обязательны. Roughness кандидата использует зелёный канал исходника на всей карте, как и PBR bake. Подробнее — [PBR texture intake](.claude/skills/pbr-texture-intake/SKILL.md).
