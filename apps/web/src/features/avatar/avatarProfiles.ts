/** 拟真面试官形象配置（CSS 矢量人像，无外部资源依赖）。 */

export interface AvatarProfile {
  label: string;
  hair: string;
  skin: string;
  suit: string;
  shirt: string;
  accent: string;
  gender: "male" | "female";
}

export const AVATAR_PROFILES: Record<string, AvatarProfile> = {
  professional_male: {
    label: "专业男面试官",
    hair: "#2c1810",
    skin: "#e8b896",
    suit: "#1e3a5f",
    shirt: "#f1f5f9",
    accent: "#3b82f6",
    gender: "male",
  },
  senior_male: {
    label: "资深男面试官",
    hair: "#3f3f46",
    skin: "#d4a574",
    suit: "#292524",
    shirt: "#fafaf9",
    accent: "#a8a29e",
    gender: "male",
  },
  gentle_female: {
    label: "亲和女面试官",
    hair: "#4a3728",
    skin: "#f0c4a8",
    suit: "#4c1d95",
    shirt: "#faf5ff",
    accent: "#a78bfa",
    gender: "female",
  },
  hr_female: {
    label: "HR 女面试官",
    hair: "#78350f",
    skin: "#f5d0b0",
    suit: "#9a3412",
    shirt: "#fff7ed",
    accent: "#fb923c",
    gender: "female",
  },
  young_female: {
    label: "青年女面试官",
    hair: "#1e1b4b",
    skin: "#f3c6a8",
    suit: "#312e81",
    shirt: "#eef2ff",
    accent: "#818cf8",
    gender: "female",
  },
  strict_expert: {
    label: "严厉专家",
    hair: "#1a1a1a",
    skin: "#d4a574",
    suit: "#1c1917",
    shirt: "#e7e5e4",
    accent: "#ef4444",
    gender: "male",
  },
};
