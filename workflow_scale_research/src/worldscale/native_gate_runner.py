"""Subprocess boundary for upstream modules that expose functions but no CLI."""

import json
import sys
from pathlib import Path


def main():
    upstream, kind, input_file, output_file = sys.argv[1:]
    review = Path(upstream) / "forge/stage4_review"
    sys.path.insert(0, str(review))
    payload = json.loads(Path(input_file).read_text(encoding="utf-8"))
    if kind == "geometry":
        from geometry_integrity import measure_geometry_integrity

        result = measure_geometry_integrity(payload)
    elif kind == "loop":
        from correction_loop import decide

        result = decide(payload)
    else:
        raise ValueError("UNKNOWN_NATIVE_FUNCTION_GATE")
    Path(output_file).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "kind": kind,
                "passed": result.get("passed"),
                "action": result.get("action"),
                "stop": result.get("stop"),
            }
        )
    )
    return 0 if result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
