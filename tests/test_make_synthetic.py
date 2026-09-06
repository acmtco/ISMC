"""Покрытие scripts/make_synthetic.py на 3 сутки бенчмарка.

Проверяет то, что важно для честного ground truth (CLAUDE.md, правило 6):
формат кадров и JSONL по контракту (docs/02-data-contract.md), уважение
--days, и детерминированность по seed (иначе метрики в docs/04 не
воспроизводимы).
"""
import json
import re
from pathlib import Path

import pytest

from scripts.make_synthetic import generate
from scripts.synth.scenario import load_scenario

SCENARIO_PATH = Path("data/ref/scenario_demo.yaml")
FRAME_NAME_RE = re.compile(r"^\d{8}T\d{6}\.jpg$")


@pytest.fixture
def scenario_3days():
    return load_scenario(SCENARIO_PATH)


def _run(tmp_path: Path, scenario, days: int = 3):
    out_dir = tmp_path / "synthetic"
    benchmark_dir = tmp_path / "benchmark"
    sprites_dir = tmp_path / "sprites"
    frame_count = generate(scenario, days, sprites_dir, out_dir, benchmark_dir)
    return frame_count, out_dir, benchmark_dir


def test_generates_frames_and_ground_truth(tmp_path, scenario_3days):
    frame_count, out_dir, benchmark_dir = _run(tmp_path, scenario_3days, days=3)

    frames = sorted((out_dir / scenario_3days.camera_id).glob("*.jpg"))
    assert len(frames) == frame_count > 0
    for frame in frames:
        assert FRAME_NAME_RE.match(frame.name), frame.name

    gt_path = benchmark_dir / "ground_truth.jsonl"
    lines = gt_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == frame_count

    dates_seen = set()
    for line in lines:
        record = json.loads(line)
        assert record["camera_id"] == scenario_3days.camera_id
        assert set(record) == {"camera_id", "ts", "frame_uri", "quality", "objects"}
        assert set(record["quality"]) == {"blur", "night", "occlusion", "score"}
        dates_seen.add(record["ts"][:10])
        for obj in record["objects"]:
            assert set(obj) == {
                "track_id",
                "cls",
                "conf",
                "bbox",
                "zone_id",
                "state",
                "state_conf",
                "features",
            }
            assert obj["state"] in {"active", "idle", "parked"}
            assert len(obj["bbox"]) == 4

    # --days 3 должно строго ограничивать диапазон дат
    assert dates_seen == {"2026-09-08", "2026-09-09", "2026-09-10"}


def test_expected_deviations_present_and_valid(tmp_path, scenario_3days):
    _, _, benchmark_dir = _run(tmp_path, scenario_3days, days=3)

    dev_path = benchmark_dir / "expected_deviations.jsonl"
    lines = dev_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 1

    ids = set()
    for line in lines:
        record = json.loads(line)
        assert set(record) == {
            "deviation_id",
            "type",
            "work_id",
            "zone_id",
            "period",
            "severity",
            "params",
        }
        ids.add(record["deviation_id"])

    # INJ-0001 (R4_silence, 2026-09-08..09) пересекается с окном первых 3 суток
    assert "INJ-0001" in ids


def test_respects_days_argument(tmp_path, scenario_3days):
    frame_count_3, _, benchmark_dir_3 = _run(tmp_path / "a", scenario_3days, days=3)
    frame_count_1, _, _ = _run(tmp_path / "b", scenario_3days, days=1)

    assert frame_count_1 < frame_count_3
    assert frame_count_3 == frame_count_1 * 3


def test_deterministic_by_seed(tmp_path, scenario_3days):
    _, out_a, bench_a = _run(tmp_path / "run_a", scenario_3days, days=3)
    _, out_b, bench_b = _run(tmp_path / "run_b", scenario_3days, days=3)

    gt_a = (bench_a / "ground_truth.jsonl").read_text(encoding="utf-8").replace(str(out_a), "X")
    gt_b = (bench_b / "ground_truth.jsonl").read_text(encoding="utf-8").replace(str(out_b), "X")
    assert gt_a == gt_b

    dev_a = (bench_a / "expected_deviations.jsonl").read_text(encoding="utf-8")
    dev_b = (bench_b / "expected_deviations.jsonl").read_text(encoding="utf-8")
    assert dev_a == dev_b

    camera_id = scenario_3days.camera_id
    frame_name = sorted((out_a / camera_id).glob("*.jpg"))[0].name
    bytes_a = (out_a / camera_id / frame_name).read_bytes()
    bytes_b = (out_b / camera_id / frame_name).read_bytes()
    assert bytes_a == bytes_b


def test_no_network_access(tmp_path, scenario_3days, monkeypatch):
    import socket

    def _blocked(*args, **kwargs):
        raise AssertionError("генератор не должен обращаться к сети")

    monkeypatch.setattr(socket, "socket", _blocked)
    frame_count, _, _ = _run(tmp_path, scenario_3days, days=3)
    assert frame_count > 0
