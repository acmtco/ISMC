import createClient from "openapi-fetch";

import type { paths } from "./schema";

const baseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const apiClient = createClient<paths>({ baseUrl });

/** Короткий таймаут — при недоступном бэкенде хуки должны быстро уйти в
 * демо-режим, а не заставлять эксперта ждать (docs/01-principles.md, правило 3). */
export const API_TIMEOUT_MS = 2500;

export function withTimeout(ms: number = API_TIMEOUT_MS): AbortSignal {
  return AbortSignal.timeout(ms);
}
