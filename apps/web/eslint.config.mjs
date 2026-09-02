// ESLint 9 flat config（Next.js 官方迁移路径）。
// eslint-config-next 15.5 仍为 legacy .eslintrc 格式，用 FlatCompat 包装；
// 见 https://nextjs.org/docs/app/api-reference/config/eslint#migrating-existing-config
import { FlatCompat } from "@eslint/eslintrc";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({ baseDirectory: __dirname });

const eslintConfig = [
  // 构建产物与依赖不参与 lint
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "out/**",
      "next-env.d.ts",
      "vitest.config.ts",
      "public/**",
    ],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "@/lib/api/apiService",
              message: "使用 profileHttp（@/lib/api/clients）",
            },
            {
              name: "@/lib/api/agentService",
              message: "使用 prepCoachHttp（@/lib/api/clients）",
            },
            {
              name: "@/lib/api/interviewService",
              message: "使用 interviewHttp（@/lib/api/clients）",
            },
          ],
        },
      ],
    },
  },
];

export default eslintConfig;
