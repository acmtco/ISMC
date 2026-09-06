/** Бэкенд типизирует `type`/`severity`/`status`/`cls` как обычные `string` в
 * OpenAPI-схеме (FastAPI не объявляет их как enum) — поэтому здесь плоские
 * `Record<string, string>` со страховкой на неизвестное значение, а не
 * строгие объединения литералов. */

export const CLASS_LABELS: Record<string, string> = {
  excavator: "Экскаватор",
  dump_truck: "Самосвал",
  concrete_mixer: "Автобетоносмеситель",
  concrete_pump: "Бетононасос",
  tower_crane: "Башенный кран",
  mobile_crane: "Автокран",
  bulldozer: "Бульдозер",
  roller: "Каток",
  loader: "Погрузчик",
  drilling_rig: "Буровая установка",
};

export function classLabel(cls: string): string {
  return CLASS_LABELS[cls] ?? cls;
}

export const STATE_LABELS: Record<string, string> = {
  active: "работает",
  idle: "простаивает",
  parked: "на приколе",
  unknown: "не определено",
};

export function stateLabel(state: string): string {
  return STATE_LABELS[state] ?? state;
}

export const DEVIATION_TYPE_LABELS: Record<string, string> = {
  R0_low_confidence: "Нет данных",
  R1_resource_gap: "Ресурсный дефицит",
  R2_idle: "Простой",
  R3_front_mismatch: "Несоответствие фронта",
  R4_silence: "Тишина",
};

export function deviationTypeLabel(type: string): string {
  return DEVIATION_TYPE_LABELS[type] ?? type;
}

export const SEVERITY_LABELS: Record<string, string> = {
  low: "низкая",
  medium: "средняя",
  high: "высокая",
};

export function severityLabel(severity: string): string {
  return SEVERITY_LABELS[severity] ?? severity;
}

export const STATUS_LABELS: Record<string, string> = {
  green: "по графику",
  yellow: "риск отставания",
  red: "отставание",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}
