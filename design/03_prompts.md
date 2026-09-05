# Библиотека промптов

Каждый промпт = **стиль-блок из `02-style-block.md`** + блок ниже.
Стиль-блок вставляется дословно и целиком, каждый раз. Без него Stitch
нарисует шестой экран в другой палитре, и это будет видно на защите.

Промпты на английском, подписи интерфейса — русские строки в кавычках.
Все строки должны совпадать с `05-copy-ru.md`.

---

## S-01 · Пустое состояние: поиск региона

```
SCREEN: main working screen, empty state — nothing selected yet.

Top bar, 56px: product name "VegaWatch" on the left in 15px semibold.
In the center, a search input 420px wide with a magnifier icon and
placeholder "Регион, район или населённый пункт". On the right, a
compact status pill with a green dot and the label "Источники: 6 из 6".

Left sidebar, 320px, card background, hairline right border:
- heading "Мои полигоны" 18px semibold
- two buttons stacked, full width, 8px gap:
  primary blue button "Нарисовать полигон" with a polygon icon,
  secondary outlined button "Найти поля в регионе" with a search icon
- below them, an empty state: a small muted line-art placeholder,
  the text "Пока ничего не выбрано" in 14px secondary, and below it
  "Найдите регион в поиске сверху, затем выберите поле на карте
  или нарисуйте свой контур" in 13px muted, max 2 lines.

Main area: a map placeholder filling the whole area — a flat light gray
rectangle (#f0efec) with a subtle 40px grid of hairlines, NO fake terrain,
NO fake satellite imagery, NO invented city labels. In the bottom right
corner of the map, a small attribution line in 12px muted:
"© OpenStreetMap contributors". In the bottom left, two small square
zoom buttons "+" and "−".

Nothing else. No charts, no panels below the map — the map fills the area.
```

---

## S-02 · Найденные сельхозконтуры

```
SCREEN: main working screen after the user searched a region and pressed
"Найти поля в регионе".

Same top bar as before. The search input now contains the text
"Ставропольский край" and below it, attached, a thin result row
"Ставропольский край, Россия" in 13px secondary.

Left sidebar:
- heading "Мои полигоны" with a counter chip "0"
- the same two buttons
- a divider
- a section heading "Найдено контуров: 47" 15px semibold
- a scrollable list of 6 visible result cards. Each card: 12px padding,
  hairline border, 8px radius, 8px gap between cards. Inside a card:
  title "Контур OSM way/123456" 14px primary on one line, below it a row
  of two small muted labels "128,4 га" and "farmland" separated by a dot.
  On the right edge of the card, a small ghost icon button with a plus.
  One card in the middle is in the selected state: 1.5px #2a78d6 border
  and #cde2fb background tint.
- pinned at the bottom of the sidebar, a full width secondary button
  "Импортировать все найденные"

Main area: the same flat gray map placeholder, but now with about 20
irregular polygon outlines scattered over it — thin #2a78d6 strokes with
a very light #cde2fb fill at low opacity. One polygon is selected: thicker
2px stroke, stronger fill. Next to the selected polygon, a small popover
card, 240px wide: title "Контур OSM way/123456", two rows of label and
value — "Площадь" / "128,4 га" and "Тип" / "Пашня" — and two buttons at
the bottom: primary "Анализировать" and ghost "Сохранить".

Keep the map abstract: gray background, grid hairlines, polygon outlines.
No satellite imagery, no roads, no place names.
```

---

## S-03 · Результат анализа (главный экран)

> **Experimental mode.** Это тот экран, который попадёт на титульный слайд,
> в README и в отчёт. На него не жалко потратить 8–10 генераций.

```
SCREEN: main working screen showing a completed analysis. This is the
primary screen of the product — the densest and most important one.

Top bar as before, search shows "Ставропольский край".

Left sidebar, 320px:
- heading "Мои полигоны" with counter chip "3"
- the two action buttons
- a list of three polygon cards. Each: name in 14px primary
  ("Поле №3 у Аксая", "Северное", "Контур OSM way/123456"), a second line
  in 13px muted with area and crop ("96,2 га · озимая пшеница"), and on the
  right a small colored status dot with a label. Card 1 is SELECTED
  (#2a78d6 border, #cde2fb tint) and has a red dot with the label
  "Критично". Card 2 has a green dot "Норма". Card 3 an amber dot
  "Угнетение".

Main area, three stacked blocks separated by 12px gaps:

BLOCK 1 — MAP, about 45% of the height. Flat gray placeholder with grid
hairlines, one selected field polygon drawn with a 2px #2a78d6 stroke and
light fill, a few neighbouring polygons in thin gray strokes.
Top right of the map: a small floating card 200px wide with the field name
"Поле №3 у Аксая", the area "96,2 га" and the period "апр — окт 2025".
Bottom right: "© OpenStreetMap contributors" in 12px muted.

BLOCK 2 — CHART CARD, height about 300px, card background, 16px padding.
Header row: title "Динамика NDVI" 18px semibold on the left; on the right,
a segmented control with three options "2025", "3 года", "Всё" (the first
selected) and a small ghost icon button for download.
Below it, a chart plot area. Draw it as a REALISTIC BUT SCHEMATIC time
series, not a decorative wave:
 - Y axis from 0.0 to 1.0 with ticks 0.0 0.2 0.4 0.6 0.8 1.0 in 12px muted
 - X axis with month labels "апр" "май" "июн" "июл" "авг" "сен" "окт"
 - a light gray band (#f0efec) running across as the climatology corridor
 - a thin dashed gray line inside the band as the climatology mean
 - the main data: a #2a78d6 line 2px, rising from ~0.25 in April to a peak
   ~0.75 in June, dipping visibly to ~0.35 in mid July, partially recovering
   to ~0.5 by September
 - about 14 point markers on that line in three shapes: circles filled
   #2a78d6, squares filled #eb6834, triangles filled #1baf7a, each with a
   2px white ring
 - two vertical translucent bands behind the line: an amber one
   (#fab219 at ~14% opacity) over mid May, a red one (#d03b3b at ~14%
   opacity) over the July dip
 - segments of the line between distant markers drawn DASHED instead of
   solid, to mark reconstructed values
Legend row under the plot, horizontal, 12px, each item an icon plus a
label: circle "Sentinel-2", square "Landsat", triangle "MODIS",
a short solid line "Наблюдения", a short dashed line "Восстановлено",
a gray line "Климатическая норма", an amber swatch "Угнетение",
a red swatch "Критическая аномалия".

BLOCK 3 — ANOMALY FEED, height about 180px, card background, 16px padding,
internally scrollable. Header "Аномальные периоды" 18px semibold with a
counter chip "2" next to it. Below, two anomaly cards stacked, 8px gap.
Each anomaly card: a 4px colored left bar, 12px padding, hairline border.
Card 1 (critical, red bar #d03b3b): a row with a red circular warning icon,
the title "8 — 29 июля · 22 дня" 15px semibold, and on the right two small
chips "−2,3σ" and "Засуха". Second line, 13px secondary, two lines max:
"За 30 дней 4 мм осадков при норме 48 мм, температура на 3,6 °C выше нормы.
Соседние поля просели в среднем на 0,9σ."
Card 2 (moderate, amber bar #fab219): amber triangle icon, title
"12 — 24 мая · 13 дней", chips "−1,4σ" and "Локальная", description
"Соседние поля в норме, погода без отклонений. Снижение локализовано
на этом поле."

Everything must fit 1440x900 without scrolling the outer layout.
```

---

## S-04 · Сбор данных идёт

> **Experimental mode.** Экран, который доказывает автосбор данных.

```
SCREEN: main working screen while the service is collecting data for a
newly selected field. The map is visible but dimmed; a progress panel is
the focus.

Top bar and left sidebar as in the previous screen. The selected polygon
card in the sidebar shows a small spinner dot and the label "Обработка".

Main area: the map placeholder at the top at 60% opacity, and over the
lower two thirds a large progress card, full width, card background,
20px padding, 8px radius.

Progress card content:
- header row: title "Сбор данных" 18px semibold on the left; on the right,
  muted 13px text "18 из 86 сцен"
- a thin 4px progress bar, #cde2fb track, #2a78d6 fill at about 42%
- below it, a vertical list of 9 stage rows, 32px tall each, separated by
  hairlines. Each row has three parts: a 16px status icon on the left,
  the stage name in 14px, and a right-aligned 13px muted result.
  Rows and their states:
    green check  "Поиск сцен Sentinel-2"      → "43 сцены · 0,9 с"
    green check  "Поиск сцен Landsat"          → "31 сцена · 1,4 с"
    green check  "Поиск сцен MODIS"            → "12 композитов · 0,4 с"
    blue spinner "Чтение растров"              → "18 / 86"
    gray dot     "Маскирование облаков"        → "—"
    gray dot     "Агрегация по полигону"       → "—"
    gray dot     "Загрузка погоды"             → "—"
    gray dot     "Климатическая норма"         → "—"
    gray dot     "Восстановление пропусков"    → "—"
  Completed rows have primary text; the running row has primary text and a
  #2a78d6 spinner; pending rows have muted text.
- at the bottom, a ghost button "Отменить" aligned left.

The stage names must be exactly the Russian strings above.
```

---

## S-05 · Рисование полигона

```
SCREEN: main working screen while the user is drawing a polygon by hand.

Top bar as before. Left sidebar shows the heading "Мои полигоны", and
below it an active drawing panel instead of the usual list:
- heading "Новый полигон" 15px semibold
- a text input labeled "Название" containing "Поле у реки"
- a select labeled "Культура" showing "Озимая пшеница"
- a muted 13px row "Площадь: 64,8 га · 6 вершин"
- a hint block on #f0efec background, 12px padding, 13px muted text:
  "Кликайте по карте, чтобы добавить вершины. Двойной клик завершает
  контур. Esc отменяет, Backspace убирает последнюю вершину."
- two buttons at the bottom: primary "Сохранить полигон" and ghost
  "Отменить"

Main area: the flat gray map placeholder. In the middle, a polygon being
drawn: five placed vertices as 8px white circles with 2px #2a78d6 borders,
connected by a 2px solid #2a78d6 line, and a dashed line from the last
vertex to the cursor position closing back to the first vertex. The
interior has a very light #cde2fb fill. Next to the cursor, a small dark
tooltip chip with white 12px text "64,8 га".

No satellite imagery. Map stays abstract gray with grid hairlines.
```

---

## S-06 · Раскрытая карточка аномалии

> **Experimental mode.** Этот экран — весь ответ на критерий «качество
> интерпретации и объяснения причин».

```
SCREEN: the anomaly feed with one card expanded into a detail view.
Show only the chart block and the anomaly block — the map is cropped out
at the top, we are looking at the lower two thirds of the working area.

Top: the bottom edge of the NDVI chart card, with the July region zoomed:
X axis showing "1 июл" "8 июл" "15 июл" "22 июл" "29 июл", a #2a78d6 line
dipping from 0.62 down to 0.31 and slowly recovering, a light gray
climatology band well above the line, and a translucent red band
(#d03b3b at 14%) covering 8—29 июля.

Below it, a full width expanded anomaly card, card background, 20px
padding, 4px red left bar:
- header row: red circular warning icon, title "Критическая аномалия"
  18px semibold, and on the right a ghost icon button with a chevron up
- a subtitle row 14px secondary: "8 — 29 июля 2025 · 22 дня · минимум −2,3σ"
- a row of four KPI tiles, equal width, 12px gap, each on #f0efec
  background with 12px padding and 6px radius. Each tile has a 12px muted
  label on top and a 24px semibold value below:
    "Осадки за 30 дней" / "4 мм"      with a 12px muted sub-line "норма 48 мм"
    "Температура" / "+3,6 °C"          sub-line "к норме"
    "Дней без осадков" / "19"          sub-line "подряд"
    "Соседние поля" / "−0,9σ"          sub-line "12 полей района"
- a section heading "Интерпретация" 15px semibold
- a paragraph, 14px secondary, max 4 lines:
  "С 8 по 29 июля NDVI держался ниже климатической нормы, минимум −2,3σ
  (0,31 при норме 0,58). За предыдущие 30 дней выпало 4 мм осадков при
  норме 48 мм. Соседние поля района просели в среднем на 0,9σ — угнетение
  шире одного поля, что характерно для почвенной засухи."
- a section heading "Доказательства" 15px semibold, and under it a compact
  two column key-value list, 13px, six rows:
    "Осадки, 30 дней" / "4,0 мм (норма 48,0)"
    "Аномалия температуры" / "+3,6 °C"
    "Средний z соседей" / "−0,91"
    "Число соседей" / "12"
    "Сенсоры согласованы" / "Да"
    "Наблюдений в периоде" / "6 из 22 дней"
- at the bottom, two ghost buttons: "Экспорт CSV" and "Показать на карте"
```

---

## Состояния

Состояния делаются из готового экрана уточняющим промптом. Дешевле полной
генерации и гарантирует, что композиция совпадёт.

### ST-02 · Загрузка

```
Same screen, loading state. Replace the chart plot area and the anomaly
cards with skeleton placeholders: rounded #f0efec rectangles matching the
real content blocks in size and position. Keep the headings and the
segmented control visible and enabled. No spinners in the content area,
skeletons only.
```

### ST-03 · Нет данных

```
Same screen, empty result state. Replace the chart plot area with a
centered empty state: a small muted line-art icon, the heading
"Нет пригодных наблюдений" 15px semibold, the text "За выбранный период
не нашлось снимков без облачности. Попробуйте расширить диапазон дат."
13px muted on two lines, and a secondary button "Расширить период"
under it. The anomaly block shows "Аномалии не найдены" in 14px muted,
centered.
```

### ST-04 · Часть источников недоступна

```
Same screen with a warning banner. Above the chart card, add a full width
notice strip: #fab219 left bar 4px, very light amber background, 12px
padding, an amber triangle icon, the text "Sentinel-2 недоступен, ряд
построен по Landsat и MODIS" in 14px primary, and a ghost button
"Подробнее" on the right. The status pill in the top bar changes to an
amber dot with the label "Источники: 4 из 6".
```

### ST-05 · Мало истории

```
Same screen without climatology. Remove the gray corridor band and the
dashed climatology line from the chart. Add a notice strip above the chart:
neutral gray style, an info icon, the text "Недостаточно истории для
климатической нормы: доступно 2 сезона из 3 необходимых. Показан
упрощённый анализ." Remove the sigma chips from the anomaly cards and
replace them with the chip "Без нормы".
```

### ST-06 · Низкое покрытие

```
Same screen with a reliability warning. Under the chart title, add an
inline chip on light orange background with an icon and the text
"Покрытие 4% · результаты ненадёжны". Reduce the number of point markers
on the chart to four, and make most of the line dashed to show that almost
everything is reconstructed.
```

### ST-07 · Контуры не найдены

```
Same as S-02 but with no results. The sidebar section shows the heading
"Контуры не найдены" and an empty state: muted icon, the text "В этом
районе OpenStreetMap не содержит размеченных сельхозконтуров." 13px muted,
and a primary button "Нарисовать полигон" below it. The map has no polygon
outlines.
```

### ST-08 · Ошибка геометрии

```
Same as S-05 but the drawn polygon self-intersects: the outline crosses
itself and the crossing segments are drawn in #d03b3b. Under the input
fields in the sidebar, add an error block: red left bar, very light red
background, an error icon and the text "Контур пересекает сам себя —
перерисуйте его без самопересечений" in 13px. The "Сохранить полигон"
button is in the disabled state.
```

---

## Дополнительные экраны

### S-07 · Сравнение полей

```
SCREEN: the chart card only, in comparison mode. Header "Сравнение полей"
with three removable chips: "Поле №3 у Аксая", "Северное",
"Контур OSM way/123456", each chip with a small colored dot and an x.
The plot shows three lines without markers — #2a78d6, #eb6834, #1baf7a —
following similar seasonal shapes, with the #2a78d6 line clearly running
below the other two from July onward. A thin gray dashed line labeled
"Среднее по району" sits between them. Legend under the plot with the
three field names and the average.
```

### S-08 · Хитмап региона

```
SCREEN: map view with a regional heatmap. The gray map placeholder now
shows about 40 field polygons filled with a diverging color scale: dark
red #d03b3b, salmon #e08a70, pale #f0c8b4, neutral gray #f0efec, light
blue #9ec5f4, blue #2a78d6. Most fields are neutral to light blue, a
cluster of six in one corner is red. Bottom left of the map: a horizontal
legend strip 220px wide showing the gradient with the labels "−3σ",
"0", "+2σ" under it and the caption "Худшее отклонение за период".
Top right of the map: a small card with the title "Ставропольский край",
the line "47 полей · апр — окт 2025" and a red chip "6 полей в критической
зоне".
```
