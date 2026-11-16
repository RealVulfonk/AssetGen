---
name: assetgen
description: Generate low-poly dungeon models and textures for Godot through this project's JSON DSL and Blender CLI. Use when the user asks to create or change an asset, prop, GLB, texture, material, pivot, or collision in this repository.
---

# Skill: AssetGen (low-poly dungeon props)

## ЖЕЛЕЗНЫЕ ПРАВИЛА
1. При обычном создании ассетов НЕ меняй код в `blender/`, схемы и тесты — меняй ТОЛЬКО JSON в `specs/`.
   Исключение — явно запрошенное сопровождение генератора/DSL: тогда можно менять `assetgen.py`, `blender/*.py`, схемы, пресеты, тесты и документацию, обновляя их согласованно. Никогда не меняй bpy/Python просто ради настройки отдельного ассета.
2. Цвета текстур — ТОЛЬКО имена палитр из `presets/palettes.json` или явный список hex, если пользователь его дал.
3. Всегда начинай с шаблона: `python assetgen.py new <template> <name>`.
   Ближайший шаблон: бочка/ваза/кубок → `barrel` или `urn` (lathe);
   дверь/ящик/стол/полка → `door`, `chest`, `table` (box);
   гроб/надгробие/щит → `coffin` (extrude); кость/факел/палка → `bone` или `torch`.
4. Максимум 3 итерации сборки. Потом покажи результат пользователю и спроси.
5. Имена: snake_case + номер для вариантов: `barrel_01`, `coffin_stone_02`.
6. Не добавляй поля, которых нет в схеме. Назначение части записывай в `comment`.

## СТИЛЬ
- Low-poly, плоские грани. segments: 6–8 мелочь, 8–12 крупные круглые формы.
- Бюджет треугольников: мелочь 50–200, проп 200–600, крупное 600–1200.
- Bevel только у box/extrude, width 0.005–0.02, segments 1.
- jitter 0.002–0.008 у дерева и камня; 0 у металла.
- Детали (обручи, полосы) выступают из основы на 0.005–0.02 м.

## РЕАЛЬНЫЕ РАЗМЕРЫ (метры, X×Y×Z)
дверь 1.0×0.1×2.0 | бочка Ø0.6×0.9 | сундук 0.8×0.5×0.55 | гроб 0.65×1.95×0.5
череп 0.15×0.2×0.18 | бедренная кость 0.45 длина | свеча Ø0.04×0.15 | факел 0.5

## СОГЛАШЕНИЯ DSL
- Метры, Z вверх. glTF-экспортёр сам переводит координаты в Y-up для Godot.
- `box`, `cylinder`, `sphere` центрированы; `lathe`, `extrude` начинаются от z=0.
- Порядок: создание → scale → bevel → jitter → rotate → translate → mirror.
- `array.offset` задаёт шаг в метрах; `mirror_x` отражает часть вместе с её положением.
- `pivot`: `bottom_center` для предметов на полу, `hinge_left` для дверей, `center` для свободно вращающихся объектов.
- `collision`: `mesh` повторяет видимую геометрию для статичных предметов; `convex` создаёт выпуклую оболочку; `box` — дешёвый куб; `none` — без коллизии.
- Теги материалов связывают модель и текстуру: `wood`, `metal`, `bone`, `stone`, `cloth`, `gold`.

## ПРОЦЕСС: МОДЕЛЬ
1. Выбери шаблон, создай спеку командой `new`.
2. Продумай части. Каждой части дай `comment` и `material`.
3. Заполни `expected_size`, `tri_budget`, `pivot` и при необходимости `collision`.
4. `python assetgen.py validate <name>` → исправляй, пока не будет OK.
5. `python assetgen.py model <name>`.
6. Прочитай `out/<name>/report.json`: status, warnings, tris, dimensions.
   Посмотри `preview_front/side/iso/top.png`.
7. Если WARN или силуэт неверный → поправь ЧИСЛА в JSON → шаг 5.
8. Ответ пользователю: путь к .glb, превью, tris, размеры, список материалов.

## ПРОЦЕСС: ТЕКСТУРА
1. Возьми список materials из `report.json` модели.
2. Создай `specs/textures/<name>.json`. Каждому тегу назначь preset + palette; добавь `default`.
   - wood → `wood` (direction X — вертикальные волокна, Z — горизонтальные);
   - stone → `stone`;
   - metal/bone/cloth → `noise`/`metal`/`bone`/`cloth`;
   - маленькое однотонное → `flat`.
3. Для обычного мягкого стиля используй `_soft`-палитру и НЕ пиши `pixel`, `quantize`, `gradient`: defaults уже `false/false/ease`.
   Для ретро задай явно `pixel: true`, `quantize: true` и `gradient: constant` у материалов; исходные палитры сохранены.
4. size: мелочь 64, проп 128, крупное 256. По умолчанию samples 64, margin 4.
5. `python assetgen.py validate-texture <name>` → исправь спеку до запуска Blender.
6. `python assetgen.py texture <name>` → смотри превью и `report_texture.json`.
7. Слишком пёстро → уменьши contrast или сузь палитру. Contrast работает вокруг `contrast_pivot` (0.5).
   AO и edge применяются поверх цвета: для мягкого стиля начинай с ao 0.2–0.35, edge 0.05–0.15.
8. Собственные `layers` используй только если пресет не даёт нужного рисунка. Не сочетай их с `preset` и preset-only полями.

## ТИПИЧНЫЕ ОШИБКИ
- box центрирован: чтобы стоял на полу, `location.z = size.z / 2`.
- cylinder центрирован по высоте; lathe и extrude начинаются от z=0.
- Повёрнутый cylinder: `rotation: [0,90,0]` кладёт его вдоль X.
- Профиль lathe начинай и заканчивай `r=0`, если не нужен открытый сосуд с явно описанной внутренней стенкой.
- Точки extrude — простой многоугольник без самопересечений.
- Сначала собери модель, потом запускай текстуру: bake загружает `out/<name>/<name>.blend`.
