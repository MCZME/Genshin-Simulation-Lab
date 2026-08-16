import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 开发模式代理到本地后端；后端端口以 genshin-sim ui 实际启动为准
      "/api": "http://127.0.0.1:8000",
    },
  },
});
