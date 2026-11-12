"""AST-backed JavaScript source inspection through the pinned Node toolchain."""

import json
import re
import subprocess
from functools import lru_cache

from worldascode.config import RESOURCE_ROOT, paths


@lru_cache(maxsize=128)
def _analyze(source, toolchain):
    # Binary transport preserves source offsets: text-mode stdin on Windows
    # expands LF to CRLF before the JavaScript parser sees it.
    result = subprocess.run(
        ["node", str(RESOURCE_ROOT / "javascript/analyze.mjs"), toolchain],
        input=source.encode("utf-8"),
        capture_output=True,
        timeout=30,
    )
    if result.returncode:
        raise ValueError(
            "JAVASCRIPT_ANALYSIS_FAILED: "
            + result.stderr.decode("utf-8", errors="replace")[-1600:]
        )
    return json.loads(result.stdout)


def analyze_source(source):
    return _analyze(source, str(paths().node_modules))


def method_blocks(source):
    # Acorn offsets count UTF-16 code units; Python strings count code points.
    encoded = source.encode("utf-16-le")
    return {
        name: encoded[item["start"] * 2 : item["end"] * 2].decode("utf-16-le")
        for name, item in analyze_source(source)["methods"].items()
    }


"""Focused service extracted from the reconstruction workflow."""


FORBIDDEN = re.compile(
    r"\b(?:import|require|fetch|XMLHttpRequest|WebSocket|eval|Function|localStorage|Worker|setTimeout|setInterval)\b|\b(?:document|window|globalThis|navigator)\s*[.\[]"
)


def lint(code):
    problems = []
    if not isinstance(code, str) or "export function design(" not in code:
        problems.append("Script must define `export function design(site, b, style)`.")
        return problems
    stripped = re.sub(r"//[^\n]*|/\*.*?\*/", "", code, flags=re.S).replace(
        "export function design(", "function design(", 1
    )
    found = sorted({m.strip(" .[") for m in FORBIDDEN.findall(stripped)})
    if found:
        problems.append("Not allowed in a design script: " + ", ".join(found))
    if len(code) > 30_000:
        problems.append("Script too long; use loops and kit parts.")
    return problems
