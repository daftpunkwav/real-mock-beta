"use client";

import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import type { Components } from "react-markdown";

/** 仅允许 http(s) 外链，拒绝 javascript: 等协议。 */
function safeHttpUrl(url: string | undefined): string | null {
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

const components: Components = {
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

/**
 * 规范化模型输出的表格，避免：
 * - 空格/Tab 分列无法渲染
 * - 行间夹杂 ``--- --- ---`` 被当成水平线 / 多表头
 * - 错误地在每一行数据前插入分隔行
 */
export function normalizeLooseTables(src: string): string {
  if (!src) return src;
  // 先丢掉「整行都是 ---」的垃圾分隔（模型/旧逻辑常见）
  const cleaned = src
    .split("\n")
    .filter((line) => !isJunkSeparatorLine(line))
    .join("\n");

  if (cleaned.includes("|")) {
    return ensureGfmTableSeparators(cleaned);
  }
  return convertLooseColumnBlocks(cleaned);
}

/** 整行仅为破折号/冒号/管道/空白 → 无信息量的伪分隔行 */
function isJunkSeparatorLine(line: string): boolean {
  const t = line.trim();
  if (!t) return false;
  // --- 或 --- --- --- 或 |---|---| 或 | --- | --- |
  if (/^[\s|:\-]+$/.test(t) && /-/.test(t)) return true;
  return false;
}

function convertLooseColumnBlocks(src: string): string {
  const lines = src.split("\n");
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i] ?? "";
    const cols = splitLooseColumns(line);
    if (cols.length < 2 || isDashOnlyCells(cols)) {
      out.push(line);
      i += 1;
      continue;
    }

    const block: string[][] = [cols];
    let j = i + 1;
    while (j < lines.length) {
      const next = lines[j] ?? "";
      if (!next.trim()) break;
      if (isJunkSeparatorLine(next)) {
        j += 1; // 跳过行间 ---，继续拼同一张表
        continue;
      }
      const nextCols = splitLooseColumns(next);
      if (nextCols.length < 2) break;
      if (isDashOnlyCells(nextCols)) {
        j += 1;
        continue;
      }
      if (Math.abs(nextCols.length - cols.length) > 1) break;
      block.push(nextCols);
      j += 1;
    }

    if (block.length >= 2) {
      const width = Math.max(...block.map((r) => r.length));
      const pad = (row: string[]) => {
        const r = [...row];
        while (r.length < width) r.push("");
        return r.slice(0, width);
      };
      const header = pad(block[0]!);
      out.push(`| ${header.join(" | ")} |`);
      // 分隔行只输出一次
      out.push(`| ${header.map(() => "---").join(" | ")} |`);
      for (let k = 1; k < block.length; k += 1) {
        out.push(`| ${pad(block[k]!).join(" | ")} |`);
      }
      i = j;
      continue;
    }

    out.push(line);
    i += 1;
  }

  return out.join("\n");
}

function isDashOnlyCells(cols: string[]): boolean {
  return cols.length > 0 && cols.every((c) => /^:?-{1,}:?$/.test(c.trim()));
}

function splitLooseColumns(line: string): string[] {
  const t = line.trim();
  if (!t) return [];
  if (t.includes("\t")) {
    return t.split(/\t+/).map((c) => c.trim()).filter(Boolean);
  }
  if (/\s{2,}/.test(t)) {
    return t.split(/\s{2,}/).map((c) => c.trim()).filter(Boolean);
  }
  return [];
}

/**
 * 对已有 pipe 表格：仅在「表头后紧跟数据行且缺少分隔行」时插入一行 ---。
 * 不会在每一行数据之间重复插入。
 */
function ensureGfmTableSeparators(src: string): string {
  const lines = src.split("\n");
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i] ?? "";
    out.push(line);

    if (isPipeRow(line) && !isSeparatorRow(line)) {
      const next = lines[i + 1] ?? "";
      // 已是合法 GFM：表头 + 分隔行
      if (isSeparatorRow(next)) {
        i += 1;
        continue;
      }
      // 表头后直接是数据行 → 补一次分隔
      if (isPipeRow(next) && !isSeparatorRow(next)) {
        const n = countPipeColumns(line);
        out.push(`| ${Array.from({ length: n }, () => "---").join(" | ")} |`);
        // 后续连续 pipe 数据行原样输出，不再插入
        i += 1;
        while (i < lines.length) {
          const row = lines[i] ?? "";
          if (!isPipeRow(row) || isSeparatorRow(row)) break;
          // 跳过夹在数据行之间的垃圾分隔
          out.push(row);
          i += 1;
          // 偷看下一行是否是 junk separator（已在入口 filter，这里防 | --- |）
          while (i < lines.length && isJunkSeparatorLine(lines[i] ?? "")) {
            i += 1;
          }
        }
        continue;
      }
    }
    i += 1;
  }

  return out.join("\n");
}

function countPipeColumns(line: string): number {
  const parts = line.trim().split("|").map((p) => p.trim());
  // 去掉首尾因 |a|b| 产生的空段
  const cells = parts.filter((p, idx) => {
    if (idx === 0 && p === "") return false;
    if (idx === parts.length - 1 && p === "") return false;
    return true;
  });
  return Math.max(cells.length, 1);
}

function isPipeRow(line: string): boolean {
  const t = line.trim();
  return t.includes("|") && (t.startsWith("|") || /\|.+\|/.test(t));
}

function isSeparatorRow(line: string): boolean {
  const t = line.trim();
  if (!t) return false;
  // | --- | :---: | ---: |
  if (/^\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$/.test(t)) return true;
  if (/^:?-{3,}:?(\s+|:?-{3,}:?)+$/.test(t)) return true;
  return false;
}

export function MarkdownContent({
  content,
  className = "",
}: {
  content: string;
  className?: string;
}) {
  const normalized = useMemo(() => normalizeLooseTables(content), [content]);

  return (
    <div className={`markdown-body text-sm min-w-0 max-w-full overflow-x-auto ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={components}
      >
        {normalized}
      </ReactMarkdown>
    </div>
  );
}
