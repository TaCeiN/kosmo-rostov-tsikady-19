---
name: Precision Earth Observation
colors:
  surface: '#fcf8f8'
  surface-dim: '#dcd9d9'
  surface-bright: '#fcf8f8'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f6f3f2'
  surface-container: '#f0edec'
  surface-container-high: '#ebe7e7'
  surface-container-highest: '#e5e2e1'
  on-surface: '#1c1b1b'
  on-surface-variant: '#414752'
  inverse-surface: '#313030'
  inverse-on-surface: '#f3f0ef'
  outline: '#727784'
  outline-variant: '#c1c6d4'
  surface-tint: '#005eb4'
  primary: '#005bb0'
  on-primary: '#ffffff'
  primary-container: '#2474d2'
  on-primary-container: '#fefcff'
  inverse-primary: '#a8c8ff'
  secondary: '#5f5e5b'
  on-secondary: '#ffffff'
  secondary-container: '#e2dfdb'
  on-secondary-container: '#64625f'
  tertiary: '#914800'
  on-tertiary: '#ffffff'
  tertiary-container: '#b65c00'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d5e3ff'
  primary-fixed-dim: '#a8c8ff'
  on-primary-fixed: '#001b3c'
  on-primary-fixed-variant: '#00468a'
  secondary-fixed: '#e5e2de'
  secondary-fixed-dim: '#c9c6c2'
  on-secondary-fixed: '#1c1c19'
  on-secondary-fixed-variant: '#484744'
  tertiary-fixed: '#ffdcc6'
  tertiary-fixed-dim: '#ffb784'
  on-tertiary-fixed: '#301400'
  on-tertiary-fixed-variant: '#713700'
  background: '#fcf8f8'
  on-background: '#1c1b1b'
  surface-variant: '#e5e2e1'
  surface-page: '#f9f9f7'
  surface-card: '#fcfcfb'
  surface-sunken: '#f0efec'
  text-primary: '#0b0b0b'
  text-secondary: '#52514e'
  text-muted: '#898781'
  border-hairline: rgba(11, 11, 11, 0.10)
  gridline: '#e1e0d9'
  brand-weak: '#cde2fb'
  status-good: '#0ca30c'
  status-warning: '#fab219'
  status-critical: '#d03b3b'
  status-serious: '#ec835a'
  sensor-s2: '#2a78d6'
  sensor-landsat: '#eb6834'
  sensor-modis: '#1baf7a'
typography:
  kpi-number:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 38px
  headline-1:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-2:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
  headline-3:
    fontFamily: Geist
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 22px
  body:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 21px
  body-medium:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 21px
  small:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  caption:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  axis-label:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 4px
  space-1: 4px
  space-2: 8px
  space-3: 12px
  space-4: 16px
  space-5: 20px
  space-6: 24px
  space-8: 32px
  topbar-height: 56px
  sidebar-width: 320px
---

# VegaWatch Design System

## Brand & Product Identity
- **Product:** VegaWatch — web service for monitoring crop vegetation dynamics from satellite data.
- **Audience:** Agronomists, analysts, precision agriculture specialists.
- **Tone:** Precise, calm, data-dense, technical clarity (Linear/Vercel dashboard style). No decorative fluff, no gradients, no glassmorphism.
- **Theme:** Light theme default.

## Color Palette
- `--surface-page`: `#f9f9f7` (Page background)
- `--surface-card`: `#fcfcfb` (Card/panel background)
- `--surface-sunken`: `#f0efec` (Inputs, subtle containers, neutral plot corridor)
- `--text-primary`: `#0b0b0b` (Headings, primary metrics)
- `--text-secondary`: `#52514e` (Body copy, subtitles)
- `--text-muted`: `#898781` (Captions, axis labels, gridlines)
- `--border`: `rgba(11, 11, 11, 0.10)` (Hairline borders)
- `--gridline`: `#e1e0d9` (Chart gridlines)
- `--brand`: `#2a78d6` (Accent, primary actions, active state)
- `--brand-weak`: `#cde2fb` (Selected polygon fill, badge background)
- `--status-good`: `#0ca30c` (Normal/nominal)
- `--status-warning`: `#fab219` (Biomass inhibition / stress)
- `--status-critical`: `#d03b3b` (Critical anomaly)
- `--status-serious`: `#ec835a` (Unreliable / low coverage)
- `--sensor-s2`: `#2a78d6` (Sentinel-2, circle)
- `--sensor-landsat`: `#eb6834` (Landsat, square)
- `--sensor-modis`: `#1baf7a` (MODIS, triangle)

## Typography
- Font Family: `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`
- H1: 24px / 32px line-height, semibold (600)
- H2: 18px / 26px line-height, semibold (600)
- H3: 15px / 22px line-height, semibold (600)
- Body: 14px / 21px line-height, regular (400)
- Small: 13px / 18px line-height, regular (400)
- Caption / Axis: 12px / 16px line-height, regular (400)
- KPI Number: 32px / 38px line-height, semibold (600)
- Numbers in tables and axes use `font-variant-numeric: tabular-nums`. Minimum font size: 12px.

## Spacing & Layout
- Grid unit: 4px base step.
- App layout: Desktop 1440x900 viewport.
- Top bar: 56px height.
- Left sidebar: 320px fixed width.
- Main area: Flex/grid layout.
- Border radius: 8px cards, 6px buttons and inputs, 4px chips/tags.
- Shadow: `0 1px 2px rgba(11, 11, 11, 0.06)` (strictly single subtle elevation level).
