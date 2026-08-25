import { createContext, useContext } from "react";

import type { AnalysisSchemaCatalog } from "../workflow/templates";

export const AnalysisSchemaCatalogContext = createContext<AnalysisSchemaCatalog | null>(null);

export function useAnalysisSchemaCatalog(): AnalysisSchemaCatalog | null {
  return useContext(AnalysisSchemaCatalogContext);
}
