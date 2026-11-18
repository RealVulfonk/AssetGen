# AssetGen для Godot

JSON-driven генератор low-poly ассетов в стиле Neverlooted Dungeon. Агент описывает модель и текстуру в JSON; Blender-скрипты строят геометрию, UV и коллизию, запекают процедурный albedo и экспортируют GLB.

## Быстрый старт

Требования: Python 3.10+, Blender 4.x/5.x, пакет `jsonschema`. NumPy уже входит в Blender.

```powershell
python -m pip install -r requirements.txt
python assetgen.py new barrel barrel_01
python assetgen.py validate barrel_01
python assetgen.py model barrel_01
python assetgen.py validate-texture barrel_01
python assetgen.py texture barrel_01
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
- `report.json` и `report_texture.json`.

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

Чтобы автоматически копировать GLB и albedo (без превью), укажи в `assetgen.config.json` относительный или абсолютный путь:

```json
"godot_assets": "../my_game/assets/props"
```

Пустая строка отключает копирование. Категория из спеки становится подпапкой.

Фильтрация уже записана в GLB samplers: `pixel: false` экспортирует linear filtering, `pixel: true` — nearest with mipmaps. Post-import для выбора фильтрации не нужен. `godot/post_import_pixel.gd` оставлен только как legacy/retro-only override: он принудительно делает все материалы nearest, поэтому не назначай его мягким ассетам. Если старый import preset уже назначен, сними его и переимпортируй GLB. Замена внешнего PNG не обновляет текстуру, встроенную в GLB, — пересобери и переимпортируй ассет.

В `<asset>_godot.glb` тип `collision` определяет коллайдер: `mesh` копирует видимые треугольники через `-colonly`, `convex` создаёт выпуклую оболочку через `-convcolonly`, `box` использует ограничивающий куб, `none` отключает коллизию. Используй в игре Godot-вариант: обычные просмотрщики не знают эти суффиксы и отображают collision-меши как геометрию.

## DSL модели

Примитивы: `box`, `cylinder`, `sphere`, `lathe`, `extrude`. Общие операции: `scale`, `rotation`, `location`, `bevel`, `jitter`, `array`, `mirror_x`. Полная строгая схема — `schemas/model.schema.json`.

`uv_projection: "cylindrical"` применяет к детали `lathe` боковую полосу и две плоские крышки. Профиль идёт снизу вверх, начинается и заканчивается на оси и имеет плоские торцы, как у корпуса `barrel_01`. Smart UV разворачивает остальные детали, затем сборщик пакует все острова в общий атлас.

Шаблоны: `barrel`, `door`, `coffin`, `bone`, `chest`, `skull`, `candle`, `torch`, `pillar`, `urn`, `table`, `cell_bars`.

Правила для агента и рекомендации по размерам находятся в `.claude/skills/assetgen/SKILL.md`. Обычный authoring меняет только JSON; сопровождение генератора выполняется как отдельная явно запрошенная задача с обновлением схемы, тестов и документации.

## Текстуры

Полная схема — `schemas/texture.schema.json`. Проверка спеки не требует модели или Blender:

```powershell
python assetgen.py validate-texture pillar
```

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
python tests/verify_outputs.py
& $env:BLENDER -b --factory-startup --python-exit-code 1 -P tests/verify_texture_pipeline.py -- $PWD
& $env:BLENDER -b --factory-startup --python-exit-code 1 -P tests/verify_texture_colors.py -- $PWD
& $env:BLENDER -b out/interiors/pillar/pillar.blend --python-exit-code 1 -P tests/verify_determinism.py -- $PWD pillar
```

Если `BLENDER` не задана, укажи полный путь к `blender.exe`.

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
