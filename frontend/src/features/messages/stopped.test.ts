import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetStoreFields } from "../../stores/signal-field";
import { stream } from "../../stores/stream";
import { turnDone } from "../send/turn";
import { renderStored as renderOlderPage } from "../sessions/transcript";
import { renderStored } from "./list";
import { finishStoppedStream } from "./stopped";
import { feed, startStream, type LiveStream } from "./stream";

/** Just enough DOM for the stream and the stored renderer (no jsdom here). */
class FakeClassList {
  readonly tokens = new Set<string>();
  constructor(initial?: string) {
    if (initial) for (const t of initial.split(/\s+/).filter(Boolean)) this.tokens.add(t);
  }
  add(...names: string[]): void {
    for (const n of names) this.tokens.add(n);
  }
  remove(...names: string[]): void {
    for (const n of names) this.tokens.delete(n);
  }
  contains(name: string): boolean {
    return this.tokens.has(name);
  }
  toggle(name: string, force?: boolean): boolean {
    const on = force === undefined ? !this.tokens.has(name) : force;
    if (on) this.tokens.add(name);
    else this.tokens.delete(name);
    return on;
  }
  get value(): string {
    return [...this.tokens].join(" ");
  }
}

class FakeText {
  data: string;
  constructor(data: string) {
    this.data = data;
  }
  appendData(more: string): void {
    this.data += more;
  }
  get textContent(): string {
    return this.data;
  }
}

class FakeEl {
  tagName: string;
  id = "";
  classList = new FakeClassList();
  children: Array<FakeEl | FakeText> = [];
  parent: FakeEl | null = null;
  dataset: Record<string, string> = {};
  style: Record<string, string> = {};
  onclick: unknown = null;
  title = "";
  scrollTop = 0;
  scrollHeight = 0;
  clientHeight = 0;
  private _text = "";
  constructor(tag: string) {
    this.tagName = tag.toUpperCase();
  }
  get className(): string {
    return this.classList.value;
  }
  set className(value: string) {
    this.classList = new FakeClassList(value);
  }
  get textContent(): string {
    if (this.children.length) return this.children.map((c) => c.textContent).join("");
    return this._text;
  }
  set textContent(value: string) {
    this.children = [];
    this._text = value == null ? "" : String(value);
  }
  set innerHTML(value: string) {
    this.children = [];
    this._text = String(value).replace(/<[^>]+>/g, "");
  }
  get innerHTML(): string {
    return this._text;
  }
  setAttribute(name: string, value: string): void {
    this.dataset["attr:" + name] = value;
  }
  appendChild<T extends FakeEl | FakeText>(child: T): T {
    if (child instanceof FakeEl) child.parent = this;
    this.children.push(child);
    return child;
  }
  remove(): void {
    if (!this.parent) return;
    this.parent.children = this.parent.children.filter((c) => c !== this);
    this.parent = null;
  }
  querySelector(sel: string): FakeEl | null {
    return this.querySelectorAll(sel)[0] || null;
  }
  querySelectorAll(sel: string): FakeEl[] {
    const out: FakeEl[] = [];
    const walk = (node: FakeEl): void => {
      for (const child of node.children) {
        if (!(child instanceof FakeEl)) continue;
        if (matches(child, sel)) out.push(child);
        walk(child);
      }
    };
    walk(this);
    return out;
  }
}

function matches(node: FakeEl, sel: string): boolean {
  if (sel.startsWith("#")) return node.id === sel.slice(1);
  if (sel.startsWith(".")) return sel.slice(1).split(".").every((c) => node.classList.contains(c));
  return node.tagName === sel.toUpperCase();
}

class FakeDoc {
  body = new FakeEl("body");
  host = new FakeEl("div");
  constructor() {
    this.host.id = "messages";
    this.body.appendChild(this.host);
  }
  createElement(tag: string): FakeEl {
    return new FakeEl(tag);
  }
  createTextNode(data: string): FakeText {
    return new FakeText(data);
  }
  getElementById(id: string): FakeEl | null {
    return id === "messages" ? this.host : null;
  }
  querySelector(sel: string): FakeEl | null {
    if (sel === "#messages") return this.host;
    return this.body.querySelector(sel);
  }
  querySelectorAll(sel: string): FakeEl[] {
    return this.body.querySelectorAll(sel);
  }
}

let doc: FakeDoc;

function live(): LiveStream {
  return stream.value as LiveStream;
}

function cellHeader(): void {
  feed("tool", "⚙ run_python\n", { type: "text_chunk", block_type: "tool", cell_index: 1 });
  feed("tool", "↳ step 1\n", { type: "text_chunk", block_type: "tool" });
}

const marker = {
  type: "text_chunk",
  block_type: "text",
  chunk: "\n\n_Stopped by user._\n",
  cancelled: { reason: "user", request_id: "req-1", execution_id: "exec-1" },
};

beforeEach(() => {
  resetStoreFields();
  doc = new FakeDoc();
  vi.stubGlobal("document", doc);
  vi.stubGlobal("requestAnimationFrame", () => 1);
  vi.stubGlobal("cancelAnimationFrame", () => undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("stopped turn marker", () => {
  it("renders the streamed marker as a stopped marker and stops the running card", () => {
    startStream();
    feed("text", "I have prepared a Python cell and am running it now.\n", {
      type: "text_chunk",
      block_type: "text",
    });
    cellHeader();
    const card = live().toolCard as unknown as FakeEl;
    expect(card).toBeTruthy();

    feed("text", marker.chunk, marker);

    const wrap = live().wrap as unknown as FakeEl;
    const markers = wrap.querySelectorAll(".msg-stopped");
    expect(markers).toHaveLength(1);
    expect(markers[0]!.dataset.stopReason).toBe("user");
    expect(markers[0]!.dataset.requestId).toBe("req-1");
    expect(markers[0]!.textContent).toContain("Stopped by user");
    expect(card.classList.contains("stopped")).toBe(true);
    expect(card.querySelector(".meta")!.textContent).toContain("Stopped");
    // Rendered as a marker, never appended to the markdown as prose.
    expect(live().text).not.toContain("_Stopped by user._");
    expect(live().full).not.toContain("_Stopped by user._");
  });

  it("leaves a card that finished before the stop alone", () => {
    startStream();
    cellHeader();
    const card = live().toolCard as unknown as FakeEl;
    feed("text", "The cell finished; now summarising.\n", { type: "text_chunk", block_type: "text" });

    feed("text", marker.chunk, marker);

    expect(card.classList.contains("stopped")).toBe(false);
    expect((live().wrap as unknown as FakeEl).querySelectorAll(".msg-stopped")).toHaveLength(1);
  });

  it("the terminal fallback adds one marker when the chunk was never seen", () => {
    startStream();
    cellHeader();
    finishStoppedStream(live(), {
      status: "cancelled",
      cancelled: { reason: "auto_budget", request_id: "req-2" },
    });
    finishStoppedStream(live(), { status: "cancelled" });

    const wrap = live().wrap as unknown as FakeEl;
    const markers = wrap.querySelectorAll(".msg-stopped");
    expect(markers).toHaveLength(1);
    expect(markers[0]!.dataset.stopReason).toBe("auto_budget");
    expect(markers[0]!.textContent).toContain("Auto Mode budget");
  });

  it("a cancelled terminal closes the live block with the marker", () => {
    startStream();
    cellHeader();
    const wrap = live().wrap as unknown as FakeEl;
    const card = live().toolCard as unknown as FakeEl;

    turnDone("cancelled", {
      type: "frame_update",
      status: "cancelled",
      cancelled: { reason: "user", request_id: "req-3" },
    });

    expect(wrap.querySelectorAll(".msg-stopped")).toHaveLength(1);
    expect(card.classList.contains("stopped")).toBe(true);
    expect(stream.value).toBeNull();
  });

  it("a completed or failed terminal adds no marker", () => {
    for (const status of ["completed", "failed"]) {
      startStream();
      cellHeader();
      const wrap = live().wrap as unknown as FakeEl;
      turnDone(status, { type: "frame_update", status });
      expect(wrap.querySelectorAll(".msg-stopped")).toHaveLength(0);
    }
  });

  it("does not duplicate the marker when the chunk precedes the terminal", () => {
    startStream();
    feed("text", marker.chunk, marker);
    finishStoppedStream(live(), { status: "cancelled", cancelled: marker.cancelled });
    expect((live().wrap as unknown as FakeEl).querySelectorAll(".msg-stopped")).toHaveLength(1);
  });

  it("reopens the stored marker row as the same marker, not as prose", () => {
    const node = renderStored({
      role: "assistant",
      content: "_Stopped by user._",
      created_at: "2026-09-14T00:00:00Z",
      cancelled: { reason: "user", request_id: "req-1", execution_id: "exec-1" },
    }) as unknown as FakeEl;

    expect(node.querySelectorAll(".msg-stopped")).toHaveLength(1);
    expect(node.querySelector(".msg-stopped")!.textContent).toContain("Stopped by user");
    expect(node.querySelectorAll(".md")).toHaveLength(0);
    expect(node.querySelectorAll(".msg-actions")).toHaveLength(0);
    expect(doc.host.children).toContain(node);
  });

  it("an older page (load earlier) reopens the marker the same way", () => {
    const node = renderOlderPage({
      role: "assistant",
      content: "_已由用户停止。_",
      created_at: "2026-09-14T00:00:00Z",
      cancelled: { reason: "user", request_id: "req-9" },
    }) as unknown as FakeEl;

    expect(node.querySelectorAll(".msg-stopped")).toHaveLength(1);
    expect(node.querySelector(".msg-stopped")!.dataset.requestId).toBe("req-9");
    expect(node.querySelectorAll(".md")).toHaveLength(0);
  });

  it("renders an ordinary or malformed row as prose", () => {
    for (const cancelled of [undefined, { reason: "because" }, "user"]) {
      const node = renderStored({
        role: "assistant",
        content: "_Stopped by user._",
        cancelled: cancelled as never,
      }) as unknown as FakeEl;
      expect(node.querySelectorAll(".msg-stopped")).toHaveLength(0);
      expect(node.querySelectorAll(".md")).toHaveLength(1);
    }
  });
});
