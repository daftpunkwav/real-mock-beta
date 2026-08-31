import {
  BarChart3,
  BookOpen,
  Building2,
  FileText,
  KeyRound,
  MessageSquare,
  Mic,
  Shield,
  Sparkles,
  Video,
} from "lucide-react";

export const STEPS = [
  {
    n: "01",
    title: "接入密钥",
    desc: "BYOK 配置 LLM,本地加密存储",
    href: "/settings",
    icon: KeyRound,
  },
  {
    n: "02",
    title: "上传简历",
    desc: "解析档案,生成多维度评价",
    href: "/resume",
    icon: FileText,
  },
  {
    n: "03",
    title: "开始面试",
    desc: "选公司 + 岗位,进入模拟",
    href: "/interview",
    icon: Mic,
  },
];

export const FEATURES = [
  { icon: Sparkles, title: "动态出题", desc: "基于简历与岗位实时生成问题,不刷固定题库。", tint: "brand" },
  { icon: MessageSquare, title: "深度追问", desc: "回答含糊时自动深挖细节,贴近真实面试官节奏。", tint: "green" },
  { icon: Building2, title: "企业风格", desc: "字节 / 腾讯 / 阿里等公司面试风格可切换。", tint: "warning" },
  { icon: Video, title: "音视频交互", desc: "摄像头与语音实时参与,还原临场压力。", tint: "danger" },
  { icon: BookOpen, title: "面试准备", desc: "教练式辅导与面经检索,上场前系统梳理。", tint: "brand" },
  { icon: BarChart3, title: "报告与成长", desc: "场次评分、改进建议,弱项跨场次沉淀。", tint: "green" },
] as const;

export const STATS = [
  { value: 50, suffix: "+", label: "企业风格库" },
  { value: 1000, suffix: "+", label: "题目规模" },
  { value: 100, suffix: "%", label: "本地可用" },
  { value: 0, suffix: "", label: "账号注册" },
];

export const TRUST_POINTS = [
  { icon: Shield, tint: "icon-badge-success", title: "本地优先", desc: "面试数据与密钥默认留在本机,不强制上云" },
  { icon: KeyRound, tint: "icon-badge-brand", title: "自带密钥", desc: "BYOK 接入你的 LLM,成本与模型自己掌控" },
  { icon: Sparkles, tint: "icon-badge-warning", title: "开源可审计", desc: "代码透明,流程可改,适合二次定制" },
];
