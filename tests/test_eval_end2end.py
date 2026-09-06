from pathlib import Path

import pytest

from scripts import eval_end2end


@pytest.fixture
def small_run(tmp_path):
    # относительные config/data пути ниже разрешаются от рабочей директории
    # репозитория, откуда pytest и запускается (см. pyproject.toml)
    out = tmp_path / "metrics.md"
    img_dir = tmp_path / "img"
    argv = [
        "--scenario",
        "data/ref/scenario_demo.yaml",
        "--benchmark-dir",
        str(tmp_path / "bench"),
        "--frames-dir",
        str(tmp_path / "frames"),
        "--sprites-dir",
        str(tmp_path / "sprites"),
        "--days",
        "5",
        "--out",
        str(out),
        "--img-dir",
        str(img_dir),
    ]
    eval_end2end.main(argv)
    return out, img_dir


def test_main_generates_benchmark_when_missing_and_writes_report(small_run):
    out, img_dir = small_run
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "# Метрики качества" in content
    assert "## 1. Детекция техники" in content
    assert "## 5. Выявление отклонений" in content
    assert (img_dir / "state_confusion_matrix.png").exists()
    assert (img_dir / "mh_active_predicted_vs_truth.png").exists()
    assert (img_dir / "deviation_precision_recall.png").exists()


def test_main_reports_missing_detector_weights_honestly(small_run):
    out, _ = small_run
    content = out.read_text(encoding="utf-8")
    assert "нет в репозитории" in content
    assert "MOTA | — |" in content


def test_ensure_benchmark_skips_when_already_generated(tmp_path):
    benchmark_dir = tmp_path / "bench"
    benchmark_dir.mkdir()
    (benchmark_dir / "ground_truth.jsonl").write_text('{"already": "here"}\n', encoding="utf-8")

    # days=None и валидный сценарий, но т.к. файл уже существует, генерация не
    # должна запускаться (иначе перезаписала бы файл валидным содержимым)
    eval_end2end._ensure_benchmark(
        Path("data/ref/scenario_demo.yaml"), benchmark_dir, tmp_path / "sprites", tmp_path / "frames", None
    )
    content = (benchmark_dir / "ground_truth.jsonl").read_text(encoding="utf-8")
    assert content == '{"already": "here"}\n'
