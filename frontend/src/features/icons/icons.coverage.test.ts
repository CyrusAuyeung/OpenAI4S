/**
 * Every icon name the workbench paints must resolve to a drawing.
 *
 * `icon()` falls back to an empty `<svg>` for an unknown name, so a missing
 * table entry is invisible in code and in tests that only look at
 * `data-icon`: the button keeps its size and its click handler and shows
 * nothing. That is how the sidebar collapse/reopen, dock and theme toggles
 * shipped blank -- and at phone width the invisible `#sidebar-reopen` was
 * the only way back to the sidebar.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { icon as chromeIcon } from "../chrome/dom";
import { icon as sessionsIcon, paintIcons } from "../sessions/icon";

const here = dirname(fileURLToPath(import.meta.url));
const srcRoot = join(here, "../..");

const SHAPE = /<(path|circle|rect|line|polyline|polygon|ellipse)\b/;

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) out.push(...sourceFiles(path));
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name)) out.push(path);
  }
  return out;
}

/** Names written as markup (`data-icon="x"`) or set on a node (`setAttribute("data-icon", "x")`). */
function paintedNames(): Map<string, string[]> {
  const names = new Map<string, string[]>();
  const note = (name: string, file: string) => {
    const where = relative(srcRoot, file);
    names.set(name, [...(names.get(name) ?? []), where]);
  };
  for (const file of sourceFiles(srcRoot)) {
    const text = readFileSync(file, "utf8");
    for (const m of text.matchAll(/data-icon="([a-z0-9-]+)"/g)) note(m[1]!, file);
    for (const m of text.matchAll(/setAttribute\(\s*"data-icon",\s*"([a-z0-9-]+)"\s*\)/g)) {
      note(m[1]!, file);
    }
  }
  // refreshThemeToggle swaps the theme buttons between these two.
  const theme = join(srcRoot, "features/theme/theme.ts");
  note("sun", theme);
  note("moon", theme);
  return names;
}

describe("workbench icon coverage", () => {
  const names = paintedNames();

  it("finds the Shell's icon buttons, so the scan itself is not vacuous", () => {
    for (const name of ["panel-left", "panel-right", "moon", "settings", "plus"]) {
      expect(names.has(name), name).toBe(true);
    }
  });

  it("draws every painted icon name", () => {
    const blank = [...names.keys()].filter((name) => !SHAPE.test(sessionsIcon(name))).sort();
    expect(blank).toEqual([]);
  });

  it("paintIcons fills the Shell's sidebar, dock and theme buttons", () => {
    const nodes = ["panel-left", "panel-right", "moon", "sun"].map((name) => ({
      dataset: { icon: name, iconSize: "20" } as Record<string, string>,
      innerHTML: "",
    }));
    paintIcons({ querySelectorAll: () => nodes } as unknown as ParentNode);
    for (const node of nodes) expect(node.innerHTML, node.dataset.icon).toMatch(SHAPE);
  });

  it("the chrome and sessions icon helpers draw the same picture for a name", () => {
    const drift = [...names.keys(), "sparkles", "file", "message-square"]
      .filter((name) => chromeIcon(name, 16) !== sessionsIcon(name, 16))
      .sort();
    expect(drift).toEqual([]);
  });
});
