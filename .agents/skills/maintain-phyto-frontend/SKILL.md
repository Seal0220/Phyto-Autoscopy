---
name: maintain-phyto-frontend
description: Preserve and extend the Phyto-Autoscopy Next.js and React frontend using its established Tailwind CSS v4 visual system, shared component architecture, feature modules, interaction rules, responsive behavior, and BFF boundaries. Use whenever reviewing, fixing, refactoring, or adding files under frontend/, including feature modules, settings, notifications, camera/session views, shared UI primitives, responsive styling, accessibility, or frontend API routes.
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
- Put every feature-owned screen, control, hook, config, and utility in `frontend/src/features/<Feature>/`. Use PascalCase component filenames without redundant feature prefixes, such as `Schedule.js` and `components/ModeCard.js`; never reintroduce `section-*`, `schedule-*`, or lowercase component filenames.
- Keep each feature entry component focused on data wiring and feature composition rather than nested component definitions or domain algorithms.
- Put shared functional primitives, frames, and containers only in `frontend/src/components/`, organised by role. Do not put feature UI there.
- A feature's `*Config.js` may contain only stable constants/metadata/default values; put parsing, validation, transformations, serialization, and API-related helpers in that feature's `lib/*Utils.js`.
- Keep global hooks and utilities only when they are genuinely used by multiple features; otherwise put them in their owning feature.
- `SettingPanel` is a shared disclosure/container primitive only. It must accept composed children and must never branch on a settings group or render feature-specific fields.
- Keep hover motion to color, border, and fill changes unless the live primitive already establishes rotation, chevron rotation, or switch-thumb translation.
- Keep field and settings tooltips hover-only. Do not bind their visibility to focus.
- Do not add gradients, colored side rails, explanatory description bars, decorative English labels, oversized status treatments, or an unrelated component style.
- Keep user-facing copy in Traditional Chinese and backend identifiers at data boundaries.
- Preserve unrelated user changes in a dirty worktree.
