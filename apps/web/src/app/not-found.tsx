import Link from "next/link";
import { Compass, Home } from "lucide-react";

export default function NotFound() {
  return (
    <main className="flex min-h-[70vh] flex-col items-center justify-center px-6 text-center">
      <span className="empty-state-icon">
        <Compass size={24} />
      </span>
      <p className="page-eyebrow mt-4">404</p>
      <h1 className="mt-1 text-[22px] font-semibold tracking-tight text-ink">找不到该页面</h1>
      <p className="mt-2 max-w-md text-[13px] leading-relaxed text-ink-muted">
        你访问的链接可能已被删除、合并,或者从来没有过。
      </p>
      <Link href="/" className="btn-primary mt-7">
        <Home size={14} /> 返回首页
      </Link>
    </main>
  );
}
