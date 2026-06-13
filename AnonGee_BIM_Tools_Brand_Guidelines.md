# AnonGee BIM Tools
## Brand & Design System

> **Version 3.0** · June 2026 · Confidential — Internal Reference
> Supersedes v2.0. Palette unchanged; document restructured to design-system standard and reconciled with the shipping `pyZaid.extension` codebase.

---

## How to read this document

This is a **design system specification**, not a style suggestion. It is the single source of truth for every interface, document, and message produced under the AnonGee BIM Tools name. It is organized in three layers, mirroring how the system is actually built in code:

1. **Foundations** (§3–§7) — the primitives: color, type, space, motion, iconography, voice. These never change per-tool.
2. **Components** (§8–§9) — the assembled controls and patterns built from foundations.
3. **Delivery** (§10–§15) — how the system ships inside pyRevit, who it serves, and how it is governed.

Every visual value in this document maps to a named token in `pyZaid.extension/Resources/`. **Tokens are authoritative; this prose describes them.** Where a number here and a number in code disagree, the code wins and this document is wrong — file it as a defect (§15.4).

---

## Table of Contents

**Foundations**
1. [Brand Identity](#1-brand-identity)
2. [Logo & Wordmark](#2-logo--wordmark)
3. [Color System](#3-color-system)
4. [Typography](#4-typography)
5. [Spacing, Layout & Density](#5-spacing-layout--density)
6. [Motion & Interaction](#6-motion--interaction)
7. [Iconography](#7-iconography)

**Components & Voice**
8. [Voice & Tone](#8-voice--tone)
9. [UI Component Guidelines](#9-ui-component-guidelines)

**Quality & Delivery**
10. [Accessibility Standards](#10-accessibility-standards)
11. [UX & Content Patterns](#11-ux--content-patterns)
12. [pyRevit Delivery Standards](#12-pyrevit-delivery-standards)
    - [12.7 WPF ControlTemplate Constraints](#127-wpf-controltemplate-constraints) — A–P (16 validated rules)
    - [12.8 Modeless Window Architecture](#128-modeless-non-blocking-window-architecture) — IExternalEventHandler, thread bridging, CPython 3 rules
    - [12.9 CPython 3 Engine Stability](#129-cpython-3-engine-stability) — persistent engine, handler/GC crash traps, stripped stdlib, native-fault truth
13. [Design Tokens & Theme Architecture](#13-design-tokens--theme-architecture)
14. [Audience Profiles](#14-audience-profiles)
15. [Governance & Contribution](#15-governance--contribution)
16. [Document & Report Standards](#16-document--report-standards)
    - [16.1 Spreadsheet / Schedule Export (Excel)](#161-spreadsheet--schedule-export-excel) — brand colors, fonts, alignment & AutoFit rules for .xlsx output
17. [Brand Don'ts](#17-brand-donts)
18. [Appendix — Token Reference](#18-appendix--token-reference)

---

## 1. Brand Identity

**AnonGee BIM Tools** is a professional suite of structural and architectural BIM automation tools engineered for Autodesk **Revit 2025**, delivered through **pyRevit 6.10.0**. The suite combines AI-assisted workflows, pyRevit scripting, and model-context tooling to give the modern BIM professional precision automation that behaves like native, engineered software — not a collection of macros.

### 1.1 Brand Principles

These three principles govern *what the brand says*.

**Precision.** Every output is exact, traceable, and repeatable. The brand never overpromises or speaks loosely about technical outcomes. Counts are reported. Failures are named.

**Authority.** AnonGee BIM Tools is the work of a practitioner. The visual language and tone reflect deep domain expertise — not generic SaaS aesthetics.

**Clarity.** Complex workflows are made intelligible. The UI, documentation, and messaging strip away noise and surface what matters first.

### 1.2 Design Principles

These four principles govern *how the product behaves*. They resolve disputes when guidelines conflict.

| Principle | Meaning | In practice |
|---|---|---|
| **Native, not novel** | Tools should feel like a deliberate extension of Revit, not a foreign app. | Honor Revit's modal/docking conventions; never fight the host window manager. |
| **Density with breathing room** | Engineers work with dense data; respect their screen but never crowd. | Default density is compact (§5.4); whitespace separates *regions*, not every row. |
| **State is always visible** | The user must never wonder what the tool is doing. | Every long operation shows progress; disabled controls stay visible, never hidden. |
| **Fail loud, fail useful** | Errors are surfaced immediately with a next action. | Error copy states what failed, why, and what to do (§8.2). |

### 1.3 Brand Hierarchy

| Level | Name | Description |
|---|---|---|
| Parent | **AnonGee** | The practitioner identity and studio name |
| Suite | **AnonGee BIM Tools** | The full product suite (the Revit ribbon tab) |
| Products | **AnonGee · [Tool Name]** | Individual tools (pyRevit pushbuttons) within the suite |

> **Note — ribbon identifier.** The extension currently ships its ribbon tab as `pyZaid.tab` (folder `pyZaid.extension`). This is the legacy internal identifier. Public-facing surfaces — window titles, splash, documentation — use the **AnonGee BIM Tools** brand. Reconciling the ribbon tab label to the brand is tracked as a governance item (§15.4).

---

## 2. Logo & Wordmark

### 2.1 Primary Wordmark

```
AnonGee BIM Tools
```

### 2.2 Construction Rules

- **AnonGee** — Title case only. Never `ANONGEE`, `anongee`, or `Anon Gee`.
- **BIM** — Always uppercase; it is an established industry acronym.
- **Tools** — Title case.
- The wordmark is set in **Source Serif 4 SemiBold** in all digital contexts.

### 2.3 Sub-Product Naming Convention

The **·** (middle dot, U+00B7) is the canonical separator between the brand name and tool name, with one space on each side.

| Tool (shipping) | Full Display Name |
|---|---|
| BIM Generation | AnonGee · BIM Generation |
| CAD Generation | AnonGee · CAD Generation |
| Filter Parameter | AnonGee · Filter Parameter |
| Parameter Combination | AnonGee · Parameter Combination |
| Export Schedule | AnonGee · Export Schedule |
| Obscured Rebar | AnonGee · Obscured Rebar |
| Copy Rebar Visibility | AnonGee · Copy Rebar Visibility |
| BBS Generator *(beta)* | AnonGee · BBS Generator |

A window's title bar shows the full display name; the header version badge shows the tool's semantic version (e.g. `v1.2`).

### 2.4 Wordmark on Color

| Background | Wordmark Color |
|---|---|
| White / Light surfaces | Charcoal Black `#141414` |
| Dark / Black surfaces | White `#FFFFFF` |
| Vivid Red surfaces | White `#FFFFFF` |
| Silver Steel surfaces | Charcoal Black `#141414` |

---

## 3. Color System

The palette is **unchanged from v2.0** and is fixed. It is built on three brand colors — **Vivid Red** (primary action/identity), **Charcoal Black** (structural foundation), **Silver Steel** (precision complement) — extended by neutrals, semantic states, and the interaction (hover/pressed) variants that the codebase already ships.

### 3.1 Brand Colors

| Name | Hex | Token | Role |
|---|---|---|---|
| **Vivid Red** | `#E02020` | `ColorVividRed` | Primary brand color. CTAs, active states, key highlights, accent rules. |
| **Charcoal Black** | `#141414` | `ColorCharcoalBlack` | Structural foundation. Headers, dark surfaces, primary text. |
| **Silver Steel** | `#C0C8D8` | `ColorSilverSteel` | Precision complement. Borders, dividers, secondary UI, icons on dark. |

### 3.2 Surface & Text Neutrals

| Name | Hex | Token | Role |
|---|---|---|---|
| **Pure White** | `#FFFFFF` | `ColorPureWhite` | Page canvas, card surfaces. |
| **Off White** | `#F4F4F6` | `ColorOffWhite` | Subtle background tint, footers, alternating rows. |
| **Mid Grey** | `#6B7280` | `ColorMidGrey` | Secondary/body text, metadata, placeholders. |
| **Light Border** | `#E2E4EA` | `ColorLightBorder` | Dividers, input borders, card outlines on white. |

### 3.3 Semantic / State Colors

Reserved exclusively for system feedback — never decorative.

| Name | Hex | Token | Use |
|---|---|---|---|
| **Success Green** | `#16A34A` | `ColorSuccessGreen` | Completed operations, valid states. |
| **Caution Amber** | `#D97706` | `ColorCautionAmber` | Warnings, beta labels, non-critical notices. |
| **Error Red** | `#DC2626` | `ColorErrorRed` | Failures, destructive actions, invalid input. **Distinct from Vivid Red — never substitute.** |
| **Info Blue** | `#2563EB` | `ColorInfoBlue` | Informational notices only. |

### 3.4 Interaction Variants

These ship in `Colors.xaml` so hover/pressed/disabled states are never improvised. **Do not hand-mix new shades** — use these tokens.

| Name | Hex | Token | Use |
|---|---|---|---|
| Vivid Red — Hover | `#C41A1A` | `ColorVividRedHover` | Primary button hover. |
| Vivid Red — Pressed | `#A81515` | `ColorVividRedPressed` | Primary/danger pressed. |
| Vivid Red — 10% | `#1AE02020` | `ColorVividRed10` | Secondary (outline) hover fill, very light red tint. |
| Error Red — Hover | `#B91C1C` | `ColorErrorRedHover` | Danger button hover. |
| Off White — Hover | `#E8E8EC` | `ColorOffWhiteHover` | Ghost/neutral hover fill. |

### 3.5 Surface-Specific Tints

Used in tables, badges, and selection states. These are intentionally not part of the core palette and appear only in the components that define them.

| Context | Hex | Where |
|---|---|---|
| Table row hover | `#FDECEA` | `BrushTableRowHover` |
| Selected row / secondary surface | `#FEF2F2` | `BrushTableRowSelected` |
| Success badge bg / text | `#DCFCE7` / `#15803D` | Status badges (§9.5) |
| Warning badge bg / text | `#FEF9C3` / `#92400E` | Status badges |
| Error badge bg / text | `#FEE2E2` / `#991B1B` | Status badges |
| Info badge bg / text | `#DBEAFE` / `#1D4ED8` | Status badges |

### 3.6 Color Hierarchy in Practice

1. **Vivid Red** carries the most visual weight. Reserve it for the single most important action or identity element per screen — the primary button, the active tab indicator, the accent rule. Do not scatter it.
2. **Charcoal Black** grounds the layout: headers, window chrome, primary text. Authoritative, not oppressive — balance it with whitespace.
3. **Silver Steel** operates quietly: borders, dividers, secondary icons, subtle surfaces. It defines structure without demanding attention.

### 3.7 Color Usage Rules

- Never set Vivid Red text on Charcoal Black — contrast is insufficient for body text; use white.
- Vivid Red as a background requires white text at **≥14px / 11pt** (it passes WCAG AA for normal text at 4.78:1 — see §10).
- **Silver Steel is never text on white** (1.68:1 — fails AA). It is a border / dark-surface color only.
- Semantic colors are never substituted for brand colors, and the reverse.
- No off-palette colors in any designed output without versioned approval (§15).

---

## 4. Typography

### 4.1 Typeface Stack

| Role | Primary | WPF Fallback chain | Token |
|---|---|---|---|
| UI, Body & Headings | **JetBrains Mono** | `JetBrains Mono, Source Serif 4, Inter, Segoe UI, Calibri` | `FontSans` |
| Code, Technical Output & Status | **JetBrains Mono** | `JetBrains Mono, Consolas, Courier New` | `FontMono` |

JetBrains Mono and Source Serif 4 are open-source ([fonts.google.com](https://fonts.google.com)). Because pyRevit tools run inside Revit's process, **do not assume the fonts are installed** — the fallback chain guarantees a graceful degrade to **Segoe UI / Calibri / Consolas**, which are present on every Revit 2025 host. Embedding is optional; the fallback is mandatory.

> **Token-name note.** The primary face is now **monospace** (JetBrains Mono), with Source Serif 4 as the first fallback. The token is still named `FontSans` for backward compatibility with shipped XAML — do **not** rename it. Treat `FontSans` as "the primary UI typeface". (Migration history: Inter → Source Serif 4 (v3.1) → JetBrains Mono-led (v3.2).)

### 4.2 Type Scale

WPF device-independent units are **authoritative** (this is a WPF toolkit). The px column is the web / design-tool equivalent.

| Level | WPF | ≈ px | Weight | Letter-spacing | Token | Usage |
|---|---|---|---|---|---|---|
| Display | 27 | 36 | Bold | −0.5px | — | Splash / marketing only |
| H1 | 21 | 28 | Bold | −0.3px | `FontSizeH1` | Window titles, primary headings |
| H2 | 16.5 | 22 | SemiBold | −0.2px | `FontSizeH2` | Section headings |
| H3 | 12 | 16 | SemiBold | 0 | `FontSizeH3` | Panel/group headings, card titles |
| H4 | 10.5 | 14 | Medium | 0 | `FontSizeH4` | Sub-section labels |
| Body | 10.5 | 14 | Regular | 0 | `FontSizeBody` | Prose, form labels |
| Body Small | 9 | 12 | Regular | 0 | `FontSizeSmall` | Compact lists, secondary content |
| Caption | 9 | 12 | Regular | +0.1px | `FontSizeCaption` | Metadata, footnotes, timestamps, badges |
| Code | 9 | 12 | Regular | 0 | `FontSizeCode` | All code & technical output |

> **Reconciliation note.** v2.0 prose listed Caption at 8.25 WPF; the shipping `Typography.xaml` uses **9**. Code is authoritative — Caption and Body Small are both `9`.

### 4.3 Line Heights

| Context | Line Height (WPF) |
|---|---|
| H1 | 26 |
| H2 / H3 | auto |
| Body | 17 |
| Code | 14 |

### 4.4 Named Text Styles

These `TextBlock` styles exist in `Typography.xaml`; reference them — do not set font properties inline.

| Style key | Maps to | On-dark variant |
|---|---|---|
| `TextH1` | H1, Charcoal Black | — |
| `TextH2` | H2, Charcoal Black | `TextH2OnDark` (white) |
| `TextH3` | H3, Charcoal Black | `TextH3OnDark` (Silver Steel) |
| `TextH4` | H4, Charcoal Black | — |
| `TextBody` | Body, Mid Grey, wraps | `TextBodyOnDark` (Silver Steel) |
| `TextSmall` | Body Small, Mid Grey | — |
| `TextCaption` | Caption, Mid Grey | — |
| `TextCode` | Mono on Charcoal Black, Silver Steel text | — |
| `TextError` | Caption-size, Error Red, 4px top margin | — |

### 4.5 Typography Rules

- **Headings are Charcoal Black** on light surfaces — never Vivid Red.
- **Body text is Mid Grey** (`#6B7280`) on white, not pure black.
- **All technical output is monospace** (JetBrains Mono) — element IDs, parameter names, file paths, API responses, script logs. Never proportional.
- **Status badges and all-caps state labels use JetBrains Mono** at Caption size (`READY`, `BETA`, `ERROR`, `v1.2`, success/error footer text). Mono = status + code; the serif `FontSans` is for everything else.
- **All-caps is reserved for badges** (`BETA`, `ERROR`, `v1.2`) at Caption size with positive letter-spacing. Never for headings or prose.

---

## 5. Spacing, Layout & Density

### 5.1 Base Unit

All spacing derives from an **8px base unit** (WPF: 8 units). Every margin, padding, and gap is a whole multiple of 8, with a single 4px half-step for tight inline pairs.

| Token | Value | WPF | Typical use |
|---|---|---|---|
| `space-xs` | 4px | 4 | Icon-to-label gap, tight inline pairs |
| `space-sm` | 8px | 8 | Compact internal padding |
| `space-md` | 16px | 16 | Standard component padding |
| `space-lg` | 24px | 24 | Between related sibling groups |
| `space-xl` | 32px | 32 | Between sections within a panel |
| `space-2xl` | 48px | 48 | Between major layout regions |
| `space-3xl` | 64px | 64 | Page-level breathing room |

### 5.2 Border Radius

| Context | Radius | Token tier |
|---|---|---|
| Badges, chips, checkboxes | 3px | `radius-sm` |
| Buttons, inputs, ComboBoxes, list items | 5px | `radius-md` |
| Cards, panels, GroupBoxes (popups 6px) | 8px | `radius-lg` |
| Dialogs, modal windows | 10px | `radius-xl` |

### 5.3 Elevation

Elevation establishes hierarchy, not decoration. Resources `ElevationLevel0`–`ElevationLevel3` ship in `Controls.xaml`.

| Level | Usage | Shadow |
|---|---|---|
| 0 | Flat / inline | None |
| 1 | Cards on canvas | `0 1px 3px rgba(0,0,0,0.10)` — **prefer a Light Border stroke over a shadow** |
| 2 | Dropdowns, popovers, elevated cards | `0 4px 12px rgba(0,0,0,0.14)` |
| 3 | Dialogs, modals | `0 8px 24px rgba(0,0,0,0.18)` |

In WPF, use `DropShadowEffect` only at Levels 2–3. Level 1 is simulated with a `BrushLightBorder` stroke (`CardBorder` style) for crisp rendering inside Revit.

### 5.4 Density

Revit users work on dense models; the default is **compact**. Density is expressed through control height and padding, never by shrinking the type scale below the §4.2 tokens.

| Mode | Control height | Row padding | When |
|---|---|---|---|
| **Compact** *(default)* | 28px | `8,6` | Dockable panels, data lists, parameter tables |
| **Comfortable** | 36px | `10,8` | Standard tool windows and dialogs |

- Buttons and inputs default to **36px** (`Comfortable`) in dialogs; list items and checkboxes default to **28px** (`Compact`).
- Never mix densities within one region. A dialog action bar is uniformly comfortable; a parameter grid is uniformly compact.

### 5.5 Layout Constraints

| Surface | Width rule | Resize |
|---|---|---|
| Standard tool window | Explicit `Width` (typ. 480–560), `SizeToContent="Height"` | `NoResize` unless content is variable-length |
| Dialog / modal | Fixed `Width` 480, `SizeToContent="Height"` | `NoResize`, always `CenterOwner` |
| Dockable panel | `MinWidth=240`, `MaxWidth=360`, single column | Host-managed |

---

## 6. Motion & Interaction

Motion in AnonGee BIM Tools is **functional, not expressive**. It communicates state change and spatial relationship — nothing more. A structural engineer should never wait on an animation.

### 6.1 Duration Tokens

| Token | Duration | Use |
|---|---|---|
| `motion-instant` | 0ms | Changes that must feel immediate (checkbox tick, selection) |
| `motion-fast` | 120ms | Hover/pressed color transitions, button feedback |
| `motion-standard` | 200ms | Popups, dropdown open/close, expander toggle |
| `motion-slow` | 300ms | Dialog/window fade-in (use sparingly) |

### 6.2 Easing

- **Standard easing:** `CubicEase, EaseOut` for entrances; `EaseInOut` for moves. In WPF: `<CubicEase EasingMode="EaseOut"/>`.
- ComboBox popups use the built-in `PopupAnimation="Slide"` (already set in `InputComboBox`).
- No bounce, no overshoot, no spin. Loading uses a determinate progress bar where possible (§11.3); an indeterminate bar only when total work is genuinely unknown.

### 6.3 Rules

- Color-only transitions (hover/press) may animate at `motion-fast`; everything structural stays ≤ `motion-standard`.
- **Never animate** a value the user is reading (counts, results, table data) — it appears instantly.
- Animations must never block the Revit UI thread. Long operations report via progress, not motion.

---

## 7. Iconography

### 7.1 Icon Library

**Lucide Icons** (MIT) is the canonical library. Icons ship as `Geometry` resources in `Icons.xaml` and are drawn with `Path`.

- Stroke weight: **1.5px** (do not deviate).
- Sizes: **16px / 12u** inline, **20px / 15u** standard, **24px / 18u** feature-level.
- Icons in interactive controls always carry a visible text label; icon-only buttons require a `ToolTip`.

### 7.2 Icon Color Rules

| Surface | Icon color |
|---|---|
| White / light panel | Charcoal Black `#141414` |
| Charcoal Black header | White `#FFFFFF` or Silver Steel `#C0C8D8` |
| Vivid Red surface | White `#FFFFFF` |
| Disabled state | Silver Steel `#C0C8D8` |
| Active / selected state | Vivid Red `#E02020` |

### 7.3 Shipping Icon Set

These geometry keys exist in `Icons.xaml`. Use them by key; add new icons only from Lucide and only via PR (§15).

| Concept | Geometry key | Concept | Geometry key |
|---|---|---|---|
| Checkmark (inline) | `IconCheck` | Settings | `IconSettings` |
| Success / complete | `IconCheckCircle` | Log / output / terminal | `IconTerminal` |
| Error / failure | `IconXCircle` | Processing / analysis | `IconCpu` |
| Warning / beta | `IconAlertTriangle` | Information | `IconInfo` |
| Open Revit model | `IconFolderOpen` | Sync / reload | `IconRefresh` |
| Export (IFC/DWG/PDF) | `IconDownload` | Find / search | `IconSearch` |
| Run script | `IconPlayCircle` | Next / proceed | `IconArrowRight` |
| Structural element | `IconLayers` | Dismiss / close | `IconClose` |
| Parameter / property | `IconSliders` | Add | `IconPlus` |
| AI / MCP connection | `IconZap` | Remove | `IconMinus` |
| Grid / axis | `IconGrid` | Expand / dropdown | `IconChevronDown` |
| View management | `IconLayout` | Copy to clipboard | `IconCopy` |

### 7.4 Ribbon (PNG) Icons

pyRevit ribbon buttons require raster `icon.png` (32×32 base; provide `icon.dark.png` if a dark-ribbon variant is needed). These are distinct from the in-window vector icons:

- Drawn from the same Lucide geometry, exported at 32×32 and 64×64 (HiDPI).
- Stroke-based, Charcoal Black on transparent; the active tool may use a single Vivid Red accent stroke.
- No photographic content, no gradients, no drop shadows on ribbon icons.

---

## 8. Voice & Tone

AnonGee BIM Tools communicates with the confidence of a senior BIM engineer: precise, direct, technically fluent. The voice never hedges, inflates, or condescends.

### 8.1 Core Principles

| Principle | Correct | Incorrect |
|---|---|---|
| **Precision** | "Placed 14 structural columns on Grid A, levels 1–5." | "Added some columns to the model." |
| **Directness** | "Export failed. Target directory does not exist." | "Hmm, something went wrong with your export!" |
| **Concision** | "Export complete. 3 files written to C:\Output." | "Your export has been completed successfully!" |
| **Authority** | "Running PlaceColumns_v2." | "Trying to run the script now, please wait…" |
| **Neutrality** | "Warning: 2 elements skipped — unsupported type 'GenericModel'." | "Oops! We couldn't handle those elements." |

### 8.2 The Error Message Contract

Every error message states three things, in order:

1. **What failed** — the operation, named.
2. **Why** — the cause, if determinable.
3. **What next** — the user's corrective action.

> *"Schedule export failed. The file `BBS_Level3.xlsx` is open in another application. Close it and run the export again."*

### 8.3 Writing Standards

- **Active voice** everywhere.
- Industry terms — Revit, IFC, BIM, MCP, API, IronPython, CPython — are always capitalized correctly.
- Tool names are written in full on first reference: **AnonGee · Export Schedule**, not "the export tool."
- Avoid filler qualifiers: *just, simply, easily, quickly, basically*.
- Success messages confirm; they do not celebrate. **No exclamation marks** in system messages, logs, or dialogs.

### 8.4 Terminology

| Use | Do not use |
|---|---|
| Revit model | "file", "project file" |
| Element | "object", "thing", "item" |
| Parameter | "field", "property" (in Revit context) |
| Export | "save as", "output to" |
| Script / tool | "macro", "program" |

---

## 9. UI Component Guidelines

Every component below is implemented as a named style in `Controls.xaml` / `Panels.xaml`. Each spec includes the **state matrix** — the system's contract for default → hover → pressed → focus → disabled.

### 9.1 Buttons

Strict hierarchy. **One Primary button per view or dialog.**

| Variant | Style key | Background | Text | Border |
|---|---|---|---|---|
| **Primary** | `ButtonPrimary` | Vivid Red | White | none |
| **Secondary** | `ButtonSecondary` | White | Vivid Red | 1.5px Vivid Red |
| **Neutral** | `ButtonNeutral` | Off White | Charcoal Black | 1px Light Border |
| **Danger** | `ButtonDanger` | Error Red | White | none |
| **Ghost** | `ButtonGhost` | Transparent | Mid Grey | none |

All variants derive from `ButtonBaseStyle` (5px radius, 36px height, `FontSans` SemiBold Body, `Cursor=Hand`).

**State matrix:**

| State | Primary | Secondary | Danger | Ghost / Neutral |
|---|---|---|---|---|
| Hover | bg `ColorVividRedHover` | bg `ColorVividRed10` | bg `ColorErrorRedHover` | bg `ColorOffWhiteHover` / Light Border |
| Pressed | bg `ColorVividRedPressed` | border + text Pressed | bg `ColorVividRedPressed` | — |
| Disabled | bg Light Border, text Silver Steel | border + text disabled | bg Light Border | text Silver Steel |

**Sizing:**

| Size | Height | Padding H | Font | Use |
|---|---|---|---|---|
| Large | 44px | 20px | Body | Primary dialog action |
| Default | 36px | 16px | Body | Standard |
| Small | 28px | 12px | Body Small | Compact / inline |

### 9.2 Text Inputs

`InputTextBox` — White bg, 1px Light Border, 5px radius, `10,8` padding, 36px height.

| State | Border |
|---|---|
| Default | 1px Light Border |
| Focus | 1.5px Vivid Red (`BrushInputFocusBorder`) |
| Error (`Validation.HasError`) | 1.5px Error Red (`BrushInputErrorBorder`) |
| Disabled | bg Light Border, text Silver Steel |

Inline validation only: errors render as a `TextError` line directly below the field (§11.5). Never a `MessageBox` for field-level validation.

### 9.3 ComboBox

`InputComboBox` — same base treatment as TextBox, with a custom chevron and a popup using `BrushLightBorder` (1px), 6px radius, white bg, `ElevationLevel2`, `PopupAnimation="Slide"`, `MaxHeight=200`. Focus border is Vivid Red 1.5px.

### 9.4 Selection Controls

| Control | Style key | Selected indicator | Hit target |
|---|---|---|---|
| CheckBox | `InputCheckBox` | 16×16, 3px radius, Vivid Red fill + white tick | ≥28px row |
| RadioButton | `InputRadioButton` | 16×16 ring, 8px Vivid Red dot | ≥28px row |
| ListBox | `InputListBox` + `ListBoxItemBase` | hover `BrushTableRowHover`; selected `BrushTableRowSelected` + 3px left Vivid Red border | item padding `8,6` |

Hover border on checkboxes is Vivid Red. The whole row is the hit target, not just the box. **Use the checkbox for list selection only** — for a binary on/off setting use the **Toggle Switch (§9.9)**.

> **`InputListBox` must be re-templated for a rounded container.** WPF's default `ListBox` template draws **square** corners — setting `BorderBrush`/`BorderThickness` alone is not enough. Re-template at 5px (`radius-md`, §5.2) to match TextBox/ComboBox, using the **fill / content / stroke-on-top** structure (§12.7.O) so all four edges stay uniform. The same pattern applies to TextBox and any bordered scroller.

### 9.5 Status Badges & Tags

| Status | Background | Text | Token pair |
|---|---|---|---|
| Success | `#DCFCE7` | `#15803D` | `BrushSuccessBadge*` |
| Warning | `#FEF9C3` | `#92400E` | `BrushWarningBadge*` |
| Error | `#FEE2E2` | `#991B1B` | `BrushErrorBadge*` |
| Info | `#DBEAFE` | `#1D4ED8` | `BrushInfoBadge*` |
| Beta | Charcoal Black | Silver Steel | `BrushBetaBadge*` |
| Active | Vivid Red | White | `BrushActiveBadge*` |

Badge text is uppercase, Caption size, 3px radius, positive letter-spacing.

### 9.6 Cards & Sections

| Element | Style key | Treatment |
|---|---|---|
| Card | `CardBorder` | White, 1px Light Border, 8px radius, 16px padding |
| Elevated card | `CardElevated` | Card + Level-2 shadow |
| Section group | `SectionGroup` (GroupBox) | White, 1px border, 8px radius, H3 header, `14,12` padding |
| Divider | `SectionDivider` | 1px Light Border, `0,16` margin |

### 9.7 Code & Log Output

All script output, API responses, and element IDs use the `TextCode` style: Charcoal Black background, Silver Steel text, JetBrains Mono, `16,12` padding, 5px radius. Syntax highlights: Vivid Red (keywords), `#A8D8A8` soft green (strings/values). Label the block with its context (`python`, `revit-api`, `log`) and provide a copy control (`IconCopy`) top-right.

### 9.8 Data Tables

- Header row: Charcoal Black bg, white text, `FontSans` SemiBold, `FontSizeH3`.
- Rows: White / Off White alternating; hover `#FDECEA`; selected `#FEF2F2` with 3px left Vivid Red border.
- Cell padding: `14,10` (comfortable) or `10,6` (compact, §5.4).
- Dividers: 1px Light Border.

### 9.9 Toggle Switch

The **toggle switch is the required control for a binary on/off option** (Android-style). Use it instead of a checkbox whenever the choice is a self-contained setting that takes effect immediately or on submit (export options, feature flags). Reserve the **checkbox** (§9.4) for *list selection* — picking items from a set (e.g. which schedules to export).

| Part | Spec |
|---|---|
| Track | 38 × 20, fully rounded (`CornerRadius=10`). **Off:** Silver Steel `#C0C8D8`. **On:** Vivid Red `#E02020`. |
| Thumb | 16 × 16 white ellipse, 2px inset; slides left↔right (`TranslateTransform` X 0 → 18) over **150 ms**. |
| Label | Primary UI font (`FontSans`), Body size, Charcoal Black, **left of the track** (track right-aligned in its cell). |
| States | Hover: track 0.85 opacity. Disabled: track `BrushDisabledBackground`, label `BrushDisabledForeground`. |
| Hit target | ≥24px row; the whole label+track row toggles. |

**Implementation.** Style **targets `CheckBox`** (keyed `ToggleSwitch`) so existing `IsChecked` script logic is unchanged — only the `ControlTemplate` differs. The slide is a `DoubleAnimation` on the thumb's `TranslateTransform` in `IsChecked` Enter/Exit actions (works under `XamlReader.Load`, no code-behind). Reference implementation: Export Schedule `ui.xaml`.

---

## 10. Accessibility Standards

Accessibility is a release gate, not a nicety. Target: **WCAG 2.1 AA** for all UI.

### 10.1 Contrast Ratios (computed from the palette)

| Foreground / Background | Ratio | AA Normal (4.5) | AA Large (3.0) | Verdict |
|---|---|---|---|---|
| Charcoal Black on White | **18.4:1** | ✅ | ✅ | Body & headings |
| Charcoal Black on Off White | **16.8:1** | ✅ | ✅ | Body on tinted rows |
| White on Charcoal Black | **18.4:1** | ✅ | ✅ | Header text |
| Mid Grey on White | **4.83:1** | ✅ | ✅ | Body text (passes) |
| White on Vivid Red | **4.78:1** | ✅ | ✅ | Primary button label |
| Vivid Red on White | **4.78:1** | ✅ | ✅ | Secondary button label |
| Silver Steel on Charcoal Black | **10.96:1** | ✅ | ✅ | Secondary text/icons on dark |
| **Silver Steel on White** | **1.68:1** | ❌ | ❌ | **Borders/dividers only — never text** |

Consequences baked into the system: Mid Grey (not Silver Steel) is the body-text color on white; white (not Vivid Red) is text on Charcoal; Vivid Red backgrounds require white text at ≥14px.

### 10.2 Focus & Keyboard

- Every interactive control has a **visible focus state** — the 1.5px Vivid Red border on inputs, and a focus visual on buttons. Never remove focus visuals.
- Tab order follows reading order (top-to-bottom, left-to-right).
- Dialogs set `IsDefault` on confirm and `IsCancel` on cancel, so Enter / Esc work.
- Mnemonics: `RecognizesAccessKey="True"` is set on button/checkbox content — provide `_Underscore` access keys on primary actions.

### 10.3 Hit Targets & Disabled States

- Minimum interactive target: **28px** (compact) / **36px** (comfortable). Inline icon buttons get ≥24px padding to a 28px box.
- Disabled controls stay **visible and non-interactive** (Light Border bg, Silver Steel text). Never use `Visibility="Collapsed"` to express disablement — a control that vanishes destroys spatial memory.

### 10.4 Non-Color Signaling

State is never communicated by color alone. Errors pair Error Red with a message and (where present) `IconAlertTriangle`/`IconXCircle`; success pairs Success Green with `IconCheckCircle`. A red border always accompanies an error message string.

---

## 11. UX & Content Patterns

Reusable patterns for the situations every BIM tool hits. Consistency here is what makes the suite feel engineered.

### 11.1 Empty States

When a list or result region has nothing to show, render a centered block: a Silver Steel icon (24px), one H3 line stating the state, one `TextBody` line of guidance, and — if there is an action — a Secondary button.

> *"No parameters selected. Choose one or more parameters above to begin filtering."*

### 11.2 Loading & Long Operations

Revit operations can run for minutes. Never leave the user guessing:

- Operations < ~500ms: no indicator.
- Operations with known size: **determinate** progress bar + `TextCaption` count ("Processing 142 / 980 elements").
- Operations of unknown size: **indeterminate** bar + a status line naming the current phase.
- Disable the triggering button and show its label as the running verb ("Exporting…").

### 11.3 Progress Reporting

Progress bars use Vivid Red on a Light Border track, 4px tall, 3px radius. Pair with a live count in `TextCaption`. Where the operation writes a log, stream meaningful milestones — not every iteration.

### 11.4 Confirmation & Destructive Actions

- Reversible actions: no confirmation.
- **Irreversible/destructive** actions (delete elements, overwrite files): a dialog with a `ButtonDanger` confirm, a `ButtonGhost` cancel, and copy that names the exact consequence and count.
- The danger button label is a verb, not "OK" — "Delete 38 elements".

### 11.5 Inline Validation

Validation is inline and immediate (§9.2). On error: set the input border to Error Red and render a `TextError` line beneath. Clear both the instant the input becomes valid. The primary action is disabled while any field is invalid.

### 11.6 Notifications & Results

- Terminal results (export complete, N elements modified) appear as a status line in the footer/action bar or as a result card — factual, with counts and output paths.
- Use pyRevit's output window (`script.get_output()`) for long, scrollable logs; use in-window status for the one-line outcome.
- Never use a blocking `TaskDialog` / `MessageBox` for routine success.

---

## 12. pyRevit Delivery Standards

This section is specific to shipping inside **pyRevit 6.10.0 on Revit 2025**. It is where the design system meets the host.

### 12.1 Engine: CPython 3 default, IronPython 2 legacy

- New scripts target **CPython 3** (`#! python3` shebang). Python.NET 3.0+ requires **explicit imports** — never `from Autodesk.Revit.DB import *`.
- A minority of legacy tools run **IronPython 2**; these are slated for CPython migration. Until migrated, IronPython tools must still consume the same theme tokens.
- WPF loading is consistent across both engines: add `PresentationFramework`, `PresentationCore`, `WindowsBase`, `System.Xaml`, then `XamlReader.Load()` from a `.xaml` file. This pattern works identically on IronPython 2 and CPython 3 and is the only supported way to build windows.

### 12.2 XAML lives in files, not Python strings

The legacy pattern embedded XAML as a raw string literal inside `script.py`. The standard is now a sibling **`ui.xaml`** file per pushbutton (see `OneFilterParameter`, `BIM Generation`). This gives syntax highlighting, designer preview, and clean diffs. New tools must use a separate `ui.xaml`; do not embed markup in Python.

### 12.3 Theme distribution — the canonical rule

The shared theme lives at `pyZaid.extension/Resources/AnonGeeTheme.xaml` (merging Colors, Typography, Controls, Panels, Icons). Two consumption strategies exist; pick by constraint:

1. **Merge by absolute path (preferred)** — at load time, resolve the absolute path to `AnonGeeTheme.xaml` and add it to the window's `Resources.MergedDictionaries` in Python before `XamlReader.Load`. Single source of truth; tools inherit fixes automatically.
2. **Inline copy (current fallback)** — some shipping tools (e.g. `BIM Generation/ui.xaml`) paste the full dictionary inline under a "COMBINED RESOURCE DICTIONARIES" banner, because `pack://application` URIs do not resolve reliably inside Revit's sandbox.

> **Standard:** Prefer strategy 1. Where the sandbox forces strategy 2, the inline block must be a **verbatim, unmodified copy** of the shared dictionaries — never a hand-edited variant. Any divergence between an inline copy and `Resources/*.xaml` is a defect. A future task should add a build/sync check that fails when they drift (§15.4).

Either way: **reference tokens by key** (`{DynamicResource BrushVividRed}`), never hardcode hex outside `Colors.xaml`.

### 12.4 Window hosting rules

- Always set `WindowStartupLocation="CenterOwner"` and assign the Revit main window as `Owner` (prevents the dialog appearing behind Revit).
- Modeless tools that touch the model use a pyRevit `ExternalEvent` / handler — never mutate the document off the API context.
- Wrap all model changes in a `Transaction` with a descriptive name matching the tool ("AnonGee · Obscured Rebar").
- Dockable panels implement `IDockablePaneProvider`, stay single-column, and respect `MinWidth=240 / MaxWidth=360`.

### 12.5 Bundle conventions

Each tool is a `*.pushbutton` (or grouped in a `*.splitbutton`) with:

```
ToolName.pushbutton/
├── bundle.yaml      # title, author, tooltip
├── icon.png         # 32×32 ribbon icon (§7.4), icon.dark.png if needed
├── ui.xaml          # WPF layout (no embedded markup in script.py)
└── script.py        # #! python3 ; CPython 3 by default
```

`bundle.yaml` `title` uses the tool's display name; `tooltip` is two to four factual lines (what it does, what it needs selected) — voice per §8.

### 12.6 Window template controls

Use the shipping `ControlTemplate` resources rather than hand-building chrome:

| Template key | For |
|---|---|
| `AnonGeeWindowTemplate` | Standard tool window — Charcoal header, 3px Vivid Red rule, white scroll content, Off White footer |
| `AnonGeeDialogTemplate` | Fixed-width modal — header, accent rule, content, Cancel(Ghost)/Confirm(Primary) action bar |
| `DockablePanelTemplate` | `IDockablePaneProvider` compact panel, 2px accent rule, single column |

**Header & footer layout.**
- The **header** carries only the tool title (`TextH2OnDark`) on the Charcoal band — keep it clean, no metadata.
- The **live count / status metadata** (`x:Name="LiveCount"`) lives in the **footer status row**, right of the badges and left of the Close button (`TextCaption`, Mid Grey). Do **not** place the count in the header. The status badge (Info/Success/Error) and live count sit together so all transient state is in one place.

### 12.7 WPF ControlTemplate Constraints

Validated constraints discovered during **OneFilterParameter v3.0** development (June 2026). These are hard rules, not preferences.

#### A. Never use StaticResource on root Window attributes

```xml
<!-- WRONG — XamlReader resolves Window attributes BEFORE Window.Resources is parsed -->
<Window Background="{StaticResource BrushPureWhite}" ...>
    <Window.Resources>...</Window.Resources>

<!-- CORRECT — use literal values on the root element -->
<Window Background="White" FontFamily="JetBrains Mono, Source Serif 4, Inter, Segoe UI, Calibri" ...>
    <Window.Resources>...</Window.Resources>
```

`XamlReader.Load()` resolves root `<Window>` attribute expressions before the `Window.Resources` block is parsed. Any `{StaticResource}` or `{DynamicResource}` reference on a `Window` attribute (Background, FontFamily, Foreground, etc.) throws at parse time. Use literal values only on the `<Window>` element itself; all child elements inside `Window.Resources` can use resource references freely.

#### B. Always use the inline theme strategy

Runtime injection (`window.Resources.MergedDictionaries.Add(...)` after `XamlReader.Load()`) does not cause `DynamicResource` references in Style Setters to resolve inside Revit's pyRevit WPF sandbox. The only reliable strategy is to inline all theme content directly under `<Window.Resources>` before loading. The inline copy must be verbatim — paste from `Resources/*.xaml` in merge order: Colors → Typography → Controls → Panels → Icons.

#### C. ComboBox editable mode requires PART_EditableTextBox in the ControlTemplate

If `IsEditable="True"` is set on a ComboBox but the ControlTemplate does not contain a `TextBox x:Name="PART_EditableTextBox"`, the editable mode silently fails — the control renders but users cannot type. The standard InputComboBox ControlTemplate must include both parts:

```xml
<!-- Required named parts for editable ComboBox -->
<ContentPresenter x:Name="ContentSite" .../>       <!-- shows selection in read-only mode -->
<TextBox x:Name="PART_EditableTextBox" .../>        <!-- activated when IsEditable=True -->

<!-- IsEditable trigger swaps them -->
<Trigger Property="IsEditable" Value="True">
    <Setter TargetName="PART_EditableTextBox" Property="Visibility" Value="Visible"/>
    <Setter TargetName="ContentSite"          Property="Visibility" Value="Hidden"/>
</Trigger>
```

Also name the Popup `PART_Popup` (not `Popup`) to match WPF's expected part name.

#### D. Always add an implicit ComboBoxItem style

Without an implicit `<Style TargetType="ComboBoxItem">` (no `x:Key`), dropdown items inherit the ambient Foreground from the system theme — which can be white-on-white inside Revit's dark shell. Add a keyless ComboBoxItem style after InputComboBox:

```xml
<Style TargetType="ComboBoxItem">
    <Setter Property="Foreground" Value="{StaticResource BrushCharcoalBlack}"/>
    <Setter Property="Padding"    Value="8,5"/>
    <Setter Property="MinHeight"  Value="28"/>
</Style>
```

#### E. TextBox ControlTemplate — never use Margin="{TemplateBinding Padding}" vertically

A pattern like:

```xml
<Border Height="36">
    <ScrollViewer x:Name="PART_ContentHost" Margin="{TemplateBinding Padding}"/>
</Border>
```

…with `Padding="10,8"` leaves the ScrollViewer only 20px tall (36 − 16), clipping the rendered text. Fix: use a fixed horizontal margin only and let the ScrollViewer center vertically.

```xml
<!-- CORRECT -->
<Border>  <!-- no fixed Height; use MinHeight on the Style -->
    <ScrollViewer x:Name="PART_ContentHost"
                  Margin="8,0"
                  VerticalAlignment="Center"/>
</Border>
```

Set `MinHeight="32"` on the Style instead of a fixed `Height`. The ScrollViewer's `VerticalAlignment="Center"` positions text correctly inside the Border regardless of its actual height.

#### F. Use focus trigger IsKeyboardFocusWithin, not IsFocused

`IsFocused` on a ComboBox does not fire when a child TextBox has keyboard focus. Use `IsKeyboardFocusWithin` for all focus-state border color triggers on container controls (ComboBox, ListBox, GroupBox). `IsFocused` is correct only for leaf controls like a standalone TextBox.

#### G. DataGrid data binding — use `__slots__` + ArrayList + ItemsSource (not INPC)

DataTemplate bindings to Python `@property` objects on classes that implement `INotifyPropertyChanged` fail silently in CPython 3 / Python.NET 3 — bindings return empty strings or the template instantiates without errors but with blank cells. The reliable pattern uses a plain `__slots__` class with no INPC, a `System.Collections.ArrayList`, and `DataGrid.ItemsSource`:

```python
from System.Collections import ArrayList

class PreviewItem:
    __slots__ = ['ElementId', 'FamilyName', 'TypeName',
                 'FilterValue', 'EditPreview', 'IsSelected', 'InFilter', 'Element']
    def __init__(self, ...):
        self.IsSelected = True   # Python bool works with DataTrigger (see §L)
        self.InFilter   = True   # internal visibility flag; not bound to any column

def refresh():
    items = ArrayList()
    for item in state["preview_items"]:
        if item.InFilter:          # only show rows that passed the filter
            items.Add(item)
    preview_list.ItemsSource = None  # force WPF to flush all row containers
    preview_list.ItemsSource = items # recreate rows so updated IsSelected is re-read
```

**Why `ItemsSource = None` first?** WPF DataGrid may reuse existing row containers when the same Python objects appear in a new collection. Setting `ItemsSource = None` forces the DataGrid to destroy and recreate all rows, ensuring `DataTrigger` bindings re-read fresh values.

**Slot names must exactly match XAML binding paths.** `{Binding FamilyName}` requires a slot (or property) named `FamilyName`. Python attribute names are case-sensitive.

#### H. DataGrid selection colors — override `SystemColors` keys in `DataGrid.Resources`

WPF DataGrid uses `SystemColors.HighlightBrush` (system blue) and `SystemColors.HighlightTextBrush` (white) for selected rows. These are applied by the DataGrid's visual state manager at a level that overrides `RowStyle` trigger backgrounds. Override them at the DataGrid scope by redefining the system color keys inside `DataGrid.Resources`:

```xml
<DataGrid ...>
    <DataGrid.Resources>
        <!-- Scoped override — only affects this DataGrid, not the rest of the window -->
        <SolidColorBrush x:Key="{x:Static SystemColors.HighlightBrushKey}"                      Color="#FECACA"/>
        <SolidColorBrush x:Key="{x:Static SystemColors.HighlightTextBrushKey}"                  Color="#141414"/>
        <SolidColorBrush x:Key="{x:Static SystemColors.InactiveSelectionHighlightBrushKey}"     Color="#FECACA"/>
        <SolidColorBrush x:Key="{x:Static SystemColors.InactiveSelectionHighlightTextBrushKey}" Color="#141414"/>
    </DataGrid.Resources>
    ...
</DataGrid>
```

This is the only mechanism that reliably prevents white text on selection without a full DataGrid ControlTemplate override. Also set `Foreground=BrushCharcoalBlack` on `DataGrid.CellStyle` as a default to ensure text stays dark even in partially themed scenarios.

#### I. `InputCheckBox` ControlTemplate — always target named inner elements in triggers

The `CheckBox.Background` dependency property is **not** the background of the inner `Border` inside a custom ControlTemplate. They are separate objects. An `IsChecked=True` trigger with no `TargetName` sets `CheckBox.Background`, which has no visual effect if the template's `Border` has a hardcoded `Background` attribute.

**Incorrect (invisible tick, border stays white):**
```xml
<Trigger Property="IsChecked" Value="True">
    <Setter TargetName="CheckMark" Property="Visibility" Value="Visible"/>
    <Setter Property="Background">          <!-- sets CheckBox.Background — does nothing visible -->
        <Setter.Value><SolidColorBrush Color="{StaticResource ColorVividRed}"/></Setter.Value>
    </Setter>
</Trigger>
```

**Correct (red box, white tick visible):**
```xml
<!-- Border must carry x:Name="CheckBoxBorder" -->
<Trigger Property="IsChecked" Value="True">
    <Setter TargetName="CheckMark"      Property="Visibility" Value="Visible"/>
    <Setter TargetName="CheckBoxBorder"  Property="Background" Value="{StaticResource BrushVividRed}"/>
</Trigger>
<Trigger Property="IsMouseOver" Value="True">
    <Setter TargetName="CheckBoxBorder"  Property="BorderBrush" Value="{StaticResource BrushVividRed}"/>
</Trigger>
```

The same rule applies to ALL named child elements in a ControlTemplate: any property you want to change in a trigger must be targeted by `TargetName`.

#### J. Prefer `DataTrigger` over `ControlTemplate.Trigger` for Python data bindings

`ControlTemplate.Trigger Property="IsChecked"` watches the `CheckBox.IsChecked` dependency property (`Nullable<bool>`). Python `bool` (`True`/`False`) is not reliably converted to `Nullable<bool>` through the Python.NET 3 TypeDescriptor binding path — the trigger may never fire even when the bound source is `True`.

`DataTrigger Binding="{Binding IsSelected}" Value="True"` bypasses the control property entirely and reads the data item's Python attribute directly. WPF converts `Value="True"` (string) to the bound type via `TypeConverter`, which correctly handles Python.NET 3 `bool` → `System.Boolean` comparison.

**Preferred pattern for a visual indicator column (tick-box display):**

```xml
<DataGridTemplateColumn Header="" Width="36">
    <DataGridTemplateColumn.CellTemplate>
        <DataTemplate>
            <Border Width="16" Height="16" CornerRadius="3"
                    HorizontalAlignment="Center" VerticalAlignment="Center" BorderThickness="1">
                <Border.Style>
                    <Style TargetType="Border">
                        <Setter Property="Background"  Value="White"/>
                        <Setter Property="BorderBrush" Value="#E2E4EA"/>
                        <Style.Triggers>
                            <DataTrigger Binding="{Binding IsSelected}" Value="True">
                                <Setter Property="Background"  Value="#E02020"/>
                                <Setter Property="BorderBrush" Value="#E02020"/>
                            </DataTrigger>
                        </Style.Triggers>
                    </Style>
                </Border.Style>
                <Path Data="M2,7 L5,10 L11,3" Stroke="White" StrokeThickness="1.5"
                      HorizontalAlignment="Center" VerticalAlignment="Center">
                    <Path.Style>
                        <Style TargetType="Path">
                            <Setter Property="Visibility" Value="Collapsed"/>
                            <Style.Triggers>
                                <DataTrigger Binding="{Binding IsSelected}" Value="True">
                                    <Setter Property="Visibility" Value="Visible"/>
                                </DataTrigger>
                            </Style.Triggers>
                        </Style>
                    </Path.Style>
                </Path>
            </Border>
        </DataTemplate>
    </DataGridTemplateColumn.CellTemplate>
</DataGridTemplateColumn>
```

This avoids `DataGridCheckBoxColumn` (poor Python.NET 3 compatibility) and `InputCheckBox` style (IsChecked trigger issues) entirely.

#### K. DataGrid row click / Shift+click selection via MouseLeftButtonUp

Because `refresh_preview_display()` resets `ItemsSource` (which clears DataGrid row selection), `SelectionChanged` cannot be used as a toggle mechanism — it creates a feedback loop where a selection triggers a refresh that clears the selection, breaking range selection anchors.

Use `DataGrid.MouseLeftButtonUp` instead: it fires **after** the DataGrid processes the click, so the Shift modifier state is readable. Walk the visual tree upward from `args.OriginalSource` to find the `DataGridRow`, then toggle `item.IsSelected` directly in Python:

```python
from System.Windows.Media import VisualTreeHelper          # PresentationCore — NOT System.Windows
from System.Windows.Controls import DataGridRow as WpfDataGridRow

def on_row_click(sender, args):
    if state.get("_refreshing"):
        return
    try:
        from System.Windows.Input import Keyboard, ModifierKeys
        dep_obj = args.OriginalSource
        while dep_obj is not None:
            if isinstance(dep_obj, WpfDataGridRow):
                item = dep_obj.Item
                if hasattr(item, 'InFilter') and item.InFilter:
                    visible = [i for i in state["preview_items"] if i.InFilter]
                    idx = visible.index(item)
                    if bool(Keyboard.Modifiers & ModifierKeys.Shift) and state["last_idx"] >= 0:
                        lo, hi = min(state["last_idx"], idx), max(state["last_idx"], idx)
                        for i in range(lo, hi + 1):
                            visible[i].IsSelected = True
                    else:
                        item.IsSelected = not bool(item.IsSelected)
                        state["last_idx"] = idx
                    refresh_preview_display()
                return
            dep_obj = VisualTreeHelper.GetParent(dep_obj)
    except Exception:
        pass

preview_list.MouseLeftButtonUp += on_row_click
```

The `_refreshing` guard (set in `refresh_preview_display()`) prevents this handler from firing during the `ItemsSource = None → items` reset cycle.

#### L. Real-time filter gate — always require explicit Apply before debounced updates

Without a gate, the debounced filter callback fires as soon as the user changes the filter parameter dropdown. At that point the value field is still empty, so the filter matches nothing and the preview goes blank — confusing UX.

Gate the callback with a `filter_applied_once` flag:

```python
state["filter_applied_once"] = False   # reset on Load Parameters

def realtime_filter_update():
    if not state.get("filter_applied_once"):
        return   # wait for explicit Apply
    # ... run filter ...

def on_apply_filter(...):
    state["filter_applied_once"] = True
    # ... run filter ...
```

After the first Apply, subsequent edits to the value field trigger live re-filtering — which is good UX since the user has already configured the filter parameter and operator.

#### N. Custom title-bar chrome — `WindowStyle="None"` pattern

When a tool needs a fully branded Charcoal Black title bar (no native Windows chrome), use `WindowStyle="None"` with `ResizeMode="CanResizeWithGrip"`.

**Required Window attributes (all literals — see §A):**
```xml
<Window WindowStyle="None"
        ResizeMode="CanResizeWithGrip"
        Background="#FF141414"   <!-- prevents white bleed behind DockPanel header -->
        ...>
```

**Header layout — separate drag zone from chrome buttons:**
```xml
<!-- Outer Grid: Col 0 = drag area (*), Col 1 = chrome buttons (Auto) -->
<Grid DockPanel.Dock="Top" Background="{StaticResource BrushCharcoalBlack}">
    <Grid.ColumnDefinitions>
        <ColumnDefinition Width="*"/>
        <ColumnDefinition Width="Auto"/>
    </Grid.ColumnDefinitions>
    <!-- x:Name="HeaderDrag" — MouseLeftButtonDown → window.DragMove() wired in script.py -->
    <Grid Grid.Column="0" x:Name="HeaderDrag" Margin="16,13,8,13">
        <!-- title + live count TextBlocks here -->
    </Grid>
    <!-- Chrome buttons StackPanel — separate subtree, events do NOT bubble to HeaderDrag -->
    <StackPanel Grid.Column="1" Orientation="Horizontal" VerticalAlignment="Stretch">
        <Button x:Name="BtnMinimize" Style="{StaticResource ButtonChrome}" VerticalAlignment="Stretch"/>
        <Button x:Name="BtnMaximize" Style="{StaticResource ButtonChrome}" VerticalAlignment="Stretch"/>
        <Button x:Name="BtnHeaderClose" Style="{StaticResource ButtonChromeClose}" VerticalAlignment="Stretch"/>
    </StackPanel>
</Grid>
```

**Why separate subtrees?** `DragMove()` is a blocking call — it does not return until the mouse button is released. If `HeaderDrag.MouseLeftButtonDown` were wired on the *outer* Grid, a click on a chrome button would trigger `DragMove()` before the button's `Click` event, blocking it. Placing the drag handler only on the left column (Col 0) means chrome button clicks stay in Col 1 and never reach the drag handler.

**`ButtonChrome` / `ButtonChromeClose` style specs:**
- Independent styles (no `BasedOn=ButtonBaseStyle`) to avoid inheriting `Height="28"`
- `Width="46"`, no explicit Height (stretch to fill header)
- `Background="Transparent"`, hover: `#26FFFFFF` (subtle white at 15% opacity)
- `ButtonChromeClose` hover: `BrushVividRed` (red close affordance, consistent with macOS/VS Code)
- Path icons: minimize `M0,5 L10,5`, maximize/restore `M0.5,0.5 L9.5,0.5 L9.5,9.5 L0.5,9.5 Z`, close `M0,0 L10,10 M10,0 L0,10` — all wrapped in `<Viewbox Width="10" Height="10">`, Stroke `#FFFFFFFF`, StrokeThickness `1.5–1.8`

**Minimize — use Win32, not `WindowState.Minimized`:**
```python
import ctypes
from System.Windows.Interop import WindowInteropHelper

def _on_minimize(self, sender, args):
    hwnd = int(WindowInteropHelper(self.window).Handle)
    ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE = 6
```
`WindowState = Minimized` propagates to Revit's host window in pyRevit's `ShowDialog()` execution context because WPF inherits the minimize from its process-level window management. Win32 `ShowWindow` on the window's own HWND minimizes only that specific window.

**Maximize/restore toggle (safe via WPF):**
```python
def _on_maximize(self, sender, args):
    if self.window.WindowState == WindowState.Maximized:
        self.window.WindowState = WindowState.Normal
    else:
        self.window.WindowState = WindowState.Maximized
```

#### M. OneFilterParameter — validated feature state (June 2026)

| Feature | Status |
|---|---|
| Window opens in Revit, inline theme loads | ✅ |
| Load Parameters → DataGrid populates | ✅ |
| Filter Param column updates on Confirm | ✅ |
| Edit Preview column updates on Confirm | ✅ |
| Apply Filter → hides non-matching rows | ✅ |
| Apply Filter → narrows Edit Param dropdown to filtered elements | ✅ |
| Real-time filter after Apply Filter clicked | ✅ |
| Row click toggles tick-box; Shift+click range-selects | ✅ |
| Select All / Clear buttons toggle visible rows only | ✅ |
| Row hover (light pink `#FDECEA`) | ✅ |
| Row selection (brand red `#FECACA`, dark text) | ✅ |
| Custom 8 px thin scrollbar | ✅ |
| Tick-box: unchecked = white border box; checked = red box + white ✓ | ✅ |

#### O. Rounded borders on content-hosting controls — draw the stroke on top

A single rounded `Border` that both *fills* and *strokes* **and** hosts a `ScrollViewer` (TextBox `PART_ContentHost`, ListBox items) renders an **uneven border** — the bottom edge looks thinner/flatter — because the scroller's rectangular content area ignores `CornerRadius` and rides over the inner edge where the corner curve gives least clearance. Buttons/ComboBoxes are unaffected because their content is inset by `Padding` and never touches the stroke.

**Rule:** for `InputTextBox` and `InputListBox` (and any bordered scroller), split the template into three layers inside a `Grid`:

```xml
<Grid SnapsToDevicePixels="True">
    <Border x:Name="Bg" Background="{TemplateBinding Background}" CornerRadius="5"/>
    <!-- content: ScrollViewer / PART_ContentHost / ItemsPresenter -->
    <Border x:Name="Stroke" CornerRadius="5"
            BorderBrush="{TemplateBinding BorderBrush}"
            BorderThickness="{TemplateBinding BorderThickness}"
            IsHitTestVisible="False"/>   <!-- drawn last → uniform on all 4 edges -->
</Grid>
```

Focus/disabled triggers target `Stroke` (border color/thickness) and `Bg` (fill), not the old single `Root` border. The TextBox **must** still keep its `ScrollViewer x:Name="PART_ContentHost"`. ListBox content gets `Margin="{TemplateBinding BorderThickness}"` so it sits inside the stroke. This is the reference pattern shipped in every tool and in Dev → Brand Guidelines.

#### P. ScrollBar — style BOTH orientations, and editable ComboBox needs `PART_EditableTextBox`

Two separate traps that surface together on a populated dropdown:

- **The implicit `ScrollBar` style must define both orientations.** A style that only templates the vertical bar (fixed `Width=8`, vertical `Track`) makes a **horizontal** scrollbar render as a broken thin strip that still reacts to hover/drag. Drive the template from a `Style.Triggers` block keyed on `Orientation`: *Vertical* → `Width=8`, vertical `Track` (`IsDirectionReversed=True`, `PageUp/PageDownCommand`); *Horizontal* → `Height=8`, horizontal `Track` (`PageLeft/PageRightCommand`), thumb `Margin="0,2"`. Same thin 8px Silver-Steel thumb (Charcoal hover, Vivid Red drag) for both.
- **ComboBox dropdown sizes to its content (min = combo width).** Do **not** pin the popup to `Width="{TemplateBinding ActualWidth}"` — that clips long items. Instead put `MinWidth="{TemplateBinding ActualWidth}"` + a `MaxWidth` cap (≈520) on the popup's content `Border`, and `HorizontalScrollBarVisibility="Hidden"` on its `ScrollViewer`. **Hidden** lets the items measure wide so the popup grows to the widest item; **Disabled** would clamp them back to the combo width (and re-introduce the broken horizontal bar). Net: the dropdown is never narrower than the combo and never spawns a horizontal scrollbar.
- **Editable ComboBox (`IsEditable=True`) requires a `TextBox x:Name="PART_EditableTextBox"` in the template** (§12.7.C). A full-area `ToggleButton` (bound to `IsDropDownOpen`) under the content opens the list; an `IsEditable` trigger swaps the `PART_EditableTextBox` (visible) for the `ContentSite` `ContentPresenter` (collapsed). Reference implementation: Advance → Multi Filter Parameter `ui.xaml`.
- **To load dependent fields off a ComboBox selection, handle `DropDownClosed` (+ `LostFocus`), never `SelectionChanged`.** `SelectionChanged` fires for every item you arrow-/scroll-past while the dropdown is open, so dependent fields get loaded for a half-highlighted, un-committed item (values bleed across selections). `DropDownClosed` fires once on commit; add `LostFocus` so a typed/autocompleted value also commits when focus leaves. **Guard the handler to no-op when the value is unchanged** (track the last-applied text per control) — otherwise the second trigger (`DropDownClosed` then `LostFocus`) wipes the dependent fields the user just set. Programmatic `Items.Clear()/Add()` must not fire these (they don't open/close the dropdown or move focus). Reference: Multi Filter Parameter `confirm_filter_row` / `confirm_edit_row`.

> **Marshalling note (not a template rule, but it bites here):** build `List[ElementId]` for `Selection.SetElementIds` with `.Add()` in a loop — `List[ElementId](python_list)` throws *"No method matches given arguments for List\`1..ctor"* in CPython 3/pythonnet (§12.9.4).

---

## 12.8 Modeless (Non-Blocking) Window Architecture

A **modeless** tool opens with `window.Show()` — Revit remains interactive while the window is visible. Use this pattern for tools where the user needs to navigate the model, select elements, or inspect views while the UI is open.

> **Default is modal (`ShowDialog()`).** Only upgrade to modeless when the workflow genuinely requires Revit to remain interactive. Modeless adds complexity (thread bridging, state management) that modal tools avoid entirely.

### 12.8.1 When to use each mode

| Mode | Call | Revit interactive? | Use when |
|---|---|---|---|
| **Modal** | `window.ShowDialog()` | No | Self-contained action — no Revit navigation needed |
| **Modeless** | `window.Show()` | Yes | User must navigate views, pick elements, or inspect model while UI is open |

### 12.8.2 Mandatory thread-bridging via `IExternalEventHandler`

`window.Show()` runs WPF on a **separate thread**. All Revit API calls (reads and writes) must occur on Revit's primary thread. Calling the Revit API directly from a WPF event handler crashes Revit.

**Architecture (CPython 3):**

```python
#! python3
from Autodesk.Revit.DB import Transaction
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent

class ApplyHandler(IExternalEventHandler):
    def __init__(self):
        self.data = {}          # shared state: set from WPF thread, read on Revit thread

    def Execute(self, app):
        doc = app.ActiveUIDocument.Document
        # All DB reads/writes here — runs on Revit's primary thread
        t = Transaction(doc, "AnonGee · My Tool")
        t.Start()
        try:
            # ... use self.data set by WPF button handler ...
            t.Commit()
        except Exception:
            t.RollBack()

    def GetName(self):
        return "AnonGee_ApplyHandler"

# --- entry point ---
handler   = ApplyHandler()
ext_event = ExternalEvent.Create(handler)

dialog = MyDialog(ext_event, handler)
dialog.show()   # calls window.Show(), not ShowDialog()
```

**WPF button handler (on WPF thread):**
```python
def _on_apply(self, sender, args):
    self._handler.data["source_view"] = self._source_combo.SelectedItem
    self._handler.data["targets"]     = self._get_checked_views()
    self._ext_event.Raise()    # queues Execute() onto Revit's event loop
```

### 12.8.3 `WindowInteropHelper` anchoring

Anchor the modeless window to Revit's main window so it stays on top without blocking:

```python
from System.Windows.Interop import WindowInteropHelper
import ctypes

class MyDialog(object):
    def __init__(self, ext_event, handler):
        ...
        self._ext_event = ext_event
        self._handler   = handler

    def show(self):
        self.window.Show()
        # Anchor to Revit main window AFTER Show()
        helper = WindowInteropHelper(self.window)
        helper.Owner = __revit__.MainWindowHandle
```

### 12.8.4 CPython 3 import restrictions (modeless)

**NEVER import pyRevit modules** in a modeless CPython 3 script:

| Forbidden import | Reason |
|---|---|
| `from pyrevit import revit` | IronPython dependency — crashes CPython 3 engine |
| `from pyrevit import forms` | Same |
| `from pyrevit.revit import events` | Same |

Use only:
- `Autodesk.Revit.DB.*`, `Autodesk.Revit.UI.*`
- `System.*`, `System.Windows.*`
- Standard Python stdlib (`os`, `ctypes`, `threading`, etc.)

### 12.8.5 State management — shared data dict

Pass data between the WPF thread and the Revit thread via a mutable dict on the handler:

```python
# WPF thread (button click):
self._handler.data["view_id"] = selected_view.Id

# Revit thread (Execute):
view = doc.GetElement(self.data["view_id"])
```

Avoid complex locks for simple scalar/list assignments — Python's GIL protects basic dict writes. For large state mutations, set a single "ready" flag last.

### 12.8.6 Validated rollout strategy

> Test modeless on ONE tool first. If the `IExternalEventHandler` bridge works correctly in the target Revit + pyRevit version, port remaining tools. If it fails (e.g., `ExternalEvent.Create()` returns null or `Raise()` is silently dropped), fall back to modal (`ShowDialog()`).

---

## 12.9 CPython 3 Engine Stability

> A circulating "best practices" list is **mostly correct but has one misleading item and omits the single biggest cause of CPython3 crashes.** This section is the corrected, authoritative version. A genuine engine crash forces a full Revit restart, so prevention is the whole game.

### 12.9.1 The hard truth: you cannot catch a native crash

A real engine crash is a **`System.AccessViolationException` / Corrupted-State Exception (CSE)**. By default in .NET 4+, CSEs **bypass every managed handler** — no `except Exception:`, no `except System.Exception:`, and no `try/finally` will catch them. Therefore:

- `try/except` protects you from **Python and .NET *logic* errors** (and keeps tracebacks clean so the engine stays usable). It does **NOT** protect against the hard faults that restart Revit.
- The only defense against native faults is to **never trigger one**: correct marshaling, valid element references, no stale transactions, no use-after-free of .NET objects.
- **Misleading claim to reject:** "catch `System.Exception` explicitly for extra safety." pythonnet already surfaces .NET exceptions as ordinary Python exceptions, so `except Exception:` already catches them. Adding `except System.Exception:` is *redundant*, not a crash shield. (It is still fine to split them when you want to report *which side* failed — see the engine health-check tool.)

### 12.9.2 The persistent engine — the real crash source

The CPython 3 engine is **reused across every button click in a session.** Module globals, `sys.modules`, and `+=` event subscriptions all persist. This is the omission in most guides and the cause of most real crashes:

| Trap | Mechanism | Rule |
|------|-----------|------|
| **Handler accumulation** | Each runtime `btn.Click += self._h` *adds another* subscription. Click N times → handler fires N× against possibly-dead objects → crash | Build a fresh dialog object per run inside `run()`/`main()` (never subscribe at module scope) |
| **Delegate / window GC** | If the only reference to a window or `+=` delegate is a local that falls out of scope, Python GCs it while .NET still calls it → callback into freed memory → crash | Keep window + handlers on `self`; **for modeless windows hold a module-level reference** or it dies the instant `run()` returns (see §12.8) |
| **Stale module cache** | `sys.modules` persists — edited `lib\` modules don't reload between runs | Reload the engine during dev; version-bump shared modules |
| **Global state leak** | Module-level globals survive across runs | Put all state in `run()`/`main()` — for correctness, not just style |

### 12.9.3 Stripped stdlib

This engine ships a **partial stdlib path** — confirmed *missing*: `csv`, `re` (present: `os`, `traceback`, `tempfile`, `zipfile`, `json`, numpy, openpyxl). Never assume a pure-Python stdlib module exists. Either probe with the engine health-check tool, or write an inline fallback (see Export Schedule's `_parse_tsv_row()` and `_strip_unit()`). Third-party modules require the extension's own `lib\` + `path_resolver.update_paths()`.

### 12.9.4 Confirmed-good practices (keep these)

- **Marshal Python lists to `List[T]`** before passing to Revit API methods — raw `[]` is a fatal marshaling fault across the pythonnet bridge.
- **Build .NET `Object[]` with `System.Array.CreateInstance(System.Object, n)`, not `System.Array[object]`.** The Python builtin `object` is not reliably accepted as a generic type argument in this engine and raises `TypeError: type expected` (hit during COM `InvokeMember` calls for Excel→PDF). Use a small `_obj_arr(*items)` helper.
- **`try/finally` around every Transaction**, gated: `if t.HasStarted() and not t.HasEnded(): t.RollBack()`. Never leave a transaction orphaned.
- **All logic inside `main()`/`run()`** — never heavy work at module scope (it runs at load and leaks into the persistent engine).
- **Module-level guard** at the entry point so a logic error reports cleanly instead of leaving the engine in a half-state.
- **Do not import pyRevit IronPython modules** (`pyrevit.revit`, `pyrevit.forms`, …) in CPython 3 (see §12.8.4).

### 12.9.5 Engine health-check tool

`AnonGee.tab\dev.panel\CPython3 engine.pushbutton` is the canonical diagnostic: it reports **fresh-vs-reused** engine (a counter stashed on `sys` survives across runs, resets on engine restart), lib + stdlib availability, and a live Revit-bridge probe. If you see *any* output the engine is alive; a high reuse count when a tool misbehaves points at accumulated state — reload the engine.

---

## 13. Design Tokens & Theme Architecture

### 13.1 Token Tiers

The system uses a three-tier token model. Higher tiers reference lower tiers; **components never reference primitives directly.**

```
Tier 1 — Primitive   ColorVividRed (#E02020), ColorCharcoalBlack, ColorMidGrey …
   ↓ referenced by
Tier 2 — Semantic     BrushInputFocusBorder, BrushDisabledForeground,
                      BrushTableHeaderBackground, BrushActiveBadgeBackground …
   ↓ referenced by
Tier 3 — Component    ButtonPrimary, InputTextBox, SectionGroup, AnonGeeDialogTemplate …
```

This is why the palette can stay fixed while behavior evolves: a new component composes existing semantic tokens; it never invents a color.

### 13.2 ResourceDictionary Architecture

```
pyZaid.extension/Resources/
├── AnonGeeTheme.xaml     ← master merge (Colors→Typography→Controls→Panels→Icons)
├── Colors.xaml           ← Tier 1 colors + Tier 2 semantic brushes
├── Typography.xaml       ← font families, sizes, named TextBlock styles
├── Controls.xaml         ← buttons, inputs, selection controls, cards, elevation
├── Panels.xaml           ← window/dialog/dockable templates, GroupBox, divider
└── Icons.xaml            ← Lucide Path geometries
```

**Merge order matters:** Colors and Typography must precede Controls and Panels, which reference them.

### 13.3 Master merge file

```xml
<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    <ResourceDictionary.MergedDictionaries>
        <ResourceDictionary Source="Colors.xaml"/>
        <ResourceDictionary Source="Typography.xaml"/>
        <ResourceDictionary Source="Controls.xaml"/>
        <ResourceDictionary Source="Panels.xaml"/>
        <ResourceDictionary Source="Icons.xaml"/>
    </ResourceDictionary.MergedDictionaries>
</ResourceDictionary>
```

### 13.4 Enforcement Rules (PR-blocking)

- **No hardcoded colors.** Every color reference uses a `{StaticResource}` / `{DynamicResource}` brush key from `Colors.xaml`. Inline hex outside `Colors.xaml` is rejected.
- **No inline font declarations.** Font family/size come only from `FontSans`/`FontMono` and the size tokens.
- **No default WPF button chrome.** Every `Button` carries a named style.
- **Dialogs are `CenterOwner`** with the Revit window as `Owner`.
- **Dockable panels are single-column**, 240–360px.
- **Inline validation only** — no `MessageBox` for field errors.
- **Disabled states stay visible.**
- **All technical output uses `TextCode`** (monospace), never proportional.
- **Inline theme copies are verbatim** (§12.3) — divergence from `Resources/*.xaml` is a defect.

---

## 14. Audience Profiles

The suite serves three professionals plus the wider modern audience. Design decisions are validated against their needs.

| Profile | What they value | Design implication |
|---|---|---|
| **Structural Engineer** | Correctness, traceable counts, repeatability | Show exact element counts; name grids/levels; precise error causes; compact data tables |
| **Architect** | Clarity, visual order, fast iteration | Clean hierarchy, generous region spacing, obvious primary action, restrained color |
| **BIM Modeler / Coordinator** | Speed, batch operations, status visibility | Keyboard flow, multi-select, progress on long ops, dockable persistent panels |
| **Modern audience (broad)** | Polish, responsiveness, trust | Consistent components, smooth ≤200ms motion, no system-chrome leakage, professional copy |

Shared truth across all four: **they will not trust a tool that hides what it is doing.** Visible state (§1.2, §11) is the through-line.

---

## 15. Governance & Contribution

### 15.1 Versioning

The design system is versioned with **semantic versioning**, independent of any single tool:

- **Major** — a breaking token rename/removal, or a palette change (palette changes require explicit sign-off and are not expected).
- **Minor** — additive: new tokens, components, patterns.
- **Patch** — fixes, doc corrections, value reconciliation.

This document is **v3.0** (major restructure; palette unchanged). The shipping `Resources/*.xaml` headers are tagged `v3.0` to match, kept in lockstep with the system version on each edit.

### 15.2 Adding to the System

1. Check whether an existing token/component already solves it. Reuse beats addition.
2. New colors are almost never the answer — compose existing semantic tokens.
3. New components are defined in the appropriate `Resources/*.xaml`, documented here, and only then used by a tool.
4. New icons come from Lucide, exported per §7, added to `Icons.xaml`.

### 15.3 Contribution Checklist (PR)

- [ ] No hardcoded hex/font outside the token files.
- [ ] Every control uses a named style/template.
- [ ] Dialog is `CenterOwner` with Revit `Owner`; modal sizing per §5.5.
- [ ] Inline validation, visible disabled states, monospace output.
- [ ] Contrast verified for any new fg/bg pairing (§10).
- [ ] Long operations show progress; destructive actions confirm.
- [ ] If theme is inlined, the block is a verbatim copy of `Resources/*.xaml`.
- [ ] `bundle.yaml` and `icon.png` present; voice per §8.

### 15.4 Open Reconciliation Items

| Item | Status |
|---|---|
| Ribbon tab `pyZaid.tab` vs brand "AnonGee BIM Tools" | To reconcile (§1.3) |
| Re-tag `Resources/*.xaml` headers `v2.0 → v3.0` | ✅ Done |
| Build check: inline theme copies vs shared dictionaries | Proposed (§12.3) |
| Caption size prose `8.25 → 9` | ✅ Fixed in this doc |

---

## 16. Document & Report Standards

All generated documents — export summaries, model reports, script logs — follow this layout.

### Header
- Left: **AnonGee BIM Tools** wordmark, Source Serif 4 SemiBold, Charcoal Black.
- Right: project/document title, Source Serif 4 Regular, Mid Grey.
- Below: full-width 3px Vivid Red rule.

### Body
- Primary font: Source Serif 4 Regular, 11pt, Mid Grey.
- Headings: Source Serif 4 SemiBold/Bold, Charcoal Black.
- Code/data: JetBrains Mono, 10pt, Charcoal Black background.
- Tables per §9.8.

### Footer
- Left: classification (`Internal · Confidential`).
- Center: page number.
- Right: date in `DD MMM YYYY`.
- All footer text: Source Serif 4 Regular, Caption, Mid Grey.

### 16.1 Spreadsheet / Schedule Export (Excel)

Applies to any tool that writes `.xlsx` (e.g. Export Schedule). Excel cannot resolve WPF font-fallback chains and is not a layout engine, so the brand maps to fixed values plus a true-AutoFit pass.

**Typeface.** Data cells, headers and title use the primary brand face **Source Serif 4**. Excel cannot resolve fallback chains and substitutes silently if a font is absent, so **install Source Serif 4 on export hosts**; the documented Excel fallback is **Georgia** (the brand's guaranteed serif, always present on Windows). Any genuinely code/ID-like column may use **JetBrains Mono** (→ Consolas fallback), consistent with the "mono = status/code" rule (§4.5).

**Cell styling**

| Band | Rows | Fill | Font | Size / weight | Text color |
|---|---|---|---|---|---|
| **Title** | row 1 (merged across all columns) | Charcoal Black `#141414` | Source Serif 4 | 13pt Bold | White `#FFFFFF` |
| **Column headers** | the single header row (row 2, or row 3 when Revit emits a blank gap row) | Vivid Red `#E02020` | Source Serif 4 | 10pt Bold | White `#FFFFFF` |
| **Body — odd rows** | data | Pure White `#FFFFFF` | Source Serif 4 | 10pt | Charcoal Black `#141414` |
| **Body — even rows (zebra)** | data | Off White `#F4F4F6` | Source Serif 4 | 10pt | Charcoal Black `#141414` |

- **Borders:** thin, **Silver Steel `#C0C8D8`**, all four sides, every cell.
- **Zebra shading** uses **Off White `#F4F4F6`** (§3.2) — never a red tint. Toggle via the tool's "Zebra Shading" option.

**Alignment**

- **Vertical:** centre — *every* cell, all bands.
- **Horizontal — headers & title:** centre.
- **Horizontal — body:** **numbers (int/float) right-aligned; text/strings left-aligned.** Determine by the cell's stored type *after* unit-stripping, so a value like `"12.5 m³"` becomes the number `12.5` and right-aligns; a type/mark string stays left.

**Number formats** (apply after unit-stripping, to numeric cells only; both right-aligned)

- **Integers:** `#,##,##0` → e.g. `1,00,000`.
- **Floats:** `#,##,##0.000` (3-decimal precision) → e.g. `1,00,000.000`.
- Grouping is **Indian (lakh/crore)** — Excel repeats the leftmost 2-digit group, so the single code `#,##,##0` yields `1,00,000` and `1,00,00,000`. Text cells carry no number format.

**Layout & output**

- **Column widths:** apply *true* Excel `Columns.AutoFit()` (matches double-clicking the column border) — never hand-pad. When Excel is unavailable, fall back to a tight estimate (no `+N` padding; exclude the merged title row; scale ~0.92 for the 10pt body vs Excel's 11pt width unit).
- **Row heights:** **minimum 20 ruler units** for every row (title/headers taller as needed). Do **not** run Excel `Rows.AutoFit()` — it shrinks rows below the 20 minimum; set fixed heights in openpyxl instead.
- **Freeze panes** immediately below the column-header row.
- **Page setup (also governs PDF export):** **Landscape**, **fit all columns to one page wide** (`FitToPagesWide = 1`, `FitToPagesTall = auto`, `Zoom = off`).

**Implementation note.** Build the workbook with **openpyxl** (no Excel needed for the styled `.xlsx`), then run a single Excel-COM "polish" pass for true Auto­Fit + page setup + optional PDF (`ExportAsFixedFormat`). Build COM argument arrays with `System.Array.CreateInstance(System.Object, n)` (§12.9.4).

---

## 17. Brand Don'ts

Non-negotiable across all touchpoints.

- **Do not** render the wordmark in Vivid Red — it is for accents/CTAs, not the name.
- **Do not** use Vivid Red as a large background fill. It is an accent; use Charcoal Black for dark surfaces.
- **Do not** apply more than one semantic state color in the same UI region.
- **Do not** introduce off-palette colors without versioned approval.
- **Do not** use default system/Aero button chrome — every `Button` carries a named style.
- **Do not** abbreviate the brand to `AGT`, `AG`, or `ABIM`.
- **Do not** use emoji in documentation, logs, dialogs, or error states.
- **Do not** set body text in pure black — Charcoal Black for headings, Mid Grey for body.
- **Do not** use Silver Steel as text on white (1.68:1 — fails AA).
- **Do not** hide a disabled control with `Collapsed` — keep it visible and inert.
- **Do not** embed XAML as a Python string in new tools — use a `ui.xaml` file.
- **Do not** block the Revit UI thread for model work — use `Transaction` + `ExternalEvent`.

---

## 18. Appendix — Token Reference

### 18.1 WPF Brush Quick Reference

| Key | Hex | Role |
|---|---|---|
| `BrushVividRed` | `#E02020` | Primary brand / CTA |
| `BrushCharcoalBlack` | `#141414` | Headers, dark surfaces, primary text |
| `BrushSilverSteel` | `#C0C8D8` | Borders, secondary icons, dividers |
| `BrushPureWhite` | `#FFFFFF` | Canvas, card backgrounds |
| `BrushOffWhite` | `#F4F4F6` | Subtle backgrounds, footers |
| `BrushMidGrey` | `#6B7280` | Body text, captions |
| `BrushLightBorder` | `#E2E4EA` | Input borders, card outlines, dividers |
| `BrushSuccessGreen` | `#16A34A` | Success states |
| `BrushCautionAmber` | `#D97706` | Warning states |
| `BrushErrorRed` | `#DC2626` | Error states (not a Vivid Red substitute) |
| `BrushInfoBlue` | `#2563EB` | Informational notices |
| `BrushVividRedHover` / `…Pressed` | `#C41A1A` / `#A81515` | Primary interaction |
| `BrushErrorRedHover` | `#B91C1C` | Danger hover |
| `BrushSecondaryHover` | `#1AE02020` | Outline-button hover fill |
| `BrushGhostHover` | `#E8E8EC` | Ghost/neutral hover |
| `BrushDisabledBackground` / `…Foreground` | `#E2E4EA` / `#C0C8D8` | Disabled controls |

### 18.2 CSS Custom Properties (web / artifact use)

```css
:root {
  /* ── Brand ── */
  --color-vivid-red:       #E02020;
  --color-charcoal-black:  #141414;
  --color-silver-steel:    #C0C8D8;

  /* ── Surfaces & Text ── */
  --color-pure-white:      #FFFFFF;
  --color-off-white:       #F4F4F6;
  --color-mid-grey:        #6B7280;
  --color-light-border:    #E2E4EA;

  /* ── Semantic ── */
  --color-success:         #16A34A;
  --color-caution:         #D97706;
  --color-error:           #DC2626;
  --color-info:            #2563EB;

  /* ── Interaction variants ── */
  --color-vivid-red-hover:    #C41A1A;
  --color-vivid-red-pressed:  #A81515;
  --color-error-red-hover:    #B91C1C;
  --color-vivid-red-10:       rgba(224,32,32,0.10);
  --color-off-white-hover:    #E8E8EC;

  /* ── Typography ── */
  --font-sans:  'JetBrains Mono', 'Source Serif 4', 'Inter', 'Segoe UI', Calibri, monospace;
  --font-mono:  'JetBrains Mono', Consolas, 'Courier New', monospace;
  --text-h1:    1.75rem;   /* 28px */
  --text-h2:    1.375rem;  /* 22px */
  --text-h3:    1rem;      /* 16px */
  --text-body:  0.875rem;  /* 14px */
  --text-small: 0.75rem;   /* 12px */
  --text-code:  0.75rem;   /* 12px */

  /* ── Spacing ── */
  --space-xs: 4px;   --space-sm: 8px;   --space-md: 16px;
  --space-lg: 24px;  --space-xl: 32px;  --space-2xl: 48px; --space-3xl: 64px;

  /* ── Radius ── */
  --radius-sm: 3px;  --radius-md: 5px;  --radius-lg: 8px;  --radius-xl: 10px;

  /* ── Motion ── */
  --motion-fast: 120ms; --motion-standard: 200ms; --motion-slow: 300ms;
  --ease-standard: cubic-bezier(0.33, 0, 0.2, 1);
}
```

---

*AnonGee BIM Tools · Brand & Design System · Version 3.0 · June 2026*
*Confidential. Do not distribute outside the AnonGee product team.*
