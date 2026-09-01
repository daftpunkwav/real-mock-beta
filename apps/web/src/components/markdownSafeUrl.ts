/** 仅允许 http(s) 外链，拒绝 javascript: 等协议。 */
export function safeHttpUrl(url: string | undefined): string | null {
  if (!url) return null;
  const t = url.trim();
  try {
    const u = new URL(t, "https://example.invalid");
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    // 相对链接：保留原 pathname
    if (t.startsWith("/") || t.startsWith("#")) return t;
    return u.href;
  } catch {
    return null;
  }
}

/** 仅允许绝对 http(s) URL（拒绝相对路径与危险协议）。 */
export function safeAbsoluteHttpUrl(url: string | undefined): string | null {
  if (!url) return null;
  const t = url.trim();
  try {
    const u = new URL(t);
    if (u.protocol === "http:" || u.protocol === "https:") return u.toString();
  } catch {
    /* invalid */
  }
  return null;
}
