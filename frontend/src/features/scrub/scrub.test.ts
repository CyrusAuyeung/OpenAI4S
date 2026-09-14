import { describe, expect, it } from "vitest";
import { publicModelId, publicText } from "./scrub";

describe("publicText", () => {
  it("redacts Bearer, key-shaped tokens, and query credentials", () => {
    expect(publicText("Bearer abc.def")).toBe("Bearer [redacted]");
    expect(publicText("sk-abcdefghijk")).toBe("[redacted]");
    expect(publicText("https://h/?api_key=secret&x=1")).toBe(
      "https://h/?api_key=[redacted]&x=1",
    );
  });

  it("ellipsizes past the limit", () => {
    expect(publicText("abcdefghij", 4)).toBe("abc…");
    expect(publicText(null)).toBe("");
  });
});

describe("publicModelId", () => {
  it("leaves model ids that merely start with a credential prefix alone", () => {
    for (const id of ["ark-code-latest", "ark-deepseek-v3-250324", "sk-small-2024-08-06", "claude-sonnet-4-5-20250929"]) {
      expect(publicModelId(id)).toBe(id);
    }
    // The generic scrubber is unchanged, and still takes the short test shape.
    expect(publicText("ark-code-latest")).toBe("[redacted]");
    expect(publicText("sk-abcdefghijk")).toBe("[redacted]");
  });

  it("still redacts real key shapes, Bearer tokens and query credentials", () => {
    expect(publicModelId("sk-proj-fake-Q3vT9wXk2LmN8pRz4YbC7dFh1JsA6uEo")).toBe("[redacted]");
    expect(publicModelId("sk-ant-api03-fake-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789-_aa")).toBe("[redacted]");
    expect(publicModelId("sk-fake-0123456789abcdefghijABCDEFGHIJ")).toBe("[redacted]");
    expect(publicModelId("Bearer abc.def")).toBe("Bearer [redacted]");
    expect(publicModelId("m?api_key=secret")).toBe("m?api_key=[redacted]");
  });

  it("trims and caps", () => {
    expect(publicModelId("  gpt-4o  ")).toBe("gpt-4o");
    expect(publicModelId("abcdefghij", 4)).toBe("abc…");
    expect(publicModelId(null)).toBe("");
  });
});
