from datetime import timedelta, timezone

import numpy as np
import pytest
from PIL import Image

from services.perception.source import FolderSource, ReplaySource, open_source

MSK = timezone(timedelta(hours=3))


def _write_frame(dir_path, ts: str) -> None:
    img = Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8))
    img.save(dir_path / f"{ts}.jpg")


def test_folder_source_yields_frames_in_chronological_order(tmp_path):
    _write_frame(tmp_path, "20260910T090000")
    _write_frame(tmp_path, "20260908T070000")
    _write_frame(tmp_path, "20260909T120000")

    frames = list(FolderSource(tmp_path).iter_frames())

    assert [f.ts.isoformat() for f in frames] == [
        "2026-09-08T07:00:00+03:00",
        "2026-09-09T12:00:00+03:00",
        "2026-09-10T09:00:00+03:00",
    ]
    assert frames[0].image.shape == (8, 8, 3)
    assert frames[0].uri.endswith("20260908T070000.jpg")


def test_replay_source_paces_by_speed(tmp_path, monkeypatch):
    _write_frame(tmp_path, "20260908T070000")
    _write_frame(tmp_path, "20260908T070100")  # +60s

    sleeps = []
    monkeypatch.setattr("services.perception.source.time.sleep", lambda s: sleeps.append(s))

    frames = list(ReplaySource(tmp_path, speed=60).iter_frames())

    assert len(frames) == 2
    assert sleeps == [1.0]  # 60 реальных секунд / speed=60 -> 1 секунда паузы


def test_replay_source_without_speed_does_not_sleep(tmp_path, monkeypatch):
    _write_frame(tmp_path, "20260908T070000")
    _write_frame(tmp_path, "20260908T070100")

    monkeypatch.setattr(
        "services.perception.source.time.sleep",
        lambda s: (_ for _ in ()).throw(AssertionError("не должно вызываться")),
    )

    frames = list(ReplaySource(tmp_path, speed=None).iter_frames())
    assert len(frames) == 2


def test_open_source_dispatches_by_kind(tmp_path):
    folder_src = open_source({"kind": "folder", "uri": str(tmp_path)})
    assert isinstance(folder_src, FolderSource)

    replay_src = open_source({"kind": "replay", "uri": str(tmp_path)}, replay_speed=30)
    assert isinstance(replay_src, ReplaySource)
    assert replay_src.speed == 30


def test_open_source_rejects_unknown_kind():
    with pytest.raises(ValueError, match="неизвестный тип"):
        open_source({"kind": "carrier-pigeon", "uri": "n/a"})
