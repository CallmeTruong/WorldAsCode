import numpy as np
from PIL import Image

from worldascode.evidence.georeference import (
    Frame,
    build_evidence,
    load_evidence,
    project,
    vertical_fov,
)


def test_local_frame_enu_south_and_ecef_roundtrip():
    frame = Frame(139.7632, 35.6784, 38.85)
    origin = frame.to_ecef(0, 0, 0)
    east = np.asarray(frame.to_ecef(1, 0, 0)) - origin
    up = np.asarray(frame.to_ecef(0, 1, 0)) - origin
    south = np.asarray(frame.to_ecef(0, 0, 1)) - origin
    assert np.isclose(np.linalg.norm(east), 1, atol=1e-6)
    assert np.isclose(np.linalg.norm(up), 1, atol=1e-6)
    assert np.isclose(np.linalg.norm(south), 1, atol=1e-6)
    assert abs(float(east @ up)) < 1e-6
    assert abs(float(east @ south)) < 1e-6
    assert abs(float(up @ south)) < 1e-6


def test_exact_cesium_matrix_projection_uses_column_major_capture():
    camera = {
        "width": 100,
        "height": 100,
        "local_to_ecef": np.eye(4).tolist(),
        # Cesium Matrix4.toArray stores identity in column-major order.
        "view_matrix": np.eye(4).flatten(order="F").tolist(),
        "projection_matrix": np.eye(4).flatten(order="F").tolist(),
    }
    pixels, depth = project(camera, [[0, 0, 0], [1, 1, 0]])
    assert np.allclose(pixels, [[50, 50], [100, 0]])
    assert np.all(depth > 0)


def test_cesium_landscape_fov_is_converted_to_vertical_fov():
    result = vertical_fov({"width": 1440, "height": 1080, "fov_deg": 60})
    assert np.isclose(result, 46.826, atol=0.01)


def test_evidence_records_exact_or_approximate_camera_provenance(tmp_path):
    capture_dir = tmp_path / "capture"
    capture_dir.mkdir()
    Image.new("RGB", (100, 100), "black").save(capture_dir / "north.png")
    identity = np.eye(4).flatten(order="F").tolist()
    manifest = {
        "target": {"longitude": 139.76, "latitude": 35.68, "height": 40},
        "views": [
            {
                "view": "north",
                "heading_deg": 0,
                "stats": {
                    "camera": {
                        "longitude": 139.76,
                        "latitude": 35.681,
                        "height": 80,
                        "view_matrix": identity,
                        "projection_matrix": identity,
                    }
                },
            }
        ],
    }
    precise = build_evidence(
        tmp_path / "precise",
        [[139.759, 35.679], [139.761, 35.679], [139.761, 35.681], [139.759, 35.681]],
        manifest,
        capture_dir,
        38,
        20,
        "test/way",
    )
    assert precise["views"][0]["camera"]["projection_source"].startswith("captured")
    assert len(precise["views"][0]["camera"]["local_to_ecef"]) == 4

    manifest["views"][0]["stats"]["camera"].pop("view_matrix")
    manifest["views"][0]["stats"]["camera"].pop("projection_matrix")
    approximate = build_evidence(
        tmp_path / "approximate",
        [[139.759, 35.679], [139.761, 35.679], [139.761, 35.681], [139.759, 35.681]],
        manifest,
        capture_dir,
        38,
        20,
        "test/way",
    )
    assert (
        "assumed Cesium default"
        in approximate["views"][0]["camera"]["projection_source"]
    )
    assert "Approximate" in approximate["views"][0]["calibration"]
    assert load_evidence(tmp_path / "approximate")["object_id"] == "test/way"
