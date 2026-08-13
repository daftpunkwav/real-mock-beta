"use client";

import { motion, useMotionValue, useSpring } from "framer-motion";
import { ReactNode } from "react";

interface BaseProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  strength?: number;
}

/** 渲染为 ``motion.a`` 时允许透传的 props 子集；
 * 排除 onDrag/onDragStart/onDragEnd 等 React 而非 framer-motion 兼容的事件。 */
type SafeAnchorProps = Omit<
  React.AnchorHTMLAttributes<HTMLAnchorElement>,
  | "children"
  | "className"
  | "onClick"
  | "onDrag"
  | "onDragEnd"
  | "onDragStart"
  | "onAnimationStart"
  | "onAnimationEnd"
  | "onAnimationIteration"
  | "onTransitionEnd"
>;

type MagneticButtonProps =
  | (BaseProps & { renderAs?: "button" })
  | (BaseProps & SafeAnchorProps & { renderAs: "a" });

/** 磁吸按钮：根据 ``renderAs`` 渲染为 ``motion.button`` 或 ``motion.a``，
 * 避免旧实现把 ``<Link>`` 直接放进 ``<button>`` 导致 HTML 不合法（焦点路径交叉 / 嵌套交互元素）。 */
export function MagneticButton(props: MagneticButtonProps) {
  const {
    children,
    className = "",
    onClick,
    strength = 0.3,
    renderAs = "button",
  } = props;

  // 单一 hook 链：useMotionValue/useSpring 与 ref 强绑定，确保动画 & DOM 一致。
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 150, damping: 15 });
  const springY = useSpring(y, { stiffness: 150, damping: 15 });

  function handleMouseMove(e: React.MouseEvent) {
    const target = e.currentTarget as HTMLElement;
    const rect = target.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    x.set((e.clientX - centerX) * strength);
    y.set((e.clientY - centerY) * strength);
  }

  function handleMouseLeave() {
    x.set(0);
    y.set(0);
  }

  if (renderAs === "a") {
    const { renderAs: _omit, ...anchorRest } = props as BaseProps &
      SafeAnchorProps & { renderAs: "a" };
    return (
      <motion.a
        className={className}
        style={{ x: springX, y: springY }}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onClick={onClick}
        whileTap={{ scale: 0.97 }}
        {...anchorRest}
      >
        {children}
      </motion.a>
    );
  }

  return (
    <motion.button
      type="button"
      className={className}
      style={{ x: springX, y: springY }}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      onClick={onClick}
      whileTap={{ scale: 0.97 }}
    >
      {children}
    </motion.button>
  );
}
