# Phyto-Autoscopy frontend standard

This document records the design language and code organization actually used by the current `frontend/` implementation. It is a maintenance standard, not a proposal for a new visual system.

## Table of contents

1. [Authority and maintenance](#1-authority-and-maintenance)
2. [Technology and application shape](#2-technology-and-application-shape)
3. [Directory ownership](#3-directory-ownership)
4. [Design foundations](#4-design-foundations)
5. [Layout and responsive behavior](#5-layout-and-responsive-behavior)
6. [Shared component standards](#6-shared-component-standards)
7. [Feature composition standards](#7-feature-composition-standards)
8. [Interaction and motion](#8-interaction-and-motion)
9. [Accessibility](#9-accessibility)
10. [JavaScript and React conventions](#10-javascript-and-react-conventions)
11. [State, data, and network boundaries](#11-state-data-and-network-boundaries)
12. [Extraction and reuse rules](#12-extraction-and-reuse-rules)
13. [Patterns to avoid](#13-patterns-to-avoid)
14. [Change workflow](#14-change-workflow)
15. [Validation checklist](#15-validation-checklist)

## 1. Authority and maintenance

Inspect the live implementation before editing. The most important visual sources of truth are:

- `frontend/src/app/globals.css`
- `frontend/src/app/icon.svg`
- `frontend/src/app/layout.js`
- `frontend/src/components/panels/Panel.js`
- `frontend/src/components/panels/InnerPanel.js`
- `frontend/src/components/panels/SettingPanel.js`
- `frontend/src/components/panels/SettingsGear.js`
- `frontend/src/components/cards/StatusCard.js`
- `frontend/src/components/data/InformationGrid.js`
- `frontend/src/components/actions/ActionRow.js`
- `frontend/src/components/buttons/Button.js`
- `frontend/src/components/headers/SubsectionHeader.js`
- `frontend/src/components/inputs/Input.js`
- `frontend/src/components/inputs/SelectMenu.js`
- `frontend/src/components/inputs/Toggle.js` (`Toggle` and `ToggleRow`)
- `frontend/src/components/fields/FieldFrame.js`
- `frontend/src/components/Tooltip.js`
- `frontend/src/components/VerticalLine.js`

If this prose conflicts with a shared component that the user has intentionally edited, preserve the live component and update this document as part of the same design-system change. Do not silently normalize user-authored details back to an older rule.

The current `StatusCard` is a particularly important reference. Its compact card structure, title/content/note hierarchy, and visual density represent the user's preferred status presentation.

## 2. Technology and application shape

The frontend currently uses:

- Next.js 15 App Router.
- React 19.
- JavaScript rather than TypeScript.
- Tailwind CSS v4 through `@import "tailwindcss"` in `globals.css` and `@tailwindcss/postcss`.
- `react-icons` for interface icons.
- The `@/` path alias mapped to `frontend/src`.
- Server-rendered entry points with narrow client boundaries for interactive components and hooks.
- Same-origin Next.js route handlers as a backend-for-frontend proxy.

Do not add a second styling framework, CSS-in-JS runtime, form framework, global state library, or class-name package merely for convenience. A new dependency needs a concrete application-level reason.

## 3. Directory ownership

Use the following ownership model:

```text
frontend/src/
├─ app/
│  ├─ (pages)/               # every App Router page entry; group is absent from URLs
│  │  ├─ page.js             # root login page; authenticated users redirect to /capture
│  │  ├─ capture/page.js     # GOAL-01 capture controls
│  │  ├─ analysis/           # analysis dashboard and nested analysis pages
│  │  └─ models/page.js      # models placeholder
│  ├─ actions/               # server actions such as authentication
│  ├─ api/                   # same-origin BFF route handlers
│  ├─ globals.css            # Tailwind v4 entry point only
│  └─ layout.js              # document shell and authenticated application shell
├─ components/
│  ├─ actions/               # shared ActionRow
│  ├─ buttons/               # shared Button
│  ├─ cards/                 # shared StatusCard
│  ├─ data/                  # shared label/value information grids
│  ├─ fields/                # shared FieldFrame
│  ├─ headers/               # shared SubsectionHeader
│  ├─ inputs/                # shared Input, SelectMenu, Toggle, ToggleRow
│  ├─ navigation/            # shared NavLink
│  ├─ panels/                # shared Panel, InnerPanel, SettingPanel, SettingsGear
│  ├─ Tooltip.js             # ungrouped shared tooltip primitive
│  └─ VerticalLine.js        # ungrouped shared primitive
├─ features/
│  ├─ Login/                 # login UI
│  ├─ ControlPanel/          # `/capture` composition boundary for GOAL-01 features
│  ├─ ImagePreview/          # image preview, dedicated settings and utilities
│  ├─ Control/               # direct hardware control and MotorControls
│  ├─ MainNavigation/        # top-level route navigation and global header actions
│  ├─ Analysis/              # `/analysis` feature, separate from capture controls
│  ├─ Calibration/           # independent `/calibration` unified hardware calibration
│  ├─ Models/                # `/models` feature
│  ├─ Notifications/         # toast/history UI and notification hook
│  ├─ Schedule/              # Schedule, config, mode components and utilities
│  ├─ RecordsStorage/        # record list, storage path settings and utilities
│  ├─ Settings/              # general settings editor, config and utility logic
│  └─ SystemStatus/          # 系統狀態 overview
├─ hooks/                    # truly cross-feature client lifecycles
└─ lib/                      # truly cross-feature pure/server utilities
```

Every `page.js` belongs below `app/(pages)/`, including the root `/` entry. Never place a page beside `app/layout.js` or inside `app/api`; keep `layout.js`, `actions/`, `api/`, `globals.css`, and application assets outside the route group. Because `(pages)` is a Next.js route group, it organizes source files without adding a URL segment.

`app/layout.js` owns the authenticated application shell. After resolving the login session, it mounts the single `PhytoSocketProvider`, the page-level `main` background and horizontal padding, and `MainNavigation` once around authenticated page content. Feature entries must not repeat this shell; they begin with their own max-width, top-spacing, responsive grid, and panels. The unauthenticated login keeps its dedicated centered `main` because the root layout does not mount the authenticated shell without a valid session.

### 3.1 `components`

Place a component here only when it describes a reusable visual or interaction primitive, frame, or container rather than a business feature. Organise it by role (`actions`, `inputs`, `panels`, and so on). Examples include `Panel`, `InnerPanel`, `SettingPanel`, `StatusCard`, `ActionRow`, `SubsectionHeader`, `Button`, fields, select menus, toggles, `VerticalLine`, tooltips, and the settings gear.

A UI primitive should:

- expose a small semantic prop interface;
- own its established classes and interaction states;
- accept `className` when consumers need layout-level extension;
- avoid importing feature metadata or calling feature APIs;
- remain usable by more than one feature.

### 3.2 Feature folders

Every independent business area belongs in `features/<Feature>/`, using the PascalCase feature directory names already present (`ImagePreview`, `Schedule`, `Control`, `Settings`, and so on). A feature entry component is named directly after the feature, such as `ImagePreview.js` or `Schedule.js`. Every subcomponent in `components/` uses the owning feature as a PascalCase prefix in both its filename and component identifier, such as `ImagePreviewSettings.js`, `ScheduleModeCard.js`, or `RecordsStorageSettings.js`. This explicit prefix prevents ambiguous imports such as `Field`, `Settings`, `Header`, `Section`, or `ModeCard` when several features are open together.

`Control/components/MotorControls.js` is the deliberate exception to the normal feature-prefix rule: it names the hardware-specific motor control group requested by the product vocabulary. Keep `MotorControls`; do not restore a top-level `Motor` feature.

Use these feature-internal destinations:

- `components/` for feature-only JSX components;
- `hooks/` for feature-only client state/lifecycle;
- `<feature>Config.js` for constants, metadata, option lists, and defaults only;
- `lib/*Utils.js` for deterministic parsing, formatting, validation, serialization, or API helpers.

Do not put feature UI under `src/components`, and do not put generic UI primitives into a feature just because that feature was its first consumer. Create a feature folder when multiple files share one domain and keeping them globally would obscure ownership.

### 3.3 Naming and entry components

Do not use lowercase or hyphenated component filenames such as `section-schedule.js` or `schedule-mode-card.js`. React component filenames and identifiers are PascalCase. A feature entry uses only the feature name, while every child component uses `<Feature><Role>` without separators. Utilities and configuration use descriptive camelCase names such as `scheduleConfig.js` and `scheduleUtils.js`. A feature entry component may select feature data, invoke hooks passed from its parent, arrange feature components, and display loading/error/empty states. It should not contain:

- a locally defined reusable card or control;
- a long option/configuration registry;
- payload serialization;
- angle, time, schedule, or status algorithms;
- a reusable effect or event subscription;
- duplicated formatting helpers.

### 3.4 Shared hooks and libraries

Use root `hooks` only for reusable client lifecycles and state machines genuinely needed across feature boundaries, such as `usePhytoSocket`, `useSettings`, and `useElapsedSeconds`. Keep a hook inside its feature when it has one feature owner.

Use root `lib` only for cross-feature deterministic/server modules such as:

- date, duration, value, or status formatting;
- request and BFF helpers;
- authenticated session helpers.

Shared display formatting belongs in `lib/formatUtils.js`. Optional elapsed values, numbers with units, Boolean state labels, and ranges with units must use its exported helpers rather than feature-local `display*` functions.

Capture records are a separate domain. Use `record`/`Record`, `record_id`, `record_path`, `/api/records`, and `records.list` at that boundary. The word `session` is reserved for login/authentication state and its signed cookie/ticket helpers. Normalize legacy capture-record session names at the boundary instead of spreading them through feature code. The filesystem root remains `captures_dir` (`data/captures` by default) because it stores captured images, per-mode folders, CSV logs, and `config.json`; SQLite stores the Record/Capture relationships, metadata, states, and file paths used by read APIs.

Schedule captures use a mode-first hierarchy. A Record directory is named `record_<timestamp>` and contains the complete parent `config.json`, `metadata.csv`, and `record.log.csv`. Each mode is stored below `modes/<ModeName>.<number>/` with its own `config.json`, `metadata.csv`, `mode.log.csv`, and `rounds/` directory. Rotating modes use `rounds/round.01`, `rounds/round.02`, and so on without timestamps; continuous or non-rotating capture uses the sole `rounds/round.00`. Snapshot folders use `snapshot.<number>_<timestamp>`, and image filenames use `<camera>-<mode abbreviation>.<mode number>_r.<round number>_s.<snapshot number>_<timestamp>.jpg`. Every filesystem timestamp uses `YYYY.MM.DD-hh.mm.ss.xxxxxx` in the project timezone; serialized CSV and JSON time fields remain ISO 8601. Keep the canonical mode names `ContinuousInterval`, `TimeInterval`, `AngleInterval`, `SpecificAngles`, and `EqualDivisions`, with abbreviations `CI`, `TI`, `AI`, `SA`, and `ED`.

Feature-specific pure code belongs in that feature's `lib/`, even when it currently has one caller. A feature config file must never contain algorithms; pure code belongs in its `lib/*Utils.js` file.

## 4. Design foundations

### 4.1 Overall visual language

The interface is a dense, dark, near-black green control dashboard with translucent glass-like surfaces. It should feel technical and calm, not decorative.

The application favicon in `app/icon.svg` mirrors the header's `PiPlantFill` mark: a light emerald plant on a deep green rounded surface with a subtle emerald border. Keep the favicon and header mark visually aligned when the application identity changes.

Core principles:

- The page recedes; active controls and important values carry contrast.
- Borders and translucent fills separate hierarchy more often than large spacing.
- Emerald is the normal interactive and success accent.
- Amber communicates warning or pending attention.
- Rose communicates error, destructive action, or offline state.
- Neutral palette values form gray text hierarchy; white opacity values remain for borders and translucent surfaces.
- Status content stays concise and scannable.
- Gradients and bright multi-color decoration are not part of this system.

### 4.2 Color roles

| Role                      | Established value/classes                | Usage                                   |
| ------------------------- | ---------------------------------------- | --------------------------------------- |
| Page background           | `bg-[#06100c]`                         | Root body and deepest page layer        |
| Deep popup surface        | `bg-[#07130f]/95`                      | Tooltips and select menus               |
| Deep notification surface | `bg-[#08140f]/95`                      | Toasts/history surfaces                 |
| Main panel                | `bg-white/[0.07]`                      | Top-level dashboard panels              |
| Panel header              | `bg-white/[0.04]`                      | Header band inside a panel              |
| Inner panel               | `bg-white/[0.06]`                      | Grouped feature content                 |
| Quiet control             | `bg-black/15`, `bg-black/15`         | Inputs, unselected control rows         |
| Structural border         | `border-white/15`                      | Panels, cards and ordinary grouping     |
| Control border            | `border-white/15`                      | Inputs, buttons and popups              |
| Strong neutral hover      | `border-white/25`, `bg-white/[0.13]` | Default button hover                    |
| Accent                    | Emerald 100–500                         | Active, selected, focus, success        |
| Warning                   | Amber 200–500                           | Warning status only                     |
| Error/destructive         | Rose 100–600                            | Errors, offline and destructive actions |

Use opacity deliberately for surfaces and borders. Do not replace translucent white/black surfaces with flat opaque gray. Text is the exception: use solid `text-neutral-*` values instead of white with opacity. Do not introduce another normal accent color for a new feature.

### 4.3 Text colors

- Primary headings and values: `text-white` or `text-neutral-100`.
- Common control text: `text-neutral-100` or `text-neutral-200`.
- Secondary/supporting text: `text-neutral-300` or `text-neutral-400`.
- Units and low-priority text: `text-neutral-500`; reserve `text-neutral-600` for the least important metadata such as timestamps.
- Accent labels: `text-emerald-200` or `text-emerald-100`.
- Dark text appears on solid emerald primary buttons: `text-emerald-950`.

Do not use `text-white/<opacity>` to create gray text. Choose the semantic neutral shade directly so text remains an opaque, predictable color.

### 4.4 Typography hierarchy

The root uses the locally configured Chiron Go Round TC variable font through `var(--font-chiron)`. Preserve this font setup.

| Purpose                          | Current treatment                                             |
| -------------------------------- | ------------------------------------------------------------- |
| Panel heading                    | `text-lg font-black tracking-tight`                         |
| Ordinary section/control heading | `text-sm` or `text-base`, usually `font-black`          |
| Status-card micro heading        | `text-[10px] font-black tracking-[0.12em] text-emerald-200` |
| Status-card main value           | `text-2xl font-semibold leading-5`                          |
| Status-card note                 | `text-xs font-semibold text-neutral-300`                    |
| Floating field label             | `text-xs font-black leading-none text-neutral-300`          |
| Input/select text                | `text-sm font-bold`                                         |
| Button text                      | `text-sm font-extrabold`                                    |
| Status pill                      | `text-[11px] font-black tracking-[0.04em]`                  |
| Helper/tooltip text              | `text-xs font-semibold leading-5`                           |

Use heavy weights to maintain the current interface character. Keep titles short. Do not add decorative all-caps English eyebrow labels.

### 4.5 Radius hierarchy

| Layer                      | Radius                                                           |
| -------------------------- | ---------------------------------------------------------------- |
| Main panel                 | `rounded-[28px]`                                               |
| Inner feature panel        | `rounded-xl`                                               |
| Controls and compact cards | `rounded-xl`                                                   |
| Popup options and tooltip  | `rounded-lg` or `rounded-xl` according to the live primitive |
| Pills/status chips         | `rounded-full`                                                 |

Do not use one radius everywhere. The size hierarchy communicates containment.

### 4.6 Borders, shadows, and blur

Main panels use `overflow-visible` so field tooltips and menus can escape their containing panel. Surface children that touch the outer edge carry their own edge-specific rounding: `PanelHeader` has the top corners and an expanded `SettingsPanel` surface has the bottom corners. Do not solve corner leakage by clipping panel-level popups.

Main panel treatment:

```text
border border-white/15
bg-white/[0.07]
shadow-[0_24px_80px_rgba(0,0,0,0.26),inset_0_1px_0_rgba(255,255,255,0.08)]
backdrop-blur-2xl
```

Inner panel treatment:

```text
border border-white/15
bg-white/[0.06]
shadow-[inset_0_1px_0_rgba(255,255,255,0.07)]
```

Compact status card treatment:

```text
border border-white/15
bg-white/6
shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]
```

Use deep external shadows mainly on top-level panels, floating menus, and notifications. Avoid individually shadowing every small field.

## 5. Layout and responsive behavior

### 5.1 Root constraints

- Keep the document language `zh-Hant`.
- Preserve the `min-w-[320px]` body floor.
- Keep horizontal overflow prevented at the page level.
- Keep authenticated page background, `px-5 pb-8 max-sm:px-3`, and `MainNavigation` in the root layout rather than copying them into page or feature components.
- Use `min-w-0` on flex/grid children that contain IDs, filenames, device names, or other long data.
- Truncate or wrap long operational identifiers intentionally; do not let them widen the viewport.

### 5.2 Spacing rhythm

The current interface primarily uses:

- `gap-2` for closely related compact status items;
- `gap-3` for control rows and paired content;
- `gap-4` for normal panel content and feature groups;
- `p-3` for compact cards and toggle rows;
- `p-4` for inner panels and mobile panel content;
- `px-5 py-4` for panel headers on larger screens;
- `max-sm:px-4` for compact panel headers.

Prefer existing spacing steps before inventing arbitrary padding. The UI is intentionally compact; do not turn each small fact into a large block.

### 5.3 Breakpoints

The current dashboard uses both Tailwind defaults and targeted arbitrary breakpoints around the layout's real transition points. Important widths seen in the frontend include:

- approximately `520px` for very narrow control/card adjustments;
- `720px` for stacking or expanding schedule and field layouts;
- `900px` for intermediate dashboard organization;
- `980px`/`981px` for major desktop-versus-mobile dashboard behavior;
- `1180px` for wide desktop arrangements.

When editing an existing feature, preserve its current breakpoint unless the layout problem spans the entire dashboard. Test at 320px, near each touched breakpoint, and a wide desktop width.

Do not add several near-duplicate breakpoints to patch one component. Prefer `minmax(0, 1fr)`, `min-w-0`, wrapping, and a single meaningful transition.

### 5.4 Grid and flex rules

- Use grid for repeated fields, status cards, and feature cards that must align.
- Use flex for headers, actions, pills, and simple one-dimensional rows.
- Use `grid-cols-[minmax(0,1fr)_auto]` when content should shrink but an action/status must remain visible.
- Use `shrink-0` for icons, switches, and fixed action controls.
- Use `flex-1` dividers or content only when their shrinking behavior is explicit.

## 6. Shared component standards

### 6.1 `Panel` and `PanelHeader`

Use `Panel` for top-level dashboard regions. It accepts an optional `as` prop and owns the 28px surface, deep shadow, and blur. Consumers may add layout classes through `className`, but should not restate the base surface.

Use `PanelHeader` for the established header row:

- minimum height 68px;
- 8px emerald dot at the left;
- short `h2` title;
- flexible white/10 horizontal rule;
- optional action at the right;
- wrapping and smaller horizontal padding on narrow screens.

Do not replace the header with a colored rail, description block, or oversized banner.

### 6.2 `InnerPanel`

Use `InnerPanel` for a semantically grouped feature inside a main panel. It is a grid with `gap-4`, 22px radius, white/10 border, translucent surface, `p-4`, and a subtle inset highlight.

Avoid nesting multiple `InnerPanel` layers solely for visual decoration. A nested surface should represent real grouping.

### 6.3 `StatusCard`

Always import:

```jsx
import StatusCard from "@/components/cards/StatusCard";
```

Canonical use:

```jsx
<StatusCard
  title="執行時間"
  content="2 分 10 秒"
  note="/ 共 20 分 0 秒"
/>
```

Its semantic regions are fixed:

- `title`: the name only, placed at the upper left;
- `content`: the primary status message/value, centered and visually dominant;
- `note`: a short denominator, unit, total, or supporting status at the lower right.

The live component is a compact `article` with `rounded-xl`, `p-3`, and no descriptive rail. Do not reproduce its markup inside a feature. If a generally useful capability is missing, extend the shared component without changing existing consumers unnecessarily.

For a group of status cards, use an explicit equal-width grid such as `grid-cols-3`; never use content-sized implicit columns such as `grid-flow-col`. Preserve the compact side-by-side presentation when space allows, and add responsive stacking only when content genuinely cannot fit. Each card's content region must remain `min-w-0` and centered so long status text wraps inside its fixed column rather than changing card widths.

#### Shared `InformationGrid`

Use `InformationGrid` from `components/data/InformationGrid.js` for compact fixed-format label/value information. It owns configurable numeric `rows` and `columns`, column-first item flow, full-height neutral column dividers, label/value alignment, optional hover-only requirement tooltip, semantic value tones, narrow-screen stacking, and optional internal horizontal scrolling. Callers provide an `items` array containing `label`, `value`, optional `tone`, optional `requirement`, and optional `truncate`; they must not restate the grid, divider, `dt`, or `dd` classes. Pass only `rows` to derive `columns`, or only `columns` to derive `rows`; when neither is provided the component defaults to two rows and derives its columns. Pass both only when an exact grid capacity is intentional.

Current consumers include calibration coverage metrics, camera intrinsic summaries, available-Record summaries, and persisted capture configuration. Use named props rather than `children` because the component owns a fixed information schema. This component is for compact facts, not dominant runtime status; continue to use `StatusCard` when content requires the title/content/note hierarchy.

### 6.4 `ActionRow`

Use `ActionRow` from `components/actions/ActionRow.js` for an action-button group placed at the bottom of a form, settings surface, or content card. It centrally owns this layout:

```text
place-self-end flex flex-wrap items-center pt-2 gap-2
```

This keeps bottom actions right-aligned, wrapping safely, and separated from the content above. It is currently appropriate for schedule execution controls, settings save actions, and login submission. A compact image-preview footer that keeps status and its capture/reconnect actions on one row uses a direct inline action container rather than `ActionRow`, so it does not acquire the action-row divider.

Do not apply `ActionRow` to panel-header tools, navigation actions, table-cell links, popup close buttons, or controls located at the top of a card.

### 6.5 `SubsectionHeader`

Use `SubsectionHeader` for the small heading group at the top of an internal content block. It fixes the title and description hierarchy across schedule controls and settings subsections. In a schedule mode card, put the selected mode's dynamic description on the `擷取模式` field tooltip instead, so the explanation remains directly attached to its selector.

Its API deliberately combines two separate slot types:

- `title`: required fixed title content;
- `description`: optional fixed supporting text;
- `titleId`: optional ID applied to the heading for `aria-labelledby`;
- `titleMode`: numeric title presentation mode; `0` is the default white title and `1` is the compact emerald title;
- `children`: optional caller-composed actions placed on the right.

The header uses a fixed `minmax(0, 1fr) auto` two-column grid. The title and description wrap only inside the left column, while `children` remains aligned at the upper right and must not be pushed onto a second row by a long description.

Title modes are fixed:

| Mode | Classes | Use |
| --- | --- | --- |
| `0` | `text-base font-black tracking-widest text-white` | Default subsection title |
| `1` | `text-sm font-black tracking-widest text-emerald-200` | Compact repeated-card title such as `擷取 01` |

```jsx
<SubsectionHeader
  titleId="capture-modes-title"
  title="擷取模式"
  description="共五種擷取模式，每一模式將獨立產生紀錄檔。"
>
  <Button>新增擷取</Button>
</SubsectionHeader>
```

Do not locally rebuild its `h3`/description pair. `children` is only the right-side composition slot; it does not replace `title` or `description`.

### 6.6 `Button`

All ordinary action buttons should use the shared `Button`.

Established variants:

- `default`: translucent neutral surface; stronger white border/fill on hover.
- `primary`: solid emerald surface with dark emerald text; lighter emerald on hover.
- `danger`: rose surface for destructive or stopping actions only.
- `ghost`: transparent neutral action with a subtle white hover fill.
- `dangerGhost`: transparent neutral destructive action that changes to a subtle rose fill and rose text only on hover.

Base behavior:

- minimum height 40px;
- `gap-2` between composed icon and text content;
- 12px radius;
- border, horizontal padding 16px and vertical padding 8px;
- `text-sm font-extrabold`;
- 150ms transitions limited to background, border, color, and opacity;
- visible emerald focus outline;
- native disabled state with reduced opacity and non-interactive cursor.

Every standalone text action button includes a leading semantic `react-icons` icon. Use a 16px (`size-4`) non-shrinking icon for ordinary buttons and 14px (`size-3.5`) for compact text-xs actions, with `aria-hidden="true"` because the visible button text supplies the accessible name. Keep existing icon-only controls such as settings, delete, notification, fullscreen, select, and stepper actions icon-only with descriptive `aria-label`; do not add a second icon to them. Toggles, select options, navigation links, and status pills are not standalone action buttons and do not inherit this rule.

Do not manually rebuild these variants in feature files.

### 6.7 Inputs, fields, and number steppers

Use `TextInput`, `NumericInput`, `DurationInput`, and `SelectInput` from `components/inputs/Input.js` for labeled controls. `components/fields/FieldFrame.js` owns only the shared `FieldFrame` surface.

The established field structure uses:

- a `group relative min-w-0` wrapper;
- a floating label at `-top-0.5 left-3`, centered on the control's top border through the `pt-1` field-frame offset;
- minimum input/select-trigger height `min-h-10.5`, so the complete labeled field is the standard 46px height;
- a black/15 input surface;
- white/15 default border;
- `pt-3 pb-2` field text padding that clears the floating label while placing text slightly above vertical center;
- bold 14px input text;
- emerald border and subtle emerald ring on focus.

`NumericInput` keeps values as strings while editing, but its DOM input must use native `type="number"`. Every `Input` control uses `w-full`, so its width follows the available parent space. For numeric inputs, `Input` uses real grid columns for the shrinkable value region, the suffix, and the fixed-width stepper—never invisible right padding or an absolutely overlaid suffix. The numeric control owns one outer border; the suffix receives no box or border, while the stepper retains its existing divider. `Input` itself owns number semantics, clamping, decimal precision, and the shared right-side `NumberStepper`: when `type="number"`, it suppresses the browser-native spinner buttons and renders the stepper automatically. Numeric callers provide `label` for the stepper's accessible names and `onValueChange` for controlled numeric state. Do not introduce another wrapper around `NumericInput`. Preserve the stepper's two-button vertical split and chevron interaction.

Provide stable, feature-prefixed IDs. Repeated schedule-mode fields must incorporate the mode instance ID so no two controls share an ID.

Do not use browser-native number spinners as a visual substitute for the shared number stepper.

Use `DurationInput` for every user-editable duration or interval. It composes the shared `FieldFrame`, presents four linked inputs—days, hours, minutes, and seconds—as one continuous four-column grid. Internal cells remove their duplicate left borders so they sit flush without overlap or overflow, then returns its value in the caller's declared `unit` (`minutes`, `seconds`, or `milliseconds`). Keep API payloads and runtime-setting units unchanged; `durationParts` and `durationValue` in `lib/durationUtils.js` own this pure conversion at the UI boundary.

### 6.8 `SelectMenu`

Use the custom shared select menu when the current form uses it. It provides:

- a 46px rounded trigger matching other fields;
- hover and focus changes to border/fill rather than scale or displacement;
- an emerald selected/open state that still becomes slightly lighter on hover;
- a 150ms chevron rotation and popup opacity transition;
- a deep green translucent popup with blur and shadow;
- outside-pointer and Escape dismissal;
- `aria-haspopup`, `aria-expanded`, `aria-controls`, `listbox`, `option`, and `aria-selected` state.

If adding keyboard option navigation, implement it in the shared component for every consumer rather than in one feature.

### 6.9 `Toggle` and `ToggleRow`

`Toggle` is the visual switch indicator. It uses a 200ms `ease-in-out` transition for the track and thumb, and disables motion under `motion-reduce`.

`ToggleRow` is the actual semantic button and owns `aria-pressed`:

- It shares the standard 46px (`min-h-11.5`) full-field height with labeled inputs/select triggers; use `px-3 py-2`, not oversized vertical padding.
- unselected: white/10 border and black/10 fill;
- unselected hover: subtle emerald border and light neutral fill;
- selected: emerald border and emerald translucent fill;
- selected hover: a lighter emerald border and fill;
- disabled: native disabled behavior and reduced opacity;
- no hover translation or scaling.

Use a single choice/control location for a single system action. Do not create multiple independent motor, capture, or schedule toggles that can contradict one another.

### 6.10 `Tooltip`

The shared tooltip is hover-only by product direction. Visibility is controlled by `group-hover`, not `focus`, `focus-within`, click, or persistent state.

Visual behavior:

- deep green translucent surface;
- white/15 border;
- 8px radius;
- compact 12px text;
- shadow and backdrop blur;
- 150ms opacity transition;
- 150ms initial delay and immediate display after hover begins;
- viewport-aware maximum width.

The parent interactive region must provide the `group` class and suitable positioning/z-index behavior. Tooltip text should clarify an unfamiliar control, not repeat a visible label unnecessarily.

Because panel blur creates stacking contexts, `Panel` starts at `z-0` and raises itself with `hover:z-100` and `focus-within:z-100`. This keeps an active panel's tooltip above later dashboard panels.

### 6.11 `SettingsGear`

Use the shared settings gear for opening and closing settings panels. It keeps one gear icon in both states rather than changing to a close cross.

- Closed tooltip: `開啟設定`.
- Open tooltip: `關閉設定`.
- Closed state: neutral translucent button.
- Open state: emerald border/fill/text.
- Hover: lighter emerald border/fill/text.
- Icon: 12-degree hover rotation and 30-degree open rotation.
- Semantics: descriptive `aria-label` and `aria-expanded`.

The gear rotation is an established exception to the general no-transform hover rule.

### 6.12 Status pills

`StatusPill` is exported from `components/panels/Panel.js`. It is a small rounded-full label with a current-color status dot.

Use tones semantically:

- `success`: emerald;
- `warning`: amber;
- `offline`: rose;
- `neutral`: white/black translucent.

Do not use a status pill where the information needs the title/content/note structure of a `StatusCard`.

### 6.13 Notifications

All transient application notifications should flow through the shared notification state and the bottom-right toast/history interface. Do not recreate a separate "近期通知" panel inside a dashboard section.

Notification UI belongs in `features/Notifications/Notifications.js`; notification state belongs in `features/Notifications/hooks/useNotifications.js`. Mount `NotificationsProvider` once from the root layout so capture, analysis, calibration, models, navigation actions, and future pages share the same bottom-right history. Feature components use `useNotificationsContext`; never mount another `Notifications` instance locally.

Notification interactions always use transitions: trigger, collapse, and close actions use the established 150ms color/fill transition, while history expansion/collapse and toast entry/exit use a 200ms opacity or grid-row transition. Preserve `motion-reduce:transition-none`, and keep hidden history content inert and outside keyboard focus.

Use consistent tone mapping:

- success/normal positive event: emerald;
- warning or incomplete attention: amber;
- error/failure/offline: rose;
- informational event: neutral treatment unless an existing tone applies.

Messages should contain enough operational context to act on, while remaining short enough for a toast. History provides persistence and expansion; individual dashboard sections should not maintain independent message archives.

### 6.14 Login surface

The login form uses the same background, panel, field, button, radius, and typography system as the dashboard. Authentication is not a separate brand surface. Preserve concise Traditional Chinese error feedback and avoid exposing server credentials or implementation details.

## 7. Feature composition standards

### 7.1 Control panel

`features/ControlPanel/ControlPanel.js` is the GOAL-01 capture-system composition boundary and is mounted only by `/capture`. It coordinates capture data, connection state, notifications, settings disclosure state, and the five capture-page regions: `ImagePreview` (`攝影機`), `SystemStatus`, `Schedule`, `Control`, and `RecordsStorage`. Keep feature-specific markup and transformations out of it, and do not mount these capture controls in `/analysis` or `/models`.

`features/MainNavigation/MainNavigation.js` owns the application-level `[捕捉] [分析] [校正] [模型]` route navigation, connection status, emergency stop, logout, and capture-page secondary navigation. It is mounted once by the root layout, derives the five capture anchors from the `/capture` pathname, and consumes the shared socket context rather than accepting page-owned runtime props. Other routes render only the route navigation and global actions. Icon-only actions need accessible labels and must use existing button language.

### 7.2 Schedule

The schedule feature is split by responsibility:

- `Schedule.js`: feature entry and execution controls;
- `components/ScheduleCommonControls.js`: the authoritative arm toggle and the common timing/angle controls selected by that toggle;
- `components/ScheduleModes.js`: list composition and add/remove behavior;
- `components/ScheduleModeCard.js`: one mode container and its controls;
- `components/ScheduleModeFields.js`: mode-specific input selection;
- `components/ScheduleRuntimeStatus.js`: independent top-level `運行狀態` panel rendered immediately before the schedule panel, with four compact status cards for `排程狀態`, `排程執行時間`, `排程`, and `目前角度`;
- `scheduleConfig.js`: defaults and stable mode/status metadata only;
- `lib/scheduleUtils.js`: mode lookup, validation, normalization, and payload construction.

Multiple modes may participate in one schedule. Keep each mode instance independently identifiable, and keep output/logging concepts distinguishable by mode. Shared parameters belong above the mode list rather than repeated within every mode.

`啟用旋臂` is the authoritative schedule movement mode, not a camera-selection switch. Every schedule captures `top + side + rotating`. When disabled, the rotating camera remains fixed, the schedule exposes only total duration, and every added mode must be `continuous_interval`. When enabled, the arm moves while the same three cameras capture, the schedule exposes total cycles, inter-cycle interval, start/end angles, angle tolerance, rotating-arm height, stabilization delay, return-path capture, and final return-to-origin behavior, and permits all five established capture modes. Keep the existing mode-card add, remove, select, and three-column list interaction in both states; only the available mode options and common inputs change. Do not expose a per-cycle-duration or manual rotation-step input. The backend merges the enabled angle-based modes into one ordered set of stop angles; the arm passes through other angles without creating artificial stops.

For rotating schedules, runtime is an observed result rather than a configured limit. The `排程執行時間` status card shows total elapsed execution time without a planned denominator, and the `排程` status card shows the backend-reported actual elapsed time for the current or most recently completed round. Fixed dual-camera schedules continue using the entered `duration_seconds` and may display that configured total as the denominator.

`每輪間隔` (`cycle_interval_seconds`) is a non-negative duration shared by all round-scoped modes. It starts only after one complete forward/return cycle has returned to `0°`, and delays the beginning of the next cycle. The interval counts toward the schedule's total duration, excludes paused time, remains immediately interruptible by stop, and is not applied after the final or an incomplete cycle. Reset every round-scoped mode's per-cycle capture state at the beginning of each new forward/return cycle; in particular, reset each `time_interval` mode's next due time to the new cycle start so waiting time cannot trigger or carry a capture into the next cycle. `continuous_interval` is the deliberate exception: it runs from the schedule clock and continues evaluating during movement and inter-cycle waits.

`Schedule.js` emits the `運行狀態` and `排程` panels as sibling control-panel grid items so both can share the same schedule form state without duplicating it in `ControlPanel`. Keep runtime cards out of the schedule form. The runtime panel contains the equal-width status-card grid directly beneath its `PanelHeader`, without a description block or extra nested surface. Use the live motor command position for `目前角度`, falling back to the schedule angle only when motor status is unavailable.

Every schedule cycle reaches the shared end angle and then returns to the `0°` origin before the next cycle. `往返皆擷取` (`capture_on_return`) selects how that return is performed: when disabled, reaching the end angle is followed by a direct return to the origin with no return-path capture evaluation; when enabled, the motor revisits the same ordered angle-mode stop targets on the return path, excluding the duplicated end point. Reset angle-target completion at the direction change so each target may be captured once in the forward direction and once in the return direction; time-interval modes continue evaluating on the return path only when this option is enabled. Record `motion_direction` in every mode log so the two passes remain distinguishable. Do not add a per-cycle motor-release setting because the motor must remain engaged between cycles. The separate `排程結束後回到原點` option is applied once when the whole schedule completes, stops, or fails so an interrupted partial cycle can still return to `0°`.

The `通用配置` header owns `重新載入`, `儲存配置`, and `預設` actions through `SubsectionHeader` children. The Schedule panel has no settings gear or separate settings disclosure. `儲存配置` persists the moved execution behavior and the shared rotating-arm height together; the height is the same `cameras.rotating.arm_height_mm` value used by camera settings. `預設` restores only `SCHEDULE_COMMON_DEFAULTS`, preserves the current rotating-arm height, and leaves capture modes intact.

Schedule transport mode names are `continuous_interval`, `time_interval`, `angle_interval`, `specific_angles`, and `equal_divisions`. `continuous_interval` means uninterrupted schedule-clock capture and is the only mode permitted without the rotating arm. `time_interval` resets for each rotating round, captures by the round clock while the arm moves, and does not create angle stops or capture during the inter-round wait. Angle-interval, specific-angle, and equal-division modes define the actual stabilization and capture stops. `seconds_interval` is obsolete and may appear only in an explicit legacy-normalization path.

Scheduled output uses snapshot-owned camera files rather than camera-owned folders. Round-scoped modes write `rounds/round-xx/<mode>/snapshots/snapshot-xx_<timestamp>/<camera>.jpg`; reset the snapshot sequence to `01` inside every new round. `continuous_interval` and every fixed dual-camera schedule write `continuity/<mode>/snapshots/snapshot-xx_<timestamp>/<camera>.jpg` with one schedule-wide sequence. Keep the mode log beside its `snapshots` directory. Every snapshot folder groups the `top`, `side`, and when enabled `rotating` observations from one trigger.

Mode-specific calculation rules must not be hidden in JSX. Angle-tolerance logic, parsing comma-separated angle strings, equal-division calculation, and payload construction belong in the schedule library. Equal divisions treat `points` as the total number of capture points including both the shared start and end angles; the interval is therefore `(end - start) / (points - 1)`. Fixed dual-camera submissions send `duration_seconds`. Rotating submissions send `total_cycles` and `cycle_interval_seconds`; they do not send a planned per-cycle duration or step angle. All editable durations remain expressed in seconds at the backend boundary. Convert minute-based stored defaults only when loading them into the schedule UI.

### 7.3 Settings

`components/panels/SettingPanel.js` is only the composed disclosure/container surface. It owns the shared `ActionRow` placement through its `footer` slot, with `px-6 pb-6` as the default footer spacing, but it must not branch on a settings group, fetch data, own field layouts, or contain feature-specific markup. `features/Settings/Settings.js` owns the generic settings editor; its config, field components, and utilities remain inside the Settings feature.

`features/ImagePreview/components/ImagePreviewSettings.js` is an independent ImagePreview feature component whose formal UI title is `攝影機`. It owns the camera-only layout: no repeated camera title, an enabled toggle across each camera column, regular inputs in a responsive grid of at most three columns, and a same-column `相機安裝參數` subsection. `top` and `side` own optional installation height and optional horizontal distance to the world origin. Their directions are fixed domain constants rather than editable settings: `top` points vertically downward (`90°`) and `side` points horizontally (`0°`). `rotating` owns the optional shared rotating-arm height and its own optional horizontal distance to the world origin. Camera settings must never be restored as a conditional branch inside `SettingPanel` or the Settings feature.

Exposure remains owned by each camera driver's native automatic-exposure behavior. Do not expose central metering, target brightness, baseline exposure, manual exposure range, or a custom exposure-adjustment toggle in camera settings, and do not make the frontend imply that the application writes hardware exposure values.

The ImagePreview `裝置索引` field uses the shared custom select rather than a numeric input. Its first option is always `無`, representing a real unassigned `null` value and disabling that camera when selected. Every camera field displays the same complete set of detected physical devices, including devices currently owned by another ImagePreview role or by its active worker; never hide a device merely because another role uses it. Continue to omit empty, undetected index placeholders. Labels use only `裝置 {index} {name}` without backend role names, mock badges, availability text, or parenthetical status. Selecting a device assigns it to the current role and enables that role; if another role already owns the device, atomically clear and disable the previous role so one physical camera serves exactly one view. A successful scan only refreshes the option list and must not change assignments by itself. Keep the explicit rescan action with pending and failure handling, and reject an enabled camera without an assigned device before saving. Backend reconfiguration must release every changed worker before opening replacements so transferring a device cannot briefly create two readers for the same index.

The `攝影機` panel header keeps its actions in this order: `擷取全部`, `重新連線全部`, then the settings gear. `擷取全部` remains unavailable while a schedule is active; `重新連線全部` uses the single `camera.reconnect_all` command and remains available during a schedule, matching individual camera reconnection. Let the action group wrap on narrow screens instead of overflowing the panel header.

Each image preview places its camera name over the upper center of the image instead of repeating it in the footer. The name uses a compact translucent bordered surface with square top corners and `rounded-b-xl` lower corners. An icon-only enlarge action remains at the lower right of the image. `features/ImagePreview/components/ImagePreviewFullscreen.js` owns the full-viewport dialog and renders it through a body portal so panel overflow and stacking contexts cannot clip it. Opening and closing use 400ms opacity and size transitions with `motion-reduce` support. Preserve background-click and Escape dismissal, body-scroll locking, a visible close action, and descriptive Traditional Chinese accessible labels.

Each inline preview also shows `FPS: {value}` in a compact translucent bordered badge at the lower left. The value comes from the backend camera worker's measured, encoded-frame publication rate, rounded to a whole number; it is never copied from the configured preview or capture FPS. Show `FPS: 0` until enough live frames exist or whenever the stream becomes stale or disconnected.

The inline image-preview viewport and its waiting/disabled placeholder use `aspect-video` for a stable 16:9 layout. Render the stream on its existing black surface with `object-contain` so scientific image content remains complete instead of being cropped to fill the viewport. Fullscreen preview continues to contain the complete image within the available screen.

Mount an MJPEG `<img>` only while that camera is enabled, connected, and the browser page is visible. The first connected render opens the stream with its current source exactly once; do not change the source merely because status changed from disconnected to connected or because a reconnect action completed. Stream errors own bounded source-token retries. Unmount the stream when the camera disconnects or the page becomes hidden so long-lived HTTP/1.1 requests cannot accumulate and exhaust the browser's same-origin connection pool, which would otherwise block settings and control requests.

ControlPanel settings disclosure state is an array of open group IDs, not a single selected group. Toggling one gear changes only that group's membership, so multiple setting panels may remain open together. Initialize the capture page with the `cameras` group open; users may still close it with its settings gear.

`features/Settings/components/SettingsSection.js` uses `content-start` so each settings column remains top-aligned when a neighboring section contains more controls. Do not stretch or distribute a section's controls to fill the tallest grid row.

Do not redefine each setting field in the panel file. Preserve one authoritative control for an action/status rather than allowing separate settings and main-section controls to diverge.

### 7.4 Image preview, control, records storage, and system status

Feature entry components may arrange their domain data and actions but should reuse:

- `Panel`/`PanelHeader` for section framing;
- `InnerPanel` for grouped device/record content;
- `Button`, fields, pills, and toggles for controls;
- pure helpers from the owning feature's `lib/` or root `lib/` only when shared;
- the shared notification channel for results and errors.

`RecordsStorage` presents each record's `ID`, status, storage path, creation time, terminal end time, and export actions in one table. Keep the table within a height-limited internal scroll area with a sticky header. `ended_at` remains empty for active and legacy records and is written only when a schedule reaches `completed`, `stopped`, or `failed`; display unavailable values as `—`.

The formal UI title is `紀錄與儲存`. Use `record_id` and `record_path` from the transport and `recordId` in local JavaScript. Its configured file root is the project-relative `captures_dir` path (`data/captures` by default), and the label is `擷取檔案儲存位置`. Every storage setting returned to or saved by the frontend, and every Record-level `record_path` stored in SQLite or displayed in the Record list, must remain relative to the project root. Do not introduce a machine-specific absolute-path mapping layer. Captured binaries and required log/export files stay under this directory; do not move them into SQLite or rename the root to `records_dir`. Keep capture paths inside Record metadata relative to the Record root because they are portable relationships.

The canonical camera identifiers and Traditional Chinese view names are `top`/`俯視角`, `side`/`側視角`, and `rotating`/`旋臂視角`. Use them consistently in frontend metadata, backend settings, API payloads, runtime state, schedule fields (`capture_top`, `capture_side`, `capture_rotating`), and all newly generated storage paths. Manual capture actions in ImagePreview are standalone snapshots. Both the individual `擷取` action and `擷取全部` use snapshot actions rather than Record capture actions, store images directly in `snapshots_dir` (`data/snapshots` by default) without nested directories, and use filenames containing the camera identifier plus a timestamp. Snapshot operations do not create Record/Capture rows; scheduled and record-owned captures continue using `captures_dir` and SQLite relationships.

Motor and capture actions must have one authoritative activation point. The `控制` panel owns simple direct motor actions: holding torque, moving to a target angle, setting/returning to origin, and stopping. Other locations may show state, but must not create independent controls with conflicting state. The backend starts motor auto-detection and connection independently of user commands, retries while no controller is available, and publishes `motor.connected` as the authoritative state. `系統狀態` displays a dedicated `馬達連接` row. Disable and apply grayscale to the complete direct-control surface and its settings whenever the realtime connection or motor connection is unavailable, or while a schedule is running, paused, or stopping. A rotating schedule cannot start while the motor is disconnected; fixed dual-camera capture remains available.

The motor origin is always the numeric `0°` reference and is not an editable setting. `設為原點` redefines the motor's current physical position as `0°`; `回到原點` consequently moves to `0°`. Never reintroduce an `origin_deg` field or a configurable origin-angle value in the frontend, API model, persisted settings, or hardware adapter. In motor movement settings, place `速度限制` and `加速度限制` in the same two-column grid with an explicit gap, and let the duration-style movement timeout span the full row beneath them.

While a schedule is running, paused, or stopping, every user-initiated modification is locked across the control panel: schedule configuration and modes, direct motor controls, manual camera capture, and every settings group. Keep read-only views, notification history, record refresh, camera reconnection, schedule pause/resume/stop, and emergency stop available. Use native disabled controls inside a visually grayscale group, and preserve matching backend enforcement so stale clients cannot bypass the lock.

### 7.5 Analysis creation and calibration

Analysis creation has one Record-backed source workflow. Do not show source-type cards, analysis-method cards, tabs, a data-source discriminator, or manual directory entry. Make the Record list the first `選擇紀錄` step of `新增分析`; do not render it as a separate dashboard panel or inside `配置設定`. Give the list a fixed maximum height and let its record items scroll internally. Each Record's preselection information list shows exactly four metrics: start time, end time, persisted capture-mode count, and total captured-image count. Do not show per-camera or pairable-frame counts there; pairing belongs to the post-selection scan result. Present these four metrics in the same two-row, column-flow layout as `CalibrationCoverageMap`, with the complete divider between its two columns. Selecting a Record fills one read-only Record root directory and its available schedule modes from persisted metadata. Keep every `continuous_interval` mode visible but unselected by default, default-select every other available mode, and immediately scan only when that default selection contains at least one mode. The second `配置設定` step owns `捕捉配置`; never expose separate per-camera or mode-directory path fields. Display the immutable Record-level schedule configuration directly below the root directory using the same two-row, column-flow metric layout as `CalibrationCoverageMap`: labels and values share a row, values use emerald emphasis, and full-height neutral dividers separate columns. Render the modes inside one compact `選取模式` block, with one `aria-pressed` selectable pill per mode. Pills wrap within the block, retain lighter hover feedback when selected, use `cursor-pointer`, and display the mode name, instance number, persisted configuration, and actual image count. Use a hollow-circle icon for an unselected mode and a check icon for a selected mode. Changing the selected modes immediately rescans the selected data without rewriting the Record root. Render the top, side, and rotating enabled flags as three controls in one separate responsive row; toggling a flag does not invalidate the directory preview.

Render the `捕捉配置` heading, read-only Record root, Record summary, immutable Record-level schedule configuration, mode selector, camera row, and controls directly in the second-step setup panel. Its summary repeats the selected Record's start time, end time, persisted mode count, and total captured-image count using the shared `InformationGrid` before the schedule configuration values. Do not wrap that section in another `InnerPanel`, repeat its heading, or add a decorative nested surface. The scan result is a same-level sibling section separated by the established white/10 rule. Transient step validation and source-scan warnings belong only in the global bottom-right notification history; do not duplicate them as amber or rose warning blocks inside `新增分析`.

Render the three canonical sources as `top`/`俯視角`, `side`/`側視角`, and `rotating`/`旋臂視角`. Each source row owns its enabled toggle and path input, then shows scan-derived image count, resolution, pairing state, and safe Traditional Chinese errors. A path change invalidates the previous preview. Do not let the user proceed until the current paths have been scanned, enabled files are readable and resolution-consistent, and pairing is valid.

Treat camera toggles as Boolean analysis flags. `top` and `side` are mandatory, permanently enabled, disabled controls in the UI, and are forced to `enabled: true` again at the payload boundary. `rotating` defaults to enabled after initialization and every Record selection, but remains user-adjustable. Changing the rotating flag preserves the Record path, invalidates the previous preview, cancels any stale scan, and immediately scans again with the newly inferred method. Infer `rotating` when the rotating camera is enabled and otherwise use `fixed`, rather than presenting separate method-selection buttons.

The only method values are:

- `fixed`: fixed top-and-side tip analysis; requires enabled `top` and `side` sources.
- `rotating`: Round-based multi-view reconstruction; requires all three sources, at least one valid rotating angle, valid Round grouping, camera intrinsics, an ArUco world reference, and an available reconstruction backend.

Rotating angles may come from Record metadata, canonical filenames, or an imported angle CSV. Present their availability as source-validation state rather than as another analysis mode. Missing or invalid rotating observations must be explained before submission; during result rendering, a rejected rotating observation falls back to the `top+side` baseline for that frame instead of failing the complete run.

Calibration is an independent top-level feature at `/calibration`, beside `/analysis` in the main navigation. Analysis must not render calibration or ArUco creation, editing, validation, settings, matrices, or profile-management UI. It consumes the available intrinsic calibration and the ArUco reference as read-only analysis dependencies. Missing required calibration is reported through the shared notification channel and directs the operator to `/calibration`; do not recreate an embedded calibration or ArUco step.

The `/calibration` page owns one unified single-page workflow arranged as three top-level panels: `校正板`, `ArUco 基準`, and `內部參數`. On desktop widths at `981px` and above, place `校正板` and `ArUco 基準` side by side in one equal-width row; stack them vertically below that breakpoint, while `內部參數` remains full width beneath them. `校正板` keeps its OpenCV board controls permanently visible instead of hiding them behind an add disclosure. Its board type, profile name, ArUco dictionary, marker ratio, and print margin are fixed implementation details and must not be selectable or displayed as form fields. The operator selects only the paper size, print orientation, and grid dimensions; the backend derives the physical square/marker sizes from the printable paper area, generates a 300 DPI PNG at the selected paper dimensions, saves a reusable historical profile, renders its preview, and provides a direct download. `ArUco 基準` is directly visible in its panel and owns only the marker-world reference; it has no settings gear and never contains camera installation parameters. `內部參數` presents `top`, `side`, and `rotating` horizontally as three camera-owned cards. Each card combines one shared live stream, connection/board/intrinsics status, a three-value active-intrinsics summary (model, resolution, reprojection error), and the current calibration actions. Do not restore separate preview and intrinsics rows, snapshot controls, marker/corner/sharpness counters, full error breakdowns, or a second undistorted preview in this panel. Camera-model comparison remains fixed to automatic selection. Rebuild intrinsics only after the physical camera/lens/focus/resolution relationship changes. A failed calibration attempt must remain retryable and must not overwrite the last valid result.

Nominal CM1.3M30M12Q specifications such as AR0130, 2.1 mm lens, or 126° diagonal FOV are initialization hints only. Never present them as solved intrinsics. Matrices shown in advanced calibration views are read-only and system-calculated; no frontend form may accept a manually entered transformation matrix.

The analysis request boundary sends `record_id`, selected `mode_ids`, `method`, `camera_sources.top|side|rotating` entries shaped as `{ enabled, path }`, and `calibration_id`. A manually entered source may send a null `record_id` and an empty `mode_ids` list. Never derive separate downstream pipelines from how paths were populated: both Record-filled and manual paths become the same immutable input manifest and use the same scan, pairing, analysis, and result flow.

Each analysis owns one result page and one chart set. `fixed` displays the fixed-camera tip-marker trajectory. `rotating` displays each Round model, plant point cloud, skeleton, three-dimensional tip marker, reprojections, and the cross-Round trajectory. Preserve per-view pose and reprojection quality, rotating angles, selected reconstruction views, model quality, and tip-marker provenance so every result remains auditable.

## 8. Interaction and motion

### 8.1 Default motion

- Use 150ms for button, select, tooltip, gear-color, chevron, border, background, color, and opacity feedback.
- Use 200ms `ease-in-out` for toggle track/thumb changes.
- Restrict transition properties rather than using broad animation when possible.
- Add `motion-reduce:transition-none` to meaningful movement, especially switches and new transform-based state changes.

### 8.2 Hover

Normal hover feedback changes border, fill, and text color. Selected controls must retain hover feedback by becoming slightly lighter or clearer.

Do not use:

- scale-up or scale-down hover;
- positional shifts;
- bouncing;
- large shadow jumps;
- attention-seeking continuous animation.

Existing allowed transforms are switch-thumb translation, select-chevron rotation, and settings-gear rotation.

### 8.3 Focus

Interactive controls require a visible emerald `focus-visible` outline or the established emerald field border/ring. Tooltip visibility remains hover-only even when the parent receives focus.

Focus should not visually move or enlarge a control.

### 8.4 Disabled, loading, and pending

- Use native `disabled` wherever possible.
- Pair disabled state with `cursor-not-allowed` and reduced opacity.
- Prevent duplicate async submissions at the action boundary.
- Keep the previous layout size while loading to avoid jumps.
- Display operational pending/error results through the shared status or notification components rather than inserting a new banner style.

## 9. Accessibility

Every change must preserve or improve:

- semantic `button`, `form`, `label`, heading, list, table, and article elements;
- `aria-label` for icon-only controls;
- `aria-expanded` for disclosure/menu/settings triggers;
- `aria-pressed` for toggle buttons;
- `aria-haspopup`, `aria-controls`, and listbox state for custom selects;
- `aria-live` for changing operational messages where appropriate;
- native `disabled` state;
- keyboard dismissal of popups with Escape;
- sufficient contrast for operational information;
- readable content at 320px without horizontal page scrolling.

Do not rely on color alone for important state: pair color with a text label, icon, or explicit state value.

Repeated component instances must have unique IDs. Do not generate IDs from an array index if instances can be reordered or removed and already have stable domain IDs.

## 10. JavaScript and React conventions

### 10.1 Imports and modules

- Use JavaScript files and the existing `@/` alias for source imports.
- Keep import groups readable: external packages before internal modules, with a blank line when it improves scanning.
- Prefer default exports for the repository's single-component modules and named exports for modules that intentionally expose a small related set.
- Do not add barrel files merely to shorten imports.

### 10.2 Class names

Build classes directly with template literals:

```jsx
className={`base classes ${active ? "active classes" : "inactive classes"} ${className || ""}`}
```

Do not use or add `cx`, `cn`, `clsx`, `classnames`, or a homegrown joiner. Keep class branches adjacent to the visual state they represent.

Avoid constructing Tailwind class names from partial strings because the scanner cannot reliably discover them. Select complete utility strings in each branch.

#### Readable prop and parameter layout

Keep multi-part React and JavaScript declarations readable. When a component invocation, JSX element, or function declaration has more than one prop or parameter, put every prop or parameter on its own line. A one-line form is reserved for exactly one prop or parameter.

Keep conditional template-literal class sections on their own lines as well. Do not compress a multi-branch `className` expression into one long line merely to reduce line count.

### 10.3 Component shape

- Keep props explicit and domain-named.
- Pass remaining DOM props with `...props` only in low-level primitives where it is intentional.
- Use an `as` prop only for primitives that genuinely support multiple semantic elements, as `Panel` and `InnerPanel` do.
- Prefer small early-return rendering helpers over deeply nested conditional JSX.
- Keep event handlers near the state/action they invoke, but move reusable transformations into `lib`.
- Use stable keys from domain IDs rather than array positions.

#### Container content versus fixed-format props

Choose a component API from the component's structural responsibility:

- Use an explicit `children` prop when the component is primarily a layout, surface, or semantic container whose nested content is intentionally composed by its caller.
- Use semantic named props when the component owns a fixed visual and semantic format with known slots.
- Destructure `children` explicitly. Do not rely on `children` being forwarded accidentally through `...props`.
- Render a container with an opening and closing element and place `{children}` at the intended content location.
- Do not offer both arbitrary `children` and named props for the same content slot; this creates two competing APIs.

Container-style examples:

```jsx
export default function InnerPanel({
  as: Component = "div",
  children,
  className,
  ...props
}) {
  return (
    <Component
      className={`base classes ${className || ""}`}
      {...props}
    >
      {children}
    </Component>
  );
}
```

Use this pattern for components such as `InnerPanel` and `ActionRow`, where callers intentionally provide different child components. Content-bearing primitives such as `Button` may also accept `children` because their label/icon composition is caller-owned.

Fixed-format examples:

```jsx
<StatusCard
  title="執行時間"
  content="2 分 10 秒"
  note="/ 共 20 分鐘"
/>
<PanelHeader
  title="排程"
  action={<SettingsGear />}
/>
<ToggleRow
  label="鎖定馬達位置"
  description="…"
  status={<StatusPill>保持中</StatusPill>}
/>
```

Keep `StatusCard`, `PanelHeader`, `ToggleRow`, fields, and similar structured components on named props because the component owns the meaning, order, and styling of each slot. Do not replace these props with arbitrary children merely to reduce the prop count. A component such as `SubsectionHeader` may still use `children` for a distinct caller-owned action slot while keeping its fixed title and description on named props.

### 10.4 Client boundaries

Add `"use client"` only where hooks, browser APIs, event state, or interactive client behavior require it. Do not spread the directive into pure components or server entry points simply because a child is interactive.

Browser-only APIs belong inside effects or client modules. Server and initial client markup must remain deterministic to avoid hydration mismatches.

The root layout currently tolerates browser-extension attribute injection at the document boundary. Do not use hydration suppression to conceal application-generated nondeterminism elsewhere.

### 10.5 Language and naming

- User-facing content is Traditional Chinese.
- Component and JavaScript identifiers use clear English names.
- Backend field names may remain English `snake_case` at the transport boundary.
- Normalize transport shapes in `lib` before broad UI use when that reduces repeated boundary-specific naming.
- Stable metadata and option lists use named constants rather than inline anonymous arrays repeated across renders.
- Formal names are fixed: `ControlPanel`/控制台, `Control`/控制, `SystemStatus`/系統狀態, `Schedule`/排程, and `RecordsStorage`/紀錄與儲存. Keep `MotorControls` as the motor-specific child of `Control`.
- Never use `Experiment` for schedule behavior, `Status` or 即時狀態 for the SystemStatus feature, or business-domain `Session` for capture records.

## 11. State, data, and network boundaries

### 11.1 State ownership

Keep state at the narrowest level that owns the behavior:

- purely visual local disclosure state stays in the component;
- feature state shared by feature components stays in their nearest feature parent or hook;
- application-wide notification/socket/settings-panel behavior stays in reusable hooks coordinated by the control panel;
- deterministic derived values are calculated by pure helpers rather than duplicated state.

Avoid keeping two independently mutable copies of one backend status.

### 11.2 WebSocket behavior

Reusable connection, reconnection, message parsing, and cleanup behavior belongs in `usePhytoSocket.js`. The authenticated root layout mounts one `PhytoSocketProvider`; `MainNavigation` and feature hooks consume `usePhytoSocketContext` so route components never open parallel status sockets or pass connection state back up into the application shell.

Always clean up listeners, timers, and connections created by an effect. Keep same-origin/session ticket behavior intact.

### 11.3 HTTP and BFF routes

Browser components call the same-origin `/api/...` surface. Next.js route handlers proxy to the backend using shared helpers rather than exposing backend credentials to the browser.

Preserve these current security and transport expectations:

- authentication session data stays in signed, `httpOnly`, `SameSite=Strict` cookies;
- backend secrets/tokens remain server-only;
- password verification remains timing-safe;
- proxied paths are safely encoded;
- only intended request/response headers are forwarded;
- response caching remains disabled for live operational data;
- request bodies respect the proxy's size limit;
- errors returned to the browser do not leak credentials or internal stack details.

Do not bypass shared `api-proxy`, `backend`, `http`, or `session` helpers with an ad hoc route implementation.

### 11.4 Formatting and validation

Formatting functions must tolerate missing, stale, and malformed backend values. A UI component should receive a display-ready value or a predictable fallback rather than reproduce parsing logic.

Validate schedule/settings payloads before submission. Error messages should identify the relevant Traditional Chinese field or mode, while transport field names remain inside the library/API boundary.

### 11.5 Async failures, retries, cancellation, and reset

Every asynchronous feature must define its pending, success, failure, retry, cancellation, stale-result, and reset behavior. Never leave a rejected promise, spinner, disabled control, socket command, or optimistic value without a terminal path.

- Convert unknown transport failures to concise Traditional Chinese messages; do not expose stacks, credentials, backend origins, raw HTML, or unbounded response bodies.
- Release pending flags, timers, and request registries in `finally`. Guard state and notifications after unmount, and use an AbortController, request generation, or identity check so an older completion cannot overwrite newer state.
- Keep the previous valid snapshot/list while refreshing. A failed read must expose a visible retry action; a successful retry clears only that feature's load error.
- Automatically retry only idempotent reads, status polling, preview recovery, ticket acquisition, or reconnect operations. Bound retry delay/frequency, clean every timer on unmount, and respect normalized `retryable`/`Retry-After` hints when available.
- Never automatically retry a mutation after timeout or transport loss because the backend may already have applied it. Report that the result is unknown and require status refresh before another mutation.
- Prevent duplicate mutations with an action-scoped pending registry. Do not use one global busy flag when unrelated recovery actions must remain available.
- Blocking manual motor move and return-to-origin actions use a same-origin HTTP/BFF request with an action-scoped timeout long enough for the configured motor movement timeout, leaving the status WebSocket free to publish snapshots. Motor stop and emergency stop use separate HTTP requests so they can interrupt an active move, and their pending state remains separate from the original movement.
- Backend code `operation_cancelled` means an intentional interruption. Resolve the interrupted UI action without an error toast, and never copy it into notification history or backend `recent_errors`.
- Clear shared errors only after `system.errors.reset` succeeds, then clear the local notification history. If reset fails, preserve both lists and show the reset failure.
- Schedule runtime reset is separate from error-history reset. Never reset a live worker; preserve a failed schedule and its `last_error` until the explicit schedule reset succeeds.
- Settings saves must not overwrite edits made while a request is pending. Disable the edited surface or merge/commit only the submitted revision after success.

## 12. Extraction and reuse rules

Extract a JSX block when at least one of these is true:

- it has a stable name and visual identity;
- it has its own props or behavior;
- it is repeated or likely to be used across features;
- it obscures the parent's orchestration purpose;
- it needs independent accessibility or responsive treatment.

Extract a function when at least one of these is true:

- it is pure and testable;
- it performs parsing, validation, normalization, formatting, or serialization;
- it is reused;
- it represents a domain rule;
- its detail makes the component's intent difficult to see.

Keep code local when it is a short, single-use expression whose extraction would only create navigation overhead.

Choose the destination by meaning:

| Extracted item                      | Destination              |
| ----------------------------------- | ------------------------ |
| Cross-feature visual primitive/frame/container | `components/<role>` |
| Feature entry or feature-only component | `features/<Feature>/` or `features/<Feature>/components/` |
| Feature-only state/effect lifecycle | `features/<Feature>/hooks/` |
| Cross-feature state/effect lifecycle | `hooks/` |
| Feature config constants | `features/<Feature>/<feature>Config.js` |
| Feature parsing/validation/serialization/API helper | `features/<Feature>/lib/*Utils.js` |
| Cross-feature pure/server utility | `lib/` |
| Server mutation with form semantics | `app/actions`          |
| Same-origin backend proxy endpoint  | `app/api`              |

After extraction, update all consumers and remove the old definition. A shared component plus a stale local copy is not a completed refactor.

## 13. Patterns to avoid

Do not introduce:

- local copies of `StatusCard`, `Button`, field, toggle, tooltip, panel, or settings-gear markup;
- locally restated bottom action-row layouts instead of the shared `ActionRow`;
- locally rebuilt small title/description groups instead of the shared `SubsectionHeader`;
- feature components or helper methods nested inside a large feature entry component without a strong locality reason;
- multiple independent controls for the same motor, capture, or schedule action;
- a second recent-message list outside the shared notification history;
- description bars above status values;
- colored side rails used as generic status decoration;
- English decorative labels such as `LIVE`, `SYSTEM`, or `CONTROL` when they add no operational meaning;
- gradients or unrelated accent colors;
- oversized narrative status panels for small values;
- hover movement or scale effects;
- focus-triggered tooltips;
- broad `transition-all` when a limited property list is sufficient;
- duplicated IDs in mapped fields;
- dynamic partial Tailwind utility strings;
- white text opacity utilities such as `text-white/55` when a neutral gray text color is intended;
- `cx`, `cn`, or class-joining dependencies;
- server credentials, backend base URLs, or session secrets in client code;
- silent catches that discard an actionable failure;
- hydration suppression as a general fix for nondeterministic rendering;
- business-domain `Session`, `session_id`, `session_path`, `/api/sessions`, or `sessions.list` names outside an explicit legacy adapter;
- automatic retry of mutations with an unknown outcome;
- clearing local error UI before its backend reset succeeds;
- treating intentional `operation_cancelled` as an operational error.

## 14. Change workflow

For every frontend task:

1. Read the user request and identify whether it changes behavior, visual language, architecture, or all three.
2. Inspect the active file plus its imported components, hooks, helpers, and consumers.
3. Search for an existing shared implementation before writing new markup or logic.
4. Check the worktree and preserve unrelated user edits.
5. Decide ownership before editing.
6. Implement the smallest coherent change, including all affected consumers.
7. Remove obsolete local implementations and stale imports.
8. Review desktop and mobile layout classes, hover/open/selected/disabled states, and keyboard semantics.
9. Run static checks and a proportionate build/HTTP check.
10. Report exactly what changed, what was verified, and any limitation that remains.

When a request intentionally changes the design system, update the shared primitive first, then its consumers, then this standard. Do not patch each consumer independently.

## 15. Validation checklist

### Architecture

- [ ] No reusable component was added inside a section file.
- [ ] No pure domain rule remains embedded in JSX or an event handler.
- [ ] Existing shared primitives were reused.
- [ ] All old local copies and imports were removed.
- [ ] Client boundaries remain as narrow as practical.

### Visual consistency

- [ ] New surfaces use the established green/white translucent palette.
- [ ] Radius follows the 28px/22px/12px/full hierarchy.
- [ ] Typography matches the existing role hierarchy.
- [ ] Gray text uses `text-neutral-*`, not `text-white/<opacity>`.
- [ ] Selected controls still have visible hover feedback.
- [ ] No unrequested gradient, colored rail, description bar, or decorative English label was added.
- [ ] Status information uses the appropriate `StatusCard` or `StatusPill` form.

### Interaction and accessibility

- [ ] Hover does not translate or scale controls.
- [ ] Motion duration and `motion-reduce` behavior are appropriate.
- [ ] Tooltips are hover-only.
- [ ] Icon buttons have accessible labels.
- [ ] Disclosure/toggle/select state has correct ARIA attributes.
- [ ] Disabled and pending controls cannot submit twice.
- [ ] Repeated fields have unique stable IDs.

### Responsive behavior

- [ ] Layout works at the 320px minimum.
- [ ] Long IDs/names cannot force horizontal page overflow.
- [ ] Touched layouts were checked around 520px, 720px, 900px, 980px, and 1180px as relevant.
- [ ] Fixed-size icons/actions do not collapse and content uses `min-w-0` where needed.

### Data and security

- [ ] Browser requests stay on the same-origin BFF surface.
- [ ] Server credentials and signed-session details stay server-only.
- [ ] Payload validation and transport formatting use shared helpers.
- [ ] Effects clean up sockets, listeners, and timers.
- [ ] Rendering is deterministic across server and initial client output.
- [ ] Every async pending state has success, failure, cleanup, stale-result, retry, and reset behavior.
- [ ] Automatic retries are bounded and limited to safe/idempotent work.
- [ ] Capture records use Record naming; login/authentication state alone uses session naming.
- [ ] Intentional motor cancellation does not enter notifications or recent_errors.

### Commands and process

- [ ] Search touched paths for stale references and duplicate implementations.
- [ ] Run `git diff --check`.
- [ ] Run a relevant frontend compile/build check when feasible.
- [ ] If a development service is already running, use it only for non-destructive verification.
- [ ] Never stop a service started by the user.
- [ ] If a test server was started for validation, stop it before finishing.
- [ ] Report active `.next` locking or build limitations instead of deleting user state.
