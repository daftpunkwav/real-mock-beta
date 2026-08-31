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
