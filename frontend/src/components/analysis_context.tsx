import { createContext, useContext } from "react";

import type { TemplateCatalog } from "../workflow/templates";

export const TemplateCatalogContext = createContext<TemplateCatalog | null>(null);

export function useTemplateCatalog(): TemplateCatalog | null {
  return useContext(TemplateCatalogContext);
}
