"""Site brief: the few measured facts a designer needs, and nothing else.

The brief is deliberately small. It carries the outline, key heights, roof
character and the positions of roof features found in the height field, so a
design script can anchor to reality without being handed a mesh to copy.
"""

import math

import numpy as np

from . import dsm, massing

COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
MAIN_PLANE_M2 = 15.0


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
            }
        )
    return result


def nearest_edge(plan, x, n):
    best = None
    for i, (a, b) in enumerate(zip(plan, plan[1:] + plan[:1])):
        dx, dn = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((x - a[0]) * dx + (n - a[1]) * dn) / (dx * dx + dn * dn)))
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
    pitch = float(np.degrees(np.arctan(np.median(np.hypot(gx, gy)[main])))) if main.any() else 0.0
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
                {"x": round(x, 1), "z": round(-n, 1), "width_m": round(width, 1),
                 "height_m": round(top, 1)}
            )
        elif 1.4 <= area <= 14.0 and inset <= 5.0 and top - eave >= 0.8:
            found["dormers"].append(
                {"edge": f"e{index}", "t": round(t, 3), "width_m": round(min(width, 3.5), 1),
                 "height_m": round(top - eave, 1)}
            )
    for items in found.values():
        del items[40:]
    return found, {"eave": eave, "ridge": ridge, "top": report["top_height_m"], "pitch": pitch}


def site_brief(evidence, program, heights=None):
    """``heights`` is an optional ``(grid, layout)`` pair from ``dsm.load``."""
    plan = massing.registered_plan(evidence["footprint"], program.registration)
    brief = {
        "object_id": evidence["object_id"],
        "label": evidence.get("label", ""),
        "tags": evidence.get("tags", {}),
        "footprint": [[round(x, 2), round(z, 2)] for x, z in massing.from_plan(plan)],
        "edges": edges(plan),
        "wings": [
            {"length_m": round(max(w["length_m"], w["width_m"]), 1),
             "width_m": round(min(w["length_m"], w["width_m"]), 1)}
            for w in evidence.get("wings", [])
        ],
        "axis_yaw": evidence.get("wings", [{}])[0].get("rotation_y_rad", 0.0),
        "storeys": program.storeys,
        "eave_m": round(program.eave_height, 1),
        "ridge_m": round(program.eave_height + program.roof.rise, 1),
        "top_m": round(program.eave_height + program.roof.rise, 1),
        "roof": {"form": program.roof.form, "pitch_deg": None},
        "features": {"dormers": [], "chimneys": [], "towers": []},
        "colours": {k: getattr(program.appearance, k) for k in ("wall", "roof", "trim")},
        "sources": {
            "outline": evidence.get("footprint_source", "evidence footprint"),
            "heights": "multi-view silhouette fit",
            "features": "none",
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
        brief["sources"]["heights"] = "sampled photogrammetric height field (not surveyed)"
        brief["sources"]["features"] = "small roof planes in the height field; counts and sizes approximate"
    return brief
