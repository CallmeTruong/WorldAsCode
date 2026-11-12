import pytest

from worldascode.geometry.registration import bind_wing_poses


def test_camera_driven_wing_translation_is_replaced_by_metric_pose():
    source = "node_wall_0.position.set(99,0,99); node_wall_0.rotation.set(0,1,0);"
    spec = {
        "componentTree": [
            {
                "id": "wall",
                "parent": "root",
                "level": "macro",
                "dimensions": {"width": 2, "depth": 1},
            }
        ]
    }
    evidence = {
        "wings": [
            {
                "length_m": 20,
                "width_m": 10,
                "centre_xz": [10, -20],
                "rotation_y_rad": -0.25,
            }
        ]
    }
    fixed, changes = bind_wing_poses(source, spec, evidence, 10)
    assert "position.set(1.0, 0, -2.0)" in fixed
    assert "rotation.set(0, -0.25, 0)" in fixed
    assert changes[0]["component"] == "wall"
    with pytest.raises(ValueError, match="ANCHOR_MISSING"):
        bind_wing_poses("different code", spec, evidence, 10)
