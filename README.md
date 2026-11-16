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

Путь к Blender задаётся в `assetgen.config.json`; переменная окружения `BLENDER` имеет приоритет. Результаты появляются в `out/<asset>/`:

- `<asset>.blend` — модель с цветовыми материалами;
- `<asset>.glb` — видимая модель без collision-меша;
- `<asset>_godot.glb` — вариант с `-colonly` для Godot, если включена коллизия;
- `<asset>_tex.blend` и `<asset>_albedo.png` — после запекания;
- `preview_front.png`, `preview_side.png`, `preview_iso.png`, `preview_top.png`;
- `report.json` и `report_texture.json`.

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

## Проверка собранных ассетов

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/verify_outputs.py
& $env:BLENDER -b --factory-startup --python-exit-code 1 -P tests/verify_texture_pipeline.py -- $PWD
& $env:BLENDER -b --factory-startup --python-exit-code 1 -P tests/verify_texture_colors.py -- $PWD
& $env:BLENDER -b out/pillar/pillar.blend --python-exit-code 1 -P tests/verify_determinism.py -- $PWD pillar
```

Если `BLENDER` не задана, укажи полный путь к `blender.exe`.

- `test_texture_schema.py` проверяет спеки, палитры и custom layers.
- `verify_outputs.py` разбирает GLB, отчёты, превью, коллизии, embedded textures и samplers.
- `verify_texture_pipeline.py` проверяет рецепты, математику слоёв, contrast, цветовое пространство, quantization и filtering.
- `verify_texture_colors.py` проверяет все текстурные спеки: quantized PNG — по палитре, soft PNG — по валидности и промежуточным цветам.
- `verify_determinism.py` запекает ассет дважды из исходного `.blend` и сравнивает пиксели и настройки.

Дополнительно смотри albedo и все превью: автоматические тесты не обнаруживают нежелательный художественный стиль, локальные UV-швы и слабый island bleed.

## Отладка

CLI запускает Blender с `--python-exit-code 1` и дополнительно считает наличие `Traceback` ошибкой. При сбое выводятся последние 40 строк журнала. Не убирай эти проверки: Blender иначе может вернуть код 0 после исключения Python.

Для живой отладки в открытом Blender можно выполнить:

```python
import sys
sys.argv = ["blender", "--", "C:/absolute/path/specs/models/barrel_01.json", "C:/absolute/path/out/barrel_01"]
exec(open("C:/absolute/path/blender/build_model.py", encoding="utf-8").read())
```

`build_model.py` начинает с `read_factory_settings(use_empty=True)` и очищает открытую сцену. Обычная сборка всегда идёт через CLI для воспроизводимости. После повторной сборки модели текстуру нужно запечь заново: `model` перезаписывает обычный GLB без текстуры.
