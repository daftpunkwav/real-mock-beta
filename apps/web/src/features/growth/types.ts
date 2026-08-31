/** 系统自我成长聚合响应（与 getSystemInsights 返回结构同源；纯类型，不拉 API 运行时）。 */
export type SystemInsights = Awaited<
  ReturnType<(typeof import("@/lib/api/interviewService").interviewService)["getSystemInsights"]>
>;
