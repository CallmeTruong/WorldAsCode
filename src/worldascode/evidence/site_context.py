"""Site brief: the few measured facts a designer needs, and nothing else.

The brief is deliberately small. It carries the outline, key heights, roof
character and the positions of roof features found in the height field, so a
design script can anchor to reality without being handed a mesh to copy.
"""

import math

import numpy as np

import worldascode.geometry.massing as massing
import worldascode.geometry.surface_height as dsm

COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
MAIN_PLANE_M2 = 15.0


def registered_wings(evidence, registration):
    """Preserve measured wing poses; dimensions alone lose the roof layout.

    These remain approximate rectangular priors, never replacements for the
    protected polygon. Apply the same translation/growth as footprint fitting.
    """
    result = []
    for wing in evidence.get("wings", []):
        length, width = wing["length_m"], wing["width_m"]
        yaw = wing.get("rotation_y_rad", 0.0)
        if length < width:
            length, width = width, length
            yaw += math.pi / 2
        item = {
            "length_m": length + 2 * registration.grow,
            "width_m": width + 2 * registration.grow,
            "rotation_y_rad": yaw,
            "confidence": "approximate rectangular evidence prior",
        }
        centre = wing.get("centre_xz")
        if centre is not None:
            x, z = centre[0] + registration.dx, centre[1] + registration.dz
            u, v = (math.cos(yaw), -math.sin(yaw)), (math.sin(yaw), math.cos(yaw))
            item["centre_xz"] = [x, z]
            item["corners"] = [
                [
                    x
                    + su * u[0] * item["length_m"] / 2
                    + sv * v[0] * item["width_m"] / 2,
                    z
                    + su * u[1] * item["length_m"] / 2
                    + sv * v[1] * item["width_m"] / 2,
                ]
                for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))
            ]
        result.append(item)
    return result


def edges(plan):
    ends = massing.end_edges(plan)
    result = []
    for i, (a, b) in enumerate(zip(plan, plan[1:] + plan[:1])):
        dx, dn = b[0] - a[0], b[1] - a[1]
        # Outward normal of a counter-clockwise edge is (dn, -dx) in (east, north).
        bearing = math.degrees(math.atan2(dn, -dx)) % 360
        result.append(
            {
                "id": f"e{i}",
                "length_m": round(math.hypot(dx, dn), 1),
                "facing": COMPASS[int((bearing + 22.5) // 45) % 8],
                "end": bool(ends[i]),
                "role": "wing_end" if ends[i] else "facade",
            }
        )
    return result


def nearest_edge(plan, x, n):
    best = None
    for i, (a, b) in enumerate(zip(plan, plan[1:] + plan[:1])):
        dx, dn = b[0] - a[0], b[1] - a[1]
        t = max(
            0.0, min(1.0, ((x - a[0]) * dx + (n - a[1]) * dn) / (dx * dx + dn * dn))
        )
        distance = math.hypot(x - a[0] - dx * t, n - a[1] - dn * t)
        if best is None or distance < best[0]:
            best = (distance, i, t)
    return best


def roof_features(grid, layout, plan, height_prior):
    """Dormers, chimneys and towers as blobs of small planes standing on the main roof."""
    _, report, labels = dsm.fit_roof(grid, layout, plan, height_prior)
    step = layout["step"]
    eave = report["eave_height_m"]
    sizes = np.bincount(labels[labels >= 0]) * step**2
    main = (labels >= 0) & (sizes[np.maximum(labels, 0)] >= MAIN_PLANE_M2)
    small = (labels >= 0) & ~main
    ridge = float(np.percentile(grid[main], 97)) if main.any() else eave
    gy, gx = np.gradient(grid, step)
    pitch = (
        float(np.degrees(np.arctan(np.median(np.hypot(gx, gy)[main]))))
        if main.any()
        else 0.0
    )
    points = dsm.grid_plan_points(layout)
    found = {"dormers": [], "chimneys": [], "towers": []}
    remaining = small.copy()
    while remaining.any():
        blob = dsm.component(remaining, tuple(np.argwhere(remaining)[0]))
        remaining &= ~blob
        area = float(blob.sum() * step**2)
        top = float(np.percentile(grid[blob], 95))
        x, n = (float(v) for v in points[blob].mean(axis=0))
        inset, index, t = nearest_edge(plan, x, n)
        rows, cols = np.where(blob)
        width = float(max(np.ptp(rows), np.ptp(cols)) + 1) * step
        # A feature stands proud of the main roof around it; a patch that merely
        # continues the slope is fitting noise.
        ring = blob.copy()
        for _ in range(2):
            grown = ring.copy()
            grown[1:] |= ring[:-1]
            grown[:-1] |= ring[1:]
            grown[:, 1:] |= ring[:, :-1]
            grown[:, :-1] |= ring[:, 1:]
            ring = grown
        around = ring & main
        proud = top - float(np.median(grid[around])) if around.sum() >= 3 else 0.0
        if proud < 0.8 or width > 9.0:
            continue
        if area <= 3.5 and proud >= 1.2:
            found["chimneys"].append(
                {"x": round(x, 1), "z": round(-n, 1), "height_m": round(proud, 1)}
            )
        elif area >= 8.0 and top >= ridge + 1.5:
            found["towers"].append(
                {
                    "x": round(x, 1),
                    "z": round(-n, 1),
                    "width_m": round(width, 1),
                    "height_m": round(top, 1),
                }
            )
        elif 1.4 <= area <= 14.0 and inset <= 5.0 and top - eave >= 0.8:
            found["dormers"].append(
                {
                    "edge": f"e{index}",
                    "t": round(t, 3),
                    "width_m": round(min(width, 3.5), 1),
                    "height_m": round(top - eave, 1),
                }
            )
    for items in found.values():
        del items[40:]
    return found, {
        "eave": eave,
        "ridge": ridge,
        "top": report["top_height_m"],
        "pitch": pitch,
    }


def site_brief(evidence, program, heights=None):
    """``heights`` is an optional ``(grid, layout)`` pair from ``dsm.load``."""
    plan = massing.registered_plan(evidence["footprint"], program.registration)
    brief = {
        "object_id": evidence["object_id"],
        "label": evidence.get("label", ""),
        "tags": evidence.get("tags", {}),
        "footprint": [[round(x, 2), round(z, 2)] for x, z in massing.from_plan(plan)],
        "edges": edges(plan),
        "wings": registered_wings(evidence, program.registration),
        "registration": program.registration.model_dump(),
        "axis_yaw": evidence.get("wings", [{}])[0].get("rotation_y_rad", 0.0),
        "storeys": program.storeys,
        "eave_m": round(program.eave_height, 1),
        "ridge_m": round(program.eave_height + program.roof.rise, 1),
        "top_m": round(program.eave_height + program.roof.rise, 1),
        "roof": {"form": program.roof.form, "pitch_deg": None},
        "features": {"dormers": [], "chimneys": [], "towers": []},
        "colours": {
            k: getattr(program.appearance, k) for k in ("wall", "roof", "trim")
        },
        "sources": {
            "outline": evidence.get("footprint_source", "evidence footprint"),
            "heights": "multi-view silhouette fit",
            "features": "none",
        },
        "confidence": {
            "outline": {
                "status": "approximate_registered_osm",
                "note": "Small image-fitted translation/offset may differ from raw OSM; not a surveyed plan.",
            },
            "heights": {
                "status": "inferred",
                "note": "Silhouette fit unless a photogrammetric height field is supplied.",
            },
            "feature_identity": {
                "status": "heuristic",
                "note": "Height blobs cannot reliably distinguish gable, dormer and turret. Confirm type in source views; use plausible details for hidden surfaces.",
            },
            "colours": {
                "status": "appearance_cues",
                "note": "Baked shadows and image exposure remain; these are not recovered reflectance.",
            },
        },
    }
    if heights is not None:
        grid, layout = heights
        features, measured = roof_features(grid, layout, plan, evidence["height_m"])
        brief["features"] = features
        brief["eave_m"] = round(measured["eave"], 1)
        brief["ridge_m"] = round(measured["ridge"], 1)
        brief["top_m"] = round(measured["top"], 1)
        brief["roof"]["pitch_deg"] = round(measured["pitch"])
        brief["sources"]["heights"] = (
            "sampled photogrammetric height field (not surveyed)"
        )
        brief["sources"]["features"] = (
            "small roof planes in the height field; counts and sizes approximate"
        )
        brief["confidence"]["heights"]["status"] = "sampled_photogrammetry_not_surveyed"
        from worldascode.evidence.roof_structure import roof_structure

        structure = roof_structure(
            grid, layout, plan, brief["wings"], measured["eave"], evidence["height_m"]
        )
        if structure and structure["sections"]:
            brief["roof"]["sections"] = structure["sections"]
            brief["roof"]["volumes"] = structure["volumes"]
            brief["roof"]["section_fit_mae_m"] = structure["section_fit_mae_m"]
            # Large proud masses are now typed volumes with a measured base and
            # cap; the untyped "tower" blobs they replace would double-count them.
            brief["features"].pop("towers", None)

            def in_volume(x, z):
                return any(
                    math.hypot(x - v["x"], z - v["z"])
                    <= 0.6 * max(v["width_m"], v["depth_m"])
                    for v in structure["volumes"]
                )

            brief["features"]["chimneys"] = [
                c
                for c in brief["features"]["chimneys"]
                if not in_volume(c["x"], c["z"])
            ]
            brief["confidence"]["feature_identity"] = {
                "status": "measured_geometry_typed_by_shape",
                "note": "Sections and volumes are measured shapes. Their architectural name (tower, cross gable, plant room) is your reading of the views; their position, base and height are not.",
            }
        elif structure:
            brief["roof"]["structure_note"] = structure["note"]
    return brief


"""Explicitly versioned ground inference, retaining uncertainty and samples."""


def estimate_ground(samples, estimator="lowest-two-mean-v1"):
    values = sorted(
        item["height"]
        for item in samples
        if isinstance(item.get("height"), (int, float))
        and math.isfinite(item["height"])
    )
    if len(values) < 2:
        raise ValueError("INSUFFICIENT_GROUND_SAMPLES")
    if estimator != "lowest-two-mean-v1":
        raise ValueError("UNKNOWN_GROUND_ESTIMATOR")
    return {
        "height_m": sum(values[:2]) / 2,
        "estimator": estimator,
        "sample_count": len(values),
        "sample_spread_m": values[-1] - values[0],
        "surveyed": False,
        "uncertainty": "Low surrounding mesh samples can include pits or neighboring surfaces; inspect before acceptance.",
    }
