"""Execution, quality and selection describe separate axes of a run."""

import traceback
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class RunOutcome(BaseModel):
    execution_status: Literal["completed", "failed", "interrupted"]
    quality_status: Literal["accepted", "rejected", "unreviewed"]
    selection_status: Literal["retained", "none"] = "none"

    @classmethod
    def from_legacy(cls, record):
        status = record.get("status", "")
        interrupted = record.get("evaluation_complete") is False or status in {
            "incomplete-run-retained",
            "kit-evolution-blocked",
        }
        failed = status in {"no-buildable-design", "baseline-failed"}
        execution = (
            "interrupted" if interrupted else "failed" if failed else "completed"
        )
        reviewed = execution == "completed"
        return cls(
            execution_status=execution,
            quality_status=("accepted" if record.get("accepted") else "rejected")
            if reviewed
            else "unreviewed",
            selection_status="retained"
            if record.get("best_attempt") is not None or record.get("selected_render")
            else "none",
        )

    def exit_code(self, require_quality=False):
        return (
            0
            if self.execution_status == "completed"
            and (not require_quality or self.quality_status == "accepted")
            else 2
        )


def normalize_result(record):
    return {**record, **RunOutcome.from_legacy(record).model_dump()}


"""Serializable failures retain their cause without hiding programmer errors."""


class FailureRecord(BaseModel):
    category: str
    code: str
    message: str
    traceback_artifact: str
    retry_allowed: bool = False


def record_failure(folder, error):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    artifact = folder / "failure-traceback.txt"
    artifact.write_text("".join(traceback.format_exception(error)), encoding="utf-8")
    message = str(error)
    category = (
        "provider"
        if any(
            key in message for key in ("PROVIDER", "HTTP_", "MODEL_BUDGET", "STREAM_")
        )
        else "input"
        if isinstance(error, (ValueError, FileNotFoundError))
        else "runtime"
        if isinstance(error, RuntimeError)
        else "programming"
    )
    return FailureRecord(
        category=category,
        code=message.split(":", 1)[0] or type(error).__name__,
        message=message,
        traceback_artifact=artifact.name,
    )
