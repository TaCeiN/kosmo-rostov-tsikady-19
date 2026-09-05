---
name: Orbital Glass Telemetry
colors:
  surface: '#0f131d'
  surface-dim: '#0f131d'
  surface-bright: '#353944'
  surface-container-lowest: '#0a0e18'
  surface-container-low: '#171b26'
  surface-container: '#1c1f2a'
  surface-container-high: '#262a35'
  surface-container-highest: '#313540'
  on-surface: '#dfe2f1'
  on-surface-variant: '#bec8d2'
  inverse-surface: '#dfe2f1'
  inverse-on-surface: '#2c303b'
  outline: '#88929b'
  outline-variant: '#3e4850'
  surface-tint: '#89ceff'
  primary: '#89ceff'
  on-primary: '#00344d'
  primary-container: '#0ea5e9'
  on-primary-container: '#003751'
  inverse-primary: '#006591'
  secondary: '#45dfa4'
  on-secondary: '#003825'
  secondary-container: '#00bd85'
  on-secondary-container: '#00452e'
  tertiary: '#ffb2b7'
  on-tertiary: '#67001b'
  tertiary-container: '#ff697b'
  on-tertiary-container: '#6c001d'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#c9e6ff'
  primary-fixed-dim: '#89ceff'
  on-primary-fixed: '#001e2f'
  on-primary-fixed-variant: '#004c6e'
  secondary-fixed: '#68fcbf'
  secondary-fixed-dim: '#45dfa4'
  on-secondary-fixed: '#002114'
  on-secondary-fixed-variant: '#005137'
  tertiary-fixed: '#ffdadb'
  tertiary-fixed-dim: '#ffb2b7'
  on-tertiary-fixed: '#40000d'
  on-tertiary-fixed-variant: '#92002a'
  background: '#0f131d'
  on-background: '#dfe2f1'
  surface-variant: '#313540'
typography:
  display-lg:
    fontFamily: Geist
    fontSize: 3.5rem
    fontWeight: '600'
    lineHeight: 4rem
    letterSpacing: -0.035em
  display-lg-mobile:
    fontFamily: Geist
    fontSize: 2.25rem
    fontWeight: '600'
    lineHeight: 2.75rem
    letterSpacing: -0.025em
  display-md:
    fontFamily: Geist
    fontSize: 2.5rem
    fontWeight: '600'
    lineHeight: 3rem
    letterSpacing: -0.03em
  headline-lg:
    fontFamily: Geist
    fontSize: 1.75rem
    fontWeight: '500'
    lineHeight: 2.25rem
    letterSpacing: -0.02em
  headline-sm:
    fontFamily: Geist
    fontSize: 1.25rem
    fontWeight: '500'
    lineHeight: 1.75rem
    letterSpacing: -0.015em
  telemetry-metric:
    fontFamily: Geist
    fontSize: 2rem
    fontWeight: '600'
    lineHeight: 2.25rem
    letterSpacing: -0.02em
  body-lg:
    fontFamily: Inter
    fontSize: 1.125rem
    fontWeight: '400'
    lineHeight: 1.75rem
    letterSpacing: -0.01em
  body-md:
    fontFamily: Inter
    fontSize: 0.9375rem
    fontWeight: '400'
    lineHeight: 1.5rem
    letterSpacing: -0.005em
  body-sm:
    fontFamily: Inter
    fontSize: 0.8125rem
    fontWeight: '400'
    lineHeight: 1.25rem
    letterSpacing: 0em
  caption-spatial:
    fontFamily: Geist
    fontSize: 0.6875rem
    fontWeight: '500'
    lineHeight: 0.875rem
    letterSpacing: 0.06em
  mono-telemetry:
    fontFamily: Geist
    fontSize: 0.75rem
    fontWeight: '500'
    lineHeight: 1rem
    letterSpacing: 0.04em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  space-3xs: 0.125rem
  space-2xs: 0.25rem
  space-xs: 0.5rem
  space-sm: 0.75rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
  space-2xl: 3rem
  space-3xl: 4rem
  gutter-mobile: 1rem
  gutter-desktop: 1.5rem
  dock-inset: 1.5rem
---

## Brand & Style

The visual identity embodies the spatial precision of visionOS combined with mission-critical geospatial telemetry. Crafted for deep orbital analytics, crop health surveillance, and planetary environmental intelligence, the interface balances spatial depth with enterprise legibility.

### Personality & Tone
- **Atmospheric & Spatial:** Deep cosmic backdrops punctuated by luminous volumetric mesh glares and optic refractions.
- **Instrument-Grade Precision:** Clean, low-latency sensory clarity where typography, data readouts, and geospatial vector boundaries operate with pinpoint accuracy.
- **Ethereal Acrylic Craft:** Translucent panels, directional glossy specular rims, and fluid ambient refraction that make complex earth observation data feel weightless yet physically rooted.

### Aesthetic Principles
- **Backdrop Diffusion:** Heavy gaussian filtration (`24px` to `40px`) turns orbital satellite layers into soft chromatic illumination behind foreground controls.
- **Specular Containment:** Components do not rely on opaque borders; instead, they feature directional light-fall lines (`rgba(255, 255, 255, 0.25)` transitioning to `rgba(255, 255, 255, 0.03)`).
- **Luminescent Signal Contrast:** Pure dark navy canvases host hyper-saturated spectral accents to indicate vegetation index variations, moisture stress, and real-time sensor streams without visual clutter.

## Colors

The palette simulates spatial light passing through refractive acrylic lenses over dark space, accented by targeted telemetry hues.

### Foundational Canvas
- **Deep Space Base:** `#06080e` (Primary canvas floor)
- **Acrylic Deep Navy:** `#0b0f19` (Root structural panels and backdrop foundation)
- **Surface Elevation Layers:**
  - Glass Tier 01 (Ambient Floating Dock): `rgba(15, 23, 42, 0.45)` with `backdrop-filter: blur(32px)`
  - Glass Tier 02 (Analytics Panel / Card): `rgba(30, 41, 59, 0.35)` with `backdrop-filter: blur(24px)`
  - Glass Tier 03 (Hover & Active Overlays): `rgba(255, 255, 255, 0.08)`

### Signal & Telemetry Accents
- **Primary Telemetry (`#0ea5e9` / `#38bdf8`):** Satellite tracking nodes, active geospatial polygons, primary system calls, orbital paths.
- **Secondary Chlorophyll Glow (`#34d399`):** Vegetation index (NDVI) health, positive yield projections, photosynthetic activity metrics.
- **Critical Thermal (`#f43f5e`):** Drought stress alerts, thermal anomalies, frost warnings, field boundary threshold infringements.
- **Solar Radiant (`#fbbf24`):** Soil moisture depletion, optical cloud coverage warnings, radar calibration alerts.

### Borders & Optical Refraction
- **Specular Top Rim:** `linear-gradient(180deg, rgba(255, 255, 255, 0.28) 0%, rgba(255, 255, 255, 0.04) 100%)`
- **Subtle Surface Stroke:** `rgba(255, 255, 255, 0.08)`

## Typography

Typography delivers geometric precision across high-density telemetry dashboards and orbital maps.

- **Geist (Headlines, Metrics & Labels):** Provides an architectural, tech-forward cadence for high-impact numbers, panel headers, and orbital coordinates. Tabular figures must be enabled (`font-variant-numeric: tabular-nums`) for all telemetry indicators to avoid jitter during real-time streaming.
- **Inter (Body & Functional Copy):** Chosen for optical stability and legibility when reading field intelligence reports, system diagnostics, and analytical descriptions against shifting glassmorphic backdrops.
- **Case Treatment:** Micro-labels, radar coordinate chips, and status flags utilize uppercase styling with widened tracking (`0.06em`) to ensure instant legibility at fractional scale.

## Layout & Spacing

The layout is built around a spatial canvas model: an edge-to-edge interactive earth observation map anchored beneath floating glass consoles, telemetry heads-up displays (HUD), and an isolated bottom-center navigation pill dock.

### Grid & Canvas Structure
- **Global Viewport:** Canvas is fluid 100vw/100vh with fixed outer padding to prevent glass surfaces from touching the physical screen perimeter.
- **Workspace Grid:** 12-column dynamic flex-grid on desktop (`1440px+`) with `1.5rem` gutters. Panels float inside the margins with absolute spatial detachment.
- **Sidebar Inspector:** Persistent 380px floating right-hand rail for deep telemetry breakdowns and spectral frequency inspection.

### Responsive Breakpoints
- **Compact (Mobile &lt; 768px):** Telemetry panels condense into a horizontal snap-scroll drawer at the screen bottom. Floating docks collapse into an ultra-compact bottom pill bar (`1rem` bottom margin). Map remains primary surface.
- **Medium (Tablet 768px - 1024px):** Single column panel overlay with collapsible secondary analytical drawer. Gutters scale down to `1rem`.
- **Expanded (Desktop &gt; 1024px):** Full multi-tier spatial glass canvas with modular side-by-side floating panels and orbital horizon map background.

## Elevation & Depth

Visual hierarchy is maintained via refractive optics, ambient color tinting, and visionOS-style directional light reflections rather than traditional dark dropshadows.

### The Glass Depth Stack
1. **Atmospheric Canvas (Layer 0):** Pure spatial viewport displaying vector raster tiles with subtle radial back-lights: Deep Sky Blue (`rgba(14, 165, 233, 0.08)`), Emerald Aurora (`rgba(52, 211, 153, 0.06)`), and Dark Indigo Mesh (`rgba(99, 102, 241, 0.07)`).
2. **Base Glass Panels (Layer 1):** `background: rgba(15, 23, 42, 0.42)`, backdrop blur of `24px`, inner shadow `inset 0 1px 1px 0 rgba(255, 255, 255, 0.15)`. Outer ambient glow: `0 12px 32px -4px rgba(0, 0, 0, 0.5)`.
3. **Floating Controls & Overlays (Layer 2):** Segmented controls, popovers, and floating docks utilize `background: rgba(30, 41, 59, 0.65)`, backdrop blur of `40px`, and outer shadow `0 20px 40px -8px rgba(0, 0, 0, 0.7)`.
4. **Active Luminescent Elements (Layer 3):** Glowing strokes with neon drop illumination: `box-shadow: 0 0 16px rgba(14, 165, 233, 0.4), inset 0 0 8px rgba(14, 165, 233, 0.2)`.

### Specular Edge Architecture
Every elevated card and glass component features a dynamic two-layer pseudo-border:
- Top and left edges receive a crisp `0.5px` white keyline highlight (`rgba(255, 255, 255, 0.28)`), mimicking ambient directional light.
- Bottom and right edges fade to near-opacity (`rgba(255, 255, 255, 0.03)`), giving components physical dimension and refraction against the dark background.

## Shapes

The design system uses Level 2 roundedness, balancing modern spatial curves with high-density data requirements.

### Curvature Assignments
- **Base Components (`rounded` - 0.5rem / 8px):** Segmented buttons, micro-metrics, drop-down cells, input fields, coordinate badges.
- **Floating Containers (`rounded-lg` - 1rem / 16px):** Telemetry cards, field parameter inspectors, modal dialogs, map floating tool groups.
- **Spatial Docks & Outer Frames (`rounded-xl` - 1.5rem / 24px):** Primary bottom dock, HUD container brackets, orbital radar shields.
- **Pills (`rounded-full`):** Status indicator bulbs, interactive map filter pills, tool toggle selectors, floating cursor beacons.

## Components

### Buttons & Segmented Controls
- **Glass Button (Default):** Translucent fill `rgba(255, 255, 255, 0.06)` with backdrop blur `16px`. Border: 1px gradient stroke (`rgba(255, 255, 255, 0.18)` to `rgba(255, 255, 255, 0.04)`). Text: pure crisp white with `Geist 500`. Hover state transitions to `rgba(255, 255, 255, 0.12)` with a soft ambient cyan back-glow.
- **Primary Telemetry Action:** Vibrant sky-cyan base (`#0ea5e9`) with an interior glossy highlight on the upper rim (`inset 0 1px 0 rgba(255, 255, 255, 0.4)`), black bold typography, and a radiant sky-blue diffusion bloom.
- **Segmented Glass Toggle:** Enclosed in a single frosted pill capsule (`rgba(15, 23, 42, 0.6)`). The active item snaps with an elevated white acrylic slide-tile (`rgba(255, 255, 255, 0.14)`), accompanied by a subtle white rim and tactile micro-shadow.

### Telemetry Cards & HUD Panels
- Built with multi-layered backdrop filtration (`blur(28px)`) and variable acrylic tinting.
- Contain a distinct header strip with an active vector pulse icon, a category tag in `caption-spatial`, and an absolute coordinates indicator in monospaced tabular numerals.
- Card interiors avoid hard horizontal dividers, separating sections with `rgba(255, 255, 255, 0.06)` hairlines or negative spatial gaps.

### Chips & Coordinate Indicators
- Compact height (`24px` to `28px`) with rounded-full pill styling.
- Left-aligned glowing micro-dot indicating telemetry status: Emerald (Connected / Nominal), Amber (Cloud Obscured / Calibrating), Rose (Critical Stress / Anomaly Detected).
- Dark transparent core (`rgba(2, 6, 23, 0.6)`) with high-contrast alphanumeric string readouts.

### Input Fields & Search Bars
- Recessed frosted styling: dark inset background (`rgba(2, 6, 23, 0.5)`), inner border `rgba(255, 255, 255, 0.08)`.
- On focus, border transitions to active cyan glow (`#0ea5e9`) with an ambient outer lens flare (`0 0 12px rgba(14, 165, 233, 0.3)`).
- Prefix icons (e.g., search crosshairs, satellite reticles) render in `rgba(255, 255, 255, 0.45)`.

### Vector Polygon Overlays & Data Visualizations
- Map boundary markers feature luminous neon strokes (`#0ea5e9`, `#34d399`, `#f43f5e`) at `1.5px` stroke-width, accompanied by a double-pass blurred drop glow (`blur: 6px, spread: 2px`).
- Polygons utilize translucent multi-stop surface fills (`rgba(14, 165, 233, 0.12)` transitioning down to `rgba(14, 165, 233, 0.02)`).
- Sensor graph curves (e.g., vegetation indices over time) use bezier neon paths with a gradient fill reflecting the underlying acrylic canvas.

### Floating Dock Navigation
- Detached, centered horizontal island anchored `1.5rem` above the screen bottom.
- Frosted glass construction with `backdrop-filter: blur(36px)`, specular edge highlight, and icon actions styled with rounded-full touch targets.
- Tooltips launch upwards in miniature acrylic bubbles with zero latency.