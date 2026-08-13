"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type ThemeMode } from "./ThemeProvider";

const LABELS: Record<ThemeMode, string> = {
  light: "浅色",
  dark: "深色",
  system: "跟随系统",
};

const ORDER: ThemeMode[] = ["light", "dark", "system"];

export function ThemeToggle({ collapsed = false }: { collapsed?: boolean }) {
  const { theme, setTheme, cycleTheme } = useTheme();

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={cycleTheme}
        title={`主题：${LABELS[theme]}（点击切换）`}
        aria-label={`当前主题 ${LABELS[theme]}，点击切换`}
        className="mx-auto mb-3 flex h-9 w-9 items-center justify-center rounded-md text-ink-muted hover:bg-surface-muted hover:text-ink"
      >
        {theme === "dark" ? <Moon size={16} /> : theme === "light" ? <Sun size={16} /> : <Monitor size={16} />}
      </button>
    );
  }

  return (
    <div className="mx-3 mb-3 rounded-md border border-surface-border bg-surface-card p-1.5">
      <div className="segmented w-full">
        {ORDER.map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setTheme(m)}
            data-active={theme === m}
            aria-pressed={theme === m}
            title={LABELS[m]}
            className="segmented-item flex-1 gap-1.5 !h-7 !text-xs"
          >
            {m === "light" && <Sun size={12} />}
            {m === "dark" && <Moon size={12} />}
            {m === "system" && <Monitor size={12} />}
            <span>{LABELS[m]}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
