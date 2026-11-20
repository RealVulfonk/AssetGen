# AssetGen для Godot

JSON-driven генератор low-poly ассетов в стиле Neverlooted Dungeon. Агент описывает модель и текстуру в JSON; Blender-скрипты строят геометрию, UV и коллизию, запекают процедурный albedo и экспортируют GLB.

Перед началом задачи открой [правила работы агентов](AGENTS.md). В [карточках задач](docs/tasks/) хранятся запросы, сообщения о багах, основания решений и результаты проверок.

Для ночной партии достаточно написать агенту: «Сгенерируй модели по референсам из `D:\Refs\Props`». Агент осмотрит изображения, подготовит спеки и соберёт ассеты через CLI. В одной карточке останутся результаты по всей папке, ссылки на GLB и превью и вопросы к утреннему просмотру. [Порядок пакетной работы](AGENTS.md#папка-референсов-на-ночь)

[Аудит и план развития AssetGen](docs/assetgen-improvement-plan.md) содержит исходные замеры и результаты последующих итераций по текстурам, углублениям и сборке.
Визуальный ориентир для материалов и освещения — [ночной двор](docs/assetgen-improvement-plan.md#визуальный-ориентир).

[Список ассетов для MoonProject](docs/moonproject-asset-list.md) связывает каталог AssetGen с потребностями первой миссии.

## Быстрый старт

Требования: Python 3.10+, Blender 4.x/5.x, пакет `jsonschema`. NumPy уже входит в Blender. Для первой сборки используй готовую пару спек `barrel_01` из репозитория.

```powershell
python -m pip install -r requirements.txt
python assetgen.py validate barrel_01
python assetgen.py validate-texture barrel_01
python assetgen.py model barrel_01 --no-copy
python assetgen.py texture barrel_01 --no-copy
python tests/verify_outputs.py barrel_01
```

Путь к Blender задаётся в `assetgen.config.json`; переменная окружения `BLENDER` имеет приоритет. Результаты появляются в `out/<group>/<asset>/`, где группа выводится из `category` спеки:

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
- `preview_front.png`, `preview_side.png`, `preview_iso.png`, `preview_top.png`;
- `preview_lighting.png` при сборке с `--lighting-preview`;
- `report.json` и `report_texture.json`.

Для изолированной сборки можно переопределить папку через `ASSETGEN_OUT` и добавить `--no-copy` к команде сборки. CLI публикует файлы после завершения Blender. Повторный `model` сбрасывает результаты старого запекания. Если базовая сборка сделана до появления `model_digest` или JSON модели изменился, перед `texture` один раз запусти `model`.

## Скрипты

Карта репозитория: что за файл и зачем он нужен.

### Точки входа

| Скрипт | Запуск | Отвечает за |
|---|---|---|
| `assetgen.py` | `python assetgen.py <cmd> <name>` | Единственный CLI. Команды: `new` (создать спеку из шаблона), `validate`, `validate-texture`, `model` (собрать геометрию), `texture` (запечь albedo). Проверяет спеку по схеме, запускает Blender, печатает отчёт, копирует результат в Godot. |
| `tools/gen_flora.py` | `python tools/gen_flora.py --all --seed N` | Процедурный генератор **спеков** флоры: пишет пары `specs/models/<name>.json` + `specs/textures/<name>.json`. Меши не строит — это делает `assetgen.py model`. |

### Общие модули

| Файл | Отвечает за |
|---|---|
| `assetgen_paths.py` | Соответствие `category` спеки → папке вывода (`interiors` / `exteriors` / `environment`). Импортируется и из CLI, и из Blender-скриптов, и из тестов, поэтому раскладка `out/` задана в одном месте. |
| `blender/common.py` | Хелперы для скриптов внутри Blender: `hex2rgb`/`hex2lin`, экспорт GLB, рендер четырёх превью. |
| `blender/build_model.py` | Строит меш из JSON-спеки: примитивы, операции, join, pivot, flat shading, smart UV, collision-меш, экспорт `.glb` и превью. |
| `blender/bake_texture.py` | Запекает процедурный albedo: собирает шейдерный граф из пресета или слоёв, считает контраст, AO и edge, опционально квантует по палитре, экспортирует текстурированный GLB. |

### Утилиты `tools/`

| Скрипт | Отвечает за |
|---|---|
| `tools/build_flora.ps1` | Пакетная сборка: прогоняет `model` + `texture` по всем ассетам, подходящим под `-Pattern` (regex-альтернатива префиксов, не glob), и печатает сводку с трисами и цветами. |
| `tools/render_sheet.py` | Один ортографический рендер ассета в `out/sheet_<name>.png` — быстрый визуальный контроль без открытия Blender. |
| `tools/outdir.py` | Печатает папку вывода для ассета (`python tools/outdir.py conifer_01`). Нужен shell-скриптам, чтобы не дублировать маппинг из `assetgen_paths.py`. |
| `tools/inspect_uv.py` | Измеряет острова, швы, покрытие, перекрытия, плотность и зазоры активной UV-карты внутри Blender. |
| `tools/regroup_out.py` | Переносит уже собранные ассеты из плоского `out/<asset>` в `out/<group>/<asset>`. Идемпотентен, есть `--dry-run`, папки без спеки не трогает. |

### Тесты `tests/`

| Скрипт | Отвечает за |
|---|---|
| `test_texture_schema.py` | Юнит-тесты: схема текстур, палитры, custom layers, defaults. Системный Python. |
| `verify_outputs.py` | Разбирает GLB, отчёты, превью, коллизии, embedded textures и samplers. Системный Python. |
| `verify_texture_pipeline.py` | Рецепты, математика слоёв, contrast, цветовое пространство, quantization, filtering. Внутри Blender. |
| `verify_texture_colors.py` | Сверяет albedo с палитрами: quantized — по цветам палитры, soft — по валидности и промежуточным цветам. Внутри Blender. |
| `verify_determinism.py` | Запекает ассет дважды из одного `.blend` и сравнивает пиксели и настройки. Внутри Blender. |

## Godot

Для проверки материала в двух вариантах освещения используй `python assetgen.py texture barrel_01 --lighting-preview`. Флаг работает и с `model` для моделей без запекания. Godot берётся из `GODOT_BIN` или `PATH`, рендеру нужна графическая сессия. В PNG слева холодный общий свет, справа к нему добавлен тёплый фонарь. Оба кадра используют один GLB, камеру и фон. Для пакетной сборки флоры флаг доступен как `-LightingPreview`.

Чтобы автоматически копировать GLB и albedo (без превью), укажи в `assetgen.config.json` относительный или абсолютный путь:

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
