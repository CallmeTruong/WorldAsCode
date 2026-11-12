"""Bounded worker lifecycle for kit regression fixtures."""

import json
import subprocess
import sys
from pathlib import Path

import psutil

from worldascode.storage.artifacts import write_json


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def regressions(kit, folder, exercise=None):
    command = [
        sys.executable,
        "-m",
        "worldascode.quality.kit_regression",
        "--kit",
        str(kit),
        "--out",
        str(folder),
    ]
    if exercise:
        command += ["--exercise", str(exercise)]
    process = subprocess.Popen(
        command,
        # Inherit the caller's cwd so an automatically discovered TOML remains
        # visible; installed resources must never become a worker workspace.
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        stdout, stderr = process.communicate(timeout=240)
    except subprocess.TimeoutExpired:
        parent = psutil.Process(process.pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        process.kill()
        stdout, stderr = process.communicate()
        result = [{"passed": False, "error": "KIT_REGRESSION_WALL_TIME_LIMIT"}]
    else:
        report = folder / "result.json"
        # Exit 2 means completed negative checks, not a crashed worker. Preserve
        # per-case diagnostics so the next developer can correct the actual bug.
        result = (
            read(report)["cases"]
            if report.exists() and process.returncode in (0, 2)
            else [{"passed": False, "error": stderr[-1800:]}]
        )
    write_json(
        folder / "worker.json",
        {
            "exit_code": process.returncode,
            "stdout": stdout[-4000:],
            "stderr": stderr[-4000:],
        },
    )
    return result
