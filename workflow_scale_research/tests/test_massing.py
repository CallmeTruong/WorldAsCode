import json
import math

import numpy as np
import pytest
from PIL import Image

from worldscale import georef, massing
from worldscale.ir import World
from worldscale.pipeline import run_massing

L_SHAPE = [[-20, 8], [10, 8], [10, -22], [0, -22], [0, -2], [-20, -2]]


def camera(heading_deg, pitch_deg=-28, distance=90.0, size=(480, 360)):
    heading, pitch = math.radians(heading_deg), math.radians(pitch_deg)
    forward = [
        math.sin(heading) * math.cos(pitch),
        math.sin(pitch),
        -math.cos(heading) * math.cos(pitch),
    ]
    target = [0.0, 3.0, 0.0]
    return {
        "position": [t - f * distance for t, f in zip(target, forward)],
        "target": target,
        "fov_deg": 60.0,
        "width": size[0],
        "height": size[1],
        "heading_deg": heading_deg,
    }


def synthetic_evidence(folder, truth, footprint=L_SHAPE):
    """Evidence whose views are silhouettes of a known programme: wall red, roof blue."""
    parts = {p["id"]: p for p in massing.compile_parts(footprint, truth)}
    views = []
    for name, heading, pitch in (
        ("north", 0, -28),
        ("east", 90, -28),
        ("south", 180, -28),
        ("west", 270, -28),
        ("overhead", 0, -89.8),
    ):
        cam = camera(heading, pitch)
        size = (cam["width"], cam["height"])
        image = np.zeros((size[1], size[0], 3), np.uint8)
        image[massing.silhouette(cam, [parts["walls"]], size)] = (190, 90, 70)
        image[massing.silhouette(cam, [parts["roof"]], size)] = (80, 100, 150)
        path = folder / (name + ".png")
        Image.fromarray(image).save(path)
        views.append({"id": name, "image": path.name, "camera": cam})
    evidence = {
        "schema": "worldscale-evidence-1",
        "object_id": "way/1",
        "frame": {"origin": {"longitude": 0, "latitude": 0}, "ground_height_m": 0},
        "footprint": footprint,
        "height_m": 14.0,
        "tags": {},
        "scope": {"below_m": 1.0, "above_m": 8.0, "grow_px": 10},
        "views": views,
        "primary_view": "north",
    }
    (folder / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    return georef.load_evidence(folder)


def test_offset_keeps_edge_count_and_degenerates_past_half_width():
    plan = massing.to_plan(L_SHAPE)
    inner = massing.offset(plan, 2.0)
    assert len(inner) == len(plan)
    assert georef.area(inner) < georef.area(plan)
    limit = massing.inset_limit(plan)
    assert 4.9 < limit < 5.01  # both wings are 10 m wide
    assert massing.offset(plan, limit + 0.2) is None


def test_gable_keeps_wing_end_walls_vertical():
    program = massing.BuildingProgram(
        eave_height=9, roof=massing.Roof(form="gable", rise=4)
    )
    plan = massing.to_plan(L_SHAPE)
    ends = massing.end_edges(plan)
    assert sum(ends) == 2
    rings, _ = massing.roof_rings(plan, program)
    top = rings[-1][1]
    for i, end in enumerate(ends):
        if end:  # the ridge ring still touches the end wall's line
            a, b = plan[i], plan[(i + 1) % len(plan)]
            cross = (b[0] - a[0]) * (top[i][1] - a[1]) - (b[1] - a[1]) * (top[i][0] - a[0])
            assert abs(cross) < 1e-6


def test_compiled_parts_form_a_valid_world_and_details_never_move_walls():
    plain = massing.BuildingProgram(eave_height=10, roof=massing.Roof(form="hip", rise=4))
    detailed = plain.model_copy(
        update={
            "storeys": 3,
            "dormers": massing.Dormers(spacing_m=6),
            "chimneys": massing.Chimneys(spacing_m=8),
        }
    )
    walls = [
        next(p for p in massing.compile_parts(L_SHAPE, program) if p["id"] == "walls")["rings"]
        for program in (plain, detailed)
    ]
    assert walls[0] == walls[1]
    parts = massing.compile_parts(L_SHAPE, detailed)
    assert any(p["id"].startswith("dormer-") for p in parts)
    assert any(p["id"].startswith("chimney-") for p in parts)
    World.model_validate(
        {
            "blueprints": [massing.blueprint("b", parts, detailed)],
            "instances": [{"id": "i", "blueprint": "b", "anchor": [0, 0, 0]}],
        }
    )


def test_loft_rejects_mismatched_rings():
    parts = massing.compile_parts(L_SHAPE, massing.BuildingProgram(eave_height=8))
    blueprint = massing.blueprint("b", parts, massing.BuildingProgram(eave_height=8))
    blueprint["components"][0]["rings"][1]["points"].pop()
    with pytest.raises(ValueError):
        World.model_validate(
            {"blueprints": [blueprint], "instances": [{"id": "i", "blueprint": "b", "anchor": [0, 0, 0]}]}
        )


def test_outline_fills_enclosed_gap_but_not_a_notch():
    mask = np.zeros((9, 9), bool)
    mask[1:8, 1:8] = True
    mask[4, 4] = False  # shadowed interior
    mask[1:4, 5:8] = False  # concave corner open to the outside
    filled = georef.outline(mask)
    assert filled[4, 4]
    assert not filled[2, 6]


def test_fit_recovers_heights_and_registration_of_a_known_building(tmp_path):
    truth = massing.BuildingProgram(
        registration=massing.Registration(dx=1.5, dz=-1.0),
        eave_height=11.0,
        roof=massing.Roof(form="hip", rise=5.0),
    )
    evidence = synthetic_evidence(tmp_path, truth)
    fitted, report = massing.fit(evidence)
    assert min(report["per_view_iou"].values()) > 0.93
    assert abs(fitted.registration.dx - 1.5) <= 0.5
    assert abs(fitted.registration.dz + 1.0) <= 0.5
    total = fitted.eave_height + fitted.roof.rise
    assert abs(total - 16.0) < 1.5
    assert fitted.roof.form != "flat"
    assert abs(fitted.eave_height - 11.0) < 1.6  # located by the wall/roof colour change


def test_fit_prefers_flat_roof_when_evidence_is_a_plain_prism(tmp_path):
    truth = massing.BuildingProgram(eave_height=20.0)
    evidence = synthetic_evidence(tmp_path, truth)
    fitted, _ = massing.fit(evidence)
    assert abs(fitted.eave_height + fitted.roof.rise - 20.3) < 1.5


def test_program_override_cannot_touch_measured_geometry(tmp_path):
    truth = massing.BuildingProgram(eave_height=10.0)
    synthetic_evidence(tmp_path, truth)
    override = tmp_path / "override.json"
    override.write_text(json.dumps({"eave_height": 40}), encoding="utf-8")
    with pytest.raises(ValueError, match="PROGRAM_OVERRIDE_NOT_A_DETAIL_FIELD"):
        run_massing(tmp_path, tmp_path / "run", override)


def test_default_program_reads_tags_without_imagery():
    height, source = massing.tag_height({"building:levels": "5"})
    assert source == "building:levels" and height == pytest.approx(17.0)
    program = massing.default_program(height, {"building:levels": "5", "roof:shape": "hipped"})
    assert program.storeys == 5 and program.roof.form == "hip"
    assert program.eave_height + program.roof.rise == pytest.approx(height)
