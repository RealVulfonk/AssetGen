---
name: assetgen
description: Generate low-poly dungeon models and textures for Godot through this project's JSON DSL and Blender CLI. Use when the user asks to create or change an asset, prop, GLB, texture, material, pivot, or collision in this repository.
---

# Skill: AssetGen (low-poly dungeon props)

До работы со спекой создай или открой карточку задачи по [правилам репозитория](../../../AGENTS.md). Здесь описаны операции над ассетом.

## Работа со спекой

1. Для отдельного пропа описывай геометрию и текстуру в JSON в `specs/`. Изменения генератора и DSL выполняй в рамках задачи на их сопровождение.
2. Цвета текстур — ТОЛЬКО имена палитр из `presets/palettes.json` или явный список hex, если пользователь его дал.
3. Для нового пропа выбери свободное имя и выполни `python assetgen.py new <template> <name>`. Для правки существующего открой его спеку. Для флоры используй генератор семейств ниже.
   Ближайший шаблон: бочка/ваза/кубок → `barrel` или `urn` (lathe);
   дверь/ящик/стол/полка → `door`, `chest`, `table` (box);
   гроб/надгробие/щит → `coffin` (extrude); кость/факел/палка → `bone` или `torch`.
4. Между сборками сверь отчёт и превью с критерием карточки. Повторяй сборку после конкретной правки. Если выбор между художественными вариантами требует решения автора, сохрани ракурсы для сравнения и сформулируй вопрос.
5. Имена: snake_case + номер для вариантов: `barrel_01`, `coffin_stone_02`.
6. Не добавляй поля, которых нет в схеме. Назначение части записывай в `comment`.

## СТИЛЬ
- Low-poly, плоские грани. segments: 6–8 мелочь, 8–12 крупные круглые формы.
- Бюджет треугольников: мелочь 50–200, проп 200–600, крупное 600–1200.
  Для флоры из `tools/gen_flora.py` бюджеты выше: дерево 1000–2400, подлесок 200–900.
- Bevel только у box/extrude, width 0.005–0.02, segments 1.
- jitter 0.002–0.008 у дерева и камня; 0 у металла.
- Детали (обручи, полосы) выступают из основы на 0.005–0.02 м.

## ФЛОРА
Деревья, сухостой, кусты и подлесок генерируются скриптом, а не пишутся руками:
`python tools/gen_flora.py --family conifer --count 8 --seed 42`. Скрипт пишет
пару `specs/models/<name>.json` + `specs/textures/<name>.json`, дальше обычный
`validate` / `model` / `texture`. Семейства и счётчики — `--list`.

Правь параметры формы в `tools/gen_flora.py` (диапазоны высот, ярусов, развала),
а не числа в сгенерированных JSON: следующая генерация их перезапишет.

## РЕАЛЬНЫЕ РАЗМЕРЫ (метры, X×Y×Z)
дверь 1.0×0.1×2.0 | бочка Ø0.6×0.9 | сундук 0.8×0.5×0.55 | гроб 0.65×1.95×0.5
череп 0.15×0.2×0.18 | бедренная кость 0.45 длина | свеча Ø0.04×0.15 | факел 0.5

## СОГЛАШЕНИЯ DSL
- Метры, Z вверх. glTF-экспортёр сам переводит координаты в Y-up для Godot.
- `box`, `cylinder`, `sphere` центрированы; `lathe`, `extrude` начинаются от z=0.
- Порядок: создание → scale → bevel → jitter → rotate → translate → mirror.
- `array.offset` задаёт шаг в метрах; `mirror_x` отражает часть вместе с её положением.
- `cutouts` вычитает резцы `box` и `cylinder` из замкнутой части после scale/bevel/jitter, до поворота и смещения. Резец пересекает наружную поверхность, материал стенок наследуется от части. Пример — `skull_01`.
- `uv_projection: "cylindrical"` даёт детали `lathe` непрерывную боковую полосу и две плоские крышки. Подходит для восходящего профиля с плоскими торцами, как корпус `barrel_01`.
- `pivot`: `bottom_center` для предметов на полу, `hinge_left` для дверей, `center` для свободно вращающихся объектов.
- `collision`: `mesh` повторяет видимую геометрию для статичных предметов; `convex` создаёт выпуклую оболочку; `box` — дешёвый куб; `none` — без коллизии.
- Теги материалов связывают модель и текстуру: `wood`, `metal`, `bone`, `stone`, `cloth`, `gold`.
- Для стекла используй одну `plane` с простым контуром `points` в локальной XY. Поверни её в плоскость проёма. Назначь отдельные теги `frame` и `glass`, чтобы при обработке MoonProject они поместились в два слота.

## ПРОЦЕСС: МОДЕЛЬ
1. Открой спеку модели или создай её по правилам выше.
2. Продумай части. Каждой части дай `comment` и `material`.
3. Заполни `expected_size`, `tri_budget`, `pivot` и при необходимости `collision`.
4. `python assetgen.py validate <name>` → исправляй, пока не будет OK.
5. Для локальной сборки выполни `python assetgen.py model <name> --no-copy`.
6. Прочитай `out/<group>/<name>/report.json`: status, warnings, tris, dimensions.
   Группа (`interiors` / `exteriors` / `environment`) выводится из `category`
   спеки; точный путь даёт `python tools/outdir.py <name>`.
   Посмотри `preview_front/side/iso/top.png`.
7. Если WARN или силуэт неверный → поправь ЧИСЛА в JSON → шаг 5.
8. Ответ пользователю: путь к .glb, превью, tris, размеры, список материалов.

## ПРОЦЕСС: ТЕКСТУРА
1. Возьми список materials из `report.json` модели.
2. Создай `specs/textures/<name>.json`. Каждому тегу назначь preset + palette; добавь `default`.
   - wood → `wood` (direction X — вертикальные волокна, Z — горизонтальные);
   - клёпаный корпус вокруг Z → `coopered_wood` (число клёпок, ширина стыка, ширина досок крышки и выраженность волокон);
   - stone → `stone`;
   - metal/bone/cloth → `noise`/`metal`/`bone`/`cloth`;
   - маленькое однотонное → `flat`.
3. Для обычного мягкого стиля используй `_soft`-палитру и НЕ пиши `pixel`, `quantize`, `gradient`: defaults уже `false/false/ease`.
   Для ретро задай явно `pixel: true`, `quantize: true` и `gradient: constant` у материалов; исходные палитры сохранены.
4. size: мелочь 64, проп 128, крупное 256. По умолчанию samples 64, margin 4. Для `pack_uv: true` поле по умолчанию равно 1, 2 или 4 px соответственно. Для проверки упаковки используй `tools/inspect_uv.py`.
5. `python assetgen.py validate-texture <name>` → исправь спеку до запуска Blender.
6. `python assetgen.py texture <name> --no-copy` → смотри превью и `report_texture.json`.
7. Слишком пёстро → уменьши contrast или сузь палитру. Contrast работает вокруг `contrast_pivot` (0.5).
   AO и edge применяются поверх цвета: для мягкого стиля начинай с ao 0.2–0.35, edge 0.05–0.15.
8. Собственные `layers` используй только если пресет не даёт нужного рисунка. Не сочетай их с `preset` и preset-only полями.

В примере рама использует непрозрачный материал, а стекло получает собственную альфу.

```json
"materials": {
  "frame": {"preset": "wood", "palette": "wood_dark_soft"},
  "glass": {"preset": "flat", "palette": "glass_blue", "value": 0.6, "opacity": 0.35, "roughness": 0.24}
}
```

`opacity` от `0` до `1` задаёт альфу всего материала, по умолчанию `1`. Значение меньше `1` делает материал двусторонним. `roughness` от `0` до `1` задаёт шероховатость, по умолчанию `0.9`. Собери модель через `python assetgen.py model window_glass_01 --no-copy`, затем запеки текстуру через `python assetgen.py texture window_glass_01 --no-copy --lighting-preview`. Для проверки импорта и съёмки через стекло используй `tests/verify_glass_import.gd` по команде из README.

## ТИПИЧНЫЕ ОШИБКИ
- box центрирован: чтобы стоял на полу, `location.z = size.z / 2`.
- cylinder центрирован по высоте; lathe и extrude начинаются от z=0.
- Повёрнутый cylinder: `rotation: [0,90,0]` кладёт его вдоль X.
- Профиль lathe начинай и заканчивай `r=0`, если не нужен открытый сосуд с явно описанной внутренней стенкой.
- Точки extrude — простой многоугольник без самопересечений.
- Сначала собери модель, потом запускай текстуру: bake загружает `out/<group>/<name>/<name>.blend`.
