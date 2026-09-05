# Стиль-блок

У Stitch **нет дизайн-системы**: он не помнит палитру между генерациями и не
даёт завести компоненты. Единственный способ получить шесть экранов в одном
стиле — вставлять один и тот же текст в начало каждого промпта.

Блок ниже — дословный. Копируется целиком, не сокращается, не пересказывается
своими словами. Любая правка блока означает перегенерацию **всех** экранов.

---

## STYLE BLOCK — вставлять в начало каждого промпта

```
STYLE SYSTEM (follow exactly, do not invent colors, sizes or components):

Product: VegaWatch — a web service for monitoring crop vegetation dynamics
from satellite data. Audience: agronomists and analysts. Tone: precise,
calm, data-dense but not cluttered. Think Linear or Vercel dashboard,
not a consumer app. No gradients, no glassmorphism, no drop shadows
beyond one subtle level, no decorative illustrations, no emoji.

Layout: desktop web app, 1440x900. Single screen, no page navigation.
Fixed 320px left sidebar, 56px top bar, the rest is the working area.
4px spacing grid — every margin and padding is a multiple of 4.
Corner radius 8px on cards, 6px on buttons and inputs, 4px on chips.
Exactly one shadow level: 0 1px 2px rgba(11,11,11,0.06).

Colors (use these hex values only):
- page background #f9f9f7
- card and panel background #fcfcfb
- sunken background for inputs #f0efec
- primary text #0b0b0b
- secondary text #52514e
- muted text and axis labels #898781
- hairline borders rgba(11,11,11,0.10)
- brand accent, primary buttons, active states #2a78d6
- weak brand fill, selected polygon, hint background #cde2fb
- status good #0ca30c
- status warning #fab219
- status critical #d03b3b
- status unreliable data #ec835a
- data source Sentinel-2 #2a78d6
- data source Landsat #eb6834
- data source MODIS #1baf7a

Typography: system sans-serif only (system-ui / Segoe UI / Roboto).
Screen title 24/32 semibold. Panel heading 18/26 semibold.
Subheading 15/22 semibold. Body 14/21 regular. Small 13/18 regular.
Axis and caption 12/16 regular. Large KPI number 32/38 semibold.
Never use any font size below 12px. Numbers in tables and axes are
tabular figures.

Icons: one single line-icon set, 1.5px stroke, 16px and 20px only.
Never mix icon styles.

Language: ALL user-facing text must be in Russian. Use exactly the
Russian strings given in the screen description below. Do not translate
them, do not paraphrase them, do not invent extra labels. Any label not
given in the description should be omitted rather than invented.

Accessibility: text contrast at least 4.5:1 against its background.
Status is never communicated by color alone — always color plus an icon
plus a text label.
```

---

## Как проверить, что блок сработал

После генерации первого экрана сверить по списку. Если что-то не так —
это правится **уточняющим промптом к тому же экрану**, а не новым с нуля:

- [ ] Фон страницы светло-серый, панели чуть светлее фона (не наоборот)
- [ ] Ровно одна ненавязчивая тень, никаких «парящих» карточек
- [ ] Кнопка действия синяя `#2a78d6`, не фиолетовая и не зелёная
- [ ] Все подписи по-русски и совпадают с `05-copy-ru.md` дословно
- [ ] Нет иконок из разных наборов
- [ ] Нет градиентов и стекла
- [ ] Мелкий текст читается: ничего меньше 12 px

## Уточняющие промпты (когда блок частично проигнорирован)

Stitch нередко «улучшает» дизайн по-своему. Готовые формулировки:

```
Remove all gradients and glass effects. Flat solid fills only,
using exactly the hex values from the style system.
```

```
The accent color must be #2a78d6 everywhere. Replace any purple,
teal or green accents with it, except status colors.
```

```
Increase all text below 12px to at least 12px. Do not shrink text
to fit — reduce the amount of content instead.
```

```
Replace all English labels with the Russian strings given earlier.
Do not translate freely — use the exact strings.
```

```
Tighten spacing to the 4px grid. Card padding 16px, gap between
cards 12px, section gap 24px.
```

## Что делать нельзя

- **Менять стиль-блок между экранами.** Даже «чуть-чуть подправлю оттенок» —
  и половина макетов окажется в другой палитре, а на защите это видно сразу.
- **Полагаться на то, что Stitch помнит предыдущий экран.** Он не помнит.
- **Просить «в фирменном стиле хакатона».** Модель не знает, что это,
  и придумает. Все цвета — только явными hex.
