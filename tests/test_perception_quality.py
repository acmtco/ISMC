import numpy as np

from services.perception.quality import assess_quality


def _solid_image(value: int, size: int = 200) -> np.ndarray:
    return np.full((size, size, 3), value, dtype=np.uint8)


def _checkerboard(size: int = 200, cell: int = 10, lo: int = 60, hi: int = 200) -> np.ndarray:
    img = np.zeros((size, size, 3), dtype=np.uint8)
    for row in range(0, size, cell):
        for col in range(0, size, cell):
            value = hi if ((row // cell) + (col // cell)) % 2 == 0 else lo
            img[row : row + cell, col : col + cell] = value
    return img


def test_bright_sharp_frame_scores_high():
    q = assess_quality(_checkerboard(lo=40, hi=220))
    assert q.night is False
    assert q.blur < 0.5
    assert q.score > 0.7


def test_dark_uniform_frame_is_flagged_night():
    q = assess_quality(_solid_image(20))
    assert q.night is True
    assert q.score < 0.7


def test_uniform_frame_has_high_blur_score():
    sharp = assess_quality(_checkerboard(lo=40, hi=220)).blur
    flat = assess_quality(_solid_image(150)).blur
    assert flat > sharp


def test_uniform_bright_frame_flagged_as_occluded():
    q = assess_quality(_solid_image(150))
    assert q.occlusion > 0.5
    assert q.score < 0.5


def test_quality_as_dict_matches_contract_keys():
    q = assess_quality(_checkerboard())
    assert set(q.as_dict()) == {"blur", "night", "occlusion", "score"}
