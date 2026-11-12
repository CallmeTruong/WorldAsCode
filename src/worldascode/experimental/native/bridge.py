"""Execute the pinned skill's real state/spec/pass tools; do not emulate their verdicts."""

import json
import subprocess
import sys
import time
from pathlib import Path

from worldascode.config import paths
from worldascode.storage.artifacts import Ledger, file_hash, write_json

CONTRACTS = [
    "SKILL.md",
    "forge/state.py",
    "forge/next.py",
    "forge/stage2_spec/new_pre_spec_assessment.py",
    "forge/stage2_spec/new_sculpt_spec.py",
    "forge/stage2_spec/validate_sculpt_spec.py",
    "forge/stage3_build/generate_threejs_factory.py",
    "forge/stage3_build/orchestrate_passes.py",
    "forge/stage4_review/append_review.py",
    "forge/stage4_review/diagnose_render.py",
    "forge/stage4_review/check_part_coverage.py",
]
CONTEXTS = {
    "observe": [
        "grimoire/intake/image_analysis.md",
        "grimoire/intake/validation_rubric.md",
        "grimoire/intake/quality_contract.md",
        "grimoire/intake/detail_inventory.md",
        "grimoire/intake/surface_topology.md",
        "grimoire/intake/local_spec_search.md",
    ],
    "spec": [
        "grimoire/intake/quality_contract.md",
        "grimoire/intake/detail_inventory.md",
        "grimoire/intake/surface_topology.md",
        "grimoire/build/geometry_patterns.md",
    ],
    "review": [
        "grimoire/review/gates_reference.md",
        "grimoire/review/self_correction.md",
        "grimoire/feedback/shading_realism.md",
    ],
}


def pin_upstream(path):
    path = Path(path).resolve()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    files = set(CONTRACTS)
    for docs in CONTEXTS.values():
        files.update(docs)
    files.update(
        [
            "forge/stage4_review/geometry_integrity.py",
            "forge/stage4_review/correction_loop.py",
            "forge/stage4_review/attachment_anchor.py",
            "forge/stage4_review/divine_eye.py",
            "forge/stage4_review/interior_difference.py",
            "forge/stage4_review/diagnose_render_multi_angle.py",
            "forge/stage3_build/emit_target.py",
            "forge/stage3_build/run_gates.py",
        ]
    )
    lock = {
        "path": str(path),
        "relative_to": "workspace",
        "commit": commit,
        "contracts": {f: file_hash(path / f) for f in sorted(files)},
    }
    write_json(paths().data_dir / "upstream.lock.json", lock)
    return lock


class NativeBlocked(RuntimeError):
    pass


class NativeBridge:
    def __init__(self, run):
        self.run = Path(run).resolve()
        self.run.mkdir(parents=True, exist_ok=True)
        self.logs = self.run / "native"
        self.logs.mkdir(exist_ok=True)
        self.ledger = Ledger(self.run / "ledger.sqlite")
        lock_path = paths().data_dir / "upstream.lock.json"
        if not lock_path.is_file():
            raise NativeBlocked(
                "UPSTREAM_NOT_CONFIGURED: run worldascode native-pin --path <checkout>"
            )
        self.lock = json.loads(lock_path.read_text())
        self.upstream = Path(self.lock["path"]).resolve()
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.upstream,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if commit != self.lock["commit"] or any(
            file_hash(self.upstream / f) != h for f, h in self.lock["contracts"].items()
        ):
            raise NativeBlocked("UPSTREAM_PIN_MISMATCH")
        dirty = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--"],
            cwd=self.upstream,
            capture_output=True,
        )
        if dirty.returncode:
            raise NativeBlocked("UPSTREAM_TRACKED_FILES_CHANGED")

    def context(self, stage):
        return "\n\n".join(
            "CONTRACT " + p + "\n" + (self.upstream / p).read_text(encoding="utf-8")
            for p in CONTEXTS[stage]
        )

    def function_gate(self, kind, input_file, output_file):
        if kind not in ("geometry", "loop"):
            raise ValueError("UNKNOWN_NATIVE_FUNCTION_GATE")
        runner = Path(__file__).with_name("gates.py")
        r = subprocess.run(
            [
                sys.executable,
                str(runner),
                str(self.upstream),
                kind,
                str(input_file),
                str(output_file),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        record = {
            "kind": kind,
            "exit_code": r.returncode,
            "stdout": r.stdout,
            "stderr": r.stderr,
            "input_sha256": file_hash(input_file),
            "adapter_sha256": file_hash(runner),
            "commit": self.lock["commit"],
        }
        write_json(self.logs / f"{time.time_ns()}-{kind}.json", record)
        return record

    def command(self, script, args=(), check=True, timeout=120):
        target = (self.upstream / script).resolve()
        if not target.is_relative_to(self.upstream / "forge") or target.suffix != ".py":
            raise ValueError("UNTRUSTED_NATIVE_COMMAND")
        started = time.monotonic()
        result = subprocess.run(
            [sys.executable, str(target), *[str(a) for a in args]],
            cwd=self.upstream,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        record = {
            "script": script,
            "args": [str(a) for a in args],
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "seconds": time.monotonic() - started,
            "script_sha256": file_hash(target),
            "commit": self.lock["commit"],
        }
        write_json(self.logs / f"{time.time_ns()}-{target.stem}.json", record)
        self.ledger.event(
            target.stem,
            "passed" if result.returncode == 0 else "blocked",
            exit_code=result.returncode,
        )
        if check and result.returncode:
            raise NativeBlocked(
                script + ": " + (result.stderr or result.stdout)[-5000:]
            )
        return record

    def init(self, reference, max_per_pass=6, max_total=18):
        self.state = self.run / ".img2threejs/state.json"
        self.spec = self.run / "object-sculpt-spec.json"
        if not self.state.exists():
            self.command(
                "forge/state.py",
                [
                    "init",
                    "--state",
                    self.state,
                    "--reference",
                    Path(reference).resolve(),
                    "--profile",
                    "generic",
                    "--spec",
                    self.spec,
                    "--max-per-pass",
                    str(max_per_pass),
                    "--max-total",
                    str(max_total),
                ],
            )
        return self.next()

    def next(self):
        result = self.command(
            "forge/next.py",
            ["--state", self.run / ".img2threejs/state.json"],
            check=False,
        )
        if result["exit_code"] == 3:
            raise NativeBlocked("NATIVE_HARD_STOP: " + result["stdout"])
        if result["exit_code"] not in (0,):
            raise NativeBlocked(result["stderr"] or result["stdout"])
        return result

    def mark(self, step, evidence, status="done", reason=None):
        state_path = self.run / ".img2threejs/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("status") == "stopped":
            raise NativeBlocked("NATIVE_HARD_STOP")
        existing = next((e for e in state["checklist"] if e["id"] == step), None)
        if (
            existing
            and existing["status"] == status
            and {str(Path(p).resolve()) for p in existing.get("evidence", [])}
            == {str(Path(p).resolve()) for p in evidence}
        ):
            if any(not Path(p).is_file() for p in evidence):
                raise NativeBlocked("RESUME_EVIDENCE_MISSING")
            self.ledger.event(
                step,
                "reused",
                evidence=[{"path": str(p), "sha256": file_hash(p)} for p in evidence],
            )
            return {"reused": True, "exit_code": 0}
        args = [
            "mark",
            step,
            "--state",
            self.run / ".img2threejs/state.json",
            "--status",
            status,
        ]
        for p in evidence:
            if not Path(p).is_file():
                raise ValueError("MISSING_STEP_EVIDENCE")
            args += ["--evidence", Path(p).resolve()]
        if reason:
            args += ["--reason", reason]
        return self.command("forge/state.py", args)

    def strict(self, strict_quality=True):
        args = [self.run / "object-sculpt-spec.json"]
        if strict_quality:
            args.append("--strict-quality")
        args.append("--json")
        return self.command(
            "forge/stage2_spec/validate_sculpt_spec.py",
            args,
            check=False,
        )

    def generate(self, pass_id, out):
        self.next()
        # Strict-quality warnings are carried as explicit approximation risks by
        # workflow.strict_repair; generation still requires a clean structural schema.
        gate = self.strict(strict_quality=False)
        if gate["exit_code"]:
            raise NativeBlocked(
                "NATIVE_STRICT_SPEC_FAILED: " + gate["stdout"] + gate["stderr"]
            )
        try:
            return self.command(
                "forge/stage3_build/generate_threejs_factory.py",
                [
                    self.run / "object-sculpt-spec.json",
                    "--pass-id",
                    pass_id,
                    "--out",
                    Path(out).resolve(),
                    "--force",
                ],
            )
        except NativeBlocked as exc:
            raise NativeBlocked("NATIVE_STRICT_SPEC_FAILED: " + str(exc)) from exc

    def status(self):
        return self.command(
            "forge/stage3_build/orchestrate_passes.py",
            ["status", self.run / "object-sculpt-spec.json", "--json"],
            check=False,
        )

    def check_pass(self, pass_id):
        return self.command(
            "forge/stage3_build/orchestrate_passes.py",
            [
                "check",
                self.run / "object-sculpt-spec.json",
                "--pass-id",
                pass_id,
                "--json",
            ],
            check=False,
        )

    def append_review(self, pass_id, review, render, comparison, features, layers):
        if review["action"] not in (
            "continue",
            "refine-spec",
            "refine-code",
            "request-input",
            "stop",
        ):
            raise ValueError("INVALID_NATIVE_REVIEW_ACTION")
        for path in (render, comparison, features, layers):
            if not Path(path).is_file():
                raise ValueError("REVIEW_EVIDENCE_MISSING")
        self.next()
        return self.command(
            "forge/stage4_review/append_review.py",
            [
                self.run / "object-sculpt-spec.json",
                "--pass-id",
                pass_id,
                "--fidelity",
                str(review["score"]),
                "--action",
                review["action"],
                "--summary",
                review["summary"],
                "--render-screenshot",
                render,
                "--comparison-image",
                comparison,
                "--ai-vision-score",
                str(review["score"]),
                "--feature-reviews-json",
                features,
                "--layer-scores-json",
                layers,
                "--in-place",
            ],
            check=False,
        )
