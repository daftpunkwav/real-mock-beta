import { CheckCircle2, Circle, Clock } from "lucide-react";

/** 场次状态徽标：completed「已完成」/ active「进行中」/ pending「待开始」。 */
export function StatusBadge({ status }: { status: string }) {
  const config = {
    completed: { icon: CheckCircle2, text: "已完成", className: "chip-green" },
    active: { icon: Clock, text: "进行中", className: "chip-blue" },
    pending: { icon: Circle, text: "待开始", className: "chip-gray" },
  };
  const c = config[status as keyof typeof config] || config.pending;
  const Icon = c.icon;
  return (
    <span className={`chip ${c.className}`}>
      <Icon size={11} />
      {c.text}
    </span>
  );
}
