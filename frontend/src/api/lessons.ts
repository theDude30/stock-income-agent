import { apiGet, apiPost } from "./client";
import type { Lesson } from "./types";

export const fetchLessons = (active = true) => apiGet<Lesson[]>(`/lessons?active=${active}`);
export const ignoreLesson = (id: number, ignored: boolean) =>
  apiPost<Lesson>(`/lessons/${id}/ignore`, { ignored });
