"""Focused service extracted from the reconstruction workflow."""

import math

import numpy as np

import worldascode.geometry.massing as massing
from worldascode.config import ACCEPT, LIMITS


def measure(run, evidence, site, report, browser, inspection=None):
    """Tolerant metric checks; they catch a wrong building, not a stylised one.

    ``inspection`` may carry the roof height comparison and the structural scan.
    Both are deterministic and both name the place that is wrong.
    """
    inspection = inspection or {}
    roof = inspection.get("roof_shape")
    structure = inspection.get("structure") or {"checked": 0, "issues": []}
    oblique = [v["id"] for v in evidence["views"] if not massing.is_plan_view(v)]
    plan = [v["id"] for v in evidence["views"] if massing.is_plan_view(v)]
    mean = float(np.mean([browser[v]["iou"] for v in oblique])) if oblique else None
    plan_iou = min((browser[v]["iou"] for v in plan), default=None)
    bounds = report.get("manifest", {}).get("bounds")
    height = bounds["max"][1] if bounds else None
    ratio = height / site["top_m"] if height else None
    triangles = report.get("manifest", {}).get("triangles", 0)
    checks = {
        "browser": bool(report.get("passed")),
        "outline_oblique": mean is None or mean >= LIMITS["mean_oblique_iou"],
        "outline_plan": plan_iou is None or plan_iou >= LIMITS["plan_iou"],
        "height": ratio is not None
        and LIMITS["height_ratio"][0] <= ratio <= LIMITS["height_ratio"][1],
        "triangles": triangles <= LIMITS["max_triangles"],
        "structure": not structure["issues"],
    }
    if roof and roof.get("available"):
        checks["roof_shape"] = bool(roof["passed"])
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "roof_shape": roof,
        "structure": structure,
        "mean_oblique_iou": None if mean is None else round(mean, 4),
        "plan_iou": plan_iou,
        "height_m": None if height is None else round(height, 2),
        "height_ratio": None if ratio is None else round(ratio, 3),
        "triangles": triangles,
        "per_view_iou": {k: v["iou"] for k, v in browser.items()},
        "limits": LIMITS,
    }


def candidate_rank(record):
    scores = record["scores"]
    return (
        record["accepted"],
        record["metrics_passed"],
        not record.get("likeness_regression", False),
        min(scores[k] / ACCEPT[k] for k in ACCEPT),
        scores["likeness"],
        sum(scores.values()),
    )


def validated_scores(review):
    scores = {}
    for key in ACCEPT:
        value = review.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 1
        ):
            raise ValueError("INVALID_CRITIC_SCORE: " + key)
        scores[key] = float(value)
    return scores
