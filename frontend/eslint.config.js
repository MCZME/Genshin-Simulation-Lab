import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist"] },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: { project: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // 编辑器大量防御式解析后端未知 JSON（readString/?? "" 兜底显示路径），
      // 这些规则会把刻意兜底误报为缺陷，收益低于噪音。
      "@typescript-eslint/no-base-to-string": "off",
      "@typescript-eslint/restrict-template-expressions": "off",
      // 事件回调以 async 命名但不 await 的写法普遍存在，由 no-floating-promises 承担真风险。
      "@typescript-eslint/require-await": "off",
      // 在 testing-library 查询结果上误报"断言不必要"且 autofix 会移除必要的
      // DOM 类型收窄（HTMLElement → HTMLInputElement），暂不启用。
      "@typescript-eslint/no-unnecessary-type-assertion": "off",
    },
  },
  {
    // 配置类 JS 文件不在 tsconfig 工程内，关闭 type-aware 规则。
    files: ["**/*.js"],
    ...tseslint.configs.disableTypeChecked,
  },
);
