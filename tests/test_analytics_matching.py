from pathlib import Path

import pytest

from services.analytics.matching import (
    ClassRange,
    MatchingConfig,
    RhythmSpec,
    WorkSignature,
    best_competing_match,
    best_match,
    cover,
    excess,
    load_signatures,
    match_score,
    rhythm_score,
)

EXCAVATION = WorkSignature(
    work_type="earthworks_excavation",
    required={"excavator": ClassRange(min=1, typical=2)},
    supporting={"dump_truck": ClassRange(min=2, typical=5), "bulldozer": ClassRange(min=0, typical=1)},
    forbidden=["tower_crane"],
    rhythm=RhythmSpec(metric="dump_truck_cycles_per_shift", min=6, typical=12),
)

FRAME = WorkSignature(
    work_type="frame_assembly",
    required={"tower_crane": ClassRange(min=1, typical=1)},
    supporting={"mobile_crane": ClassRange(min=0, typical=1)},
    forbidden=["excavator", "bulldozer"],
    rhythm=None,
)

CONFIG = MatchingConfig(
    cover_weight=0.55, rhythm_weight=0.25, excess_weight=0.20, low_confidence_threshold=0.35, epsilon=1e-6
)


def test_cover_full_composition_is_one():
    observed = {"excavator": 2, "dump_truck": 5, "bulldozer": 1}
    assert cover(observed, EXCAVATION) == pytest.approx(1.0)


def test_cover_partial_composition_is_fractional():
    observed = {"excavator": 1, "dump_truck": 2}
    # (min(1,2) + min(2,5) + min(0,1)) / (2+5+1) = 3/8
    assert cover(observed, EXCAVATION) == pytest.approx(3 / 8)


def test_cover_empty_signature_is_zero():
    empty = WorkSignature(work_type="facade", required={}, supporting={}, forbidden=[], rhythm=None)
    assert cover({"excavator": 2}, empty) == 0.0


def test_excess_zero_when_no_forbidden_present():
    assert excess({"excavator": 2, "dump_truck": 5}, EXCAVATION, epsilon=1e-6) == pytest.approx(0.0)


def test_excess_high_when_forbidden_dominates():
    observed = {"tower_crane": 8}
    assert excess(observed, EXCAVATION, epsilon=1e-6) == pytest.approx(1.0, abs=1e-3)


def test_rhythm_score_perfect_match_is_one():
    assert rhythm_score(12.0, EXCAVATION) == pytest.approx(1.0)


def test_rhythm_score_degrades_with_distance():
    assert rhythm_score(6.0, EXCAVATION) == pytest.approx(0.5)


def test_rhythm_score_clips_at_zero():
    assert rhythm_score(100.0, EXCAVATION) == 0.0


def test_rhythm_score_neutral_when_no_spec_or_no_observation():
    assert rhythm_score(None, EXCAVATION) == 1.0
    assert rhythm_score(12.0, FRAME) == 1.0  # FRAME.rhythm is None


def test_match_score_full_match_scores_near_one():
    observed = {"excavator": 2, "dump_truck": 5, "bulldozer": 1}
    score = match_score(observed, EXCAVATION, CONFIG, observed_rhythm=12.0)
    assert score == pytest.approx(1.0, abs=1e-6)


def test_match_score_wrong_composition_scores_low():
    observed = {"tower_crane": 3}
    score = match_score(observed, EXCAVATION, CONFIG)
    assert score < 0.35


def test_best_match_picks_highest_scoring_work_type():
    observed = {"tower_crane": 1, "mobile_crane": 1}
    signatures = {"earthworks_excavation": EXCAVATION, "frame_assembly": FRAME}
    result = best_match(observed, list(signatures), signatures, CONFIG)
    assert result.work_type == "frame_assembly"


def test_best_match_returns_none_for_no_candidates():
    assert best_match({}, [], {}, CONFIG) is None


def test_best_competing_match_excludes_given_type():
    observed = {"tower_crane": 1, "mobile_crane": 1}
    signatures = {"earthworks_excavation": EXCAVATION, "frame_assembly": FRAME}
    result = best_competing_match(observed, "frame_assembly", signatures, CONFIG)
    assert result.work_type == "earthworks_excavation"


def test_load_signatures_from_ref_data():
    signatures = load_signatures(Path("data/ref/work_signatures.json"))
    assert "earthworks_excavation" in signatures
    assert "frame_assembly" in signatures
    sig = signatures["earthworks_excavation"]
    assert sig.required["excavator"].typical == 2
    assert "tower_crane" in sig.forbidden
    assert signatures["facade"].rhythm is None
