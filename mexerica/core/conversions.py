"""Registry of every source → target conversion and the engine that performs it."""

from pathlib import Path

from .context import Context, OperationError
from .engines import archives, documents, images, media, pdf, sheets, slides, subtitles
from .formats import FORMATS, detect_format

ENGINES = (images, media, pdf, documents, slides, sheets, subtitles, archives)


def _build() -> dict[str, dict[str, object]]:
    registry: dict[str, dict[str, object]] = {}
    for engine in ENGINES:
        for source, targets in engine.CONVERSIONS.items():
            for target in targets:
                registry.setdefault(source, {})[target] = engine
    return registry


REGISTRY = _build()


def total_conversions() -> int:
    return sum(len(targets) for targets in REGISTRY.values())


def targets_for(paths: list[Path]) -> list[str]:
    """Targets every selected file can be converted to, in the first file's order."""
    keys = []
    for path in paths:
        fmt = detect_format(path)
        if fmt is None or fmt.key not in REGISTRY:
            return []
        keys.append(fmt.key)
    common = list(REGISTRY[keys[0]])
    for key in keys[1:]:
        common = [target for target in common if target in REGISTRY[key]]
    return common


def target_label(target: str) -> str:
    return FORMATS[target].label


def convert(source: Path, target: str, ctx: Context) -> list[Path]:
    """Runs the conversion inside ctx.workdir and returns the produced files."""
    fmt = detect_format(source)
    if fmt is None or target not in REGISTRY.get(fmt.key, {}):
        label = FORMATS[target].label if target in FORMATS else target
        raise OperationError(f"Não há conversão de {source.name} para {label}.")
    engine = REGISTRY[fmt.key][target]
    return engine.convert(source, fmt.key, target, ctx)
