import { createContext, useContext } from "react";

const MetaContext = createContext(null);
export const MetaProvider = MetaContext.Provider;
/** Fixed option lists from GET /api/meta (statuses, sources, ...). Departments are real data: see useDepartments. */
export const useMeta = () => useContext(MetaContext);
