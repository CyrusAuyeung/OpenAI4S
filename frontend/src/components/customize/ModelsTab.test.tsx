import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const hookState: unknown[] = [];
let hookCursor = 0;
const effects: Array<() => void> = [];

vi.mock("preact/hooks", () => ({
  useState: (initial: unknown) => {
    const index = hookCursor++;
    if (hookState.length === index) hookState.push(initial);
    return [hookState[index], (value: unknown) => {
      hookState[index] = typeof value === "function" ? (value as (prev: unknown) => unknown)(hookState[index]) : value;
    }];
  },
  useRef: (initial: unknown) => {
    const index = hookCursor++;
    if (hookState.length === index) hookState.push({ current: initial });
    return hookState[index];
  },
  useEffect: (fn: () => void, deps: unknown[]) => {
    const index = hookCursor++;
    const old = hookState[index] as unknown[] | undefined;
    if (old && deps.every((value, i) => value === old[i])) return;
    hookState[index] = deps;
    effects.push(() => void fn());
  },
}));

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), alive: (): boolean => true }));
vi.mock("../../i18n", () => ({
  LANG: "en",
  t: (key: string) => key,
  tOptional: () => null,
  onLanguageChange: () => undefined,
}));
vi.mock("./use-timer-lease", () => ({ useAlive: () => mocks.alive }));
vi.mock("./vendors/volcengine", () => ({ VolcenginePanel: () => null }));
vi.mock("../../features/customize/actions", () => ({ custTab: () => undefined }));

import { ModelsTab } from "./ModelsTab";

type Node = { type?: unknown; props?: Record<string, unknown> & { children?: unknown } };
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function render(): Node {
  hookCursor = 0;
  return ModelsTab() as Node;
}
function content(node: unknown): string {
  if (Array.isArray(node)) return node.map(content).join(" ");
  if (typeof node === "string" || typeof node === "number") return String(node);
  return node && typeof node === "object" ? content((node as Node).props?.children) : "";
}
function tagged(node: unknown, key: string): Node[] {
  const found: Node[] = [];
  const walk = (current: unknown): void => {
    if (Array.isArray(current)) return current.forEach(walk);
    if (!current || typeof current !== "object") return;
    const n = current as Node;
    if (n.props && key in n.props) found.push(n);
    walk(n.props?.children);
  };
  walk(node);
  return found;
}

const LIVE = {
  provider: "ark",
  model: "doubao-seed-2.0-pro",
  base_url: "https://ark.cn-beijing.volces.com/api/plan/v3",
  has_api_key: true,
};

async function open(routes: Record<string, () => Response>): Promise<Node> {
  mocks.fetch.mockImplementation((url: string) => {
    const route = Object.keys(routes).find((path) => url === "/api/v1" + path);
    return Promise.resolve(route ? routes[route]!() : response({ error: "nope" }, 404));
  });
  render();
  effects.splice(0).forEach((effect) => effect());
  await vi.waitFor(() => expect(mocks.fetch).toHaveBeenCalled());
  // Let the awaited responses settle into state before reading the tree.
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  return render();
}

beforeEach(() => {
  hookState.length = 0;
  hookCursor = 0;
  effects.length = 0;
  mocks.fetch.mockReset();
  vi.stubGlobal("fetch", mocks.fetch);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ModelsTab active configuration", () => {
  it("shows the environment/settings model when no profile is saved", async () => {
    const tree = await open({
      "/model-profiles": () => response({ profiles: [], active_id: "", protocols: ["ark"] }),
      "/config/llm": () => response(LIVE),
    });
    const text = content(tree);
    expect(text).toContain("doubao-seed-2.0-pro");
    expect(text).not.toContain("cust.models.empty2");
    const row = tagged(tree, "data-live-model")[0];
    expect(row).toBeTruthy();
    expect(content(row)).toContain("cust.models.hasKey");
    // The key itself is never in the payload, so it cannot be in the row; the
    // row says where the configuration comes from instead.
    expect(content(row)).toMatch(/environment/i);
  });

  it("keeps the empty state when nothing is configured anywhere", async () => {
    const tree = await open({
      "/model-profiles": () => response({ profiles: [], active_id: "", protocols: ["ark"] }),
      "/config/llm": () => response({ provider: "", model: "", base_url: "", has_api_key: false }),
    });
    expect(tagged(tree, "data-live-model")).toHaveLength(0);
    expect(content(tree)).toContain("cust.models.empty2");
  });

  it("does not add a second active row when a saved profile is active", async () => {
    const tree = await open({
      "/model-profiles": () =>
        response({
          profiles: [{ id: "mp-1", name: "Ark", provider: "ark", model: "doubao-seed-2.0-pro", has_api_key: true }],
          active_id: "mp-1",
          protocols: ["ark"],
        }),
      "/config/llm": () => response(LIVE),
    });
    expect(tagged(tree, "data-live-model")).toHaveLength(0);
  });

  it("still lists profiles when the live configuration cannot be read", async () => {
    const tree = await open({
      "/model-profiles": () =>
        response({
          profiles: [{ id: "mp-1", name: "Saved", provider: "ark", model: "m", has_api_key: true }],
          active_id: "",
          protocols: ["ark"],
        }),
    });
    expect(tagged(tree, "data-live-model")).toHaveLength(0);
    expect(content(tree)).not.toContain("versions.load.err");
  });
});
