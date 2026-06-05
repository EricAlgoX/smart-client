---
name: chart-sense
description: 'Generate interactive ECharts data visualization pages from any data input. Automatically selects the best chart type, applies a built-in SaaS design system, and supports plugging in external design systems (IBM Carbon, custom tokens). Use when the user provides data and asks for a chart, dashboard, or visualization. Trigger phrases: "chart sense", "给我生成图表", "visualize this data", "帮我出图", "generate chart", "数据可视化".'
---

# Chart Sense

> Give it data. It decides the chart. It generates the page.

| Field | Value |
|---|---|
| **Creator** | Lu wenwen |
| **License** | Non-commercial · 禁止商用 |
| **Version** | 2.0 |
| **Chart library** | Apache ECharts 5 (CDN · no install) |

---

## Trigger

Activate when user:
- Provides data (CSV / JSON / table / plain text) + asks for chart or visualization
- Says any of: `chart sense` · `visualize this` · `帮我出图` · `generate chart` · `数据可视化`
- Provides a design system and asks to apply it to a chart

---

## Step 1 — Parse Input

Accept data in any format — do NOT ask user to reformat:

```
Plain text:   "Q1: 120, Q2: 340, Q3: 280, Q4: 410"
Markdown table: | Category | Value |
CSV:          category,value\nA,120
JSON:         [{"label":"A","value":120}]
Description:  "top 5 communities by reach: tech 4.2M, gaming 3.8M..."
```

---

## Step 2 — Judge Chart Type

Use the **first matching rule**:

| Data shape | Chart type |
|---|---|
| One metric over time | **Line** |
| Multiple metrics over time | **Multi-line** |
| Comparing discrete categories, ≤ 8 | **Vertical bar** |
| Comparing discrete categories, > 8 or long labels | **Horizontal bar** |
| Part-of-whole, ≤ 6 slices | **Pie** |
| Part-of-whole, > 6 slices | **Donut** |
| Two numeric variables | **Scatter** |
| Multiple metrics per category | **Radar** |
| Two metrics, different scales, same time axis | **Combo (bar + line, dual y-axis)** |
| Additive segments over time | **Stacked bar** |

Conflict: **Line > Bar > Pie** priority. User-specified type overrides.

**Output in-chat before generating:**
```
Data: [what you detected]
Chart: [selected type]
Reason: [one sentence]
```

---

## Step 3 — Built-in Design System

Chart Sense ships with a default design system. **Always apply it unless the user specifies otherwise.**

### Default Palette · Linear SaaS Blue

```javascript
const DS_DEFAULT = {
  name:        'Linear SaaS Blue',
  colors:      ['#5E6AD2','#26B5CE','#6FCF97','#F2994A','#BB87FC','#EB5757','#F2C94C','#56CCF2'],
  fontFamily:  'Inter, system-ui, sans-serif',
  fontSize:    12,
  strokeWidth: 2,
  symbolSize:  5,
  background:  '#ffffff',
  gridColor:   '#f3f4f6',
  textColor:   '#6b7280',
  titleColor:  '#111827',
  tooltipBg:   '#111827',
  tooltipText: '#f9fafb',
  borderRadius: 4,
};
```

### Additional Built-in Presets

User can say `use preset [name]` to switch:

| Preset | Colors (first 3) | Vibe |
|---|---|---|
| `linear` (default) | `#5E6AD2` `#26B5CE` `#6FCF97` | Modern SaaS · blue-purple |
| `tableau` | `#4e79a7` `#f28e2b` `#e15759` | Classic · industry standard |
| `echarts6` | `#5470c6` `#91cc75` `#fac858` | Official ECharts 6 theme |
| `tailwind` | `#3B82F6` `#10B981` `#F59E0B` | Tailwind · clean SaaS |
| `muted` | `#7B9EC9` `#85BFA0` `#D4A96E` | Warm earth · low fatigue |
| `midnight` | `#4ADE80` `#60A5FA` `#FBBF24` | Cool vivid · high energy |
| `pastel` | `#93C5FD` `#86EFAC` `#FDE68A` | Soft · airy |

### What the Design System Controls

✅ **Modifiable by design system:**
- `colors` — series color array
- `fontFamily` / `fontSize` — all text
- `strokeWidth` — line / border thickness
- `symbolSize` — data point dot size
- `gridColor` — axis grid lines
- `background` — chart background
- `textColor` / `titleColor` — labels and title
- `tooltipBg` / `tooltipText` — tooltip colors
- `borderRadius` — bar corner radius

❌ **Locked (interaction layer — never override):**
- Click / hover event handlers
- Zoom and pan behavior
- Tooltip display logic
- Legend toggle behavior
- Animation triggers

---

## Step 4 — External Design System Support

Users can plug in their own design system in three ways:

### Way A — Named system

Tell the AI which design system you want to use by name. If it's a well-known system (such as IBM Carbon, Material Design, or any major public design system), the AI will look up its standard colors, fonts, and spacing and apply them automatically. You can also name any custom or internal design system — the AI will ask you for its token details if it doesn't already know them.

### Way B — CSS token object
```javascript
{
  '--color-primary': '#FF6B35',
  '--color-secondary': '#004E89',
  '--font-base': 'Inter, sans-serif',
  '--stroke-width': '2',
  '--chart-colors': '#FF6B35,#004E89,#2DC653'  // comma-separated
}
```

### Way C — Plain description
```
"use warm orange tones, Inter font, clean minimal style"
"corporate blue-green palette, dense data layout"
```
→ Infer tokens from description and apply.

**When external design system is provided:**
1. Parse tokens from whichever way the user provides
2. Map to the DS token structure above
3. Apply to chart — keep interaction layer untouched
4. Show active preset name in the design panel

---

## Step 5 — Generate the ECharts Page

### Tech stack
```
Chart library: ECharts 5 · https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js
Font:          Google Fonts · Inter (or design system font)
No build step — open directly in browser
```

### Page structure
```
[Shell Bar]      Dark top bar · "Chart Sense" · data slug · active design system badge
[Main Area]      Chart (left ~70%) + Design Panel (right ~30%, collapsible)
[Data Table]     Collapsible raw data table below chart
```

### Screen Efficiency Rules

When generating multi-module dashboards, maximize information visible without scrolling ("above the fold"):

1. **Compact spacing** — module section padding `10px 24px`, gap between cards `10px` (not 16px+)
2. **Internal scroll for long lists** — tables showing ranked data: `max-height: 280px; overflow-y: auto` with a thin 3px scrollbar. Show Top 10 by default, scroll to see more. Never paginate.
3. **Card heights** — Row-1 cards (small charts): `min-height: 240px`. Row-2 cards (tables): `min-height: 320px`.
4. **No empty space** — KPI cards, module cards, and chart panels must fill their grid cell. If a card has too much whitespace, reduce padding or increase font.
5. **Grid layout** — 3-col for small stat/chart cards, 2-col for data-heavy table cards. Never 1-col (wastes horizontal space).
6. **Placement bars** — percentage progress bars are more space-efficient than pie charts for 2-category comparisons.

### ECharts Config Rules
- Height: calculated from `window.innerHeight - shellHeight - padding` via JS, set explicitly before `echarts.init()`
- Use `requestAnimationFrame` before init to ensure DOM has painted
- `window.addEventListener('resize', () => chart.resize())` always included
- Grid: `containLabel: true`, reasonable padding on all sides
- Tooltip: dark background (`#111827`), white text, Inter font
- Legend: bottom, circle icon, Inter font
- Axis labels: Inter / monospace for numbers, `#9ca3af` color
- Grid lines: `#f3f4f6` (very subtle)
- All series lines: `strokeWidth: 2`, `symbolSize: 5`, solid (no dashed)

### Design Panel (collapsible, right side)
```
┌── Design System ────────────────┐
│ Active: Linear SaaS Blue  [▾]  │  ← preset switcher dropdown
│                                 │
│ ● ● ● ● ● ● ● ●               │  ← color swatches (click to copy hex)
│                                 │
│ Font:   Inter                   │
│ Stroke: 2px                     │
│ Grid:   #f3f4f6                 │
│                                 │
│ [Paste custom tokens...]        │  ← textarea for Way B input
└─────────────────────────────────┘
```

Switching preset re-renders chart immediately (no page reload).

---

## Step 6 — Output

### File naming
```
doc/design-exploration/chart-sense-[data-slug].html
```
`[data-slug]` = short kebab-case description of the data.

### File requirements
- Single self-contained HTML file
- No external dependencies except CDN (ECharts + Google Fonts)
- All JS inline
- Opens directly in browser, no server needed

### Report back to user
After saving:
```
✓ Chart Sense generated: doc/design-exploration/chart-sense-[slug].html
  Chart type:     [type]
  Design system:  [preset name]
  Series count:   [n]
```

---

## Execution Checklist

- [ ] Data parsed (format auto-detected)
- [ ] Chart type judgment shown in-chat
- [ ] ECharts renders (explicit height set, `requestAnimationFrame` used)
- [ ] Resize handler included
- [ ] Design system applied (default: Linear SaaS Blue)
- [ ] Design panel present with preset switcher
- [ ] All lines solid (no dashed unless user requests)
- [ ] Interaction layer untouched
- [ ] Data table collapsible section included
- [ ] File saved to correct path
- [ ] Summary reported to user

---

## Quick Examples

```
"Chart Sense: Q1 120, Q2 340, Q3 280, Q4 410"
→ Line chart · linear preset · chart-sense-quarterly-data.html

"Chart Sense: Apple 35%, Google 28%, Microsoft 19%, Others 18%"
→ Pie chart · linear preset · chart-sense-market-share.html

"Chart Sense: [table] — use IBM Carbon"
→ Bar chart · carbon preset · chart-sense-[slug].html

"Chart Sense: [data] — use tailwind preset"
→ Chart · tailwind preset applied

"Chart Sense: [data] — colors: #FF6B35, #004E89; font: Roboto"
→ Chart · custom tokens applied from Way B/C
```

---

*Chart Sense v2.0 · Created by Lu wenwen · 禁止商用*
