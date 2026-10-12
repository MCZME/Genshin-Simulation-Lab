/**
 * node:fs 最小类型声明：令牌一致性测试需要读取 tokens.css 文本，
 * 项目不引入 @types/node，这里只声明用到的表面。
 */
declare module "node:fs" {
  export function readFileSync(path: URL | string, encoding: "utf8"): string;
}
