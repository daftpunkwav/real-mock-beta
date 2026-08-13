/**
 * 前端路由 / 导航配置
 *
 * 把所有菜单项集中在这里，新增/删除页面只需要改这一处。
 *
 * - ``icon`` 必须是 ``lucide-react`` 导出的图标组件；
 * - ``hidden`` 用于临时隐藏（如功能未上线）。
 */
import {
  Home,
  User,
  FileText,
  Settings,
  Mic,
  BarChart3,
  TrendingUp,
  BookOpen,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  hidden?: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "首页", icon: Home },
  { href: "/profile", label: "个人档案", icon: User },
  { href: "/resume", label: "简历管理", icon: FileText },
  { href: "/prep", label: "面试准备", icon: BookOpen },
  { href: "/interview", label: "模拟面试", icon: Mic },
  { href: "/history", label: "面试记录", icon: BarChart3 },
  { href: "/growth", label: "成长追踪", icon: TrendingUp },
  { href: "/settings", label: "BYOK 设置", icon: Settings },
] as const;
