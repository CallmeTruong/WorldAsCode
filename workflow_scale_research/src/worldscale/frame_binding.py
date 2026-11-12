"""Bind macro wing node poses to measured evidence before camera fitting."""

import re


def bind_wing_poses(source, spec, evidence, metres_per_unit):
    walls = sorted(
        [(i, c) for i, c in enumerate(spec["componentTree"]) if c.get("level") == "macro" and c.get("parent")],
        key=lambda item: max(item[1]["dimensions"]["width"], item[1]["dimensions"]["depth"]),
        reverse=True,
    )
    wings = sorted(evidence["wings"], key=lambda w: max(w["length_m"], w["width_m"]), reverse=True)
    if len(walls) != len(wings):
        raise ValueError("WING_POSE_BINDING_AMBIGUOUS")
    changes = []
    for (index, wall), wing in zip(walls, wings, strict=True):
        if wall.get("parent") != "root":
            raise ValueError("WING_POSE_REQUIRES_ROOT_LOCAL_FRAME")
        symbol = "node_" + re.sub(r"[^a-zA-Z0-9_]", "_", wall["id"]) + "_" + str(index)
        x, z = [value / metres_per_unit for value in wing["centre_xz"]]
        yaw = wing["rotation_y_rad"]
        for field, values in (("position", [x, 0, z]), ("rotation", [0, yaw, 0])):
            pattern = re.escape(symbol) + r"\." + field + r"\.set\([^;]+\);"
            replacement = symbol + "." + field + ".set(" + ", ".join(str(v) for v in values) + ");"
            source, count = re.subn(pattern, replacement, source)
            if not count:
                raise ValueError("WING_POSE_CODE_ANCHOR_MISSING: " + symbol)
        changes.append({"component": wall["id"], "node": symbol, "position": [x, 0, z], "rotation_y": yaw})
    return source, changes
