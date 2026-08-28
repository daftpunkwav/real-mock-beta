"use client";

import { ExternalLink, Search } from "lucide-react";
import type { PrepSearchGroup } from "@/types";

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** 仅允许 http(s) 链接,防止 javascript:/data: 等危险协议。 */
function safeHttpUrl(url: string): string | null {
  try {
    const u = new URL(url);
    if (u.protocol === "http:" || u.protocol === "https:") {
      return u.toString();
    }
  } catch {
    /* invalid */
  }
  return null;
}

/** 面试准备:可点击打开原文的搜索结果卡片。 */
export function SearchResultCards({ groups }: { groups: PrepSearchGroup[] }) {
  const visible = groups.filter((g) => g.results?.length > 0);
  if (visible.length === 0) return null;

  return (
    <div className="mt-3 space-y-3 border-t border-surface-border pt-3">
      <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-subtle">
        <Search size={11} />
        检索来源
      </p>
      {visible.map((group) => (
        <div key={group.query || group.results[0]?.url} className="space-y-1.5">
          {group.query ? (
            <p className="truncate text-[11px] text-ink-subtle" title={group.query}>
              查询:{group.query}
            </p>
          ) : null}
          <ul className="space-y-1.5">
            {group.results.map((hit) => {
              const href = safeHttpUrl(hit.url);
              const inner = (
                <div className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-2 text-[13px] font-medium leading-snug text-[var(--info-ink)]">
                      {hit.title}
                    </p>
                    <p className="mt-0.5 truncate text-[11px] text-ink-subtle">
                      {hostOf(hit.url)}
                    </p>
                    {hit.snippet ? (
                      <p className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-ink-muted">
                        {hit.snippet}
                      </p>
                    ) : null}
                  </div>
                  {href ? (
                    <ExternalLink
                      size={13}
                      className="mt-0.5 shrink-0 text-ink-subtle"
                      aria-hidden
                    />
                  ) : null}
                </div>
              );
              return (
                <li key={hit.url}>
                  {href ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer nofollow"
                      className="block rounded-md border border-surface-border bg-surface-alt px-3 py-2 transition-colors hover:border-[var(--primary)] hover:bg-[var(--info-soft)]"
                    >
                      {inner}
                    </a>
                  ) : (
                    <div className="block rounded-md border border-surface-border bg-surface-alt px-3 py-2">
                      {inner}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
