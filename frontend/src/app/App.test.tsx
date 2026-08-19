import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App shell", () => {
  it("renders the application title", () => {
    const html = renderToString(<App />);
    expect(html).toContain("Genshin Simulation Lab");
  });
});
