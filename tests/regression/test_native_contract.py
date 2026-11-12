import json

import pytest

from worldascode.experimental.native.bridge import NativeBlocked, NativeBridge
from worldascode.experimental.native.workflow import (
    apply_documented_approximation_mode,
    apply_sections,
    asset_fingerprint,
    audit_material_assets,
    enforce_material_review_policy,
    material_contact_sheet,
    material_patch_status,
    verify_render_evidence,
)
from worldascode.kits.patches import json_edits
from worldascode.storage.artifacts import file_hash, write_json


def test_material_patches_need_real_source_resolution():
    assert material_patch_status((64, 64)) == "resolution_eligible_for_review"
    assert material_patch_status((128, 96)) == "resolution_eligible_for_review"
    assert material_patch_status((63, 300)) == "resolution_inadequate"
    assert material_patch_status((4, 24)) == "resolution_inadequate"


def test_json_edits_can_target_native_components_by_stable_id():
    spec = {
        "componentTree": [{"id": "wall-long", "geometryDescriptor": {"profile2D": {}}}],
        "repetitionSystems": [{"id": "roof-projections", "count": 3}],
    }
    patched = json_edits(
        spec,
        [
            {
                "op": "add",
                "path": "/componentTree/wall-long/geometryDescriptor/profile2D/depth",
                "value": 0.61,
            },
            {
                "op": "replace",
                "path": "/repetitionSystems/roof-projections/count",
                "value": 5,
            },
        ],
    )
    assert (
        patched["componentTree"][0]["geometryDescriptor"]["profile2D"]["depth"] == 0.61
    )
    assert patched["repetitionSystems"][0]["count"] == 5


def test_approximation_mode_disables_only_source_pbr_blocker():
    source = {
        "lookDevTargets": {
            "qualityPriority": "reference-fidelity",
            "materialPass": {
                "referencePbrExtraction": {"requiredWhenSourceImagePresent": True}
            },
        }
    }
    adapted = apply_documented_approximation_mode(source)
    assert (
        adapted["workflowPolicy"]["validationMode"]
        == "documented-source-derived-approximation"
    )
    assert (
        adapted["lookDevTargets"]["qualityPriority"]
        == "documented-source-derived-approximation"
    )
    assert (
        adapted["lookDevTargets"]["materialPass"]["referencePbrExtraction"][
            "requiredWhenSourceImagePresent"
        ]
        is False
    )
    assert source["lookDevTargets"]["qualityPriority"] == "reference-fidelity"


def test_material_contact_sheet_pairs_source_and_generated_proposal(tmp_path):
    from PIL import Image

    assets = tmp_path / "assets" / "stone"
    assets.mkdir(parents=True)
    Image.new("RGB", (12, 18), "#887766").save(assets / "source.png")
    Image.new("RGB", (128, 128), "#998877").save(assets / "albedo.png")
    write_json(
        assets / "extraction.json",
        {"maps": {"albedo": {"path": str(assets / "albedo.png")}}},
    )
    result = material_contact_sheet(tmp_path, ["stone"])
    assert result.is_file()
    assert Image.open(result).size[0] > 500


def test_existing_material_assets_are_reaudited_without_trusting_native_pass(tmp_path):
    from PIL import Image

    material = tmp_path / "assets" / "roof"
    material.mkdir(parents=True)
    Image.new("RGB", (20, 31), "#777777").save(material / "source.png")
    write_json(material / "extraction.json", {"verdict": "pass", "confidence": 0.9})
    audit = audit_material_assets(tmp_path, ["roof"])
    assert audit["requires_style_synthesis"] is True
    assert audit["maps_claimed_as_source_pbr"] is False
    assert audit["patches"][0]["native_extractor_verdict"] == "pass"


def test_undersampled_material_review_routes_low_score_to_code_node():
    review = {
        "action": "continue",
        "summary": "texture is flat",
        "material_score": 0.42,
    }
    routed = enforce_material_review_policy(review, requires_synthesis=True)
    assert routed["action"] == "refine-code"
    assert routed["model_action"] == "continue"
    assert "style-synthesized texture" in routed["summary"]
    assert (
        enforce_material_review_policy(
            {"action": "continue", "material_score": 0.8}, requires_synthesis=True
        )["action"]
        == "continue"
    )
    assert (
        enforce_material_review_policy({"action": "stop"}, requires_synthesis=True)[
            "action"
        ]
        == "stop"
    )
    with pytest.raises(NativeBlocked, match="CRITIC_MATERIAL_SCORE_MISSING_OR_INVALID"):
        enforce_material_review_policy({"action": "continue"}, requires_synthesis=True)


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    import os
    from pathlib import Path

    from PIL import Image

    from worldascode.experimental.native.bridge import pin_upstream

    upstream = os.getenv("WORLDASCODE_TEST_UPSTREAM")
    if not upstream:
        pytest.skip(
            "Optional upstream integration: set WORLDASCODE_TEST_UPSTREAM explicitly"
        )
    monkeypatch.setenv("WORLDASCODE_DATA_DIR", str(tmp_path / "state"))
    pin_upstream(Path(upstream))

    reference = tmp_path / "reference.png"
    Image.new("RGB", (256, 256), "white").save(reference)
    b = NativeBridge(tmp_path / "run")
    b.init(reference)
    return b


def test_real_native_state_rejects_out_of_order_marks(bridge, tmp_path):
    evidence = tmp_path / "evidence.json"
    write_json(evidence, {"actual": True})
    with pytest.raises(NativeBlocked, match="out-of-order"):
        bridge.mark("strict-validation", [evidence])
    bridge.mark("image-analysis", [evidence])
    assert bridge.mark("image-analysis", [evidence])["reused"]


def test_real_next_enforces_hard_stop(bridge):
    state = json.loads(bridge.state.read_text())
    state["status"] = "stopped"
    state["stopReason"] = "test-fixture"
    write_json(bridge.state, state)
    with pytest.raises(NativeBlocked, match="HARD_STOP"):
        bridge.next()


def test_strict_starter_does_not_generate_factory(bridge, tmp_path):
    bridge.command(
        "forge/stage2_spec/new_sculpt_spec.py",
        ["Test", "--image", tmp_path / "reference.png", "--out", bridge.spec],
    )
    assert bridge.strict()["exit_code"] != 0
    with pytest.raises(NativeBlocked, match="STRICT"):
        bridge.generate("blockout", tmp_path / "source.ts")
    assert not (tmp_path / "source.ts").exists()


def test_author_cannot_reduce_quality_or_invent_keys():
    for sections in [
        {"qualityTargets": {}},
        {"reviewHistory": [{"action": "continue"}]},
        {"inventedSchema": {}},
    ]:
        with pytest.raises(ValueError):
            apply_sections(
                {"componentTree": [], "qualityTargets": {}, "reviewHistory": []},
                sections,
            )


def test_stale_render_cannot_reach_critic(tmp_path):
    spec = {"componentTree": []}
    target = tmp_path / "target.png"
    target.write_bytes(b"target")
    for name in ["bundle.js", "createObjectModel.ts", "front.png"]:
        (tmp_path / name).write_bytes(name.encode())
    write_json(
        tmp_path / "evidence-binding.json",
        {
            "asset_fingerprint": asset_fingerprint(spec),
            "target_sha256": file_hash(target),
            "factory_sha256": file_hash(tmp_path / "createObjectModel.ts"),
        },
    )
    write_json(
        tmp_path / "render-manifest.json",
        {
            "bundle_sha256": file_hash(tmp_path / "bundle.js"),
            "captures": {"front.png": file_hash(tmp_path / "front.png")},
        },
    )
    verify_render_evidence(tmp_path, spec, target)
    (tmp_path / "front.png").write_bytes(b"changed")
    with pytest.raises(NativeBlocked, match="CAPTURE"):
        verify_render_evidence(tmp_path, spec, target)


def test_native_hard_gate_routes_to_refine_code(bridge, tmp_path):
    failures = ["silhouette IoU 0.30 < 0.85"]
    source = tmp_path / "loop-input.json"
    output = tmp_path / "loop-output.json"
    write_json(
        source,
        [
            {
                "fidelity": 0.35,
                "defectTags": failures,
                "reverted": False,
                "hardGateFailures": failures,
                "divineEye": {
                    "fidelity": 0.35,
                    "hardGateFailures": failures,
                    "action": "refine-code",
                    "verdict": "reject",
                },
            }
        ],
    )
    result = bridge.function_gate("loop", source, output)
    decision = json.loads(output.read_text())
    assert (
        result["exit_code"] == 0
    )  # This pure decision function executed successfully.
    assert decision["stop"] is True
    assert decision["action"] == "refine-code"
