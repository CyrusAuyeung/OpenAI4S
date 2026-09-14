/**
 * Credential-shaped substring redaction for user-visible strings.
 * Port of app.js:2761-2767.
 */

export function publicText(value: unknown, limit = 180): string {
  let out = String(value == null ? "" : value);
  out = out
    .replace(/\bBearer\s+[^\s,;]+/gi, "Bearer [redacted]")
    .replace(
      /\b(?:sk|ark|api[_-]?key|access[_-]?token|refresh[_-]?token)[-_][A-Za-z0-9._-]{8,}\b/gi,
      "[redacted]",
    )
    .replace(/([?&](?:key|token|api_key)=)[^&#\s]+/gi, "$1[redacted]");
  return out.length > limit ? out.slice(0, Math.max(0, limit - 1)) + "…" : out;
}

const CREDENTIAL_SHAPE =
  /\b(?:sk|ark|api[_-]?key|access[_-]?token|refresh[_-]?token)[-_][A-Za-z0-9._-]{8,}\b/gi;

/**
 * Whether a credential-prefixed token carries a random run no model id has: a
 * separator-free segment of 24+ characters, or of 16+ mixing letters and digits.
 * Model ids are short words and dates joined by `-` / `.` / `_`.
 */
function looksRandom(token: string): boolean {
  return token
    .split(/[-_.]/)
    .some((seg) => seg.length >= 24 || (seg.length >= 16 && /\d/.test(seg) && /[A-Za-z]/.test(seg)));
}

/**
 * `publicText` for a model id or protocol name. The generic scrubber redacts
 * any `sk-` / `ark-` token of 8+ characters, which rewrites legitimate ids:
 * `ark-code-latest`, the Ark router default, rendered as "[redacted]". Here a
 * prefixed token is redacted only when it also looks random, which every real
 * key does; Bearer tokens and query credentials are stripped as before.
 */
export function publicModelId(value: unknown, limit = 200): string {
  const out = String(value == null ? "" : value)
    .trim()
    .replace(/\bBearer\s+[^\s,;]+/gi, "Bearer [redacted]")
    .replace(CREDENTIAL_SHAPE, (match) => (looksRandom(match) ? "[redacted]" : match))
    .replace(/([?&](?:key|token|api_key)=)[^&#\s]+/gi, "$1[redacted]");
  return out.length > limit ? out.slice(0, Math.max(0, limit - 1)) + "…" : out;
}
