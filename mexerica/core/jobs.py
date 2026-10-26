"""Runs conversions and tools in a scratch folder and moves the results next to the source."""

import shutil
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from . import conversions
from .context import Context
from .formats import FORMATS
from .paths import cache_dir, output_dir_for, place_results


@contextmanager
def work_context(params=None, on_progress=None, cancel_event=None):
    """Scratch folder on the home disk (not tmpfs), removed when the job ends."""
    root = cache_dir() / "work"
    root.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="job-", dir=root))
    try:
        yield Context(
            workdir=workdir,
            params=dict(params or {}),
            on_progress=on_progress,
            cancel_event=cancel_event or threading.Event(),
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_conversion(
    source: Path,
    target: str,
    *,
    output_dir: str | None = None,
    on_progress: Callable[[float], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
    with work_context(on_progress=on_progress, cancel_event=cancel_event) as ctx:
        produced = conversions.convert(source, target, ctx)
        ctx.check_cancelled()
        return place_results(
            produced,
            source,
            output_dir_for(source, output_dir),
            folder_label=FORMATS[target].label,
        )


def run_tool(
    tool,
    sources: list[Path],
    params: dict,
    *,
    output_dir: str | None = None,
    on_progress: Callable[[float], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
    """Runs a tool once over all sources (merge-like tools) or once per source."""
    batches = [sources] if tool.multi else [[source] for source in sources]
    results: list[Path] = []
    for index, batch in enumerate(batches):

        def batch_progress(fraction, index=index):
            if on_progress:
                on_progress((index + fraction) / len(batches))

        with work_context(params, batch_progress, cancel_event) as ctx:
            produced = tool.run(batch, ctx)
            ctx.check_cancelled()
            results += place_results(
                produced,
                tool.name_source(batch),
                output_dir_for(batch[0], output_dir),
                suffix=tool.suffix,
            )
    return results
