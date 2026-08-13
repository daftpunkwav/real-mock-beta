/** 中文语境半角标点 → 全角（展示层兜底，兼容旧评价数据） */
const CJK = "\\u4e00-\\u9fff\\u3400-\\u4dbf\\uf900-\\ufaff";

export function normalizeCnPunctuation(text: string): string {
  if (!text) return text;
  let s = text;
  const pairs: [RegExp, string][] = [
    [new RegExp(`(?<=[${CJK}]),`, "g"), "，"],
    [new RegExp(`,(?=[${CJK}])`, "g"), "，"],
    [new RegExp(`(?<=[${CJK}])\\.`, "g"), "。"],
    [new RegExp(`\\.(?=[${CJK}])`, "g"), "。"],
    [new RegExp(`(?<=[${CJK}]);`, "g"), "；"],
    [new RegExp(`;(?=[${CJK}])`, "g"), "；"],
    [new RegExp(`(?<=[${CJK}]):`, "g"), "："],
    [new RegExp(`:(?=[${CJK}])`, "g"), "："],
    [new RegExp(`(?<=[${CJK}])!`, "g"), "！"],
    [new RegExp(`!(?=[${CJK}])`, "g"), "！"],
    [new RegExp(`(?<=[${CJK}])\\?`, "g"), "？"],
    [new RegExp(`\\?(?=[${CJK}])`, "g"), "？"],
  ];
  for (const [re, full] of pairs) {
    s = s.replace(re, full);
  }
  s = s.replace(new RegExp(`\\((?=[${CJK}])`, "g"), "（");
  s = s.replace(new RegExp(`(?<=[${CJK}])\\)`, "g"), "）");
  return s;
}

export type RewritePair = { before: string; after: string };

/** 解析改写示例：兼容对象、JSON/Python dict 字符串、改前→改后 */
export function parseRewriteExample(raw: unknown): RewritePair | null {
  if (raw == null) return null;

  if (typeof raw === "object" && !Array.isArray(raw)) {
    const o = raw as Record<string, unknown>;
    const before = String(o.before ?? o.改前 ?? o.from ?? "").trim();
    const after = String(o.after ?? o.改后 ?? o.to ?? "").trim();
    if (before && after) return { before, after };
  }

  const text = String(raw).trim();
  if (!text) return null;

  if (text.startsWith("{")) {
    try {
      const normalized = text
        .replace(/'/g, '"')
        .replace(/\bNone\b/g, "null")
        .replace(/\bTrue\b/g, "true")
        .replace(/\bFalse\b/g, "false");
      const parsed = JSON.parse(normalized) as Record<string, unknown>;
      const before = String(parsed.before ?? parsed.改前 ?? "").trim();
      const after = String(parsed.after ?? parsed.改后 ?? "").trim();
      if (before && after) return { before, after };
    } catch {
      /* 继续宽松抽取 */
    }

    const beforeMatch =
      text.match(/['"]before['"]\s*:\s*['"]([\s\S]*?)['"]\s*,\s*['"]after['"]/i) ||
      text.match(/['"]before['"]\s*:\s*['"]([\s\S]*?)['"]\s*}/i);
    const afterMatch = text.match(/['"]after['"]\s*:\s*['"]([\s\S]*?)['"]\s*}/i);
    if (beforeMatch?.[1] && afterMatch?.[1]) {
      return {
        before: beforeMatch[1].replace(/\\'/g, "'").replace(/\\"/g, '"').trim(),
        after: afterMatch[1].replace(/\\'/g, "'").replace(/\\"/g, '"').trim(),
      };
    }
  }

  // 【改前】…【改后】… / 改前：…改后：… / Before:…After:…
  const labeled =
    text.match(
      /^(?:【\s*改前\s*】|改前\s*[:：]|before\s*[:：])\s*([\s\S]*?)\s*(?:【\s*改后\s*】|改后\s*[:：]|after\s*[:：])\s*([\s\S]+)$/i,
    ) ||
    text.match(
      /(?:【\s*改前\s*】|改前\s*[:：])\s*([\s\S]*?)\s*(?:【\s*改后\s*】|改后\s*[:：])\s*([\s\S]+)/i,
    );
  if (labeled?.[1] && labeled?.[2]) {
    const before = labeled[1].trim();
    const after = labeled[2].trim();
    if (before && after) return { before, after };
  }

  const arrow = text.split(/\s*(?:→|->|=>)\s*/);
  if (arrow.length >= 2) {
    const head = arrow[0] ?? "";
    const rest = arrow.slice(1).join(" → ");
    const before = head.replace(/^(?:【\s*改前\s*】\s*|改前[:：]\s*|before[:：]\s*)/i, "").trim();
    const after = rest.replace(/^(?:【\s*改后\s*】\s*|改后[:：]\s*|after[:：]\s*)/i, "").trim();
    if (before && after) return { before, after };
  }

  return null;
}

/** 评价正文强调片段（供 UI 渲染） */
export type EvalTextPart =
  | { type: "text"; value: string }
  | { type: "bold"; value: string }
  | { type: "code"; value: string };

const MARK_SPLIT = /(\*\*[^*]+\*\*|`[^`]+`)/g;
const METRIC_RE =
  /(\d+(?:\.\d+)?%|\d+(?:\.\d+)?\s?(?:ms|s|EPS|[kK]|x|倍)|P\d{2,3}|pass@\d+|「[^」]{1,48}」|『[^』]{1,48}』)/g;

function pushMetricParts(out: EvalTextPart[], segment: string) {
  if (!segment) return;
  let last = 0;
  METRIC_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = METRIC_RE.exec(segment)) !== null) {
    if (m.index > last) out.push({ type: "text", value: segment.slice(last, m.index) });
    out.push({ type: "bold", value: m[0] });
    last = m.index + m[0].length;
  }
  if (last < segment.length) out.push({ type: "text", value: segment.slice(last) });
}

/**
 * 解析评价文本中的强调：
 * - LLM 标记的 **粗体** / `代码`
 * - 无标记时兜底高亮百分比、时延、P99、中文引号短句等
 */
export function tokenizeEvalText(raw: string): EvalTextPart[] {
  const text = raw || "";
  if (!text) return [];

  const chunks = text.split(MARK_SPLIT).filter((c) => c.length > 0);
  const out: EvalTextPart[] = [];

  for (const chunk of chunks) {
    if (chunk.startsWith("**") && chunk.endsWith("**") && chunk.length > 4) {
      out.push({ type: "bold", value: chunk.slice(2, -2) });
      continue;
    }
    if (chunk.startsWith("`") && chunk.endsWith("`") && chunk.length > 2) {
      out.push({ type: "code", value: chunk.slice(1, -1) });
      continue;
    }
    pushMetricParts(out, chunk);
  }
  return out;
}
