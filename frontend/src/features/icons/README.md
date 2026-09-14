# frontend/src/features/icons

[中文说明](README_zh.md)

The workbench's line icons (lucide paths from `app.js:7-77`) in a single table. The port had split app.js's table into per-lane copies that drifted apart: `panel-left`, `panel-right`, `moon` and `sun` ended up in no table `paintIcons()` reads, so the sidebar, dock and theme buttons painted an empty `<svg>`. `features/sessions/icon.ts` and `features/chrome/dom.ts` both draw from here; add a new name to this table, not to a lane.

Entries are static markup injected as innerHTML, the way app.js did. Never build one from data.

## Files

| File | Responsibility |
| --- | --- |
| [`paths.ts`](paths.ts) | `ICON_PATHS` and `iconSvg(name, size, cls)`. An unknown name draws nothing. |
| [`icons.coverage.test.ts`](icons.coverage.test.ts) | Every `data-icon="…"` / `setAttribute("data-icon", "…")` name in the source, plus the theme toggle's sun/moon, draws a shape through `paintIcons`; the sessions and chrome helpers draw the same picture for a name. |
