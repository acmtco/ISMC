/** react-query хуки поверх типизированного клиента. Каждый запрос обязан
 * иметь демо-фолбэк (docs/01-principles.md, правило 3: демо не имеет права упасть) —
 * `withFallback` тихо переключает на `demo-data.ts`, если бэкенд недоступен
 * или ответил ошибкой; `isDemo` в результате красит баннер в UI. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, withTimeout } from "./client";
import * as demo from "./demo-data";
import type {
  DeviationOut,
  DeviationType,
  EconomicsOut,
  GanttOut,
  LiveStateOut,
  ObjectDetailOut,
  ObjectOut,
  ScheduleImportResult,
  ZoneIn,
  ZonesUpdateResult,
} from "./types";

export interface WithDemo<T> {
  data: T;
  isDemo: boolean;
}

async function withFallback<T>(fetcher: () => Promise<T>, fallback: T): Promise<WithDemo<T>> {
  try {
    const data = await fetcher();
    return { data, isDemo: false };
  } catch {
    return { data: fallback, isDemo: true };
  }
}

export function useObjects() {
  return useQuery({
    queryKey: ["objects"],
    queryFn: () =>
      withFallback<ObjectOut[]>(async () => {
        const { data, error } = await apiClient.GET("/api/objects", { signal: withTimeout() });
        if (error || !data) throw new Error("unavailable");
        return data;
      }, demo.demoObjects),
    staleTime: 30_000,
  });
}

export function useObjectDetail(objectId: string) {
  return useQuery({
    queryKey: ["object", objectId],
    queryFn: () =>
      withFallback<ObjectDetailOut>(async () => {
        const { data, error } = await apiClient.GET("/api/objects/{object_id}", {
          params: { path: { object_id: objectId } },
          signal: withTimeout(),
        });
        if (error || !data) throw new Error("unavailable");
        return data;
      }, demo.demoObjectDetail),
    staleTime: 30_000,
  });
}

export function useLiveState(objectId: string, options?: { refetchIntervalMs?: number }) {
  return useQuery({
    queryKey: ["live", objectId],
    queryFn: () =>
      withFallback<LiveStateOut>(async () => {
        const { data, error } = await apiClient.GET("/api/objects/{object_id}/live", {
          params: { path: { object_id: objectId } },
          signal: withTimeout(),
        });
        if (error || !data) throw new Error("unavailable");
        return data;
      }, demo.demoLiveState),
    refetchInterval: options?.refetchIntervalMs ?? 20_000,
  });
}

export function useGantt(objectId: string, from: string, to: string) {
  return useQuery({
    queryKey: ["gantt", objectId, from, to],
    queryFn: () =>
      withFallback<GanttOut>(async () => {
        const { data, error } = await apiClient.GET("/api/objects/{object_id}/gantt", {
          params: { path: { object_id: objectId }, query: { from, to } },
          signal: withTimeout(),
        });
        if (error || !data) throw new Error("unavailable");
        return data;
      }, demo.demoGantt),
  });
}

export function useDeviations(objectId: string, type?: DeviationType) {
  return useQuery({
    queryKey: ["deviations", objectId, type ?? "all"],
    queryFn: () =>
      withFallback<DeviationOut[]>(async () => {
        const { data, error } = await apiClient.GET("/api/objects/{object_id}/deviations", {
          params: { path: { object_id: objectId }, query: type ? { type } : {} },
          signal: withTimeout(),
        });
        if (error || !data) throw new Error("unavailable");
        return data;
      }, demo.demoDeviations),
  });
}

export function useDeviation(deviationId: string | undefined) {
  return useQuery({
    queryKey: ["deviation", deviationId],
    enabled: Boolean(deviationId),
    queryFn: () =>
      withFallback<DeviationOut | undefined>(async () => {
        if (!deviationId) return undefined;
        const { data, error } = await apiClient.GET("/api/deviations/{deviation_id}", {
          params: { path: { deviation_id: deviationId } },
          signal: withTimeout(),
        });
        if (error || !data) throw new Error("unavailable");
        return data;
      }, demo.demoDeviations.find((d) => d.deviation_id === deviationId)),
  });
}

export function useEconomics(objectId: string, from: string, to: string) {
  return useQuery({
    queryKey: ["economics", objectId, from, to],
    queryFn: () =>
      withFallback<EconomicsOut>(async () => {
        const { data, error } = await apiClient.GET("/api/objects/{object_id}/economics", {
          params: { path: { object_id: objectId }, query: { from, to } },
          signal: withTimeout(),
        });
        if (error || !data) throw new Error("unavailable");
        return data;
      }, demo.demoEconomics),
  });
}

export function useImportSchedule(objectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    // multipart/form-data через openapi-fetch плохо типизируется — обычный
    // fetch надёжнее (тот же путь, что и скачивание PDF-акта ниже).
    mutationFn: async (file: File): Promise<ScheduleImportResult> => {
      const formData = new FormData();
      formData.append("file", file);
      const baseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
      const response = await fetch(`${baseUrl}/api/objects/${objectId}/schedule`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) throw new Error("import failed");
      return (await response.json()) as ScheduleImportResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["gantt", objectId] });
    },
  });
}

export function useUpdateZones(cameraId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (zones: ZoneIn[]): Promise<ZonesUpdateResult> => {
      const { data, error } = await apiClient.POST("/api/cameras/{camera_id}/zones", {
        params: { path: { camera_id: cameraId } },
        body: zones,
      });
      if (error || !data) throw new Error("zones update failed");
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["object"] });
    },
  });
}

export function useCreateAct(deviationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<Blob> => {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL ?? "http://localhost:8000"}/api/deviations/${deviationId}/act`,
        { method: "POST" },
      );
      if (!response.ok) throw new Error("act generation failed");
      return response.blob();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deviation", deviationId] });
      queryClient.invalidateQueries({ queryKey: ["deviations"] });
    },
  });
}
