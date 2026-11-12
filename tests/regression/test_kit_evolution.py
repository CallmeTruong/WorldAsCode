from pathlib import Path

import pytest

from worldascode.config import ROOT
from worldascode.kits.evolution import (
    activation_decision,
    apply_proposal,
    copy_active_version,
)
from worldascode.storage.artifacts import file_hash, write_json


def test_method_permissions_reject_changes_to_shared_invariants():
    source = (ROOT / "runtime/kit.mjs").read_text(encoding="utf-8")
    patch = {
        "edits": [
            {"find": "const form = o.form ??", "replace": "const form = o.form ??"}
        ]
    }
    changed, names = apply_proposal(source, patch, {"roof"})
    assert changed == source and names == []
    with pytest.raises(ValueError, match="OUTSIDE_GRANTED"):
        apply_proposal(
            source,
            {
                "edits": [
                    {
                        "find": "if (this.counts.walls) throw Error('KIT_EXACTLY_ONE_WALL_ASSEMBLY');",
                        "replace": "",
                    }
                ]
            },
            {"roof"},
        )
    with pytest.raises(ValueError, match="FORBIDDEN"):
        apply_proposal(
            source,
            {
                "edits": [
                    {
                        "find": "const form = o.form ??",
                        "replace": "fetch('/steal'); const form = o.form ??",
                    }
                ]
            },
            {"roof"},
        )
    with pytest.raises(ValueError, match="PERMISSION"):
        apply_proposal(source, {}, {"walls"})
    with pytest.raises(ValueError, match="FORBIDDEN"):
        apply_proposal(
            source,
            {
                "new_methods": [
                    {
                        "name": "cheat",
                        "code": "  cheat(o={}) { this.wallGuard.positions=[]; }",
                    }
                ]
            },
            {"roof"},
        )


def test_new_capability_is_added_without_touching_protected_builder():
    source = (ROOT / "runtime/kit.mjs").read_text(encoding="utf-8")
    proposal = {
        "edits": [],
        "new_methods": [
            {
                "name": "roofJoint",
                "code": "  roofJoint(frame,o={}) {\n    return this.box(frame,{w:1,h:1,d:1,material:o.material});\n  }",
            }
        ],
    }
    changed, names = apply_proposal(source, proposal, {"roof"})
    assert names == ["roofJoint"] and "  roofJoint(" in changed
    assert "KIT_MEASURED_WALL_GEOMETRY_MUTATED" in changed


def test_acceptance_requires_visual_gain_and_real_regression_results():
    metrics = {"passed": True, "mean_oblique_iou": 0.88}
    before = {"likeness": 0.6, "style": 0.6, "detail": 0.4}
    improved = {"likeness": 0.63, "style": 0.62, "detail": 0.48}
    assert activation_decision(metrics, metrics, before, improved, [{"passed": True}])[
        "activated"
    ]
    assert not activation_decision(metrics, metrics, before, improved, [])["activated"]
    assert not activation_decision(
        metrics, metrics, before, improved, [{"passed": False}]
    )["activated"]
    assert not activation_decision(
        metrics, metrics, before, {**improved, "likeness": 0.5}, [{"passed": True}]
    )["activated"]
    assert not activation_decision(
        metrics, metrics, before, before, [{"passed": True}]
    )["activated"]
    assert not activation_decision(
        metrics, metrics, before, {**improved, "style": 0.5}, [{"passed": True}]
    )["activated"]


def test_path_permissions_never_allow_model_file_paths():
    # The patch format addresses source substrings/methods, not filesystem paths.
    source = (ROOT / "runtime/kit.mjs").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="INVALID_NEW_METHOD"):
        apply_proposal(
            source, {"new_methods": [{"name": "../../core", "code": "x"}]}, {"roof"}
        )
    assert Path(ROOT / "runtime/kit.mjs").is_file()


def test_reusing_kit_version_rejects_changed_dependency(tmp_path):
    kit = tmp_path / "candidate"
    kit.mkdir()
    (kit / "kit.mjs").write_text("export const version=1;")
    (kit / "surfaces.mjs").write_text("export const seed=7;")
    manifest = tmp_path / "active-kit.json"
    validation = tmp_path / "decision.json"
    write_json(
        validation, {"activated": True, "candidate_sha256": file_hash(kit / "kit.mjs")}
    )
    write_json(
        manifest,
        {
            "path": str(kit / "kit.mjs"),
            "sha256": file_hash(kit / "kit.mjs"),
            "validation_path": str(validation),
            "validation_sha256": file_hash(validation),
            "scope": "run-local",
            "modules": {p.name: file_hash(p) for p in kit.glob("*.mjs")},
        },
    )
    assert copy_active_version(manifest, tmp_path / "reuse").is_file()
    (kit / "surfaces.mjs").write_text("changed")
    with pytest.raises(ValueError, match="MODULE_MISMATCH"):
        copy_active_version(manifest, tmp_path / "reject")


def test_completed_negative_worker_preserves_case_feedback(tmp_path, monkeypatch):
    from worldascode.workflows.refinement import regressions

    class Worker:
        returncode = 2

        def communicate(self, timeout):
            return "", ""

    monkeypatch.setattr(
        "worldascode.execution.regression_worker.subprocess.Popen",
        lambda *a, **kw: Worker(),
    )
    cases = [
        {
            "case": 1,
            "passed": False,
            "error": "ROOF_OUTSIDE_PLAN",
            "outside_fraction": 0.25,
        }
    ]
    write_json(tmp_path / "result.json", {"passed": False, "cases": cases})
    assert regressions(tmp_path / "kit.mjs", tmp_path) == cases


def test_wing_exercise_uses_fixture_coordinates_without_model_code():
    from worldascode.quality.kit_regression import fixture_options

    plan = [[-8, 4], [8, 4], [8, -4], [-8, -4]]
    spec = {"material": "brick", "wings": {"$fixture": "wing-corners"}}
    bound = fixture_options(spec, plan, 0)
    assert bound["wings"] == [{"corners": plan}]
    assert spec["wings"] == {"$fixture": "wing-corners"}
    l_wings = fixture_options(spec, [], 1)["wings"]
    assert len(l_wings) == 2


def test_developer_receives_previous_patch_and_executed_failure(tmp_path):
    from worldascode.kits.evolution import propose

    class Provider:
        def __init__(self):
            self.prompts = []

        def call(self, node, prompt, images, max_output):
            self.prompts.append(prompt)
            if node.startswith("kit-gap"):
                return {
                    "action": "develop-kit",
                    "methods": ["roof"],
                    "capability": "roof test",
                }
            return {
                "edits": [],
                "new_methods": [],
                "exercise": {"method": "roof", "options": {"material": "brick"}},
            }

    provider = Provider()
    prior = {
        "kit_failure": {"status": "regression-failed", "error": "ROOF_OUTSIDE_PLAN"},
        "rejected_proposal": {"summary": "bad wing coordinates"},
    }
    assert propose(
        provider, tmp_path / "cycle", ROOT / "runtime/kit.mjs", [prior], [], {}
    )
    assert "ROOF_OUTSIDE_PLAN" in provider.prompts[1]
    assert "bad wing coordinates" in provider.prompts[1]


def test_window_method_name_is_not_mistaken_for_browser_global():
    from worldascode.kits.evolution import methods

    source = (ROOT / "runtime/kit.mjs").read_text(encoding="utf-8")
    code = methods(source)["window"]
    assert (
        apply_proposal(
            source, {"edits": [{"find": code, "replace": code}]}, {"window"}
        )[0]
        == source
    )


def test_released_extension_helper_can_evolve_without_unlocking_core():
    from worldascode.kits.evolution import editable_methods

    source = (ROOT / "runtime/kit.mjs").read_text(encoding="utf-8")
    original = "  roof(o = {}) {"
    proposal = {
        "edits": [
            {
                "find": original,
                "replace": original
                + "\n    if(o.extension)return this._extendedRoof(o);",
            }
        ],
        "new_methods": [
            {
                "name": "_extendedRoof",
                "code": "  _extendedRoof(o={}) { return this.roof({...o,extension:false}); }",
            }
        ],
    }
    changed, _ = apply_proposal(source, proposal, {"roof"})
    assert "_extendedRoof" in editable_methods(changed)
    assert "_add" not in editable_methods(changed)
    update = {"edits": [{"find": "extension:false", "replace": "extension:undefined"}]}
    assert (
        "extension:undefined" in apply_proposal(changed, update, {"_extendedRoof"})[0]
    )
