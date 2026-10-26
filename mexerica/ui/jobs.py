"""Background jobs with progress, cancellation and results, observable from GTK."""

import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib, GObject  # noqa: E402

from ..core.context import Cancelled, OperationError  # noqa: E402

Work = Callable[[Callable[[float], None], threading.Event], list[Path]]


class JobItem(GObject.Object):
    __gtype_name__ = "MexericaJob"

    title = GObject.Property(type=str, default="")
    status = GObject.Property(type=str, default="Na fila")
    progress = GObject.Property(type=float, default=0.0)
    state = GObject.Property(type=str, default="queued")  # queued|running|done|failed|cancelled

    def __init__(self, title: str):
        super().__init__(title=title)
        self.results: list[Path] = []
        self.error = ""
        self.cancel_event = threading.Event()
        self.started_at = 0.0

    @property
    def finished(self) -> bool:
        return self.state in ("done", "failed", "cancelled")

    def cancel(self) -> None:
        self.cancel_event.set()
        if self.state == "queued":
            self._finish("cancelled", "Cancelado")

    def _finish(self, state: str, status: str) -> None:
        self.state = state
        self.status = status


class JobManager(GObject.Object):
    __gtype_name__ = "MexericaJobManager"
    __gsignals__ = {
        "job-started": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "job-finished": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, workers: int = 2):
        super().__init__()
        self.store = Gio.ListStore.new(JobItem)
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="mexerica-job")

    @property
    def running(self) -> int:
        return sum(1 for job in self.store if not job.finished)

    def submit(self, title: str, work: Work) -> JobItem:
        job = JobItem(title)
        self.store.insert(0, job)
        self._executor.submit(self._run, job, work)
        return job

    def clear_finished(self) -> None:
        for index in reversed(range(self.store.get_n_items())):
            if self.store.get_item(index).finished:
                self.store.remove(index)

    def _run(self, job: JobItem, work: Work) -> None:
        if job.cancel_event.is_set():
            return
        last_report = [0.0]

        def on_progress(fraction: float) -> None:
            now = time.monotonic()
            if now - last_report[0] >= 0.1 or fraction >= 1.0:
                last_report[0] = now
                GLib.idle_add(self._set_progress, job, fraction)

        GLib.idle_add(self._started, job)
        try:
            results = work(on_progress, job.cancel_event)
            GLib.idle_add(self._done, job, results)
        except Cancelled:
            GLib.idle_add(self._failed, job, "cancelled", "")
        except OperationError as error:
            GLib.idle_add(self._failed, job, "failed", str(error))
        except Exception as error:  # noqa: BLE001 - surfaced to the user, logged for debugging
            traceback.print_exc()
            GLib.idle_add(self._failed, job, "failed", f"Erro inesperado: {error}")

    def _started(self, job: JobItem) -> bool:
        job.state = "running"
        job.status = "Processando…"
        job.started_at = time.monotonic()
        self.emit("job-started", job)
        return GLib.SOURCE_REMOVE

    def _set_progress(self, job: JobItem, fraction: float) -> bool:
        if job.state == "running":
            job.progress = fraction
            job.status = f"{round(fraction * 100)}%"
        return GLib.SOURCE_REMOVE

    def _done(self, job: JobItem, results: list[Path]) -> bool:
        job.results = results
        job.progress = 1.0
        names = ", ".join(path.name for path in results[:3]) + ("…" if len(results) > 3 else "")
        job._finish("done", names or "Concluído")
        self.emit("job-finished", job)
        return GLib.SOURCE_REMOVE

    def _failed(self, job: JobItem, state: str, message: str) -> bool:
        job.error = message
        job._finish(state, "Cancelado" if state == "cancelled" else message.splitlines()[0])
        self.emit("job-finished", job)
        return GLib.SOURCE_REMOVE
