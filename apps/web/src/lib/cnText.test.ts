import { describe, expect, it } from "vitest";

import {
  normalizeCnPunctuation,
  parseRewriteExample,
  tokenizeEvalText,
} from "./cnText";

describe("normalizeCnPunctuation", () => {
  it("半角逗号在中文语境转为全角", () => {
    expect(normalizeCnPunctuation("你好,世界")).toBe("你好，世界");
    expect(normalizeCnPunctuation("前端,后端")).toBe("前端，后端");
  });

  it("英文/数字间半角标点保持不变", () => {
    expect(normalizeCnPunctuation("a,b,c")).toBe("a,b,c");
    expect(normalizeCnPunctuation("React, Vue")).toBe("React, Vue");
  });

  it("句号/问号/冒号在中文语境转换", () => {
    expect(normalizeCnPunctuation("完成了吗?")).toBe("完成了吗？");
    expect(normalizeCnPunctuation("注意:.env")).toBe("注意：.env");
    expect(normalizeCnPunctuation("很好.")).toBe("很好。");
  });

  it("括号与感叹号转换", () => {
    expect(normalizeCnPunctuation("(重要)")).toBe("（重要）");
    expect(normalizeCnPunctuation("太好了!")).toBe("太好了！");
  });

  it("空字符串原样返回", () => {
    expect(normalizeCnPunctuation("")).toBe("");
    expect(normalizeCnPunctuation("abc")).toBe("abc");
  });
});

describe("parseRewriteExample", () => {
  it("解析对象形态", () => {
    expect(parseRewriteExample({ before: "A", after: "B" })).toEqual({
      before: "A",
      after: "B",
    });
  });

  it("解析 JSON 字符串（含单引号与 None/True）", () => {
    const raw = "{'before': '你好', 'after': '您好'}";
    expect(parseRewriteExample(raw)).toEqual({ before: "你好", after: "您好" });
  });

  it("解析改前/改后标签形态", () => {
    expect(parseRewriteExample("【改前】旧文案 【改后】新文案")).toEqual({
      before: "旧文案",
      after: "新文案",
    });
  });

  it("解析箭头形态", () => {
    expect(parseRewriteExample("旧句子 → 新句子")).toEqual({
      before: "旧句子",
      after: "新句子",
    });
  });

  it("无效输入返回 null", () => {
    expect(parseRewriteExample(null)).toBeNull();
    expect(parseRewriteExample("")).toBeNull();
    expect(parseRewriteExample("无结构文本")).toBeNull();
  });
});

describe("tokenizeEvalText", () => {
  it("拆分粗体与代码片段", () => {
    const parts = tokenizeEvalText("提升 **QPS** 到 `100`");
    expect(parts).toContainEqual({ type: "bold", value: "QPS" });
    expect(parts).toContainEqual({ type: "code", value: "100" });
  });

  it("无标记时兜底高亮指标", () => {
    const parts = tokenizeEvalText("延迟 200ms，通过率 95%");
    expect(parts).toContainEqual({ type: "bold", value: "200ms" });
    expect(parts).toContainEqual({ type: "bold", value: "95%" });
  });

  it("空输入返回空数组", () => {
    expect(tokenizeEvalText("")).toEqual([]);
    expect(tokenizeEvalText(null as unknown as string)).toEqual([]);
  });
});
