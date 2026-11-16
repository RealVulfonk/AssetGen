# AssetGen для Godot

JSON-driven генератор low-poly ассетов в стиле Neverlooted Dungeon. Агент описывает модель и текстуру в JSON; проверенные Blender-скрипты строят геометрию, UV, коллизию, запекают albedo и экспортируют GLB.

## Быстрый старт

Требования: Python 3.10+, Blender 4.x/5.x, пакет `jsonschema`. NumPy уже входит в Blender.

```powershell
python -m pip install -r requirements.txt
python assetgen.py new barrel barrel_01
python assetgen.py validate barrel_01
python assetgen.py model barrel_01
python assetgen.py texture barrel_01
```

Путь к Blender задаётся в `assetgen.config.json`; переменная окружения `BLENDER` имеет приоритет. Результаты появляются в `out/<asset>/`:

- `<asset>.blend` — модель с цветовыми материалами;
- `<asset>.glb` — обычная видимая модель без collision-меша, для F3D и других просмотрщиков;
- `<asset>_godot.glb` — вариант с `-colonly` для Godot, если в спеке включена коллизия;
- `<asset>_tex.blend` и `<asset>_albedo.png` — после запекания;
- `preview_front.png`, `preview_side.png`, `preview_iso.png`, `preview_top.png`;
- `report.json` и `report_texture.json`.

## Godot

Чтобы автоматически копировать GLB и albedo (без превью), укажи в `assetgen.config.json` относительный или абсолютный путь:

```json
"godot_assets": "../my_game/assets/props"
```

Пустая строка отключает копирование. Категория из спеки становится подпапкой. Для пиксельной фильтрации назначь `godot/post_import_pixel.gd` как Editor Scene Post Import для GLB в Import dock, желательно пресетом для папки ассетов. Для мягкой фильтрации пост-импорт не нужен.

В `<asset>_godot.glb` тип `collision` определяет коллайдер: `mesh` копирует видимые треугольники через `-colonly` (точное совпадение для статичных предметов), `convex` создаёт выпуклую оболочку через `-convcolonly`, `box` использует простой ограничивающий куб, `none` отключает коллизию. Используй в игре Godot-вариант: обычные просмотрщики не знают эти суффиксы и отображают collision-меши как геометрию. В `.blend` collision-меш невидим на рендерах и не влияет на превью.

## DSL

Примитивы: `box`, `cylinder`, `sphere`, `lathe`, `extrude`. Общие операции: `scale`, `rotation`, `location`, `bevel`, `jitter`, `array`, `mirror_x`. Полная строгая схема — `schemas/model.schema.json`; параметры текстур — `schemas/texture.schema.json`.

Шаблоны: `barrel`, `door`, `coffin`, `bone`, `chest`, `skull`, `candle`, `torch`, `pillar`, `urn`, `table`, `cell_bars`.

Правила для агента и рекомендации по размерам находятся в проектном Skill `.claude/skills/assetgen/SKILL.md`. Он вызывается командой `/assetgen` или автоматически для подходящих задач генерации ассетов.

## Проверка собранных ассетов

После сборки примеров:

```powershell
python tests/verify_outputs.py
& $env:BLENDER -b --factory-startup --python-exit-code 1 -P tests/verify_texture_colors.py -- $PWD barrel_01 coffin door pillar
```

Если переменная `BLENDER` не задана, во второй команде укажи полный путь к `blender.exe`. Первая проверка разбирает GLB, отчёты, превью, коллизии и embedded textures; вторая подтверждает, что все пиксели PNG принадлежат назначенным палитрам.

## Отладка

CLI запускает Blender с `--python-exit-code 1` и дополнительно считает наличие `Traceback` ошибкой. При сбое выводятся последние 40 строк журнала. Не убирай эти проверки: Blender иначе может вернуть код 0 после исключения Python.

Для живой отладки в открытом Blender можно выполнить:

```python
import sys
sys.argv = ["blender", "--", "C:/absolute/path/specs/models/barrel_01.json", "C:/absolute/path/out/barrel_01"]
exec(open("C:/absolute/path/blender/build_model.py", encoding="utf-8").read())
```

`build_model.py` начинает с `read_factory_settings(use_empty=True)` и очищает открытую сцену. Обычная сборка всегда идёт через CLI для воспроизводимости.
