/** Удобные псевдонимы поверх типов, сгенерированных `openapi-typescript`
 * из живой OpenAPI-схемы бэкенда (`npm run generate-api`, docs/02-data-contract.md). */
import type { components } from "./schema";

export type ObjectOut = components["schemas"]["ObjectOut"];
export type ObjectDetailOut = components["schemas"]["ObjectDetailOut"];
export type CameraOut = components["schemas"]["CameraOut"];
export type ZoneOut = components["schemas"]["ZoneOut"];
export type ZoneIn = components["schemas"]["ZoneIn"];
export type ZonesUpdateResult = components["schemas"]["ZonesUpdateResult"];

export type QualityOut = components["schemas"]["QualityOut"];
export type FeaturesOut = components["schemas"]["FeaturesOut"];
export type DetectedObjectOut = components["schemas"]["DetectedObjectOut"];
export type DetectionFrameOut = components["schemas"]["DetectionFrameOut"];
export type LiveStateOut = components["schemas"]["LiveStateOut"];

export type VolumeOut = components["schemas"]["VolumeOut"];
export type ScheduleWorkOut = components["schemas"]["ScheduleWorkOut"];
export type ScheduleImportResult = components["schemas"]["ScheduleImportResult"];

export type WorkProgressOut = components["schemas"]["WorkProgressOut"];
export type GanttOut = components["schemas"]["GanttOut"];

export type UtilizationRowOut = components["schemas"]["UtilizationRowOut"];
export type EconomicsOut = components["schemas"]["EconomicsOut"];

export type PeriodOut = components["schemas"]["PeriodOut"];
export type ImpactOut = components["schemas"]["ImpactOut"];
export type EvidenceOut = components["schemas"]["EvidenceOut"];
export type DeviationOut = components["schemas"]["DeviationOut"];

export type EquipmentClass = string;
export type EquipmentState = "active" | "idle" | "parked" | "unknown";
export type DeviationType =
  | "R0_low_confidence"
  | "R1_resource_gap"
  | "R2_idle"
  | "R3_front_mismatch"
  | "R4_silence";
export type Severity = "low" | "medium" | "high";
export type GanttStatus = "green" | "yellow" | "red";
