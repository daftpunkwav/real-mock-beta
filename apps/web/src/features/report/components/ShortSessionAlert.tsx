"use client";

/** 短会话警告:维度分可能偏低,属评估结果而非缺数。 */
export function ShortSessionAlert({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div className="alert alert-warning mb-6">
      本场对话较短或有效作答很少,维度分可能偏低或接近 0,属评估结果而非页面缺数。
    </div>
  );
}
