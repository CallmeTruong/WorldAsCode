import math

import numpy as np

import worldascode.geometry.massing as massing
import worldascode.geometry.surface_height as dsm
from worldascode.contracts.world import World

FOOTPRINT = [[-15, 6], [15, 6], [15, -6], [-15, -6]]  # 30 m x 12 m, ridge along X


def gable_grid(step=0.5, eave=9.0, pitch=0.5):
    evidence = {"footprint": FOOTPRINT}
    layout = dsm.grid_layout(evidence, step)
    points = dsm.grid_plan_points(layout)
    x, n = points[..., 0], points[..., 1]
    inside = (np.abs(x) <= 15) & (np.abs(n) <= 6)
    grid = np.where(inside, eave + pitch * (6 - np.abs(n)), 0.0)
    return grid, layout, massing.to_plan(FOOTPRINT)


def test_gable_height_field_becomes_two_opposed_planes():
    grid, layout, plan = gable_grid()
    recipe, report, _ = dsm.fit_roof(grid, layout, plan, 12.0)
    large = sorted(
        recipe["planes"],
        key=lambda p: -sum((r[2] - r[0]) * (r[3] - r[1]) for r in p["rects"]),
    )[:2]
    slopes = sorted(round(math.hypot(p["a"], p["b"]), 2) for p in large)
    assert slopes == [0.5, 0.5]
    # Opposed: the two gradients cancel.
    assert (
        abs(large[0]["a"] + large[1]["a"]) < 0.02
        and abs(large[0]["b"] + large[1]["b"]) < 0.02
    )
    assert report["mean_abs_error_m"] < 0.08
    assert abs(report["eave_height_m"] - 9.0) < 0.6
    assert abs(report["top_height_m"] - 12.0) < 0.3


def test_neighbour_leaning_over_the_outline_is_not_built_as_a_tower():
    grid, layout, plan = gable_grid()
    points = dsm.grid_plan_points(layout)
    corner = (points[..., 0] > 12) & (points[..., 1] > 3)
    grid = np.where(corner, 20.0, grid)  # below the absolute cap, far above this roof
    _, report, _ = dsm.fit_roof(grid, layout, plan, 12.0)
    assert report["neighbour_cells_removed"] > 0
    assert report["top_height_m"] < 13.0


def test_chimney_inside_the_roof_is_kept():
    grid, layout, plan = gable_grid()
    points = dsm.grid_plan_points(layout)
    stack = (np.abs(points[..., 0] - 4) < 0.8) & (np.abs(points[..., 1]) < 0.8)
    grid = np.where(stack, 14.0, grid)
    recipe, report, _ = dsm.fit_roof(grid, layout, plan, 12.0)
    assert report["neighbour_cells_removed"] == 0
    assert abs(report["top_height_m"] - 14.0) < 0.2
    assert any(p["material"] == "trim" for p in recipe["planes"])


def test_rectangles_cover_a_mask_exactly_once():
    mask = np.zeros((7, 9), bool)
    mask[1:6, 1:8] = True
    mask[3:6, 4:8] = False
    cover = np.zeros(mask.shape, int)
    for c0, r0, c1, r1 in dsm.rectangles(mask):
        cover[r0:r1, c0:c1] += 1
    assert (cover == mask).all()


def test_measured_roof_compiles_into_a_valid_world_with_unchanged_walls():
    grid, layout, plan = gable_grid()
    recipe, report, _ = dsm.fit_roof(grid, layout, plan, 12.0)
    program = massing.BuildingProgram(eave_height=report["eave_height_m"], storeys=3)
    measured = massing.compile_parts(FOOTPRINT, program, recipe)
    parametric = massing.compile_parts(FOOTPRINT, program)
    assert measured[0]["rings"] == parametric[0]["rings"]
    World.model_validate(
        {
            "blueprints": [massing.blueprint("b", measured, program)],
            "instances": [{"id": "i", "blueprint": "b", "anchor": [0, 0, 0]}],
        }
    )
