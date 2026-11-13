"""Small spatial work cells and tight, complete-object source framing."""

import math

import numpy as np

from worldascode.contracts.region import Bounds, Region
from worldascode.storage.artifacts import digest


def union_bounds(entities):
    boxes = [e.world_bounds() for e in entities]
    return Bounds(
        min=tuple(min(b.min[i] for b in boxes) for i in range(3)),
        max=tuple(max(b.max[i] for b in boxes) for i in range(3)),
    )


def partition_region(region, cell_size=80, max_entities=5):
    region = region if isinstance(region, Region) else Region.model_validate(region)
    if not 20 <= cell_size <= 300 or not 1 <= max_entities <= 5:
        raise ValueError("FOCUS_CELL_LIMIT_INVALID")
    bins = {}
    for entity in sorted(region.entities, key=lambda e: e.id):
        b = entity.world_bounds()
        key = tuple(math.floor((b.min[i] + b.max[i]) / (2 * cell_size)) for i in [0, 2])
        bins.setdefault(key, []).append(entity)
    cells = []
    pending = [e for _, items in sorted(bins.items()) for e in items]
    while pending:
        group = [pending.pop(0)]
        b = group[0].world_bounds()
        key = tuple(math.floor((b.min[i] + b.max[i]) / (2 * cell_size)) for i in [0, 2])
        # Greedy nearest neighbor, bounded by actual union width/depth as well as count.
        while pending and len(group) < max_entities:
            box = union_bounds(group)
            cx = (box.min[0] + box.max[0]) / 2
            cz = (box.min[2] + box.max[2]) / 2
            candidates = sorted(
                pending,
                key=lambda e: (
                    math.hypot(
                        (e.world_bounds().min[0] + e.world_bounds().max[0]) / 2 - cx,
                        (e.world_bounds().min[2] + e.world_bounds().max[2]) / 2 - cz,
                    ),
                    e.id,
                ),
            )
            chosen = None
            for entity in candidates:
                total = union_bounds([*group, entity])
                if max(total.max[i] - total.min[i] for i in [0, 2]) <= cell_size:
                    chosen = entity
                    break
            if chosen is None:
                break
            group.append(chosen)
            pending.remove(chosen)
        cell_id = (
            f"{region.id}-cell-{key[0]}-{key[1]}-"
            + digest(sorted(e.id for e in group))[:10]
        )
        cells.append(region.model_copy(update={"id": cell_id, "entities": group}))
    return cells


def fit_range(bounds, heading, pitch, width=1440, height=1080, padding=1.12):
    """Fit all ROI corners to Cesium's default 60 degree larger-side FOV."""
    heading, pitch = math.radians(heading), math.radians(pitch)
    axis = np.array(
        [
            -math.sin(heading) * math.cos(pitch),
            -math.sin(pitch),
            math.cos(heading) * math.cos(pitch),
        ]
    )
    forward = -axis
    right = np.cross(forward, [0, 1, 0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    tan_h = math.tan(math.radians(60) / 2)
    tan_v = tan_h * height / width
    if height > width:
        tan_v = tan_h
        tan_h = tan_v * width / height
    centre = (np.array(bounds.min) + bounds.max) / 2
    corners = (
        np.array(
            [
                (x, y, z)
                for x in [bounds.min[0], bounds.max[0]]
                for y in [bounds.min[1], bounds.max[1]]
                for z in [bounds.min[2], bounds.max[2]]
            ]
        )
        - centre
    )
    distance = max(
        max(
            abs(p @ right) * padding / tan_h - p @ forward,
            abs(p @ up) * padding / tan_v - p @ forward,
        )
        for p in corners
    )
    return max(8, float(distance) + 1)
