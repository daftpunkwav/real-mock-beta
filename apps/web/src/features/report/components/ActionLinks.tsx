"use client";

import Link from "next/link";
import { RefreshCw } from "lucide-react";

/** 页尾动作:「再来一次」「查看成长记录」。 */
export function ActionLinks() {
  return (
    <div className="mt-7 flex flex-wrap gap-2.5">
      <Link href="/interview" className="btn-primary">
        <RefreshCw size={13} /> 再来一次
      </Link>
      <Link href="/growth" className="btn-secondary">
        查看成长记录
      </Link>
    </div>
  );
}
