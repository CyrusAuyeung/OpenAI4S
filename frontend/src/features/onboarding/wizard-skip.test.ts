import { beforeEach, describe, expect, it, vi } from "vitest";

// Skip must stay available while "Test connection" is waiting. A probe to an
// endpoint that never answers waits out a connect timeout and its retries,
// which is minutes; the wizard used to hold the whole footer disabled for
// that long, so the only way out of first-run setup did nothing.

const hooks = vi.hoisted(() => {
  const slots: unknown[] = [];
  let cursor = 0;
  const set = (index: number, value: unknown) => {
    slots[index] = typeof value === "function" ? (value as (v: unknown) => unknown)(slots[index]) : value;
  };
  return {
    slots,
    reset() {
      slots.length = 0;
      cursor = 0;
    },
    begin() {
      cursor = 0;
    },
    useState(initial: unknown) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], (value: unknown) => set(index, value)];
    },
    useRef(initial: unknown) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { current: initial };
      return slots[index];
    },
    useReducer(reducer: (state: unknown, action: unknown) => unknown, initial: unknown) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], (action: unknown) => set(index, reducer(slots[index], action))];
    },
  };
});

const api = vi.hoisted(() => ({
  probeModelProfile: vi.fn(),
  completeOnboarding: vi.fn(),
}));

vi.mock("preact/hooks", () => ({
  useEffect: vi.fn(),
  useReducer: hooks.useReducer,
  useRef: hooks.useRef,
  useState: hooks.useState,
}));

vi.mock("./api", async (importOriginal) => {
  const original = await importOriginal<typeof import("./api")>();
  return { ...original, ...api };
});

import { WizardHost } from "../../components/onboarding/Wizard";
import { t } from "../../i18n";
import { ot } from "./copy";
import { INITIAL_WIZARD, type WizardState } from "./machine";

type VNode = { type?: unknown; props?: Record<string, unknown> & { children?: unknown } };
type Button = { text: string; disabled: boolean; onClick: () => void };

function textOf(node: unknown): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  return textOf((node as VNode).props?.children);
}

function buttons(node: unknown, out: Button[] = []): Button[] {
  if (!node || typeof node !== "object") return out;
  if (Array.isArray(node)) {
    for (const child of node) buttons(child, out);
    return out;
  }
  const vnode = node as VNode;
  if (vnode.type === "button") {
    out.push({
      text: textOf(vnode.props?.children).trim(),
      disabled: Boolean(vnode.props?.disabled),
      onClick: vnode.props?.onClick as () => void,
    });
  }
  buttons(vnode.props?.children, out);
  return out;
}

function render(): Button[] {
  hooks.begin();
  return buttons(WizardHost());
}

function button(label: string): Button {
  const match = render().find((b) => b.text === label);
  expect(match, `no "${label}" button`).toBeTruthy();
  return match!;
}

// Slot order in WizardHost: reducer, status, busy, testing, probeRun, alive.
const REDUCER = 0;

function wizard(): WizardState {
  return hooks.slots[REDUCER] as WizardState;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

const UNREACHABLE = {
  reachable: false,
  state: "unreachable",
  detail: "the endpoint could not be reached, or the connection dropped",
  request_id: "req-late",
  capability_receipt: null,
};

describe("first-run wizard: skipping while a connection test is waiting", () => {
  beforeEach(() => {
    hooks.reset();
    api.probeModelProfile.mockReset();
    api.completeOnboarding.mockReset();
    render();
    hooks.slots[REDUCER] = {
      ...INITIAL_WIZARD,
      surface: "wizard",
      step: "test",
      decided: ["path"],
      path: {
        kind: "cloud",
        profileId: "mp-test",
        provider: "chatgpt",
        model: "",
        baseUrl: "http://127.0.0.1:9/v1",
        name: "unreachable",
      },
    } satisfies WizardState;
  });

  it("keeps Skip enabled and completes the skip before the probe answers", async () => {
    const probe = deferred<Record<string, unknown>>();
    api.probeModelProfile.mockReturnValueOnce(probe.promise);
    api.completeOnboarding.mockResolvedValueOnce({});

    button(t("cust.models.test")).onClick();
    expect(api.probeModelProfile).toHaveBeenCalledWith("mp-test");

    const testing = button(t("cust.models.testing"));
    expect(testing.disabled).toBe(true);
    const skip = button(ot("onboarding.skip"));
    expect(skip.disabled).toBe(false);

    skip.onClick();
    await vi.waitFor(() => expect(wizard().surface).toBe("done"));
    expect(api.completeOnboarding).toHaveBeenCalledWith({ skip: true });

    // The probe answers after the wizard has closed: nothing it says may land.
    probe.resolve(UNREACHABLE);
    await probe.promise;
    await Promise.resolve();
    expect(wizard().surface).toBe("done");
    expect(wizard().error).toBeNull();
  });

  it("drops a late answer once the user has moved past the test step", async () => {
    const probe = deferred<Record<string, unknown>>();
    api.probeModelProfile.mockReturnValueOnce(probe.promise);

    button(t("cust.models.test")).onClick();
    const next = button(ot("onboarding.next"));
    expect(next.disabled).toBe(false);
    next.onClick();
    expect(wizard().step).toBe("readiness");

    probe.resolve(UNREACHABLE);
    await probe.promise;
    await Promise.resolve();
    expect(wizard().error).toBeNull();
    expect(wizard().step).toBe("readiness");
  });

  it("still reports a failed probe while the user is waiting for it", async () => {
    api.probeModelProfile.mockResolvedValueOnce(UNREACHABLE);

    button(t("cust.models.test")).onClick();
    await vi.waitFor(() => expect(wizard().error?.message).toContain("could not be reached"));
    expect(wizard().error?.requestId).toBe("req-late");
    // The probe is over, so the button is usable again.
    expect(button(t("cust.models.test")).disabled).toBe(false);
  });
});
