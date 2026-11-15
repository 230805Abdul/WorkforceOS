import { api } from "../services/api";
import { useFetch } from "./useFetch";

/** Departments for dropdowns and filters, sorted by name. `refreshKey` forces a reload after changes. */
export function useDepartments(refreshKey = 0) {
  return useFetch((signal) => api.departments.list({ sort: "name", order: "asc" }, signal), [refreshKey]);
}
