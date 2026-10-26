"""Execution context shared by conversions and tools."""

import collections
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


class OperationError(Exception):
    """Failure whose message is shown to the user as is."""


class Cancelled(Exception):
    """The user cancelled the job."""


@dataclass
class Context:
    """Working directory, parameters, progress reporting and cancellation of one job."""

    workdir: Path
    params: dict = field(default_factory=dict)
    on_progress: Callable[[float], None] | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def progress(self, fraction: float) -> None:
        if self.on_progress:
            self.on_progress(max(0.0, min(1.0, fraction)))

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    def subdir(self, name: str) -> Path:
        path = self.workdir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def run(
        self,
        args: list[str],
        *,
        on_line: Callable[[str], None] | None = None,
        timeout: float | None = None,
        cwd: Path | None = None,
        env: dict | None = None,
        error_message: str | None = None,
    ) -> None:
        """Runs a subprocess, killing it when the job is cancelled or times out."""
        self.check_cancelled()
        process = subprocess.Popen(
            [str(arg) for arg in args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            errors="replace",
            cwd=cwd,
            env={**os.environ, **(env or {})},
        )
        stderr_tail = collections.deque(maxlen=40)

        def pump_stderr():
            for line in process.stderr:
                stderr_tail.append(line.rstrip())

        def pump_stdout():
            for line in process.stdout:
                if on_line:
                    on_line(line.rstrip())

        pumps = [
            threading.Thread(target=pump_stderr, daemon=True),
            threading.Thread(target=pump_stdout, daemon=True),
        ]
        for pump in pumps:
            pump.start()
        deadline = time.monotonic() + timeout if timeout else None
        while True:
            try:
                process.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if self.cancel_event.is_set():
                    process.kill()
                    process.wait()
                    raise Cancelled() from None
                if deadline and time.monotonic() > deadline:
                    process.kill()
                    process.wait()
                    raise OperationError("A operação demorou demais e foi interrompida.") from None
        for pump in pumps:
            pump.join(timeout=2)
        if process.returncode != 0:
            details = "\n".join(line for line in list(stderr_tail)[-6:] if line)
            message = error_message or f"{Path(args[0]).name} falhou"
            raise OperationError(f"{message}.\n{details}".strip())
