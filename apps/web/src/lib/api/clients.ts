/**
 * HTTP 域客户端统一入口（能力命名，与后端包名解耦）。
 *
 * - ``profileHttp``：档案 / 简历 / 处理器配置
 * - ``prepCoachHttp``：面试准备教练
 * - ``interviewHttp``：模拟面试 / 报告 / 成长
 */

export { profileHttp } from "./profileHttp";
export { prepCoachHttp, type PrepStreamCallbacks } from "./prepCoachHttp";
export { interviewHttp, type SystemGrowthInsights } from "./interviewHttp";

/** OpenAPI 契约类型 */
export * from "./contract";
