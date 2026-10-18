import sys
import traceback
from typing import Callable, Any, Optional
from PyQt6.QtCore import QThread, pyqtSignal


class WorkerThread(QThread):
    """Reusable QThread worker for executing heavy background tasks asynchronously."""

    started_task = pyqtSignal()
    finished_task = pyqtSignal(object)
    failed_task = pyqtSignal(str)
    progress = pyqtSignal(int, str)

    def __init__(self, func: Callable, *args: Any, **kwargs: Any):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.result: Optional[Any] = None

    def run(self) -> None:
        self.started_task.emit()
        try:
            # If function accepts progress_callback, pass it
            def emit_progress(pct: int, msg: str) -> None:
                self.progress.emit(pct, msg)

            if "progress_callback" in self.kwargs:
                self.kwargs["progress_callback"] = emit_progress
            elif hasattr(self.func, "__code__") and "progress_callback" in self.func.__code__.co_varnames:
                self.kwargs["progress_callback"] = emit_progress

            self.result = self.func(*self.args, **self.kwargs)
            self.finished_task.emit(self.result)
        except Exception as exc:
            traceback.print_exc()
            self.failed_task.emit(str(exc))
        finally:
            import gc
            gc.collect()