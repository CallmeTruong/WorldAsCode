"""ReleaseValidator: isolated kit-library responsibility."""

import re
import uuid
from pathlib import Path

from worldascode.kits.registry import package_files, read
from worldascode.storage.artifacts import digest, file_hash, write_json


class ReleaseValidator:
    def __init__(self, registry):
        self.registry = registry
        self.root = registry.root

    def _submission_hashes(self, folder):
        paths = [*Path(folder).glob("runtime/**/*"), *Path(folder).glob("*.json")]
        return {
            p.relative_to(folder).as_posix(): file_hash(p)
            for p in paths
            if p.is_file() and p.name not in {"submission.json", "validation.json"}
        }

    def validate(self, submission_id, heldout_runs=()):
        if not re.fullmatch(r"[a-f0-9]{64}", submission_id):
            raise ValueError("INVALID_KIT_SUBMISSION_ID")
        folder = self.root / "submissions" / submission_id
        submission = read(folder / "submission.json")
        if self._submission_hashes(folder) != submission["input_hashes"]:
            raise ValueError("KIT_SUBMISSION_CHANGED")
        # Re-run tests in a worker against the frozen submitted code. Historical
        # passed booleans are not enough to publish shared executable code.
        from worldascode.execution.regression_worker import regressions
        from worldascode.kits.evolution import apply_proposal

        base = None
        package = submission["package"]
        for release in (self.root / "releases" / package).glob("*/release.json"):
            if read(release)["files"]["kit.mjs"] == submission["base_sha256"]:
                base = (
                    self.registry.verify_release(package, release.parent.name)[0]
                    / "kit.mjs"
                )
                break
        if base is None:
            raise ValueError("KIT_SUBMISSION_BASE_NOT_IN_LIBRARY")
        permissions = read(folder / "permissions.json")
        reconstructed, _ = apply_proposal(
            base.read_text(encoding="utf-8"),
            read(folder / "proposal.json"),
            permissions["granted_methods"],
        )
        if digest(reconstructed) != digest(
            (folder / "runtime/kit.mjs").read_text(encoding="utf-8")
        ):
            raise ValueError("KIT_SUBMISSION_PATCH_MISMATCH")
        for dep in package_files(folder / "runtime"):
            if (
                dep.suffix == ".mjs"
                and dep.name != "kit.mjs"
                and file_hash(dep) != file_hash(base.parent / dep.name)
            ):
                raise ValueError("KIT_PROTECTED_DEPENDENCY_CHANGED")
        validation_id = uuid.uuid4().hex
        checks = folder / "checks" / validation_id
        compatibility = regressions(
            folder / "runtime/kit.mjs", checks / "compatibility"
        )
        capability = regressions(
            folder / "runtime/kit.mjs", checks / "capability", folder / "exercise.json"
        )
        sites = []
        for run in map(Path, heldout_runs):
            result = read(run / "result.json")
            index = result.get("best_attempt")
            if index is None:
                continue
            attempt = run / f"attempt-{index}"
            metrics = read(attempt / "metrics.json")
            review = read(attempt / "review.json")
            from worldascode.quality.evaluation import ACCEPT, validated_scores

            scores = validated_scores(review)
            kit_manifest = read(run / "input-manifest.json")
            pinned = run / "kit-versions/base/kit.mjs"
            render_path = attempt / "render-manifest.json"
            render = read(render_path) if render_path.exists() else {}
            selection_path = attempt / "selected-runtime/selection.json"
            selection = read(selection_path) if selection_path.exists() else {}
            correct_kit = (
                kit_manifest.get("kit_sha256") == submission["candidate_sha256"]
                and pinned.is_file()
                and file_hash(pinned) == submission["candidate_sha256"]
                and selection.get("master_sha256") == submission["candidate_sha256"]
            )
            real_render = (
                render.get("passed") is True
                and (attempt / "bundle.js").is_file()
                and render.get("bundle_sha256") == file_hash(attempt / "bundle.js")
            )
            accepted = (
                correct_kit
                and real_render
                and result.get("accepted") is True
                and result.get("evaluation_complete", True)
                and metrics["passed"]
                and all(scores[k] >= v for k, v in ACCEPT.items())
            )
            sites.append(
                {
                    "object_id": result.get("object_id"),
                    "accepted": accepted,
                    "evidence_sha256": result.get("evidence_sha256"),
                    "correct_kit": correct_kit,
                    "real_render_verified": real_render,
                    "run": str(run.resolve()),
                    "artifacts": {
                        str(p.resolve()): file_hash(p)
                        for p in [
                            run / "result.json",
                            run / "input-manifest.json",
                            attempt / "review.json",
                            attempt / "metrics.json",
                            render_path,
                            attempt / "bundle.js",
                            selection_path,
                            pinned,
                        ]
                        if p.is_file()
                    },
                    "review_sha256": file_hash(attempt / "review.json"),
                    "metrics_sha256": file_hash(attempt / "metrics.json"),
                }
            )
        policy = read(self.root / "policy.json")
        minimum = policy["incubating"]["minimum_fixture_cases"]
        passed = (
            len(compatibility) >= minimum
            and len(capability) >= minimum
            and all(c.get("passed") is True for c in compatibility + capability)
            and read(folder / "activation.json").get("activated") is True
        )
        accepted_sites = {
            s["object_id"]
            for s in sites
            if s["accepted"] and s["object_id"] and s["evidence_sha256"]
        }
        validation = {
            "submission": submission_id,
            "input_hashes": submission["input_hashes"],
            "policy_sha256": file_hash(self.root / "policy.json"),
            "compatibility": compatibility,
            "capability": capability,
            "incubating_eligible": passed,
            "stable_eligible": passed
            and len(accepted_sites)
            >= policy["stable"]["minimum_distinct_accepted_sites"],
            "heldout_sites": sites,
            "checks": str(checks.relative_to(self.root)),
        }
        write_json(folder / "validation.json", validation)
        submission["validation_sha256"] = file_hash(folder / "validation.json")
        write_json(folder / "submission.json", submission)
        return validation
