import { describe, expect, it } from "vitest";

import { splitThinkAnswer, stripThinking, stripToolCallJson } from "./thinkStream";

describe("splitThinkAnswer", () => {
  it("完整 think 块被拆出", () => {
    const split = splitThinkAnswer("<think>先分析</think>正式回答");
    expect(split.thinking).toBe("先分析");
    expect(split.answer).toBe("正式回答");
    expect(split.hasThinking).toBe(true);
    expect(split.inThinking).toBe(false);
  });

  it("无 think 块时全部为 answer", () => {
    const split = splitThinkAnswer("正常回答内容");
    expect(split.answer).toBe("正常回答内容");
    expect(split.thinking).toBe("");
    expect(split.hasThinking).toBe(false);
  });

  it("未闭合标签跨 token 时保留 pending 语义", () => {
    const split = splitThinkAnswer("答案前缀<think>未闭合思");
    // 未闭合的 open tag 之前的内容是 answer；剩余留待下一 token
    expect(split.answer.startsWith("答案前缀")).toBe(true);
    expect(split.inThinking).toBe(true);
    expect(split.hasThinking).toBe(true);
  });

  it("支持 <thinking> 双标签形态", () => {
    const split = splitThinkAnswer("<thinking>双标签</thinking>回答");
    expect(split.thinking).toBe("双标签");
    expect(split.answer).toBe("回答");
  });

  it("支持 ```thinking 代码块形态", () => {
    const split = splitThinkAnswer("```thinking\n代码思考\n```\n正文");
    expect(split.thinking).toContain("代码思考");
    expect(split.answer).toBe("正文");
  });

  it("思考内容 trim，answer 去掉前导空白", () => {
    const split = splitThinkAnswer("<think>   \n  思考  \n  </think>   回答");
    expect(split.thinking).toBe("思考");
    expect(split.answer).toBe("回答");
  });
});

describe("stripThinking", () => {
  it("去除思考块仅留回答", () => {
    expect(stripThinking("<think>内部</think>外部")).toBe("外部");
  });
});

describe("stripToolCallJson", () => {
  it("移除 tool 调用 JSON 片段（无嵌套花括号形态）", () => {
    const text = '前文 {"tool": "github_search", "args": "x"} 后文';
    expect(stripToolCallJson(text)).not.toContain("github_search");
    expect(stripToolCallJson(text)).toContain("前文");
    expect(stripToolCallJson(text)).toContain("后文");
  });

  it("空输入原样返回", () => {
    expect(stripToolCallJson("")).toBe("");
  });
});
