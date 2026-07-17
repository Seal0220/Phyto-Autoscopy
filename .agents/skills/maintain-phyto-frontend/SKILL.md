---
name: maintain-phyto-frontend
description: Preserve and extend the Phyto-Autoscopy Next.js and React frontend using its established Tailwind CSS v4 visual system, shared component architecture, feature modules, interaction rules, responsive behavior, and BFF boundaries. Use whenever reviewing, fixing, refactoring, or adding files under frontend/, including feature modules, settings, notifications, camera/record views, shared UI primitives, responsive styling, accessibility, or frontend API routes.
---

# Maintain Phyto Frontend

Keep every frontend change consistent with the repository's existing dark green glass interface and its separation of UI, feature composition, state, pure logic, and server boundaries.

## Required reference

Read [references/frontend-style-and-code.md](references/frontend-style-and-code.md) completely before taking frontend implementation or review actions. The reference documents the current frontend in detail.

Treat live shared components as the final visual source of truth when a user has edited them more recently than this reference. Update this reference when an intentional design-system or architecture change makes it stale.

## Workflow

1. Inspect the requested screen, its parent composition, and every shared component it consumes.
2. Search `frontend/src/components`, the relevant `frontend/src/features/<Feature>` folder, `hooks`, and `lib` before creating a component or helper.
3. Identify the correct ownership layer before editing: shared primitive/container, feature component, feature hook, feature config, feature utility, global hook/utility, route handler, or server action.
4. Preserve the established tokens, density, typography, interaction, and responsive behavior unless the user explicitly requests a system change.
5. Extract independently meaningful JSX, reusable behavior, stable metadata, validation, serialization, and formatting to their correct layer.
6. Update all consumers and remove obsolete local copies, imports, constants, and helpers.
7. Check semantics, keyboard behavior, ARIA state, repeated IDs, overflow, and the established mobile breakpoints.
8. Run proportionate static and compile validation. Never leave a test server running and never stop a server started by the user.

## Non-negotiable rules

- Use the repository's Tailwind CSS v4 utilities and current arbitrary values; do not introduce a parallel CSS system.
- Use `text-neutral-*` for gray text hierarchy. Never simulate gray text with `text-white/<opacity>`; opacity remains available for borders, backgrounds, and other translucent surfaces.
- Build conditional `className` values with template literals. Do not add `cx`, `cn`, `clsx`, or another class-combining helper.
- Preserve readable multi-line formatting: when a component, JSX element, or function has multiple props or parameters, put them on separate lines. Only a single prop or parameter may remain on one line.
- Reuse shared primitives, especially `StatusCard` from `@/components/cards/StatusCard`; never redefine them in a feature.
- Use `ActionRow` from `@/components/actions/ActionRow` for button groups at the bottom of content blocks; do not restate its layout classes locally.
- Use `SubsectionHeader` from `@/components/headers/SubsectionHeader` for small content-block headings. Pass fixed `title` and `description` props, select its numeric `titleMode` when needed, and compose optional right-side actions through `children`.
- Use `DurationInput` for every user-editable duration or time interval. Present days, hours, minutes, and seconds while preserving the caller's backend unit at the data boundary.
- Numeric controls must use native `type="number"`; `Input` must automatically suppress browser-native spinner buttons and render the shared `NumberStepper` rather than exposing a separate numeric-input component. Use layout columns for the value, suffix, and stepper; never reserve their space with invisible input padding or add borders around the suffix. Numeric controls retain one outer border and the stepper's existing divider.
- Give composition containers an explicit `children` prop and render it directly. Give fixed-format components semantic named props instead; do not use `children` to bypass a stable title/content/status/action schema.
- Put every feature-owned screen, control, hook, config, and utility in `frontend/src/features/<Feature>/`. Name the entry component directly after the feature, such as `Schedule.js`. Name every component under a feature's `components/` folder with a PascalCase feature prefix in both its filename and component identifier, such as `ScheduleModeCard.js`, `ImagePreviewField.js`, and `RecordsStorageSettings.js`; never use ambiguous child names such as `Field`, `Settings`, `Header`, or `ModeCard`.
- Put every App Router page entry under `frontend/src/app/(pages)/`, including the root login `page.js` and every nested feature page. Keep `layout.js`, `actions/`, `api/`, global assets, and styles outside this route group; `(pages)` organizes source ownership without changing public URLs.
- Preserve the formal feature vocabulary: `ControlPanel` is the application composition boundary, `Control` is the direct hardware-control feature, `SystemStatus` is the `系統狀態` feature, `Schedule` is the `排程` feature, and `RecordsStorage` owns capture records. Keep the hardware-specific child name `MotorControls`. Do not restore `Dashboard`, the main `Motor` feature, the main `Status` feature, `Experiment`, or business-domain `Session` names.
- Use `record`/`Record` for capture-record business data, routes, fields, and UI. Reserve `session` exclusively for the signed login/authentication session; never rename authentication helpers merely to satisfy the record-domain rule.
- Keep captured images, per-mode folders, CSV logs, and `record.json` under the configured `captures_dir` (`data/captures` by default). SQLite stores their Record/Capture relationships, metadata, states, and file paths for read APIs; do not rename this filesystem root to `records_dir` or store image BLOBs in SQLite.
- Use the canonical camera identifiers `top`, `side`, and `rotating` across frontend/backend transport, settings, runtime state, and new storage paths. Treat ImagePreview manual captures as standalone snapshots, not Record captures. Individual and capture-all preview actions use the snapshot API, store flat files under `snapshots_dir` (`data/snapshots` by default), and name them with the camera identifier plus a timestamp. They must not create Record/Capture database rows.
- Keep analysis creation as one unified source workflow. Record selection is an optional auto-fill action, never a separate source mode; the only analysis methods are `top_side` (`頂+側`) and `top_side_rotating` (`頂+側+環繞`). Require a successful source preview and a valid reusable calibration before submission.
- Use `time_interval` for the time-based schedule capture mode. Do not restore the obsolete `seconds_interval` transport value.
- Keep each feature entry component focused on data wiring and feature composition rather than nested component definitions or domain algorithms.
- Put shared functional primitives, frames, and containers only in `frontend/src/components/`, organised by role. Do not put feature UI there.
- A feature's `*Config.js` may contain only stable constants/metadata/default values; put parsing, validation, transformations, serialization, and API-related helpers in that feature's `lib/*Utils.js`.
- Keep global hooks and utilities only when they are genuinely used by multiple features; otherwise put them in their owning feature.
- `SettingPanel` is a shared disclosure/container primitive only. It accepts composed children and a `footer` slot, renders the shared `ActionRow` with default `px-6 pb-6` footer spacing, and must never branch on a settings group or render feature-specific fields.
- Keep hover motion to color, border, and fill changes unless the live primitive already establishes rotation, chevron rotation, or switch-thumb translation.
- Keep field and settings tooltips hover-only. Do not bind their visibility to focus.
- Do not add gradients, colored side rails, explanatory description bars, decorative English labels, oversized status treatments, or an unrelated component style.
- Keep user-facing copy in Traditional Chinese and backend identifiers at data boundaries.
- Every asynchronous boundary must expose a safe Traditional Chinese failure, release pending/busy state in `finally`, reject stale or unmounted completions, and provide a retry or reset path appropriate to that operation. Automatically retry only idempotent reads or reconnects with bounded delay; never automatically repeat a mutation whose outcome is uncertain.
- Keep resets scoped: clear a feature error after that feature succeeds, and clear shared backend `recent_errors` only after `system.errors.reset` succeeds. An intentional motor cancellation such as `operation_cancelled` is control flow, not a notification or recent error. Blocking manual motor movement uses the scoped HTTP/BFF path rather than blocking the status WebSocket; stop and emergency stop use independent HTTP requests so they can interrupt an active move.
- Preserve unrelated user changes in a dirty worktree.
