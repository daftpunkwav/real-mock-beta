"use client";

import type { Components } from "react-markdown";
import { safeHttpUrl } from "./markdownSafeUrl";

/** react-markdown 的组件映射：样式与链接安全策略集中在这里，与渲染主文件解耦。 */
export const markdownComponents: Components = {
  h1: ({ children }) => (
    <h1 className="mt-3 mb-1.5 text-base font-bold tracking-tight first:mt-0 text-ink">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mt-3 mb-1.5 text-base font-bold tracking-tight first:mt-0 text-ink">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-2.5 mb-1 text-[14px] font-semibold first:mt-0 text-ink">{children}</h3>
  ),
  p: ({ children }) => <p className="mb-2 leading-relaxed text-ink last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 text-ink">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 text-ink">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => (
    <strong className="font-semibold text-ink">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,
  code: ({ className, children }) => {
    const isBlock = className?.includes("language-");
    if (isBlock) {
      return (
        <code className="my-2 block overflow-x-auto whitespace-pre-wrap rounded-md border border-surface-border bg-surface-alt p-3 font-mono text-xs text-ink">
          {children}
        </code>
      );
    }
    return (
      <code className="rounded border border-surface-border bg-surface-muted px-1 py-0.5 font-mono text-[0.85em] text-ink">
        {children}
      </code>
    );
  },
  pre: ({ children }) => <pre className="my-2 overflow-x-auto">{children}</pre>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-[var(--primary)] pl-3 italic text-ink-muted">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-surface-border" />,
  a: ({ href, children }) => {
    const safe = safeHttpUrl(href);
    if (!safe) {
      return <span className="text-[var(--primary)]">{children}</span>;
    }
    return (
      <a
        href={safe}
        className="text-[var(--primary)] underline underline-offset-2 hover:no-underline"
        target="_blank"
        rel="noopener noreferrer"
      >
        {children}
      </a>
    );
  },
  // GFM 表格
  table: ({ children }) => (
    <div className="my-3 w-full max-w-full overflow-x-auto rounded-md border border-surface-border">
      <table className="w-full min-w-[320px] border-collapse text-left text-[13px]">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-surface-alt text-ink-muted">{children}</thead>
  ),
  tbody: ({ children }) => <tbody className="divide-y divide-surface-border">{children}</tbody>,
  tr: ({ children }) => (
    <tr className="border-b border-surface-border last:border-0 hover:bg-surface-alt">{children}</tr>
  ),
  th: ({ children }) => (
    <th className="border-b border-surface-border px-3 py-2 align-top text-[11px] font-semibold whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-2 align-top leading-relaxed text-ink-muted">{children}</td>
  ),
};
