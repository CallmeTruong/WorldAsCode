import pytest

from worldscale.evidence_gate import metric_footprint_report


def box(x0, z0, x1, z1):
    return {"id": "wall", "vertices": [[x, y, z] for x in (x0, x1) for y in (0, 2) for z in (z0, z1)]}


def test_footprint_gate_detects_translation_even_when_camera_could_hide_it():
    evidence = {"footprint": [[0, 0], [10, 0], [10, 4], [0, 4]], "footprint_source": "test"}
    correct = metric_footprint_report({"meshes": [box(0, 0, 5, 2)]}, evidence, ["wall"], 2)
    shifted = metric_footprint_report({"meshes": [box(0, 3, 5, 5)]}, evidence, ["wall"], 2)
    assert correct["passed"] and correct["footprint_iou"] > 0.99
    assert not shifted["passed"] and shifted["footprint_iou"] == 0


def test_missing_or_invalid_metric_geometry_never_passes():
    evidence = {"footprint": [[0, 0], [10, 0], [10, 4]], "footprint_source": "test"}
    assert not metric_footprint_report({"meshes": []}, evidence, ["wall"], 1)["passed"]
    with pytest.raises(ValueError, match="INVALID_METRIC_SCALE"):
        metric_footprint_report({"meshes": []}, evidence, ["wall"], 0)
