"use client";

import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { markdownComponents } from "./markdownComponents";

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
        components={markdownComponents}
      >
        {normalized}
      </ReactMarkdown>
    </div>
  );
}
