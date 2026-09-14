/**
 * The workbench mounts before its locale chunks arrive.
 *
 * `main.tsx` renders the Shell synchronously and `bindWorkbench()` runs
 * `applyStaticI18n(document)` from the Shell's first effect, while the
 * dictionaries are still an `import("./en")` / `import("./zh")` in flight.
 * Two things went wrong on a cold load (and deterministically on any link
 * with real latency): `t()` fell back to the key, so the readable JSX
 * fallback ("Projects") was overwritten with "dash.col.projects"; and
 * nothing re-applied the static labels once the dictionaries landed, so the
 * keys stayed until the user switched language.
 *
 * These tests hold the locale modules behind a gate to reproduce that order.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type FakeNode = {
  textContent: string;
  title: string;
  placeholder: string;
  value: string;
  dataset: Record<string, string>;
  classList: { toggle: (name: string, on: boolean) => void; has: (name: string) => boolean };
  getAttribute: (name: string) => string | null;
};

function fakeNode(
  attrs: Record<string, string>,
  initial: Partial<Pick<FakeNode, "textContent" | "title" | "placeholder" | "value">> = {},
): FakeNode {
  const classes = new Set<string>();
  return {
    textContent: initial.textContent ?? "",
    title: initial.title ?? "",
    placeholder: initial.placeholder ?? "",
    value: initial.value ?? "",
    dataset: attrs["data-lang"] ? { lang: attrs["data-lang"] } : {},
    classList: {
      toggle: (name, on) => {
        if (on) classes.add(name);
        else classes.delete(name);
      },
      has: (name) => classes.has(name),
    },
    getAttribute: (name) => (name in attrs ? attrs[name]! : null),
  };
}

type Shell = {
  projects: FakeNode;
  jump: FakeNode;
  search: FakeNode;
  theme: FakeNode;
  convTitle: FakeNode;
  langEn: FakeNode;
  langZh: FakeNode;
};

/** The Shell's markup as it is right after render(): readable JSX fallbacks. */
function installShell(): Shell {
  const shell: Shell = {
    projects: fakeNode({ "data-i18n": "dash.col.projects" }, { textContent: "Projects" }),
    // Several Shell fallbacks are Chinese, so an English reader still needs
    // the repaint even when no key is ever written.
    jump: fakeNode({ "data-i18n": "conv.jumpLastLabel" }, { textContent: "最新" }),
    search: fakeNode({ "data-i18n-ph": "palette.action.search" }, { placeholder: "Search" }),
    theme: fakeNode({ "data-i18n-title": "theme.toggle" }, { title: "主题" }),
    convTitle: fakeNode({ "data-i18n-val": "conv.title.default" }, { value: "会话" }),
    langEn: fakeNode({ "data-lang": "en" }),
    langZh: fakeNode({ "data-lang": "zh" }),
  };
  const bySelector: Record<string, FakeNode[]> = {
    "[data-i18n]": [shell.projects, shell.jump],
    "[data-i18n-title]": [shell.theme],
    "[data-i18n-ph]": [shell.search],
    "[data-i18n-val]": [shell.convTitle],
    ".lang-btn": [shell.langZh, shell.langEn],
  };
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    writable: true,
    value: {
      documentElement: { lang: "" },
      querySelectorAll: (selector: string) => bySelector[selector] ?? [],
    },
  });
  return shell;
}

type Runtime = typeof import("./runtime");

let release: () => void = () => undefined;

async function importRuntimeWithGatedLocales(): Promise<Runtime> {
  vi.resetModules();
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const realEn = (await vi.importActual<{ default: Record<string, string> }>("./en")).default;
  const realZh = (await vi.importActual<{ default: Record<string, string> }>("./zh")).default;
  vi.doMock("./en", async () => {
    await gate;
    return { default: realEn };
  });
  vi.doMock("./zh", async () => {
    await gate;
    return { default: realZh };
  });
  return import("./runtime");
}

const saved: Record<string, PropertyDescriptor | undefined> = {};

beforeEach(() => {
  for (const name of ["document", "localStorage"]) {
    saved[name] = Object.getOwnPropertyDescriptor(globalThis, name);
  }
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    writable: true,
    value: {
      getItem: (key: string) => (key === "os-lang" ? "en" : null),
      setItem: () => undefined,
    },
  });
});

afterEach(() => {
  release();
  vi.doUnmock("./en");
  vi.doUnmock("./zh");
  vi.resetModules();
  for (const [name, descriptor] of Object.entries(saved)) {
    if (descriptor) Object.defineProperty(globalThis, name, descriptor);
    else delete (globalThis as Record<string, unknown>)[name];
  }
});

describe("static labels painted before the locale chunks arrive", () => {
  it("never replaces a readable fallback with a bare key", async () => {
    const shell = installShell();
    const runtime = await importRuntimeWithGatedLocales();
    expect(runtime.LANG).toBe("en");

    // What bindWorkbench() does on the Shell's first effect.
    runtime.applyStaticI18n();

    expect(shell.projects.textContent).toBe("Projects");
    expect(shell.jump.textContent).toBe("最新");
    expect(shell.search.placeholder).toBe("Search");
    expect(shell.theme.title).toBe("主题");
    expect(shell.convTitle.value).toBe("会话");
  });

  it("repaints them, the language toggle and language hooks once the dictionaries load", async () => {
    const shell = installShell();
    const runtime = await importRuntimeWithGatedLocales();
    const hook = vi.fn();
    runtime.onLanguageChange(hook);

    runtime.applyStaticI18n();
    release();
    await runtime.i18nReady();

    expect(shell.projects.textContent).toBe("Projects");
    expect(shell.jump.textContent).toBe("Latest");
    expect(shell.search.placeholder).toBe("Search");
    expect(shell.theme.title).toBe("Toggle theme");
    expect(shell.convTitle.value).toBe("Session");
    expect(shell.langEn.classList.has("active")).toBe(true);
    expect(shell.langZh.classList.has("active")).toBe(false);
    expect(hook).toHaveBeenCalledTimes(1);

    // The repaint belongs to the first load, not to every caller of i18nReady().
    await runtime.i18nReady();
    expect(hook).toHaveBeenCalledTimes(1);
  });

  it("keeps i18nReady() resolved when the repaint itself throws", async () => {
    Object.defineProperty(globalThis, "document", {
      configurable: true,
      writable: true,
      value: {
        documentElement: { lang: "" },
        querySelectorAll: () => {
          throw new Error("torn-down document");
        },
      },
    });
    const runtime = await importRuntimeWithGatedLocales();
    release();
    await expect(runtime.i18nReady()).resolves.toBeUndefined();
    expect(runtime.t("theme.toggle")).toBe("Toggle theme");
  });

  it("still translates a missing key to itself through t()", async () => {
    installShell();
    const runtime = await importRuntimeWithGatedLocales();
    release();
    await runtime.i18nReady();
    expect(runtime.t("this.key.does.not.exist")).toBe("this.key.does.not.exist");
  });
});
