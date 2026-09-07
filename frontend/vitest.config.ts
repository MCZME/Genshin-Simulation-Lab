import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // 状态、转换与 API 客户端为纯逻辑测试；组件测试后续按需引入 jsdom
    environment: "node",
  },
});
