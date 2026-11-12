"""Objective roof agreement: the model's top-down height against the sampled height field.

A silhouette passes almost any roof that fills the outline. Heights do not: a
missing tower, a flat mansard or a ridge on the wrong wing shows up as metres
of error at a known place. The comparison costs no model call and its report
names where the model is too low or too high, so it can drive a revision.
"""

from pathlib import Path

import numpy as np
from PIL import Image

import worldascode.geometry.surface_height as dsm
from worldascode.evidence.site_context import nearest_edge

# Tolerant on purpose: stylised ornament and smoothed photogrammetry both move
# heights by a metre or so. These catch a different roof, not a stylised one.
MAX_MEAN_ABS_ERROR_M = 1.6
MAX_P90_ABS_ERROR_M = 4.0
REGION_ERROR_M = 2.0
REGION_MIN_M2 = 6.0


def capture(page, layout):
    """Model heights on the height field's grid; ``None`` cells are open sky."""
    flat = page.evaluate("l=>worldscale.heightMap(l)", layout)
    return np.array([np.nan if v is None else v for v in flat], float).reshape(
        layout["nv"], layout["nu"]
    )


def compare(model, grid, layout, plan, height_prior, out_image=None):
    """Error statistics and the worst regions, in the outline's own terms."""
    step = layout["step"]
    inside = dsm.polygon_mask(plan, layout)
    cap = 1.45 * height_prior + 4.0
    # The outline is approximate: ignore a rim about a metre wide, where the
    # samples may already be the street or a neighbour.
    core = inside.copy()
    for _ in range(max(1, round(1.2 / step))):
        shrunk = core.copy()
        shrunk[1:] &= core[:-1]
        shrunk[:-1] &= core[1:]
        shrunk[:, 1:] &= core[:, :-1]
        shrunk[:, :-1] &= core[:, 1:]
        core = shrunk
    valid = core & np.isfinite(grid) & (grid < cap) & (grid > 0.35 * height_prior)
    if valid.sum() >= 20:
        # A much taller mass reaching the rim is a neighbour leaning over the outline.
        tall = valid & (grid > np.percentile(grid[valid], 95) + 3.0)
        rim = core.copy()
        rim[1:-1, 1:-1] &= ~(
            core[:-2, 1:-1] & core[2:, 1:-1] & core[1:-1, :-2] & core[1:-1, 2:]
        )
        while (tall & rim).any():
            region = dsm.component(tall, tuple(np.argwhere(tall & rim)[0]))
            valid &= ~region
            tall &= ~region
    if valid.sum() < 20:
        return {"available": False, "reason": "height field does not cover the outline"}
    built = np.where(np.isfinite(model), model, 0.0)
    error = np.where(valid, built - grid, 0.0)
    values = error[valid]
    points = dsm.grid_plan_points(layout)
    regions = []
    for sign, label in ((-1, "too_low"), (1, "too_high")):
        remaining = valid & (sign * error > REGION_ERROR_M)
        while remaining.any():
            blob = dsm.component(remaining, tuple(np.argwhere(remaining)[0]))
            remaining &= ~blob
            area = float(blob.sum() * step**2)
            if area < REGION_MIN_M2:
                continue
            x, n = (float(v) for v in points[blob].mean(axis=0))
            _, edge, t = nearest_edge(plan, x, n)
            rows, cols = np.where(blob)
            regions.append(
                {
                    "problem": label,
                    "mean_error_m": round(float(error[blob].mean()), 1),
                    "area_m2": round(area, 1),
                    "x": round(x, 1),
                    "z": round(-n, 1),
                    "extent_m": [
                        round((np.ptp(cols) + 1) * step, 1),
                        round((np.ptp(rows) + 1) * step, 1),
                    ],
                    "near_edge": f"e{edge}",
                    "t": round(t, 2),
                    "measured_top_m": round(float(np.percentile(grid[blob], 90)), 1),
                    "model_top_m": round(float(np.percentile(built[blob], 90)), 1),
                }
            )
    regions.sort(key=lambda r: -abs(r["mean_error_m"]) * r["area_m2"])
    mean_abs = float(np.abs(values).mean())
    p90 = float(np.percentile(np.abs(values), 90))
    if out_image:
        # Red: model too low. Blue: model too high. Grey: within a metre.
        shade = np.clip(error / 6.0, -1, 1)
        image = np.full((*error.shape, 3), 18, np.uint8)
        image[valid] = 120
        image[valid & (shade < -1 / 6)] = np.stack(
            [150 + 105 * -shade, 90 * (1 + shade), 80 * (1 + shade)], axis=-1
        )[valid & (shade < -1 / 6)].astype(np.uint8)
        image[valid & (shade > 1 / 6)] = np.stack(
            [80 * (1 - shade), 110 * (1 - shade), 150 + 105 * shade], axis=-1
        )[valid & (shade > 1 / 6)].astype(np.uint8)
        scale = max(1, 640 // max(error.shape))
        Image.fromarray(image[::-1]).resize(
            (error.shape[1] * scale, error.shape[0] * scale), Image.NEAREST
        ).save(Path(out_image))
    return {
        "available": True,
        "passed": mean_abs <= MAX_MEAN_ABS_ERROR_M and p90 <= MAX_P90_ABS_ERROR_M,
        "mean_abs_error_m": round(mean_abs, 2),
        "p90_abs_error_m": round(p90, 2),
        "bias_m": round(float(values.mean()), 2),
        "cells": int(valid.sum()),
        "limits": {
            "mean_abs_error_m": MAX_MEAN_ABS_ERROR_M,
            "p90_abs_error_m": MAX_P90_ABS_ERROR_M,
        },
        "regions": regions[:8],
        "note": "Model top-down height minus sampled photogrammetric height inside the outline; negative means the model is lower than the building.",
    }


def baseline(grid, layout, plan, height_prior, level):
    """Error of a flat roof at ``level``: what any roof must beat to carry information."""
    flat = np.full(grid.shape, float(level))
    report = compare(flat, grid, layout, plan, height_prior)
    return report.get("mean_abs_error_m") if report.get("available") else None


__all__ = ["capture", "compare", "baseline"]
