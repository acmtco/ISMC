/** Демо-данные — обязательный запасной путь, когда бэкенд недоступен
 * (docs/01-principles.md, правило 3: демо не имеет права упасть). Согласованы со
 * сценарием `data/ref/scenario_demo.yaml` и примером из
 * `docs/02-data-contract.md` (D-0007, W-014, Z-PIT). */
import type {
  DeviationOut,
  EconomicsOut,
  GanttOut,
  LiveStateOut,
  ObjectDetailOut,
  ObjectOut,
} from "./types";

export const DEMO_OBJECT_ID = "OBJ-001";

export const demoObjects: ObjectOut[] = [
  {
    object_id: DEMO_OBJECT_ID,
    name: "Жилой комплекс, корпус 3",
    address: "г. Москва, синтетический полигон",
    timezone: "Europe/Moscow",
  },
];

export const demoObjectDetail: ObjectDetailOut = {
  ...demoObjects[0],
  cameras: [
    {
      camera_id: "CAM-01",
      title: "Северный ракурс",
      source_kind: "replay",
      source_uri: "data/synthetic/CAM-01/",
      capture_interval_sec: 1200,
      zones: [
        {
          zone_id: "Z-PIT",
          title: "Котлован",
          polygon: [
            [60, 300],
            [560, 295],
            [600, 480],
            [40, 490],
          ],
          area_m2: 2400,
        },
        {
          zone_id: "Z-FRAME",
          title: "Каркас",
          polygon: [
            [620, 200],
            [930, 200],
            [930, 480],
            [620, 480],
          ],
          area_m2: 1600,
        },
      ],
    },
  ],
};

const QUALITY_OK = { blur: 0.12, night: false, occlusion: 0.03, score: 0.94 };

export const demoLiveState: LiveStateOut = {
  object_id: DEMO_OBJECT_ID,
  ts: new Date().toISOString(),
  cameras: [
    {
      camera_id: "CAM-01",
      ts: new Date().toISOString(),
      frame_uri: "data/synthetic/CAM-01/demo-frame.jpg",
      quality: QUALITY_OK,
      objects: [
        {
          track_id: 1,
          cls: "excavator",
          conf: 0.91,
          bbox: [120, 340, 90, 60],
          zone_id: "Z-PIT",
          state: "active",
          state_conf: 0.83,
          features: { centroid_mad: 4.7, area_mad: 311.0, flow_mag: 1.94, hsv_var: 480.0 },
        },
        {
          track_id: 2,
          cls: "dump_truck",
          conf: 0.88,
          bbox: [260, 380, 80, 50],
          zone_id: "Z-PIT",
          state: "idle",
          state_conf: 0.7,
          features: { centroid_mad: 0.8, area_mad: 20.0, flow_mag: 0.2, hsv_var: 90.0 },
        },
        {
          track_id: 3,
          cls: "tower_crane",
          conf: 0.95,
          bbox: [740, 210, 56, 220],
          zone_id: "Z-FRAME",
          state: "active",
          state_conf: 0.79,
          features: { centroid_mad: 5.4, area_mad: 260.0, flow_mag: 2.1, hsv_var: 510.0 },
        },
        {
          track_id: 4,
          cls: "mobile_crane",
          conf: 0.86,
          bbox: [720, 400, 80, 60],
          zone_id: "Z-FRAME",
          state: "parked",
          state_conf: 0.6,
          features: { centroid_mad: 0.1, area_mad: 2.0, flow_mag: 0.02, hsv_var: 30.0 },
        },
      ],
    },
  ],
};

export const demoGantt: GanttOut = {
  object_id: DEMO_OBJECT_ID,
  period: { from: "2026-09-01", to: "2026-09-30" },
  works: [
    {
      date: "2026-09-20",
      work_id: "W-014",
      name: "Разработка котлована",
      mh_plan_to_date: 92.0,
      mh_fact_to_date: 61.5,
      spi: 0.67,
      rate_mh_per_day: 12.3,
      forecast_finish: "2026-10-09",
      delay_days: 7,
      status: "red",
    },
    {
      date: "2026-09-20",
      work_id: "W-101",
      name: "Монтаж каркаса",
      mh_plan_to_date: 48.0,
      mh_fact_to_date: 45.1,
      spi: 0.94,
      rate_mh_per_day: 7.6,
      forecast_finish: "2026-10-21",
      delay_days: 1,
      status: "yellow",
    },
  ],
};

export const demoDeviations: DeviationOut[] = [
  {
    deviation_id: "D-0007",
    detected_at: "2026-09-20T19:05:00+03:00",
    period: { from: "2026-09-18", to: "2026-09-20" },
    work_id: "W-014",
    zone_id: "Z-PIT",
    type: "R1_resource_gap",
    severity: "high",
    observed: { excavator: 1, dump_truck: 2 },
    expected: { excavator: 2, dump_truck: 5 },
    impact: { spi: 0.67, delay_days: 7, idle_cost_rub: 0 },
    explanation:
      "Третьи сутки на котловане работает 1 экскаватор из 2 плановых и 2 самосвала из 5 " +
      "плановых. Фактический темп 12,3 маш.-ч/сут при плановых 18,4. При сохранении темпа " +
      "работа завершится 09.10 вместо 02.10.",
    recommendation: "Вывести на объект 1 экскаватор и 3 самосвала до 24.09 либо согласовать сдвиг срока.",
    evidence: {
      frames: ["data/replay/CAM-01/20260920T101000.jpg"],
      chart: "mh_plan_vs_fact",
      confidence: 0.88,
    },
    status: "open",
  },
  {
    deviation_id: "D-0008",
    detected_at: "2026-09-25T19:05:00+03:00",
    period: { from: "2026-09-25", to: "2026-09-27" },
    work_id: "W-014",
    zone_id: "Z-PIT",
    type: "R2_idle",
    severity: "medium",
    observed: { excavator: 12.4 },
    expected: {},
    impact: { spi: null, delay_days: null, idle_cost_rub: 31000 },
    explanation: "Экскаватор на котловане простаивает: КИТ 0.21 при присутствии 8.3 ч в сутки.",
    recommendation: "Проверить причину простоя техники в Z-PIT (ожидание фронта, поломка).",
    evidence: { frames: [], chart: "mh_plan_vs_fact", confidence: 0.91 },
    status: "open",
  },
  {
    deviation_id: "D-0009",
    detected_at: "2026-09-08T19:05:00+03:00",
    period: { from: "2026-09-08", to: "2026-09-09" },
    work_id: "W-101",
    zone_id: "Z-FRAME",
    type: "R4_silence",
    severity: "high",
    observed: {},
    expected: { tower_crane: 1 },
    impact: { spi: null, delay_days: null, idle_cost_rub: 0 },
    explanation: "По графику в Z-FRAME должна идти работа «Монтаж каркаса», но техника не зафиксирована 2 суток подряд.",
    recommendation: "Связаться с подрядчиком: подтвердить причину отсутствия техники в Z-FRAME.",
    evidence: { frames: [], chart: "mh_plan_vs_fact", confidence: 0.95 },
    status: "acted",
  },
  {
    deviation_id: "D-0010",
    detected_at: "2026-09-05T19:05:00+03:00",
    period: { from: "2026-09-05", to: "2026-09-05" },
    work_id: null,
    zone_id: "Z-PIT",
    type: "R0_low_confidence",
    severity: "low",
    observed: {},
    expected: {},
    impact: { spi: null, delay_days: null, idle_cost_rub: 0 },
    explanation: "Недостаточно данных по Z-PIT за 2026-09-05: низкое качество кадров (дождь).",
    recommendation: "Проверить камеру (объектив, освещение/ночная подсветка) для Z-PIT.",
    evidence: { frames: [], chart: "mh_plan_vs_fact", confidence: 0.31 },
    status: "open",
  },
];

export const demoEconomics: EconomicsOut = {
  object_id: DEMO_OBJECT_ID,
  period: { from: "2026-09-01", to: "2026-09-30" },
  currency: "RUB",
  total_idle_cost_rub: 510600,
  by_class: [
    { zone_id: "Z-PIT", cls: "excavator", mh_present: 210.0, mh_active: 138.0, mh_idle: 72.0, utilization: 0.66, idle_cost_rub: 180000 },
    { zone_id: "Z-PIT", cls: "dump_truck", mh_present: 340.0, mh_active: 298.0, mh_idle: 42.0, utilization: 0.88, idle_cost_rub: 75600 },
    { zone_id: "Z-FRAME", cls: "tower_crane", mh_present: 180.0, mh_active: 150.0, mh_idle: 30.0, utilization: 0.83, idle_cost_rub: 105000 },
    { zone_id: "Z-FRAME", cls: "mobile_crane", mh_present: 90.0, mh_active: 40.0, mh_idle: 50.0, utilization: 0.44, idle_cost_rub: 150000 },
  ],
};
