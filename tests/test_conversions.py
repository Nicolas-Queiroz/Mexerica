"""Every registered conversion runs on a real sample and yields a readable file."""

from pathlib import Path

import pytest

from mexerica.core import conversions, jobs
from mexerica.core.formats import FORMATS

from . import samples, validate

CASES = [
    (source, target)
    for source, targets in conversions.REGISTRY.items()
    for target in targets
    if source not in samples.UNAVAILABLE
]


@pytest.fixture(scope="session")
def sample_files(tmp_path_factory) -> dict[str, Path]:
    return samples.build(tmp_path_factory.mktemp("samples"))


def test_registry_covers_formats():
    assert conversions.total_conversions() >= 275
    for source in conversions.REGISTRY:
        assert source in FORMATS
        for target in conversions.REGISTRY[source]:
            assert target in FORMATS and target != source


@pytest.mark.parametrize(("source", "target"), CASES, ids=[f"{s}-to-{t}" for s, t in CASES])
def test_conversion(source, target, sample_files, tmp_path):
    progress = []
    results = jobs.run_conversion(
        sample_files[source], target, output_dir=str(tmp_path), on_progress=progress.append
    )
    assert len(results) == 1
    validate.check(results[0], target)


def test_results_never_overwrite(sample_files, tmp_path):
    first = jobs.run_conversion(sample_files["png"], "jpg", output_dir=str(tmp_path))[0]
    second = jobs.run_conversion(sample_files["png"], "jpg", output_dir=str(tmp_path))[0]
    assert first.name == "imagem.jpg"
    assert second.name == "imagem (2).jpg"


def test_multi_page_pdf_to_images_lands_in_folder(sample_files, tmp_path):
    result = jobs.run_conversion(sample_files["pdf"], "png", output_dir=str(tmp_path))[0]
    assert result.is_dir() and result.name == "documento (PNG)"
    assert sorted(path.name for path in result.iterdir()) == ["documento-1.png", "documento-2.png"]


def test_targets_for_mixed_selection(sample_files):
    assert conversions.targets_for([sample_files["png"], sample_files["jpg"]]) == [
        "webp", "heic", "tiff", "avif", "bmp", "pdf",
    ]
    assert conversions.targets_for([sample_files["png"], sample_files["mp3"]]) == []
