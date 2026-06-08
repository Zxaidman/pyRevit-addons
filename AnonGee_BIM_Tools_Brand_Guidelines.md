# AnonGee BIM Tools
## Brand & UI Guidelines

> **Version 2.0** · June 2026 · Confidential — Internal Reference

---

## Table of Contents

1. [Brand Identity](#1-brand-identity)
2. [Logo & Wordmark](#2-logo--wordmark)
3. [Color System](#3-color-system)
4. [Typography](#4-typography)
5. [Spacing & Layout](#5-spacing--layout)
6. [Iconography](#6-iconography)
7. [Voice & Tone](#7-voice--tone)
8. [UI Component Guidelines](#8-ui-component-guidelines)
9. [Document & Report Standards](#9-document--report-standards)
10. [Brand Don'ts](#10-brand-donts)
11. [WPF UI Template Guidelines](#11-wpf-ui-template-guidelines)
12. [Appendix — Token References](#12-appendix--token-references)

---

## 1. Brand Identity

**AnonGee BIM Tools** is a professional suite of structural and architectural BIM automation tools engineered for Autodesk Revit. The product line integrates AI-powered workflows, pyRevit scripting, and model context protocols to deliver precision tooling for the modern BIM professional.

The brand is built on three core principles:

**Precision.** Every output is exact, traceable, and repeatable. The brand never overpromises or speaks loosely about technical outcomes.

**Authority.** AnonGee BIM Tools is the work of a practitioner. The visual language and tone reflect deep domain expertise — not generic software aesthetics.

**Clarity.** Complex workflows are made intelligible. The UI, documentation, and messaging strip away noise and surface what matters.

### Brand Positioning Statement

> *Professional-grade BIM automation, engineered for structural precision.*

### Brand Hierarchy

| Level | Name | Description |
|---|---|---|
| Parent | **AnonGee** | The practitioner identity and studio name |
| Suite | **AnonGee BIM Tools** | The full product suite |
| Products | **AnonGee · [Product Name]** | Individual tools within the suite |

---

## 2. Logo & Wordmark

### Primary Wordmark

```
AnonGee BIM Tools
```

### Construction Rules

- **AnonGee** — Title case only. Never `ANONGEE`, `anongee`, or `Anon Gee`.
- **BIM** — Always uppercase; it is an established industry acronym.
- **Tools** — Title case.
- The wordmark is always set in **Inter SemiBold** when rendered in digital contexts.

### Sub-Product Naming Convention

The **·** (middle dot, U+00B7) is the canonical separator between the brand name and product name. It must be surrounded by a single space on each side.

| Product | Full Display Name |
|---|---|
| Revit MCP Bridge | AnonGee · Revit MCP Bridge |
| Future products | AnonGee · [Product Name] |

### Wordmark on Color

| Background | Wordmark Color |
|---|---|
| White / Light surfaces | Charcoal Black `#141414` |
| Dark / Black surfaces | White `#FFFFFF` |
| Vivid Red surfaces | White `#FFFFFF` |
| Silver Steel surfaces | Charcoal Black `#141414` |

---

## 3. Color System

The AnonGee BIM Tools palette is built on three brand colors: **Vivid Red** as the primary action and identity color, **Charcoal Black** as the structural foundation, and **Silver Steel** as the precision complement. Supporting neutrals and semantic colors extend the system for UI state management.

### 3.1 Brand Colors

| Name | Hex | Role |
|---|---|---|
| **Vivid Red** | `#E02020` | Primary brand color. CTAs, active states, key highlights, accent bars. |
| **Charcoal Black** | `#141414` | Structural foundation. Headers, dark surfaces, primary text. |
| **Silver Steel** | `#C0C8D8` | Precision complement. Borders, dividers, secondary UI elements, icons on dark backgrounds. |

### 3.2 Extended Palette

| Name | Hex | Role |
|---|---|---|
| **Pure White** | `#FFFFFF` | Primary page canvas, card surfaces. |
| **Off White** | `#F4F4F6` | Subtle background tinting, alternating rows. |
| **Mid Grey** | `#6B7280` | Secondary body text, metadata, placeholders. |
| **Light Border** | `#E2E4EA` | Dividers, input borders, card outlines on white. |

### 3.3 Semantic / State Colors

These colors are reserved exclusively for system feedback. They are never used decoratively.

| Name | Hex | Use |
|---|---|---|
| **Success Green** | `#16A34A` | Completed operations, valid states. |
| **Caution Amber** | `#D97706` | Warnings, beta labels, non-critical notices. |
| **Error Red** | `#DC2626` | Failures, destructive actions, invalid inputs. Note: distinct from Vivid Red — do not substitute. |
| **Info Blue** | `#2563EB` | Informational notices only. |

### 3.4 Color Hierarchy in Practice

The three brand colors carry a deliberate hierarchy in every interface:

1. **Vivid Red** commands the most visual weight. Reserve it for the single most important action or identity element on a given screen — a primary button, an active tab indicator, or an accent bar. Do not scatter it.
2. **Charcoal Black** grounds the layout. It is the color of headers, window chrome, and primary text. It should feel authoritative, not oppressive — use white space to balance it.
3. **Silver Steel** operates quietly. It defines structure without demanding attention: borders, dividers, secondary icons, and subtle UI surfaces.

### 3.5 Color Usage Rules

- Never place Vivid Red text on Charcoal Black backgrounds — the contrast ratio is insufficient for body text (use white text instead).
- Vivid Red may be used as a background only when paired with white text at sizes of 14px / 11pt or larger.
- Silver Steel must never be used as text color on white backgrounds — it fails WCAG AA contrast requirements at small sizes.
- Semantic colors (Success, Caution, Error, Info) are never substituted for brand colors in UI design.
- No off-palette colors are permitted in any designed output without explicit approval.

---

## 4. Typography

### 4.1 Typeface Stack

| Role | Primary | WPF Fallback |
|---|---|---|
| UI & Body | **Inter** | Segoe UI → Arial → sans-serif |
| Code & Technical Output | **JetBrains Mono** | Consolas → Courier New → monospace |

Inter and JetBrains Mono are open-source typefaces available at [fonts.google.com](https://fonts.google.com). Both must be embedded or confirmed available in any distributed tool.

### 4.2 Type Scale

| Level | Size (Web) | WPF Units | Weight | Letter-spacing | Usage |
|---|---|---|---|---|---|
| Display | 36px | 27 | 700 Bold | −0.5px | Marketing headers, splash screens |
| H1 | 28px | 21 | 700 Bold | −0.3px | Window titles, primary page headings |
| H2 | 22px | 16.5 | 600 SemiBold | −0.2px | Section headings |
| H3 | 16px | 12 | 600 SemiBold | 0 | Panel/group headings, card titles |
| H4 | 14px | 10.5 | 500 Medium | 0 | Sub-section labels |
| Body | 14px | 10.5 | 400 Regular | 0 | General prose, form labels |
| Body Small | 12px | 9 | 400 Regular | 0 | Compact list items, secondary content |
| Caption | 11px | 8.25 | 400 Regular | +0.1px | Metadata, footnotes, timestamps |
| Code | 12px | 9 | 400 Regular | 0 | All code and technical output |

### 4.3 Line Heights

| Context | Line Height |
|---|---|
| Display / H1 | 1.2 |
| H2 / H3 | 1.3 |
| Body | 1.65 |
| Code | 1.55 |
| Caption | 1.4 |

### 4.4 Typography Rules

- **Headings are always Charcoal Black** on light surfaces. Never use Vivid Red for heading text in UI.
- **Body text is Mid Grey** (`#6B7280`) on white backgrounds — not pure black. Pure black body text reads as harsh on white.
- **Code output is always monospace.** Never render API responses, element IDs, parameter names, or script output in a proportional font.
- **All-caps is reserved for badge/label text** (e.g., `BETA`, `ERROR`, `v2.1`) set at Caption size with +0.08em letter-spacing. Never use all-caps for headings or prose.

---

## 5. Spacing & Layout

### 5.1 Base Unit

All spacing in AnonGee BIM Tools interfaces is derived from a **base unit of 8px** (WPF: 8 device-independent units). Every margin, padding, and gap value must be a whole multiple of 8.

| Token | Value | WPF | Typical Use |
|---|---|---|---|
| `space-xs` | 4px | 4 | Icon-to-label gap, tight inline pairs |
| `space-sm` | 8px | 8 | Component internal padding (compact) |
| `space-md` | 16px | 16 | Standard component padding |
| `space-lg` | 24px | 24 | Between related sibling elements |
| `space-xl` | 32px | 32 | Between sections within a panel |
| `space-2xl` | 48px | 48 | Between major layout regions |
| `space-3xl` | 64px | 64 | Page-level top/bottom breathing room |

### 5.2 Border Radius

| Context | Radius |
|---|---|
| Buttons | 5px |
| Text inputs, ComboBoxes | 5px |
| Cards, panels, GroupBoxes | 8px |
| Badges, chips, status tags | 3px |
| Dialogs, modal windows | 10px |
| Tooltips | 4px |

### 5.3 Elevation (Shadow)

Elevation is used sparingly to establish hierarchy, not decoration.

| Level | Usage | Shadow |
|---|---|---|
| 0 | Flat surfaces, inline elements | None |
| 1 | Cards, panels sitting on the canvas | `0 1px 3px rgba(0,0,0,0.10)` |
| 2 | Dropdowns, popovers | `0 4px 12px rgba(0,0,0,0.14)` |
| 3 | Dialogs, modal windows | `0 8px 24px rgba(0,0,0,0.18)` |

In WPF, use `DropShadowEffect` only at Levels 2 and 3. Level 1 should be simulated with a `Border` stroke in `Light Border` (`#E2E4EA`).

---

## 6. Iconography

### 6.1 Icon Library

**Lucide Icons** is the canonical icon library for all AnonGee BIM Tools interfaces. It is open-source (MIT licensed), consistent in geometry, and available as SVG paths suitable for WPF `Geometry` resources.

- Stroke weight: **1.5px** (do not deviate)
- Default icon size: **16px / 12 WPF units** (inline/compact), **20px / 15 WPF units** (standard UI), **24px / 18 WPF units** (feature-level)
- Icons must always be accompanied by a visible text label in interactive controls. Icon-only buttons require a `ToolTip`.

### 6.2 Icon Color Rules

| Surface | Icon Color |
|---|---|
| White / light panel | Charcoal Black `#141414` |
| Charcoal Black header | White `#FFFFFF` or Silver Steel `#C0C8D8` |
| Vivid Red surface | White `#FFFFFF` |
| Disabled state | Silver Steel `#C0C8D8` |
| Active / selected state | Vivid Red `#E02020` |

### 6.3 BIM & Revit Icon Mapping

| Action / Concept | Lucide Icon Key |
|---|---|
| Open Revit model | `folder-open` |
| Export (IFC, DWG, PDF) | `download` |
| Run pyRevit script | `play-circle` |
| Structural element | `layers` |
| Parameter / property | `sliders` |
| AI / MCP connection | `zap` |
| Grid / axis | `grid` |
| View management | `layout` |
| Warning / beta feature | `alert-triangle` |
| Success / complete | `check-circle` |
| Error / failure | `x-circle` |
| Settings / configuration | `settings` |
| Log / output | `terminal` |

---

## 7. Voice & Tone

AnonGee BIM Tools communicates with the confidence of a senior BIM engineer: precise, direct, and technically fluent. The voice never hedges, never inflates, and never condescends.

### 7.1 Core Principles

| Principle | Correct | Incorrect |
|---|---|---|
| **Precision** | "Placed 14 structural columns on Grid A at levels 1–5." | "Added some columns to the model." |
| **Directness** | "Export failed. Check that the target directory exists and is writable." | "Hmm, something went wrong with your export!" |
| **Concision** | "Export complete. 3 files written to C:\Output." | "Your export has been completed successfully and your files have been saved!" |
| **Authority** | "Running pyRevit script: PlaceColumns_v2.py" | "Trying to run the script now, please wait…" |
| **Neutrality** | "Warning: 2 elements skipped — unsupported type 'GenericModel'." | "Oops! We couldn't handle those elements." |

### 7.2 Writing Standards

- Use **active voice** in all UI copy, documentation, and error messages.
- Industry terms — Revit, IFC, BIM, MCP, IDA, API — are always capitalized correctly. Never lowercase them.
- Product names are always written in full on first reference: **AnonGee BIM Tools**, not "the tools" or "AGT".
- Avoid filler qualifiers: *just*, *simply*, *easily*, *quickly*, *basically*, *kind of*.
- **Error messages** must state: (1) what failed, (2) why it failed if determinable, (3) what the user should do next.
- **Success messages** are brief and factual. They confirm the outcome; they do not celebrate it.
- Never use exclamation marks in system messages, log output, or error dialogs.

### 7.3 Terminology Standards

| Use | Do Not Use |
|---|---|
| Revit model | "file", "project file" (in UI copy) |
| Element | "object", "thing", "item" |
| Parameter | "field", "property" (in Revit context) |
| Export | "save as", "output to" |
| Script | "macro", "program" |
| AnonGee · Revit MCP Bridge | "the bridge", "MCP tool" |

---

## 8. UI Component Guidelines

### 8.1 Buttons

Buttons follow a strict visual hierarchy. Only one Primary button should appear per view or dialog.

| Variant | Background | Text | Border | Use |
|---|---|---|---|---|
| **Primary** | Vivid Red `#E02020` | White | None | Single dominant action per screen |
| **Secondary** | White | Vivid Red `#E02020` | 1.5px Vivid Red | Supporting actions |
| **Neutral** | Off White `#F4F4F6` | Charcoal Black | 1px Light Border | Non-critical actions |
| **Danger** | `#DC2626` | White | None | Irreversible destructive actions only |
| **Ghost** | Transparent | Mid Grey `#6B7280` | None | Tertiary, dismiss, cancel |

Button sizing:

| Size | Height | Padding H | Font Size | Use |
|---|---|---|---|---|
| Large | 44px | 20px | 14px | Primary dialog actions |
| Default | 36px | 16px | 13px | Standard toolbar and panel buttons |
| Small | 28px | 12px | 12px | Compact controls, inline actions |

### 8.2 Form Inputs

All inputs share a consistent base style:

- Background: White
- Border: 1px `#E2E4EA` (Light Border)
- Border radius: 5px
- Padding: 8px 10px
- Font: Inter Regular, Body size
- Focus border: 1.5px Vivid Red `#E02020`
- Error border: 1.5px Error Red `#DC2626`

Error messages appear as a Caption-size line in Error Red directly below the input. Do not use tooltips or dialog popups for inline validation.

### 8.3 Code & Log Output Blocks

All code output, pyRevit results, API responses, and element IDs are rendered in monospace blocks:

- Background: Charcoal Black `#141414`
- Text: Silver Steel `#C0C8D8`
- Syntax highlights: Vivid Red (keywords), `#A8D8A8` soft green (strings/values)
- Padding: 12px 16px
- Border radius: 5px
- Always include a language/context label (e.g., `python`, `revit-api`, `log`) above the block.
- Include a copy-to-clipboard control in the top-right corner.

### 8.4 Status Badges & Tags

| Status | Background | Text | Border |
|---|---|---|---|
| **Success** | `#DCFCE7` | `#15803D` | None |
| **Warning** | `#FEF9C3` | `#92400E` | None |
| **Error** | `#FEE2E2` | `#991B1B` | None |
| **Info** | `#DBEAFE` | `#1D4ED8` | None |
| **Beta** | Charcoal Black `#141414` | Silver Steel `#C0C8D8` | None |
| **Active** | Vivid Red `#E02020` | White | None |

Badge text is always set in **uppercase**, Caption size, with +0.04em letter-spacing.

### 8.5 Data Tables & Lists

- Header row: Charcoal Black background, white text, Inter SemiBold, 12px / 9 WPF units.
- Alternating rows: White and Off White `#F4F4F6`.
- Row hover: `#FDECEA` (very light red tint).
- Selected row: left border 3px Vivid Red, background `#FEF2F2`.
- Cell padding: 10px vertical, 14px horizontal.
- Dividers: Light Border `#E2E4EA`, 1px.

---

## 9. Document & Report Standards

All AnonGee BIM Tools generated documents — export summaries, model reports, script logs — follow this layout:

### Header

- Left: **AnonGee BIM Tools** wordmark in Inter SemiBold, Charcoal Black.
- Right: Project name or document title in Inter Regular, Mid Grey.
- Below: Full-width 3px rule in Vivid Red `#E02020`.

### Body

- Primary font: Inter Regular, 11pt, Mid Grey `#6B7280`.
- Headings: Inter SemiBold / Bold, Charcoal Black.
- Code/data output: JetBrains Mono, 10pt, on Charcoal Black background.
- Tables follow the Data Tables spec (Section 8.5).

### Footer

- Left: Document classification (e.g., `Internal · Confidential`).
- Center: Page number.
- Right: Date generated in `DD MMM YYYY` format.
- All footer text: Inter Regular, Caption size, Mid Grey.

---

## 10. Brand Don'ts

These rules are non-negotiable across all touchpoints.

- **Do not** render the wordmark in Vivid Red — it is reserved for accents and CTAs, not the brand name itself.
- **Do not** use Vivid Red as a large background surface (e.g., full-window fills). It is an accent color; use Charcoal Black for dark surface backgrounds.
- **Do not** apply more than one semantic state color (Success, Caution, Error, Info) in the same UI region.
- **Do not** introduce off-palette colors — no blues, purples, or teals — in any tool UI or document without explicit versioned approval.
- **Do not** use default system button chrome (`Windows`/`Aero` style) in any WPF window. All buttons must apply a named AnonGee style.
- **Do not** abbreviate the brand to `AGT`, `AG`, or `ABIM` in any public-facing or client-visible material.
- **Do not** use emoji in professional documentation, log output, dialog messages, or error states.
- **Do not** set body text in pure black (`#000000`). Use Charcoal Black `#141414` for headings and Mid Grey `#6B7280` for body.
- **Do not** use Silver Steel as body text on white — it fails WCAG AA at small sizes.

---

## 11. WPF UI Template Guidelines

All WPF interfaces within the AnonGee BIM Tools suite are styled through a shared `ResourceDictionary` (`AnonGeeTheme.xaml`). This ensures visual consistency across all windows, dockable panels, and dialogs, regardless of which tool they belong to.

---

### 11.1 ResourceDictionary Architecture

```
AnonGeeBIMTools/
├── Resources/
│   ├── AnonGeeTheme.xaml        ← Master dictionary — merge all sub-dictionaries here
│   ├── Colors.xaml              ← Brand color brushes
│   ├── Typography.xaml          ← Font resources and named TextBlock styles
│   ├── Controls.xaml            ← Button, TextBox, ComboBox, CheckBox, ListBox styles
│   ├── Panels.xaml              ← Window chrome, DockablePane, GroupBox templates
│   └── Icons.xaml               ← Path geometry for Lucide icons
```

**`AnonGeeTheme.xaml` — Master merge file:**

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

**Consuming the theme in a Window or UserControl:**

```xml
<Window.Resources>
    <ResourceDictionary>
        <ResourceDictionary.MergedDictionaries>
            <ResourceDictionary Source="/AnonGeeBIMTools;component/Resources/AnonGeeTheme.xaml"/>
        </ResourceDictionary.MergedDictionaries>
    </ResourceDictionary>
</Window.Resources>
```

---

### 11.2 `Colors.xaml`

All WPF brushes map directly to named brand tokens. Reference brushes by key throughout all other dictionaries and code-behind. Never hardcode a hex color value outside this file.

```xml
<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">

    <!-- ═══ Brand Colors ═══ -->
    <Color x:Key="ColorVividRed"       >#FFE02020</Color>
    <Color x:Key="ColorCharcoalBlack"  >#FF141414</Color>
    <Color x:Key="ColorSilverSteel"    >#FFC0C8D8</Color>

    <!-- ═══ Surface & Text ═══ -->
    <Color x:Key="ColorPureWhite"      >#FFFFFFFF</Color>
    <Color x:Key="ColorOffWhite"       >#FFF4F4F6</Color>
    <Color x:Key="ColorMidGrey"        >#FF6B7280</Color>
    <Color x:Key="ColorLightBorder"    >#FFE2E4EA</Color>

    <!-- ═══ Semantic ═══ -->
    <Color x:Key="ColorSuccessGreen"   >#FF16A34A</Color>
    <Color x:Key="ColorCautionAmber"   >#FFD97706</Color>
    <Color x:Key="ColorErrorRed"       >#FFDC2626</Color>
    <Color x:Key="ColorInfoBlue"       >#FF2563EB</Color>

    <!-- ═══ SolidColorBrush Tokens ═══ -->
    <SolidColorBrush x:Key="BrushVividRed"      Color="{StaticResource ColorVividRed}"/>
    <SolidColorBrush x:Key="BrushCharcoalBlack" Color="{StaticResource ColorCharcoalBlack}"/>
    <SolidColorBrush x:Key="BrushSilverSteel"   Color="{StaticResource ColorSilverSteel}"/>
    <SolidColorBrush x:Key="BrushPureWhite"     Color="{StaticResource ColorPureWhite}"/>
    <SolidColorBrush x:Key="BrushOffWhite"      Color="{StaticResource ColorOffWhite}"/>
    <SolidColorBrush x:Key="BrushMidGrey"       Color="{StaticResource ColorMidGrey}"/>
    <SolidColorBrush x:Key="BrushLightBorder"   Color="{StaticResource ColorLightBorder}"/>
    <SolidColorBrush x:Key="BrushSuccessGreen"  Color="{StaticResource ColorSuccessGreen}"/>
    <SolidColorBrush x:Key="BrushCautionAmber"  Color="{StaticResource ColorCautionAmber}"/>
    <SolidColorBrush x:Key="BrushErrorRed"      Color="{StaticResource ColorErrorRed}"/>
    <SolidColorBrush x:Key="BrushInfoBlue"      Color="{StaticResource ColorInfoBlue}"/>

</ResourceDictionary>
```

---

### 11.3 `Typography.xaml`

```xml
<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                    xmlns:sys="clr-namespace:System;assembly=mscorlib">

    <!-- ═══ Font Families ═══ -->
    <FontFamily x:Key="FontSans">pack://application:,,,/Resources/Fonts/#Inter, Segoe UI, Arial</FontFamily>
    <FontFamily x:Key="FontMono">pack://application:,,,/Resources/Fonts/#JetBrains Mono, Consolas, Courier New</FontFamily>

    <!-- ═══ Font Sizes (WPF device-independent units) ═══ -->
    <sys:Double x:Key="FontSizeH1"      >21</sys:Double>
    <sys:Double x:Key="FontSizeH2"      >16.5</sys:Double>
    <sys:Double x:Key="FontSizeH3"      >12</sys:Double>
    <sys:Double x:Key="FontSizeH4"      >10.5</sys:Double>
    <sys:Double x:Key="FontSizeBody"    >10.5</sys:Double>
    <sys:Double x:Key="FontSizeSmall"   >9</sys:Double>
    <sys:Double x:Key="FontSizeCaption" >8.25</sys:Double>
    <sys:Double x:Key="FontSizeCode"    >9</sys:Double>

    <!-- ═══ Named TextBlock Styles ═══ -->

    <Style x:Key="TextH1" TargetType="TextBlock">
        <Setter Property="FontFamily"    Value="{StaticResource FontSans}"/>
        <Setter Property="FontSize"      Value="{StaticResource FontSizeH1}"/>
        <Setter Property="FontWeight"    Value="Bold"/>
        <Setter Property="Foreground"    Value="{StaticResource BrushCharcoalBlack}"/>
        <Setter Property="LineHeight"    Value="26"/>
        <Setter Property="Margin"        Value="0,0,0,8"/>
    </Style>

    <Style x:Key="TextH2" TargetType="TextBlock">
        <Setter Property="FontFamily"    Value="{StaticResource FontSans}"/>
        <Setter Property="FontSize"      Value="{StaticResource FontSizeH2}"/>
        <Setter Property="FontWeight"    Value="SemiBold"/>
        <Setter Property="Foreground"    Value="{StaticResource BrushCharcoalBlack}"/>
        <Setter Property="Margin"        Value="0,0,0,4"/>
    </Style>

    <Style x:Key="TextH3" TargetType="TextBlock">
        <Setter Property="FontFamily"    Value="{StaticResource FontSans}"/>
        <Setter Property="FontSize"      Value="{StaticResource FontSizeH3}"/>
        <Setter Property="FontWeight"    Value="SemiBold"/>
        <Setter Property="Foreground"    Value="{StaticResource BrushCharcoalBlack}"/>
    </Style>

    <Style x:Key="TextBody" TargetType="TextBlock">
        <Setter Property="FontFamily"    Value="{StaticResource FontSans}"/>
        <Setter Property="FontSize"      Value="{StaticResource FontSizeBody}"/>
        <Setter Property="FontWeight"    Value="Normal"/>
        <Setter Property="Foreground"    Value="{StaticResource BrushMidGrey}"/>
        <Setter Property="TextWrapping"  Value="Wrap"/>
        <Setter Property="LineHeight"    Value="17"/>
    </Style>

    <Style x:Key="TextCaption" TargetType="TextBlock">
        <Setter Property="FontFamily"    Value="{StaticResource FontSans}"/>
        <Setter Property="FontSize"      Value="{StaticResource FontSizeCaption}"/>
        <Setter Property="Foreground"    Value="{StaticResource BrushMidGrey}"/>
    </Style>

    <Style x:Key="TextCode" TargetType="TextBlock">
        <Setter Property="FontFamily"    Value="{StaticResource FontMono}"/>
        <Setter Property="FontSize"      Value="{StaticResource FontSizeCode}"/>
        <Setter Property="Foreground"    Value="{StaticResource BrushSilverSteel}"/>
        <Setter Property="Background"    Value="{StaticResource BrushCharcoalBlack}"/>
        <Setter Property="Padding"       Value="16,12"/>
        <Setter Property="LineHeight"    Value="14"/>
    </Style>

    <!-- OnDark variant — for text inside Charcoal Black headers -->
    <Style x:Key="TextH2OnDark" BasedOn="{StaticResource TextH2}" TargetType="TextBlock">
        <Setter Property="Foreground" Value="{StaticResource BrushPureWhite}"/>
    </Style>

    <Style x:Key="TextH3OnDark" BasedOn="{StaticResource TextH3}" TargetType="TextBlock">
        <Setter Property="Foreground" Value="{StaticResource BrushSilverSteel}"/>
    </Style>

</ResourceDictionary>
```

---

### 11.4 `Controls.xaml`

#### Buttons

```xml
<!-- ═══ PRIMARY BUTTON ═══ -->
<Style x:Key="ButtonPrimary" TargetType="Button">
    <Setter Property="Background"      Value="{StaticResource BrushVividRed}"/>
    <Setter Property="Foreground"      Value="{StaticResource BrushPureWhite}"/>
    <Setter Property="BorderThickness" Value="0"/>
    <Setter Property="FontFamily"      Value="{StaticResource FontSans}"/>
    <Setter Property="FontSize"        Value="{StaticResource FontSizeBody}"/>
    <Setter Property="FontWeight"      Value="SemiBold"/>
    <Setter Property="Padding"         Value="16,0"/>
    <Setter Property="Height"          Value="36"/>
    <Setter Property="Cursor"          Value="Hand"/>
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="Button">
                <Border x:Name="Root"
                        Background="{TemplateBinding Background}"
                        CornerRadius="5"
                        Padding="{TemplateBinding Padding}">
                    <ContentPresenter HorizontalAlignment="Center"
                                      VerticalAlignment="Center"/>
                </Border>
                <ControlTemplate.Triggers>
                    <Trigger Property="IsMouseOver" Value="True">
                        <Setter TargetName="Root" Property="Background" Value="#C41A1A"/>
                    </Trigger>
                    <Trigger Property="IsPressed" Value="True">
                        <Setter TargetName="Root" Property="Background" Value="#A81515"/>
                    </Trigger>
                    <Trigger Property="IsEnabled" Value="False">
                        <Setter TargetName="Root" Property="Background" Value="{StaticResource BrushLightBorder}"/>
                        <Setter Property="Foreground" Value="{StaticResource BrushSilverSteel}"/>
                    </Trigger>
                </ControlTemplate.Triggers>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>

<!-- ═══ SECONDARY BUTTON (outlined) ═══ -->
<Style x:Key="ButtonSecondary" TargetType="Button">
    <Setter Property="Background"      Value="{StaticResource BrushPureWhite}"/>
    <Setter Property="Foreground"      Value="{StaticResource BrushVividRed}"/>
    <Setter Property="BorderBrush"     Value="{StaticResource BrushVividRed}"/>
    <Setter Property="BorderThickness" Value="1.5"/>
    <Setter Property="FontFamily"      Value="{StaticResource FontSans}"/>
    <Setter Property="FontSize"        Value="{StaticResource FontSizeBody}"/>
    <Setter Property="FontWeight"      Value="SemiBold"/>
    <Setter Property="Padding"         Value="16,0"/>
    <Setter Property="Height"          Value="36"/>
    <Setter Property="Cursor"          Value="Hand"/>
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="Button">
                <Border x:Name="Root"
                        Background="{TemplateBinding Background}"
                        BorderBrush="{TemplateBinding BorderBrush}"
                        BorderThickness="{TemplateBinding BorderThickness}"
                        CornerRadius="5"
                        Padding="{TemplateBinding Padding}">
                    <ContentPresenter HorizontalAlignment="Center"
                                      VerticalAlignment="Center"/>
                </Border>
                <ControlTemplate.Triggers>
                    <Trigger Property="IsMouseOver" Value="True">
                        <Setter TargetName="Root" Property="Background" Value="#FEF2F2"/>
                    </Trigger>
                    <Trigger Property="IsEnabled" Value="False">
                        <Setter TargetName="Root" Property="BorderBrush" Value="{StaticResource BrushLightBorder}"/>
                        <Setter Property="Foreground" Value="{StaticResource BrushSilverSteel}"/>
                    </Trigger>
                </ControlTemplate.Triggers>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>

<!-- ═══ NEUTRAL BUTTON ═══ -->
<Style x:Key="ButtonNeutral" TargetType="Button">
    <Setter Property="Background"      Value="{StaticResource BrushOffWhite}"/>
    <Setter Property="Foreground"      Value="{StaticResource BrushCharcoalBlack}"/>
    <Setter Property="BorderBrush"     Value="{StaticResource BrushLightBorder}"/>
    <Setter Property="BorderThickness" Value="1"/>
    <Setter Property="FontFamily"      Value="{StaticResource FontSans}"/>
    <Setter Property="FontSize"        Value="{StaticResource FontSizeBody}"/>
    <Setter Property="Padding"         Value="16,0"/>
    <Setter Property="Height"          Value="36"/>
    <Setter Property="Cursor"          Value="Hand"/>
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="Button">
                <Border x:Name="Root"
                        Background="{TemplateBinding Background}"
                        BorderBrush="{TemplateBinding BorderBrush}"
                        BorderThickness="{TemplateBinding BorderThickness}"
                        CornerRadius="5"
                        Padding="{TemplateBinding Padding}">
                    <ContentPresenter HorizontalAlignment="Center"
                                      VerticalAlignment="Center"/>
                </Border>
                <ControlTemplate.Triggers>
                    <Trigger Property="IsMouseOver" Value="True">
                        <Setter TargetName="Root" Property="Background" Value="{StaticResource BrushLightBorder}"/>
                    </Trigger>
                </ControlTemplate.Triggers>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>

<!-- ═══ DANGER BUTTON ═══ -->
<Style x:Key="ButtonDanger" BasedOn="{StaticResource ButtonPrimary}" TargetType="Button">
    <Setter Property="Background" Value="{StaticResource BrushErrorRed}"/>
    <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
            <Setter Property="Background" Value="#B91C1C"/>
        </Trigger>
    </Style.Triggers>
</Style>

<!-- ═══ GHOST BUTTON ═══ -->
<Style x:Key="ButtonGhost" TargetType="Button">
    <Setter Property="Background"      Value="Transparent"/>
    <Setter Property="Foreground"      Value="{StaticResource BrushMidGrey}"/>
    <Setter Property="BorderThickness" Value="0"/>
    <Setter Property="FontFamily"      Value="{StaticResource FontSans}"/>
    <Setter Property="FontSize"        Value="{StaticResource FontSizeBody}"/>
    <Setter Property="Padding"         Value="12,0"/>
    <Setter Property="Height"          Value="36"/>
    <Setter Property="Cursor"          Value="Hand"/>
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="Button">
                <Border x:Name="Root"
                        Background="{TemplateBinding Background}"
                        CornerRadius="5"
                        Padding="{TemplateBinding Padding}">
                    <ContentPresenter HorizontalAlignment="Center"
                                      VerticalAlignment="Center"/>
                </Border>
                <ControlTemplate.Triggers>
                    <Trigger Property="IsMouseOver" Value="True">
                        <Setter TargetName="Root" Property="Background" Value="{StaticResource BrushOffWhite}"/>
                    </Trigger>
                </ControlTemplate.Triggers>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
```

#### TextBox

```xml
<Style x:Key="InputTextBox" TargetType="TextBox">
    <Setter Property="FontFamily"                Value="{StaticResource FontSans}"/>
    <Setter Property="FontSize"                  Value="{StaticResource FontSizeBody}"/>
    <Setter Property="Foreground"                Value="{StaticResource BrushCharcoalBlack}"/>
    <Setter Property="Background"                Value="{StaticResource BrushPureWhite}"/>
    <Setter Property="BorderBrush"               Value="{StaticResource BrushLightBorder}"/>
    <Setter Property="BorderThickness"           Value="1"/>
    <Setter Property="Padding"                   Value="10,8"/>
    <Setter Property="Height"                    Value="36"/>
    <Setter Property="VerticalContentAlignment"  Value="Center"/>
    <Style.Triggers>
        <Trigger Property="IsFocused" Value="True">
            <Setter Property="BorderBrush"     Value="{StaticResource BrushVividRed}"/>
            <Setter Property="BorderThickness" Value="1.5"/>
        </Trigger>
        <Trigger Property="Validation.HasError" Value="True">
            <Setter Property="BorderBrush"     Value="{StaticResource BrushErrorRed}"/>
            <Setter Property="BorderThickness" Value="1.5"/>
        </Trigger>
    </Style.Triggers>
</Style>
```

#### ComboBox

```xml
<Style x:Key="InputComboBox" TargetType="ComboBox">
    <Setter Property="FontFamily"      Value="{StaticResource FontSans}"/>
    <Setter Property="FontSize"        Value="{StaticResource FontSizeBody}"/>
    <Setter Property="Foreground"      Value="{StaticResource BrushCharcoalBlack}"/>
    <Setter Property="Background"      Value="{StaticResource BrushPureWhite}"/>
    <Setter Property="BorderBrush"     Value="{StaticResource BrushLightBorder}"/>
    <Setter Property="BorderThickness" Value="1"/>
    <Setter Property="Padding"         Value="10,8"/>
    <Setter Property="Height"          Value="36"/>
    <Style.Triggers>
        <Trigger Property="IsFocused" Value="True">
            <Setter Property="BorderBrush"     Value="{StaticResource BrushVividRed}"/>
            <Setter Property="BorderThickness" Value="1.5"/>
        </Trigger>
    </Style.Triggers>
</Style>
```

---

### 11.5 `Panels.xaml`

#### Standard Tool Window

The canonical layout for all AnonGee tool windows: Charcoal Black header, 3px Vivid Red accent rule, white content area, Off White footer.

```xml
<Window Background="{StaticResource BrushPureWhite}"
        FontFamily="{StaticResource FontSans}"
        WindowStartupLocation="CenterOwner">

    <DockPanel LastChildFill="True">

        <!-- ── Header ── -->
        <Border DockPanel.Dock="Top"
                Background="{StaticResource BrushCharcoalBlack}"
                Padding="16,14">
            <Grid>
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="Auto"/>
                </Grid.ColumnDefinitions>
                <TextBlock Grid.Column="0"
                           Text="AnonGee · Tool Name"
                           Style="{StaticResource TextH2OnDark}"/>
                <TextBlock Grid.Column="1"
                           Text="v2.0"
                           Style="{StaticResource TextCaption}"
                           Foreground="{StaticResource BrushSilverSteel}"
                           VerticalAlignment="Center"/>
            </Grid>
        </Border>

        <!-- ── Vivid Red accent rule ── -->
        <Border DockPanel.Dock="Top"
                Height="3"
                Background="{StaticResource BrushVividRed}"/>

        <!-- ── Footer / action bar ── -->
        <Border DockPanel.Dock="Bottom"
                Background="{StaticResource BrushOffWhite}"
                BorderBrush="{StaticResource BrushLightBorder}"
                BorderThickness="0,1,0,0"
                Padding="16,10">
            <StackPanel Orientation="Horizontal"
                        HorizontalAlignment="Right">
                <Button Content="Cancel"
                        Style="{StaticResource ButtonGhost}"
                        Margin="0,0,8,0"
                        IsCancel="True"/>
                <Button Content="Run"
                        Style="{StaticResource ButtonPrimary}"
                        IsDefault="True"/>
            </StackPanel>
        </Border>

        <!-- ── Scrollable content area ── -->
        <ScrollViewer Padding="20"
                      VerticalScrollBarVisibility="Auto"
                      HorizontalScrollBarVisibility="Disabled">
            <!-- Tool content here -->
        </ScrollViewer>

    </DockPanel>
</Window>
```

#### Dockable Panel (Revit `IDockablePaneProvider`)

Single-column, compact layout for panels hosted inside Revit's docking framework.

```xml
<UserControl Background="{StaticResource BrushPureWhite}"
             FontFamily="{StaticResource FontSans}"
             MinWidth="240"
             MaxWidth="360">

    <DockPanel LastChildFill="True">

        <!-- Compact header -->
        <Border DockPanel.Dock="Top"
                Background="{StaticResource BrushCharcoalBlack}"
                Padding="12,10">
            <TextBlock Text="Panel Title"
                       Style="{StaticResource TextH3OnDark}"/>
        </Border>

        <!-- Accent rule -->
        <Border DockPanel.Dock="Top"
                Height="2"
                Background="{StaticResource BrushVividRed}"/>

        <!-- Content -->
        <ScrollViewer Padding="12,14"
                      VerticalScrollBarVisibility="Auto"
                      HorizontalScrollBarVisibility="Disabled">
            <StackPanel>
                <!-- Panel content — single column only -->
            </StackPanel>
        </ScrollViewer>

    </DockPanel>
</UserControl>
```

#### Dialog / Modal Window

Fixed-width, `NoResize`, always `CenterOwner`. Use for confirmations, configuration dialogs, and data entry.

```xml
<Window ResizeMode="NoResize"
        WindowStartupLocation="CenterOwner"
        Background="{StaticResource BrushPureWhite}"
        FontFamily="{StaticResource FontSans}"
        Width="480"
        SizeToContent="Height">

    <DockPanel LastChildFill="True">

        <!-- Header -->
        <Border DockPanel.Dock="Top"
                Background="{StaticResource BrushCharcoalBlack}"
                Padding="20,14">
            <TextBlock Text="Dialog Title"
                       Style="{StaticResource TextH2OnDark}"/>
        </Border>

        <!-- Accent rule -->
        <Border DockPanel.Dock="Top"
                Height="3"
                Background="{StaticResource BrushVividRed}"/>

        <!-- Action bar -->
        <Border DockPanel.Dock="Bottom"
                Background="{StaticResource BrushOffWhite}"
                BorderBrush="{StaticResource BrushLightBorder}"
                BorderThickness="0,1,0,0"
                Padding="20,12">
            <StackPanel Orientation="Horizontal"
                        HorizontalAlignment="Right">
                <Button Content="Cancel"
                        Style="{StaticResource ButtonGhost}"
                        Margin="0,0,8,0"
                        IsCancel="True"/>
                <Button Content="Confirm"
                        Style="{StaticResource ButtonPrimary}"
                        IsDefault="True"/>
            </StackPanel>
        </Border>

        <!-- Body -->
        <StackPanel Margin="20,18,20,20">
            <!-- Dialog content here -->
        </StackPanel>

    </DockPanel>
</Window>
```

#### GroupBox / Section Panel

```xml
<Style x:Key="SectionGroup" TargetType="GroupBox">
    <Setter Property="BorderBrush"     Value="{StaticResource BrushLightBorder}"/>
    <Setter Property="BorderThickness" Value="1"/>
    <Setter Property="Padding"         Value="14,12"/>
    <Setter Property="Margin"          Value="0,0,0,16"/>
    <Setter Property="FontFamily"      Value="{StaticResource FontSans}"/>
    <Setter Property="HeaderTemplate">
        <Setter.Value>
            <DataTemplate>
                <TextBlock Text="{Binding}"
                           Style="{StaticResource TextH3}"
                           Margin="2,0"/>
            </DataTemplate>
        </Setter.Value>
    </Setter>
</Style>
```

---

### 11.6 Spacing in WPF

WPF uses device-independent units where 1 unit ≈ 1/96 inch (approximately 1px on a 96 DPI screen). Brand spacing tokens map directly:

| Token | Value | WPF | XAML Pattern |
|---|---|---|---|
| `space-xs` | 4px | 4 | `Margin="4"` or `Spacing="4"` |
| `space-sm` | 8px | 8 | Component internal padding |
| `space-md` | 16px | 16 | Standard element padding |
| `space-lg` | 24px | 24 | Between sibling groups |
| `space-xl` | 32px | 32 | Between panel sections |

Use `StackPanel Spacing="8"` (available in .NET 6+ WPF) for consistent item gaps. For earlier runtimes, apply `Margin="0,0,0,8"` on each child element.

---

### 11.7 WPF Enforcement Rules

These rules are mandatory for all WPF code within the AnonGee BIM Tools suite.

- **No hardcoded colors.** Every color reference must use a named `{StaticResource BrushXxx}` key from `Colors.xaml`. Pull requests with inline hex values will be rejected.
- **No inline font declarations.** Font family and font size are set only via `{StaticResource FontSans}` / `{StaticResource FontMono}` and the named size tokens.
- **No default WPF button chrome.** Every `Button` must carry a named style (`ButtonPrimary`, `ButtonSecondary`, `ButtonNeutral`, `ButtonDanger`, or `ButtonGhost`). Unstyled buttons are off-brand and will be flagged in review.
- **Dialogs must be `CenterOwner`.** Always set `WindowStartupLocation="CenterOwner"` and pass the Revit main window as `Owner` to prevent dialog placement behind the host application.
- **Dockable panels must be single-column.** Do not use `Grid` with multiple columns or horizontal `StackPanel` layouts inside `IDockablePaneProvider` controls. The minimum width is `240`; the maximum is `360`.
- **Input validation is inline.** Validation errors render as a `TextBlock` in `BrushErrorRed` directly below the offending field. Do not use `MessageBox` for field-level validation.
- **Disabled states are visible.** Disabled controls use `BrushLightBorder` background and `BrushSilverSteel` foreground. Never use `Visibility="Collapsed"` to suppress a disabled state — keep it visible and non-interactive.
- **All code output is `TextCode` style.** Element IDs, parameter values, file paths, API responses, and script output are always rendered in `{StaticResource TextCode}` or an equivalent monospace style. They are never displayed in a proportional font.

---

## 12. Appendix — Token References

### CSS Custom Properties (Web / Artifact Use)

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

  /* ── Typography ── */
  --font-sans:  'Inter', 'Segoe UI', Arial, sans-serif;
  --font-mono:  'JetBrains Mono', Consolas, 'Courier New', monospace;

  --text-h1:       1.75rem;   /* 28px */
  --text-h2:       1.375rem;  /* 22px */
  --text-h3:       1rem;      /* 16px */
  --text-body:     0.875rem;  /* 14px */
  --text-caption:  0.6875rem; /* 11px */
  --text-code:     0.75rem;   /* 12px */

  /* ── Spacing ── */
  --space-xs:   4px;
  --space-sm:   8px;
  --space-md:   16px;
  --space-lg:   24px;
  --space-xl:   32px;
  --space-2xl:  48px;
  --space-3xl:  64px;

  /* ── Radius ── */
  --radius-sm:   3px;
  --radius-md:   5px;
  --radius-lg:   8px;
  --radius-xl:   10px;
}
```

### WPF Brush Key Quick Reference

| Key | Hex | Role |
|---|---|---|
| `BrushVividRed` | `#E02020` | Primary brand / CTA |
| `BrushCharcoalBlack` | `#141414` | Headers, dark surfaces, primary text |
| `BrushSilverSteel` | `#C0C8D8` | Borders, secondary icons, dividers |
| `BrushPureWhite` | `#FFFFFF` | Page canvas, card backgrounds |
| `BrushOffWhite` | `#F4F4F6` | Subtle backgrounds, footers |
| `BrushMidGrey` | `#6B7280` | Body text, captions |
| `BrushLightBorder` | `#E2E4EA` | Input borders, card outlines, dividers |
| `BrushSuccessGreen` | `#16A34A` | Success states |
| `BrushCautionAmber` | `#D97706` | Warning states |
| `BrushErrorRed` | `#DC2626` | Error states (not a substitute for Vivid Red) |
| `BrushInfoBlue` | `#2563EB` | Informational notices |

---

*AnonGee BIM Tools · Internal Brand Reference · Version 2.0 · June 2026*
*This document is confidential. Do not distribute outside the AnonGee product team.*
