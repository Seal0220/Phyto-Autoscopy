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
- `frontend/src/app/layout.js`
- `frontend/src/components/ui/panel.js`
- `frontend/src/components/ui/inner-panel.js`
- `frontend/src/components/ui/status-card.js`
- `frontend/src/components/ui/action-row.js`
- `frontend/src/components/ui/subsection-header.js`
- `frontend/src/components/ui/button.js`
- `frontend/src/components/ui/input.js`
- `frontend/src/components/ui/field.js` (`FieldFrame` only)
- `frontend/src/components/ui/select-menu.js`
- `frontend/src/components/ui/toggle.js`
- `frontend/src/components/ui/toggle-row.js`
- `frontend/src/components/ui/vertical-line.js`
- `frontend/src/components/ui/tooltip.js`
- `frontend/src/components/ui/settings-gear.js`

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
│  ├─ actions/               # server actions such as authentication
│  ├─ api/                   # same-origin BFF route handlers
│  ├─ globals.css            # Tailwind v4 entry point only
│  ├─ layout.js              # document shell, font, body foundation
│  └─ page.js                # authenticated page entry
├─ components/
│  ├─ ui/                    # cross-feature visual primitives
│  ├─ schedule/              # schedule-only components
│  ├─ settings/              # settings-only components
│  ├─ notifications/         # notification-only components
│  ├─ sections/              # dashboard section orchestration
│  └─ *.js                   # application-level compositions
├─ hooks/                    # reusable client state and effects
└─ lib/                      # pure domain, format, validation and transport helpers
```

### 3.1 `components/ui`

Place a component here when it describes a reusable visual or interaction primitive rather than a business feature. Examples include `Panel`, `InnerPanel`, `StatusCard`, `ActionRow`, `SubsectionHeader`, `Button`, fields, select menus, toggles, `VerticalLine`, tooltips, and the settings gear.

A UI primitive should:

- expose a small semantic prop interface;
- own its established classes and interaction states;
- accept `className` when consumers need layout-level extension;
- avoid importing feature metadata or calling feature APIs;
- remain usable by more than one section or feature.

### 3.2 Feature folders

Use `components/schedule`, `components/settings`, and `components/notifications` for components whose meaning and props belong to one feature. These components may compose shared UI primitives, but they should not duplicate primitive markup.

Create a new feature folder when multiple components share one domain and keeping them beside an unrelated section would obscure ownership.

### 3.3 Sections

Files in `components/sections` are page-level compositions. A section may select feature data, invoke hooks passed from its parent, arrange feature components, and display loading/error/empty states. It should not contain:

- a locally defined reusable card or control;
- a long option/configuration registry;
- payload serialization;
- angle, time, schedule, or status algorithms;
- a reusable effect or event subscription;
- duplicated formatting helpers.

### 3.4 Hooks and libraries

Use `hooks` for reusable client lifecycles and state machines such as notifications, WebSocket connections, and settings-panel state.

Use `lib` for deterministic modules such as:

- schedule defaults, mode metadata, parsing, validation, and payload construction;
- settings schema and transformations;
- date, duration, value, or status formatting;
- camera normalization;
- request and BFF helpers;
- authenticated session helpers.

Pure code belongs in `lib` even if it currently has one caller when it represents a domain rule that should be independently testable.

## 4. Design foundations

### 4.1 Overall visual language

The interface is a dense, dark, near-black green control dashboard with translucent glass-like surfaces. It should feel technical and calm, not decorative.

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
| Quiet control             | `bg-black/15`, `bg-black/10`         | Inputs, unselected control rows         |
| Structural border         | `border-white/10`                      | Panels, cards and ordinary grouping     |
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
| Inner feature panel        | `rounded-[22px]`                                               |
| Controls and compact cards | `rounded-xl`                                                   |
| Popup options and tooltip  | `rounded-lg` or `rounded-xl` according to the live primitive |
| Pills/status chips         | `rounded-full`                                                 |

Do not use one radius everywhere. The size hierarchy communicates containment.

### 4.6 Borders, shadows, and blur

Main panels use `overflow-visible` so field tooltips and menus can escape their containing panel. Surface children that touch the outer edge carry their own edge-specific rounding: `PanelHeader` has the top corners and an expanded `SettingsPanel` surface has the bottom corners. Do not solve corner leakage by clipping panel-level popups.

Main panel treatment:

```text
border border-white/10
bg-white/[0.07]
shadow-[0_24px_80px_rgba(0,0,0,0.26),inset_0_1px_0_rgba(255,255,255,0.08)]
backdrop-blur-2xl
```

Inner panel treatment:

```text
border border-white/10
bg-white/[0.06]
shadow-[inset_0_1px_0_rgba(255,255,255,0.07)]
```

Compact status card treatment:

```text
border border-white/10
bg-white/6
shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]
```

Use deep external shadows mainly on top-level panels, floating menus, and notifications. Avoid individually shadowing every small field.

## 5. Layout and responsive behavior

### 5.1 Root constraints

- Keep the document language `zh-Hant`.
- Preserve the `min-w-[320px]` body floor.
- Keep horizontal overflow prevented at the page level.
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
import StatusCard from "@/components/ui/status-card";
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

The live component is a compact `article` with `rounded-xl`, `p-3`, and no descriptive rail. Do not reproduce its markup inside `section-experiment.js` or another feature. If a generally useful capability is missing, extend the shared component without changing existing consumers unnecessarily.

For a group of status cards, use an explicit equal-width grid such as `grid-cols-3`; never use content-sized implicit columns such as `grid-flow-col`. Preserve the compact side-by-side presentation when space allows, and add responsive stacking only when content genuinely cannot fit. Each card's content region must remain `min-w-0` and centered so long status text wraps inside its fixed column rather than changing card widths.

### 6.4 `ActionRow`

Use `ActionRow` from `components/ui/action-row.js` for an action-button group placed at the bottom of a form, settings surface, or content card. It centrally owns this layout:

```text
place-self-end flex flex-wrap items-center pt-2 gap-2
```

This keeps bottom actions right-aligned, wrapping safely, and separated from the content above. It is currently appropriate for schedule execution controls, settings save actions, and login submission. A compact camera-card footer that keeps status and its sole action on one row uses a direct inline action container rather than `ActionRow`, so it does not acquire the action-row divider.

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
  description="共四種擷取模式，每一模式將獨立產生紀錄檔。"
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
- 12px radius;
- border, horizontal padding 16px and vertical padding 8px;
- `text-sm font-extrabold`;
- 150ms transitions limited to background, border, color, and opacity;
- visible emerald focus outline;
- native disabled state with reduced opacity and non-interactive cursor.

Do not manually rebuild these variants in feature files.

### 6.7 Inputs, fields, and number steppers

Use `TextInput`, `NumericInput`, `DurationInput`, and `SelectInput` from `components/ui/input.js` for labeled controls. `components/ui/field.js` owns only the shared `FieldFrame` surface.

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

Use `DurationInput` for every user-editable duration or interval. It composes the shared `FieldFrame`, presents four linked inputs—days, hours, minutes, and seconds—as one continuous four-column grid. Internal cells remove their duplicate left borders so they sit flush without overlap or overflow, then returns its value in the caller's declared `unit` (`minutes`, `seconds`, or `milliseconds`). Keep API payloads and runtime-setting units unchanged; `durationParts` and `durationValue` in `lib/duration.js` own this pure conversion at the UI boundary.

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

`StatusPill` is exported from `components/ui/panel.js`. It is a small rounded-full label with a current-color status dot.

Use tones semantically:

- `success`: emerald;
- `warning`: amber;
- `offline`: rose;
- `neutral`: white/black translucent.

Do not use a status pill where the information needs the title/content/note structure of a `StatusCard`.

### 6.13 Notifications

All transient application messages should flow through the shared notification state and the bottom-right toast/history interface. Do not recreate a separate "近期訊息" panel inside a dashboard section.

Notification UI belongs in `components/notifications`; notification state belongs in `hooks/use-notifications.js`; application placement belongs in `toast-viewport.js`.

Use consistent tone mapping:

- success/normal positive event: emerald;
- warning or incomplete attention: amber;
- error/failure/offline: rose;
- informational event: neutral treatment unless an existing tone applies.

Messages should contain enough operational context to act on, while remaining short enough for a toast. History provides persistence and expansion; individual dashboard sections should not maintain independent message archives.

### 6.14 Login surface

The login form uses the same background, panel, field, button, radius, and typography system as the dashboard. Authentication is not a separate brand surface. Preserve concise Traditional Chinese error feedback and avoid exposing server credentials or implementation details.

## 7. Feature composition standards

### 7.1 Dashboard

`dashboard.js` is the application composition boundary. It coordinates global data, connection state, notifications, settings-panel behavior, and section placement. Keep feature-specific markup and transformations out of it.

`dashboard-header.js` owns application-level navigation/status/actions. Icon-only actions need accessible labels and must use existing button language.

### 7.2 Schedule

The schedule feature is split by responsibility:

- `schedule-common-controls.js`: total duration, start angle, end angle, execution step, and angle tolerance shared by all modes;
- `schedule-modes.js`: list composition and add/remove behavior;
- `schedule-mode-card.js`: one mode container and its controls;
- `schedule-mode-fields.js`: mode-specific input selection;
- `schedule-status-cards.js`: compact execution status presentation, including the live local clock shown with elapsed duration;
- `lib/schedule.js`: defaults, metadata, calculations, validation, normalization, and payload construction.

Multiple modes may participate in one schedule. Keep each mode instance independently identifiable, and keep output/logging concepts distinguishable by mode. Shared parameters belong above the mode list rather than repeated within every mode.

The `通用配置` header has a right-side `預設` button through `SubsectionHeader` children. It restores only `SCHEDULE_COMMON_DEFAULTS`; existing capture modes remain intact.

Mode-specific calculation rules must not be hidden in JSX. Angle-tolerance logic, parsing comma-separated angle strings, equal-division calculation, and payload construction belong in the schedule library. Equal divisions treat `points` as the total number of capture points including both the shared start and end angles; the interval is therefore `(end - start) / (points - 1)`. Schedule submissions must send `duration_seconds` to the backend; convert minute-based stored defaults only when loading them into the schedule UI.

### 7.3 Settings

`settings-panel.js` composes the panel and selection state. Reusable settings presentation belongs in `components/settings`; schema/options/transformation belong in `lib/settings.js`; client panel behavior belongs in `use-settings-panel.js`.

Dashboard settings disclosure state is an array of open group IDs, not a single selected group. Toggling one gear changes only that group's membership, so multiple setting panels may remain open together.

`SettingsSection` uses `content-start` so each settings column remains top-aligned when a neighboring section contains more controls. Do not stretch or distribute a section's controls to fill the tallest grid row.

Do not redefine each setting field in the panel file. Preserve one authoritative control for an action/status rather than allowing separate settings and main-section controls to diverge.

### 7.4 Cameras, motor, sessions, and status

Section files may arrange their domain data and actions but should reuse:

- `Panel`/`PanelHeader` for section framing;
- `InnerPanel` for grouped device/session content;
- `Button`, fields, pills, and toggles for controls;
- pure helpers from `lib` for normalization and display values;
- the shared notification channel for results and errors.

Motor and capture actions must have one authoritative activation point. The `控制` panel owns simple direct motor actions: holding torque, moving to a target angle, setting/returning to origin, and stopping. Other locations may show state, but must not create independent controls with conflicting state. Disable and apply grayscale to this direct-control group while a schedule is running, paused, or stopping.

While a schedule is running, paused, or stopping, every user-initiated modification is locked across the dashboard: schedule configuration and modes, direct motor controls, manual camera capture, and every settings group. Keep read-only views, notification history, session refresh, camera reconnection, schedule pause/resume/stop, and emergency stop available. Use native disabled controls inside a visually grayscale group, and preserve matching backend enforcement so stale clients cannot bypass the lock.

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
export default function InnerPanel({ as: Component = "div", children, className, ...props }) {
  return (
    <Component className={`base classes ${className || ""}`} {...props}>
      {children}
    </Component>
  );
}
```

Use this pattern for components such as `InnerPanel` and `ActionRow`, where callers intentionally provide different child components. Content-bearing primitives such as `Button` may also accept `children` because their label/icon composition is caller-owned.

Fixed-format examples:

```jsx
<StatusCard title="執行時間" content="2 分 10 秒" note="/ 共 20 分鐘" />
<PanelHeader title="排程" action={<SettingsGear />} />
<ToggleRow label="鎖定馬達位置" description="…" status={<StatusPill>保持中</StatusPill>} />
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

## 11. State, data, and network boundaries

### 11.1 State ownership

Keep state at the narrowest level that owns the behavior:

- purely visual local disclosure state stays in the component;
- feature state shared by feature components stays in their nearest feature parent or hook;
- application-wide notification/socket/settings-panel behavior stays in reusable hooks coordinated by the dashboard;
- deterministic derived values are calculated by pure helpers rather than duplicated state.

Avoid keeping two independently mutable copies of one backend status.

### 11.2 WebSocket behavior

Reusable connection, reconnection, message parsing, and cleanup behavior belongs in `use-phyto-socket.js`. UI sections consume normalized state/events rather than opening their own sockets.

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
| Cross-feature visual primitive      | `components/ui`        |
| Feature-only component              | `components/<feature>` |
| Page-level feature composition      | `components/sections`  |
| Reusable state/effect lifecycle     | `hooks`                |
| Pure rule/helper/schema/formatter   | `lib`                  |
| Server mutation with form semantics | `app/actions`          |
| Same-origin backend proxy endpoint  | `app/api`              |

After extraction, update all consumers and remove the old definition. A shared component plus a stale local copy is not a completed refactor.

## 13. Patterns to avoid

Do not introduce:

- local copies of `StatusCard`, `Button`, field, toggle, tooltip, panel, or settings-gear markup;
- locally restated bottom action-row layouts instead of the shared `ActionRow`;
- locally rebuilt small title/description groups instead of the shared `SubsectionHeader`;
- feature components or helper methods nested inside a large section without a strong locality reason;
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
- hydration suppression as a general fix for nondeterministic rendering.

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

### Commands and process

- [ ] Search touched paths for stale references and duplicate implementations.
- [ ] Run `git diff --check`.
- [ ] Run a relevant frontend compile/build check when feasible.
- [ ] If a development service is already running, use it only for non-destructive verification.
- [ ] Never stop a service started by the user.
- [ ] If a test server was started for validation, stop it before finishing.
- [ ] Report active `.next` locking or build limitations instead of deleting user state.
