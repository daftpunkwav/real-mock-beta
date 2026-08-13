/**
 * 流式内容中的「思考 / 正式回答」拆分。
 *
 * 兼容：
 * - ``<think>...</think>``（部分国产模型）
 * - ``<thinking>...</thinking>``
 * - ``\`\`\`thinking ... \`\`\``
 *
 * 流式场景下标签可能跨 token 切开，因此维护 ``pending`` 缓冲。
 */

export interface ThinkSplit {
  /** 已闭合或正在进行中的思考正文 */
  thinking: string;
  /** 正式回答（不含思考标签） */
  answer: string;
  /** 当前是否仍在思考块内 */
  inThinking: boolean;
  /** 思考块是否已出现过（用于决定是否展示折叠区） */
  hasThinking: boolean;
}

const OPEN_TAGS = ["<think>", "<thinking>", "```thinking"] as const;
const CLOSE_TAGS = ["</think>", "</thinking>", "```"] as const;

/** 判断 s[i:] 是否以某个 open tag 开头（大小写不敏感） */
function matchOpen(s: string, i: number): { tag: string; len: number } | null {
  const slice = s.slice(i);
  const lower = slice.toLowerCase();
  for (const tag of OPEN_TAGS) {
    if (lower.startsWith(tag.toLowerCase())) {
      // ```thinking 后允许换行
      if (tag === "```thinking") {
        let len = tag.length;
        if (slice[len] === "\n" || slice[len] === "\r") {
          len += slice[len] === "\r" && slice[len + 1] === "\n" ? 2 : 1;
        }
        return { tag, len };
      }
      return { tag, len: tag.length };
    }
  }
  return null;
}

function matchClose(s: string, i: number, openTag: string | null): { len: number } | null {
  const slice = s.slice(i);
  const lower = slice.toLowerCase();
  if (openTag === "```thinking") {
    // 代码块关闭：单独一行的 ```
    if (lower.startsWith("```") && (slice.length === 3 || /[\r\n]/.test(slice[3] ?? "\n") || slice[3] === undefined)) {
      return { len: 3 };
    }
    return null;
  }
  for (const tag of CLOSE_TAGS) {
    if (tag === "```") continue;
    if (lower.startsWith(tag.toLowerCase())) {
      return { len: tag.length };
    }
  }
  return null;
}

/**
 * 将累计的完整原始流字符串拆成 thinking / answer。
 * 每次 content 变长时重新解析即可（O(n)，prep 回复长度可接受）。
 */
export function splitThinkAnswer(raw: string): ThinkSplit {
  let thinking = "";
  let answer = "";
  let inThinking = false;
  let hasThinking = false;
  let openTag: string | null = null;
  let i = 0;

  while (i < raw.length) {
    if (!inThinking) {
      const open = matchOpen(raw, i);
      if (open) {
        inThinking = true;
        hasThinking = true;
        openTag = open.tag;
        i += open.len;
        continue;
      }
      // 可能是未写完的 open tag 前缀 —— 若剩余像标签开头则留给 pending
      const rest = raw.slice(i);
      if (couldBeTagPrefix(rest, "open")) {
        break;
      }
      answer += raw[i];
      i += 1;
    } else {
      const close = matchClose(raw, i, openTag);
      if (close) {
        inThinking = false;
        openTag = null;
        i += close.len;
        continue;
      }
      const rest = raw.slice(i);
      if (couldBeTagPrefix(rest, "close", openTag)) {
        break;
      }
      thinking += raw[i];
      i += 1;
    }
  }

  return { thinking: thinking.trim(), answer: answer.trimStart(), inThinking, hasThinking };
}

function couldBeTagPrefix(
  rest: string,
  kind: "open" | "close",
  openTag?: string | null,
): boolean {
  if (!rest || rest.length > 20) return false;
  const lower = rest.toLowerCase();
  if (kind === "open") {
    return OPEN_TAGS.some((t) => t.toLowerCase().startsWith(lower) || lower.startsWith("<") || lower.startsWith("`"));
  }
  if (openTag === "```thinking") {
    return "`".startsWith(lower) || lower.startsWith("`");
  }
  return CLOSE_TAGS.some((t) => t !== "```" && (t.toLowerCase().startsWith(lower) || lower.startsWith("<")));
}

/** 去掉思考块，仅保留正式回答（落库展示兜底） */
export function stripThinking(raw: string): string {
  return splitThinkAnswer(raw).answer;
}

/** 去掉 ReAct 工具调用 JSON（前端兜底，避免协议泄漏到气泡） */
const TOOL_JSON_RE = /\{[^{}]*["']tool["']\s*:\s*["']\w+["'][^{}]*\}/gi;

export function stripToolCallJson(text: string): string {
  if (!text) return text;
  return text
    .replace(TOOL_JSON_RE, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
