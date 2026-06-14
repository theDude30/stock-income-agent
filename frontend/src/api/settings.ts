import { apiGet } from "./client";
import type { Settings } from "./types";

export const fetchSettings = () => apiGet<Settings>("/settings");
