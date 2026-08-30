"use client";

import { tokenizeEvalText } from "@/lib/cnText";
import type { EvalTextPart } from "@/lib/cnText";

/** 评价正文：支持 **强调** / `代码`，旧数据兜底高亮指标。跨评价组件共用。 */
export function EvalRichText({ text }: { text: string }) {
  const parts = tokenizeEvalText(text);
  return (
    <>
      {parts.map((p, i) => (
        <EvalRichPart key={i} part={p} />
      ))}
    </>
  );
}

function EvalRichPart({ part }: { part: EvalTextPart }) {
  if (part.type === "bold") {
    return <strong className="eval-em">{part.value}</strong>;
  }
  if (part.type === "code") {
    return <code className="eval-code">{part.value}</code>;
  }
  return <>{part.value}</>;
}
