"""Validate actual factory-consumed fields, beyond native metadata validation."""

import copy
import math


def canonicalize_aliases(spec):
    result = copy.deepcopy(spec)
    changes = []
    for c in result.get("componentTree", []):
        d = c.get("geometryDescriptor", {})
        transform = c.get("transform", {})
        # The pinned native factory gives transform.scale precedence over dimensions.
        # Model-authored specs commonly include identity scale as a default alongside
        # meaningful dimensions; leaving it in silently turns every shape into 1 unit.
        dimensions = c.get("dimensions", {})
        dimensioned = isinstance(dimensions, dict) and any(
            isinstance(dimensions.get(key), (int, float)) and dimensions[key] > 0
            for key in ("width", "height", "depth", "length", "radius")
        )
        if (
            isinstance(transform, dict)
            and transform.get("scale") == [1, 1, 1]
            and dimensioned
        ):
            del transform["scale"]
            changes.append(
                c["id"]
                + ": identity transform.scale removed; native dimensions now drive geometry"
            )
        p = d.get("profile2D")
        if isinstance(p, dict):
            if "points" not in p and isinstance(p.get("outer"), list):
                p["points"] = p.pop("outer")
                changes.append(c["id"] + ": profile2D.outer -> points")
            if "depth" not in p and isinstance(d.get("extrudeDepth"), (int, float)):
                p["depth"] = d.pop("extrudeDepth")
                changes.append(c["id"] + ": extrudeDepth -> profile2D.depth")
    return result, changes


PASS_LEVELS = {
    "blockout": {"macro"},
    "structural-pass": {"macro", "meso"},
    "form-refinement": {"macro", "meso", "micro"},
    "material-pass": {"macro", "meso", "micro"},
    "surface-pass": {"macro", "meso", "micro"},
    "lighting-pass": {"macro", "meso", "micro"},
    "interaction-pass": {"macro", "meso", "micro"},
    "optimization-pass": {"macro", "meso", "micro"},
}
PASS_ORDER = tuple(PASS_LEVELS)


def pass_coverage_spec(spec, pass_id):
    """Return a gate-only view of details expected by this native pass."""
    import copy

    result = copy.deepcopy(spec)
    allowed = PASS_LEVELS[pass_id]
    pass_index = PASS_ORDER.index(pass_id)
    active_passes = set(PASS_ORDER[: pass_index + 1])
    explicit_refs = {
        str(ref)
        for item in spec.get("buildPasses", [])
        if isinstance(item, dict) and item.get("id") in active_passes
        for ref in item.get("componentRefs", [])
    }
    components = [
        c
        for c in spec.get("componentTree", [])
        if c.get("level", "macro") in allowed
        or str(c.get("id")) in explicit_refs
        or c.get("fidelityTier") == pass_id
    ]
    # Keep ancestors required to represent an included part in the real hierarchy.
    by_id = {str(c.get("id")): c for c in spec.get("componentTree", [])}
    included = {str(c.get("id")) for c in components}
    for component in list(components):
        parent = component.get("parent")
        while parent is not None and str(parent) in by_id:
            included.add(str(parent))
            parent = by_id[str(parent)].get("parent")
    result["componentTree"] = [
        c for c in spec.get("componentTree", []) if str(c.get("id")) in included
    ]
    component_ids = {str(c.get("id")) for c in result["componentTree"]}
    result["repetitionSystems"] = [
        r
        for r in spec.get("repetitionSystems", [])
        if r.get("level", "meso") in allowed
    ]
    assessment = result.get("preSpecAssessment", {})
    inventory = assessment.get("detailInventory", {})
    if isinstance(inventory, dict) and isinstance(inventory.get("details"), list):
        inventory["details"] = [
            d
            for d in inventory["details"]
            if str(d.get("mapsTo", {}).get("ref", "")).split("/", 1)[0] in component_ids
        ]
    return result


def issues(spec, pass_id):
    levels = (
        {"macro"}
        if pass_id == "blockout"
        else (
            {"macro", "meso"}
            if pass_id == "structural-pass"
            else {"macro", "meso", "micro"}
        )
    )
    result = []

    def polygon(points):
        return (
            isinstance(points, list)
            and len(points) >= 3
            and all(
                isinstance(p, list)
                and len(p) == 2
                and all(isinstance(x, (int, float)) and math.isfinite(x) for x in p)
                for p in points
            )
        )

    for c in spec.get("componentTree", []):
        if c.get("level") not in levels:
            continue
        if c.get("primitive") == "extrude":
            p = c.get("geometryDescriptor", {}).get("profile2D", {})
            if not polygon(p.get("points")):
                result.append(
                    {
                        "component": c["id"],
                        "error": "EXTRUDE_REQUIRES_NUMERIC_PROFILE_POINTS",
                        "field": "geometryDescriptor.profile2D.points",
                    }
                )
            if (
                not isinstance(p.get("depth"), (int, float))
                or not math.isfinite(p.get("depth", 0))
                or p.get("depth", 0) <= 0
            ):
                result.append(
                    {
                        "component": c["id"],
                        "error": "EXTRUDE_REQUIRES_POSITIVE_PROFILE_DEPTH",
                        "field": "geometryDescriptor.profile2D.depth",
                    }
                )
            if any(not polygon(hole) for hole in p.get("holes", [])):
                result.append({"component": c["id"], "error": "INVALID_HOLE_POLYGON"})
    for r in spec.get("repetitionSystems", []):
        if r.get("level", "meso") not in levels:
            continue
        if (
            not isinstance(r.get("count"), int)
            or isinstance(r.get("count"), bool)
            or r.get("count", 0) < 1
        ):
            result.append(
                {
                    "repetition": r.get("id"),
                    "error": "REPETITION_REQUIRES_NUMERIC_COUNT",
                    "field": "repetitionSystems.count",
                }
            )
        if not isinstance(r.get("placement"), dict):
            result.append(
                {
                    "repetition": r.get("id"),
                    "error": "REPETITION_REQUIRES_EXECUTABLE_PLACEMENT",
                    "field": "repetitionSystems.placement",
                }
            )
    return result
